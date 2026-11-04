"""World art museums: the open-access collections of MoMA, the Met and the Cleveland Museum of Art in one table.

All three museums publish their full collection data on GitHub under CC0 and refresh it about weekly:
- MoMA: github.com/MuseumofModernArt/collection (Artworks.csv)
- The Metropolitan Museum of Art: github.com/metmuseum/openaccess (MetObjects.csv)
- The Cleveland Museum of Art: github.com/ClevelandMuseumArt/openaccess (data.csv)

Each weekly run downloads the three files (about 550 MB together), maps them to one schema and
adds a snapshot of each collection's size, so the collections' growth can be followed over time.
If a museum's file cannot be downloaded, that museum's previous rows are kept.
"""

import logging
import re
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from ..http import make_session as base_session
from ..schema import Column, DatasetSpec, Table, files_markdown

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parents[2] / "assets"
LFS = "https://media.githubusercontent.com/media"
SOURCES = {
    "MoMA": f"{LFS}/MuseumofModernArt/collection/main/Artworks.csv",
    "The Met": f"{LFS}/metmuseum/openaccess/master/MetObjects.csv",
    "Cleveland Museum of Art": f"{LFS}/ClevelandMuseumArt/openaccess/master/data.csv",
}
MUSEUM_LINKS = {
    "MoMA": "https://github.com/MuseumofModernArt/collection",
    "The Met": "https://github.com/metmuseum/openaccess",
    "Cleveland Museum of Art": "https://github.com/ClevelandMuseumArt/openaccess",
}

ARTWORKS = Table(
    name="artworks",
    kind="history",  # each run rebuilds the table from the museums' current files
    fmt="parquet",
    description="One row per object in the three museums' open-access collections, in one shared schema.",
    key=("museum", "object_id"),
    min_rows=100_000,
    max_shrink=0.03,  # museums do deaccession or merge records, but never a large share at once
    columns=[
        Column("museum", "string", "MoMA, The Met or Cleveland Museum of Art"),
        Column("object_id", "string", "The museum's own object id"),
        Column("accession_number", "string", "The museum's accession number"),
        Column("title", "string", "Title of the work"),
        Column("artist", "string", "First listed artist or maker (empty: unknown or not recorded)"),
        Column("artists_count", "integer", "Number of listed artists or makers"),
        Column("artist_nationality", "string", "Nationality of the first artist, as the museum records it"),
        Column("artist_gender", "string", "male or female, when the museum records it (see the description)"),
        Column("artist_birth_year", "integer", "Birth year of the first artist (negative: BCE)"),
        Column("artist_death_year", "integer", "Death year of the first artist"),
        Column("date_text", "string", "The museum's date of the work, as written (e.g. 'c. 1890')"),
        Column("year_start", "integer", "Earliest year of the work (negative: BCE)"),
        Column("year_end", "integer", "Latest year of the work (negative: BCE)"),
        Column("culture", "string", "Culture or place of origin (The Met and Cleveland only)"),
        Column("department", "string", "Curatorial department"),
        Column("classification", "string", "Kind of object: painting, print, photograph, ceramics, ..."),
        Column("medium", "string", "Materials and technique"),
        Column("dimensions", "string", "Dimensions, as written"),
        Column("credit_line", "string", "How the work entered the collection (gift, purchase, bequest, ...)"),
        Column("acquisition_year", "integer", "Year the museum acquired the work"),
        Column("is_public_domain", "boolean", "Image and data free to reuse (The Met and Cleveland; empty for MoMA)"),
        Column("on_view", "boolean", "On view in a gallery when the file was published"),
        Column("is_highlight", "boolean", "Marked as a highlight of the collection (The Met only)"),
        Column("url", "string", "Page of the work on the museum's website"),
        Column("image_url", "string", "Image of the work (MoMA and Cleveland; The Met's CSV has none)"),
    ],
)

SNAPSHOTS = Table(
    name="collection_snapshots",
    kind="snapshot",
    description="Each week, the size of each collection: objects, objects on view, public domain, with images.",
    key=("snapshot_date", "museum"),
    min_rows=1,
    columns=[
        Column("snapshot_date", "datetime", "Date of the weekly update (UTC)"),
        Column("museum", "string", "Museum"),
        Column("objects", "integer", "Objects in the open-access file"),
        Column("on_view", "integer", "Objects on view"),
        Column("public_domain", "integer", "Objects marked public domain / CC0"),
        Column("with_image", "integer", "Objects with an image link"),
        Column("female_artist", "integer", "Objects whose first artist is recorded as female"),
        Column("latest_acquisition_year", "integer", "Most recent acquisition year in the file"),
    ],
)

ACQUISITIONS = Table(
    name="acquisitions_by_year",
    kind="derived",
    description="Per museum and year: works acquired, and how many by women among works whose artist's gender is recorded.",
    key=("museum", "year"),
    min_rows=0,
    columns=[
        Column("museum", "string", "Museum"),
        Column("year", "integer", "Acquisition year"),
        Column("works", "integer", "Works acquired that year"),
        Column("works_gender_known", "integer", "Of those, works whose first artist has a recorded gender"),
        Column("works_by_women", "integer", "Works whose first artist is recorded as female"),
        Column("share_by_women", "number", "works_by_women / works_gender_known (MoMA and Cleveland only)"),
        Column("artists", "integer", "Different artists among the works"),
        Column("median_work_year", "number", "Median year the acquired works were made"),
    ],
)

ARTISTS = Table(
    name="artists",
    kind="derived",
    description="One row per artist name: works in each museum, nationality, gender and life years.",
    key=("artist",),
    min_rows=0,
    columns=[
        Column("artist", "string", "Artist name as the museums write it (first listed artist of each work)"),
        Column("works", "integer", "Works in the three collections"),
        Column("museums", "integer", "Number of the three museums holding their work"),
        Column("works_moma", "integer", "Works at MoMA"),
        Column("works_met", "integer", "Works at The Met"),
        Column("works_cleveland", "integer", "Works at the Cleveland Museum of Art"),
        Column("nationality", "string", "Most often recorded nationality"),
        Column("gender", "string", "Recorded gender, when any museum records it"),
        Column("birth_year", "integer", "Most often recorded birth year"),
        Column("death_year", "integer", "Most often recorded death year"),
        Column("first_acquired", "integer", "Earliest acquisition year of their works"),
        Column("on_view", "integer", "Works on view"),
    ],
)

TABLES = [ARTWORKS, SNAPSHOTS, ACQUISITIONS, ARTISTS]

# ---------- parsing helpers ----------

YEAR = re.compile(r"(?<!\d)(\d{3,4})(?!\d)")
THIS_YEAR = pd.Timestamp.now(tz="UTC").year
# "Unknown", "Unidentified photographer", "Anonymous, Italian, 17th century": no named artist.
NO_ARTIST = re.compile(r"^(?:unknown|unidentified|anonymous|anonim|artist unknown)\b", re.IGNORECASE)


def clean(series):
    s = series.astype("string").str.strip()
    return s.mask(s.isin(["", "nan", "None", "[]"]))


def first_part(series, sep):
    return clean(series).str.split(sep, n=1, regex=False).str[0].pipe(clean)


def years_in(text):
    """(first, last) year in each text: 'c. 1890' -> (1890, 1890), '1890-1903' -> (1890, 1903), and
    abbreviated ranges '1920-25' -> (1920, 1925)."""
    text = clean(text)
    found = text.str.findall(YEAR)
    first = pd.to_numeric(found.str[0], errors="coerce")
    last = pd.to_numeric(found.str[-1], errors="coerce")
    short = text.str.extract(r"(\d{4})\s*[-–]\s*(\d{2})(?!\d)")
    short_end = pd.to_numeric(short[0], errors="coerce") // 100 * 100 + pd.to_numeric(short[1], errors="coerce")
    last = short_end.where(short_end.notna() & (short_end > last.fillna(-1e9)), last)
    return first, last


def year_number(series, low=-10000, high=2100):
    n = pd.to_numeric(clean(series).str.extract(r"(-?\d{1,5})")[0], errors="coerce")
    return n.where((n >= low) & (n <= high) & (n != 0))


def named(artist):
    """The artist name, or missing for placeholders such as 'Unknown' or 'Anonymous'."""
    artist = clean(artist)
    return artist.mask(artist.str.match(NO_ARTIST, na=False))


def count_artists(series, sep):
    s = clean(series)
    return s.str.count(re.escape(sep)).add(1).where(s.notna(), 0)


# ---------- the three museums ----------


def read_moma(path):
    m = pd.read_csv(path, dtype=str, encoding="utf-8-sig", keep_default_na=False)
    paren = lambda col: clean(m[col].str.extract(r"\(([^)]*)\)")[0])  # noqa: E731 - first "(...)" group
    start, end = years_in(m["Date"])
    out = pd.DataFrame({
        "museum": "MoMA",
        "object_id": m["ObjectID"],
        "accession_number": m["AccessionNumber"],
        "title": m["Title"],
        "artist": named(first_part(m["Artist"], ", ")),
        "artists_count": clean(m["ConstituentID"]).str.count(",").add(1).where(clean(m["ConstituentID"]).notna(), 0),
        "artist_nationality": paren("Nationality"),
        "artist_gender": paren("Gender").str.lower().where(lambda s: s.isin(["male", "female"])),
        "artist_birth_year": year_number(paren("BeginDate")),
        "artist_death_year": year_number(paren("EndDate")),
        "date_text": m["Date"],
        "year_start": start,
        "year_end": end.fillna(start),
        "culture": pd.NA,
        "department": m["Department"],
        "classification": m["Classification"],
        "medium": m["Medium"],
        "dimensions": m["Dimensions"],
        "credit_line": m["CreditLine"],
        "acquisition_year": year_number(m["DateAcquired"].str[:4], 1800, THIS_YEAR),
        "is_public_domain": pd.NA,
        "on_view": clean(m["OnView"]).notna(),
        "is_highlight": pd.NA,
        "url": m["URL"],
        "image_url": m["ImageURL"],
    })
    return out


MET_COLUMNS = ["Object ID", "Object Number", "Title", "Object Name", "Artist Display Name", "Artist Nationality",
               "Artist Gender", "Artist Begin Date", "Artist End Date", "Object Date", "Object Begin Date",
               "Object End Date", "Culture", "Department", "Classification", "Medium", "Dimensions", "Credit Line",
               "AccessionYear", "Is Public Domain", "Gallery Number", "Is Highlight", "Link Resource"]


def read_met(path):
    m = pd.read_csv(path, dtype=str, encoding="utf-8-sig", usecols=MET_COLUMNS, keep_default_na=False)
    gender = first_part(m["Artist Gender"], "|")
    out = pd.DataFrame({
        "museum": "The Met",
        "object_id": m["Object ID"],
        "accession_number": m["Object Number"],
        "title": clean(m["Title"]).fillna(clean(m["Object Name"])),
        "artist": named(first_part(m["Artist Display Name"], "|")),
        "artists_count": count_artists(m["Artist Display Name"], "|"),
        "artist_nationality": first_part(m["Artist Nationality"], "|"),
        # The Met records "Female" and leaves other artists blank, so male is never stated.
        "artist_gender": gender.str.lower().where(gender.str.lower() == "female"),
        "artist_birth_year": year_number(first_part(m["Artist Begin Date"], "|")),
        "artist_death_year": year_number(first_part(m["Artist End Date"], "|")),
        "date_text": m["Object Date"],
        "year_start": year_number(m["Object Begin Date"]),
        "year_end": year_number(m["Object End Date"]),
        "culture": m["Culture"],
        "department": m["Department"],
        "classification": clean(m["Classification"]).fillna(clean(m["Object Name"])),
        "medium": m["Medium"],
        "dimensions": m["Dimensions"],
        "credit_line": m["Credit Line"],
        "acquisition_year": year_number(m["AccessionYear"], 1800, THIS_YEAR),
        "is_public_domain": m["Is Public Domain"].str.lower().map({"true": True, "false": False}),
        "on_view": clean(m["Gallery Number"]).notna(),
        "is_highlight": m["Is Highlight"].str.lower().map({"true": True, "false": False}),
        "url": m["Link Resource"],
        "image_url": pd.NA,
    })
    return out


CMA_COLUMNS = ["id", "accession_number", "share_license_status", "title", "creation_date", "creation_date_earliest",
               "creation_date_latest", "artists_tags", "culture", "technique", "department", "type", "measurements",
               "creditline", "current_location", "url", "creators", "image_web"]
# "Camille Pissarro (French, 1830–1903), artist" -> name, nationality, life dates
CREATOR = re.compile(r"^\s*(?P<name>[^(;]+?)\s*\((?P<nat>[^,)]*)(?:,\s*(?P<life>[^)]*))?\)")


def read_cma(path):
    c = pd.read_csv(path, dtype=str, encoding="utf-8-sig", usecols=CMA_COLUMNS, keep_default_na=False)
    creators = clean(c["creators"])
    first = creators.str.split(";", n=1, regex=False).str[0]
    parsed = first.str.extract(CREATOR)
    name = clean(parsed["name"]).fillna(clean(first.str.rsplit(",", n=1).str[0]))
    life = parsed["life"].fillna("")
    born, died = years_in(life)
    died = died.where(~life.str.contains("born", na=False))  # "born 1944": still alive
    tags = c["artists_tags"].fillna("")
    male, female = tags.str.contains("'male'", regex=False), tags.str.contains("'female'", regex=False)
    gender = pd.Series(np.select([male & ~female, female & ~male], ["male", "female"], ""), index=c.index)
    out = pd.DataFrame({
        "museum": "Cleveland Museum of Art",
        "object_id": c["id"],
        "accession_number": c["accession_number"],
        "title": c["title"],
        "artist": named(name),
        "artists_count": creators.str.count(";").add(1).where(creators.notna(), 0),
        "artist_nationality": clean(parsed["nat"]),
        "artist_gender": clean(gender),
        "artist_birth_year": born,
        "artist_death_year": died,
        "date_text": c["creation_date"],
        "year_start": year_number(c["creation_date_earliest"]),
        "year_end": year_number(c["creation_date_latest"]),
        "culture": c["culture"],
        "department": c["department"],
        "classification": c["type"],
        "medium": c["technique"],
        "dimensions": c["measurements"],
        "credit_line": c["creditline"],
        # Cleveland's accession numbers start with the acquisition year ("2020.113").
        "acquisition_year": year_number(c["accession_number"].str.extract(r"^(\d{4})\.")[0], 1900, THIS_YEAR),
        "is_public_domain": c["share_license_status"].str.upper() == "CC0",
        "on_view": clean(c["current_location"]).notna(),
        "is_highlight": pd.NA,
        "url": c["url"],
        "image_url": c["image_web"],
    })
    return out


PERSON = ["artist_nationality", "artist_gender", "artist_birth_year", "artist_death_year"]


def tidy(df):
    """Empty text becomes missing, and person fields go with the first artist: an 'Unknown' maker has none."""
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            if df[col].map(lambda v: isinstance(v, str)).any():
                df[col] = clean(df[col])
    df[PERSON] = df[PERSON].where(df["artist"].notna())
    return df


READERS = {"MoMA": read_moma, "The Met": read_met, "Cleveland Museum of Art": read_cma}

# ---------- fetchers ----------


def make_session():
    return base_session()


def download(session, url, dest):
    with session.get(url, stream=True, timeout=600) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(1 << 20):
                f.write(chunk)
    head = Path(dest).read_bytes()[:200]
    if head.startswith(b"version https://git-lfs"):
        raise RuntimeError(f"{url} returned a Git LFS pointer, not the file")
    return dest


MIN_MUSEUM_ROWS = 1000  # fewer rows from a museum means a broken or truncated file


def fetch_artworks(session, previous, shared, readers=None, sources=None):
    readers, sources = readers or READERS, sources or SOURCES
    frames, failed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for museum, url in sources.items():
            try:
                path = download(session, url, Path(tmp) / f"{len(frames) + len(failed)}.csv")
                df = tidy(readers[museum](path))
                if len(df) < MIN_MUSEUM_ROWS:
                    raise ValueError(f"only {len(df)} rows")
                frames.append(df)
                log.info("%s: %d objects", museum, len(df))
            except Exception as exc:  # noqa: BLE001 - keep the other museums
                failed.append(museum)
                log.warning("%s FAILED: %s", museum, exc)
    if not frames:
        raise RuntimeError(f"no museum file could be read ({', '.join(failed)})")
    new = pd.concat(frames, ignore_index=True)
    if failed and previous is not None and not previous.empty:
        kept = previous[previous["museum"].isin(failed)]
        log.info("kept %d previous rows of %s", len(kept), ", ".join(failed))
        new = pd.concat([new, kept], ignore_index=True)
    shared["artworks"], shared["failed"] = new, failed
    return new


def snapshot(artworks, snapshot_date, museums=None):
    a = artworks if museums is None else artworks[artworks["museum"].isin(museums)]
    g = a.groupby("museum")
    out = pd.DataFrame({
        "objects": g.size(),
        "on_view": g["on_view"].apply(lambda s: int(s.fillna(False).astype(bool).sum())),
        "public_domain": g["is_public_domain"].apply(lambda s: int(s.fillna(False).astype(bool).sum())),
        "with_image": g["image_url"].apply(lambda s: int(clean(s).notna().sum())),
        "female_artist": g["artist_gender"].apply(lambda s: int((s == "female").sum())),
        "latest_acquisition_year": g["acquisition_year"].max(),
    }).reset_index()
    out.insert(0, "snapshot_date", pd.Timestamp(snapshot_date))
    return out


def make_fetchers(_, snapshot_date):
    session, shared = make_session(), {}

    def snapshots(previous):
        artworks = shared.get("artworks")
        if artworks is None:
            raise RuntimeError("artworks unavailable")
        fresh = [m for m in SOURCES if m not in shared.get("failed", [])]
        return snapshot(artworks, snapshot_date, fresh)

    return {"artworks": lambda previous: fetch_artworks(session, previous, shared),
            "collection_snapshots": snapshots}


# ---------- derived ----------


def acquisitions(artworks):
    a = artworks[artworks["acquisition_year"].notna()]
    if a.empty:
        return pd.DataFrame(columns=ACQUISITIONS.column_names)
    g = a.groupby(["museum", "acquisition_year"])
    out = pd.DataFrame({
        "works": g.size(),
        "works_gender_known": g["artist_gender"].apply(lambda s: int(s.notna().sum())),
        "works_by_women": g["artist_gender"].apply(lambda s: int((s == "female").sum())),
        "artists": g["artist"].nunique(),
        "median_work_year": g["year_start"].median(),
    }).reset_index().rename(columns={"acquisition_year": "year"})
    # The Met records only female artists, so a share would be meaningless there.
    known = out["works_gender_known"].where(out["museum"] != "The Met")
    out["share_by_women"] = (out["works_by_women"] / known.where(known > 0)).round(4)
    return out[ACQUISITIONS.column_names]


def mode(series):
    s = series.dropna()
    return s.mode().iloc[0] if len(s) else pd.NA


def artists(artworks):
    a = artworks[artworks["artist"].notna()]
    if a.empty:
        return pd.DataFrame(columns=ARTISTS.column_names)
    g = a.groupby("artist")
    per = a.groupby(["artist", "museum"]).size().unstack(fill_value=0)
    out = pd.DataFrame({
        "works": g.size(),
        "museums": (per > 0).sum(axis=1),
        "works_moma": per.get("MoMA", 0),
        "works_met": per.get("The Met", 0),
        "works_cleveland": per.get("Cleveland Museum of Art", 0),
        "nationality": g["artist_nationality"].agg(mode),
        "gender": g["artist_gender"].agg(mode),
        "birth_year": g["artist_birth_year"].agg(mode),
        "death_year": g["artist_death_year"].agg(mode),
        "first_acquired": g["acquisition_year"].min(),
        "on_view": g["on_view"].apply(lambda s: int(s.fillna(False).astype(bool).sum())),
    }).reset_index()
    return out[ARTISTS.column_names]


def derive(frames):
    art = frames.get("artworks")
    if art is None or art.empty:
        return {"acquisitions_by_year": pd.DataFrame(columns=ACQUISITIONS.column_names),
                "artists": pd.DataFrame(columns=ARTISTS.column_names)}
    return {"acquisitions_by_year": acquisitions(art), "artists": artists(art)}


# ---------- description ----------


def coverage_markdown(frames):
    art = frames.get("artworks") if frames else None
    if art is None or art.empty:
        return "(computed when the dataset is built)"
    lines = ["| Museum | Objects | On view | Public domain | With image link | Acquired up to |", "|---|---|---|---|---|---|"]
    for museum, g in art.groupby("museum"):
        pd_count = g["is_public_domain"].fillna(False).astype(bool).sum()
        lines.append(f"| [{museum}]({MUSEUM_LINKS.get(museum, '')}) | {len(g):,} | "
                     f"{int(g['on_view'].fillna(False).astype(bool).sum()):,} | "
                     f"{f'{pd_count:,}' if museum != 'MoMA' else 'not recorded'} | {int(clean(g['image_url']).notna().sum()):,} | "
                     f"{int(g['acquisition_year'].max()) if g['acquisition_year'].notna().any() else '-'} |")
    lines.append(f"| **Total** | **{len(art):,}** | | | | |")
    return "\n".join(lines)


def describe(snapshot_date, tables_written, frames=None):
    return "\n".join([
        "**Over 700,000 works of art from three of the world's great museums in one table**: the Museum of "
        "Modern Art (MoMA) in New York, The Metropolitan Museum of Art, and the Cleveland Museum of Art. "
        "From ancient Egyptian amulets and Japanese prints to Van Gogh and contemporary photography, with "
        "artists, dates, cultures, materials, departments, acquisition years and links. Updated weekly from "
        "the museums' own open-access data.",
        "",
        "## Why this dataset",
        "",
        "- **Up to date**: the best-known museum datasets on Kaggle were last updated years ago; this one "
        "follows the museums' weekly releases.",
        "- **One schema for three museums**: the same columns whatever the source, so you can compare a "
        "modern-art museum with two encyclopedic ones.",
        "- **Ready-made tables** for the classic questions: who gets collected (artists by museum, nationality "
        "and gender), how collecting changed year by year, and how the collections grow week by week.",
        "",
        "## Files",
        "",
        files_markdown(tables_written),
        "",
        "## Coverage",
        "",
        coverage_markdown(frames),
        "",
        "## How to read it",
        "",
        "- **Artist fields describe the first listed artist** of each work; `artists_count` says how many were "
        "listed. Unknown makers (most ancient and many non-Western objects) have no artist.",
        "- **Gender is recorded differently**: MoMA and Cleveland record male and female; The Met records only "
        "*female*, leaving other artists blank. Compare gender shares within MoMA and Cleveland "
        "(`acquisitions_by_year.share_by_women` is empty for The Met).",
        "- **Acquisition year**: MoMA's acquisition date, The Met's accession year, and the year that starts "
        "Cleveland's accession numbers (e.g. 2020.113).",
        "- **Public domain**: The Met's flag and Cleveland's CC0 status. MoMA's file does not say.",
        "- Artist names are matched by spelling across museums, so the same person can occasionally appear "
        "under two spellings in `artists`.",
        "",
        "## Updates",
        "",
        f"Updated weekly. Last update: {snapshot_date:%Y-%m-%d} (UTC).",
        "",
        "## Sources and license",
        "",
        *[f"- {m}: {link} (CC0)" for m, link in MUSEUM_LINKS.items()],
        "",
        "All three museums release this data under Creative Commons Zero (CC0), and so is this dataset. Images "
        "behind the image links follow each museum's own terms. This dataset is not affiliated with the museums.",
    ])


SPEC = DatasetSpec(
    name="art-museums",
    slug="art-museum-collections-moma-met-cleveland",
    title="Art Museum Collections: MoMA, Met, Cleveland",
    subtitle="700,000+ artworks from three great museums in one table, updated weekly",
    license="CC0-1.0",
    keywords=["arts and entertainment", "culture and humanities", "popular culture", "tabular",
              "data visualization"],
    tables=TABLES,
    sources=("Museum of Modern Art (github.com/MuseumofModernArt/collection), The Metropolitan Museum of Art "
             "(github.com/metmuseum/openaccess), Cleveland Museum of Art (github.com/ClevelandMuseumArt/openaccess), "
             "all CC0. Built weekly by https://github.com/daniel766hi/kaggle-compe"),
    make_fetchers=make_fetchers,
    derive=derive,
    describe=describe,
    cover=ASSETS / "art-museums-cover.png",
    update_frequency="weekly",
    run_weekday=2,  # Wednesday: after the museums' usual weekend/Monday releases
)
