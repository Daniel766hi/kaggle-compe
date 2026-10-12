#!/usr/bin/env python3
"""Ranked keyword search over the Managed-Care Operations Handbook (BM25).

Installed in the trial container as ``hb-search``. Standard library only.

    hb-search "bariatric surgery BMI criteria"        # top 8 documents with matching lines
    hb-search -k 15 "peer to peer scheduling window"
    hb-search --files "denial letter appeal rights"   # paths only
"""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import pickle
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

DEFAULT_ROOTS = (
    "/workspace/skills/managed-care-operations-handbook",
    "/logs/agent/sessions/skills/managed-care-operations-handbook",
)
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.-][a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it of on or that the this to was were "
    "will with which who what when where how should must may can not no".split()
)
K1, B = 1.5, 0.75
TITLE_WEIGHT = 3  # title and path tokens count this many times


def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in TOKEN_RE.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        tokens.append(tok)
        # Also index the parts of codes like "j1745" or "phq-9" and words like "peer-to-peer".
        if "-" in tok or "." in tok:
            tokens.extend(p for p in re.split(r"[.-]", tok) if p and p not in STOPWORDS)
    return tokens


def _title(text: str, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line.strip().startswith("title:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return path.stem


class Index:
    def __init__(self, root: Path, build: bool = True):
        self.root = root
        self.paths: list[str] = []
        self.titles: list[str] = []
        self.lengths: list[int] = []
        self.postings: dict[str, dict[int, int]] = {}
        self.avg_len = 0.0
        if build:
            self._build()

    def _build(self) -> None:
        root = self.root
        for i, path in enumerate(sorted(root.rglob("*.md"))):
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(root).as_posix()
            title = _title(text, path)
            counts = Counter(tokenize(text))
            for tok in tokenize(f"{title} {rel.replace('/', ' ').replace('_', ' ')}"):
                counts[tok] += TITLE_WEIGHT
            self.paths.append(rel)
            self.titles.append(title)
            self.lengths.append(sum(counts.values()))
            for tok, n in counts.items():
                self.postings.setdefault(tok, {})[i] = n
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0

    def search(self, query: str, k: int) -> list[tuple[float, int]]:
        n_docs = len(self.paths)
        scores: dict[int, float] = {}
        for tok in set(tokenize(query)):
            docs = self.postings.get(tok)
            if not docs:
                continue
            idf = math.log(1 + (n_docs - len(docs) + 0.5) / (len(docs) + 0.5))
            for doc, tf in docs.items():
                norm = K1 * (1 - B + B * self.lengths[doc] / self.avg_len)
                scores[doc] = scores.get(doc, 0.0) + idf * tf * (K1 + 1) / (tf + norm)
        return sorted(((s, d) for d, s in scores.items()), reverse=True)[:k]


def _fingerprint(root: Path) -> str:
    h = hashlib.sha1(str(root).encode())
    for path in sorted(root.rglob("*.md")):
        st = path.stat()
        h.update(f"{path}:{st.st_size}:{st.st_mtime_ns}".encode())
    return h.hexdigest()[:16]


def load_index(root: Path) -> Index:
    cache = Path(tempfile.gettempdir()) / f"hb-search-{_fingerprint(root)}.pkl"
    # The cache holds plain data, so it loads whether this file runs as a script or a module.
    try:
        with cache.open("rb") as fh:
            index = Index(root, build=False)
            index.__dict__.update(pickle.load(fh))
            return index
    except Exception:
        pass
    index = Index(root)
    try:
        tmp = cache.with_suffix(f".{os.getpid()}.tmp")
        with tmp.open("wb") as fh:
            pickle.dump(index.__dict__, fh)
        tmp.replace(cache)
    except OSError:
        pass
    return index


def matching_lines(path: Path, query: str, limit: int) -> list[tuple[int, str]]:
    terms = set(tokenize(query))
    scored = []
    for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        hits = len(terms & set(tokenize(line)))
        if hits:
            scored.append((hits, n, line.strip()))
    best = sorted(scored, key=lambda t: (-t[0], t[1]))[:limit]
    return [(n, line[:220]) for _, n, line in sorted(best, key=lambda t: t[1])]


def find_root(explicit: str | None) -> Path | None:
    candidates = [explicit] if explicit else [os.environ.get("HB_SEARCH_ROOT"), *DEFAULT_ROOTS]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hb-search", description=__doc__.splitlines()[0])
    parser.add_argument("query", nargs="+", help="search terms")
    parser.add_argument("-k", type=int, default=8, help="number of documents (default 8)")
    parser.add_argument("--lines", type=int, default=4, help="matching lines per document")
    parser.add_argument("--files", action="store_true", help="print paths only")
    parser.add_argument("--root", help="handbook directory")
    args = parser.parse_args(argv)

    root = find_root(args.root)
    if root is None:
        print("hb-search: handbook directory not found", file=sys.stderr)
        return 2
    query = " ".join(args.query)
    index = load_index(root)
    results = index.search(query, args.k)
    if not results:
        print(f"No handbook matches for: {query}")
        return 1
    for score, doc in results:
        path = root / index.paths[doc]
        if args.files:
            print(path)
            continue
        print(f"{path}  [{index.titles[doc]}]  score={score:.1f}")
        for n, line in matching_lines(path, query, args.lines):
            print(f"    {n}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
