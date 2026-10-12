"""Query-gap study: localize gold code nodes from issue text on the 129 dev tasks.

Usage:
    python gemma4_paper/run_study.py --data <competition data dir> --out <results dir>

See PROTOCOL.md for the frozen design. Only problem_statement is used for ranking;
patch is used only to build labels.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import math
import re
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

STOP = set(
    """a an the and or of to in on for is are was were be been it this that with as at by
    from not no but if when then else so do does did can could should would will have has had
    i we you they he she my our your their its there here what which who how why where all any
    some more most also just only than too very into out up down over under use used using get
    got like want need one two new same other such see seems seem way make made return returns
    true false none self cls def class import""".split()
)
TEST_PART = re.compile(r"(^|/)(tests?|docs|docs_src)/|(^|/)test_[^/]*\.py$|_test\.py$")


# ---------------------------------------------------------------- tokenization
def split_ident(tok: str) -> list[str]:
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok).replace("_", " ").split()
    return [p.lower() for p in parts]


def tokenize(text: str) -> list[str]:
    out = []
    for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        pieces = split_ident(raw)
        if len(pieces) > 1:
            out.append(raw.lower())
        out.extend(pieces)
    return [t for t in out if len(t) >= 2 and t not in STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = np.array([len(d) for d in docs], dtype=float)
        self.avg = self.len.mean() if len(docs) else 1.0
        df = Counter(t for d in self.tf for t in d)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(len(self.tf))
        norm = self.k1 * (1 - self.b + self.b * self.len / self.avg)
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            f = np.array([d.get(t, 0) for d in self.tf], dtype=float)
            s += idf * f * (self.k1 + 1) / (f + norm)
        return s


def zscore(x: np.ndarray) -> np.ndarray:
    sd = x.std()
    return (x - x.mean()) / sd if sd > 0 else x * 0.0


# ---------------------------------------------------------------- data loading
def load_graph(path: Path):
    g = json.loads(path.read_text())
    nodes = g["nodes"]
    ids = [str(n["id"]) for n in nodes]
    texts = [str(n.get("text") or "") for n in nodes]
    edges = [(str(e["source"]), str(e["target"]), e.get("type")) for e in g.get("edges", [])]
    return ids, texts, edges


def load_embeddings(path: Path) -> dict[str, np.ndarray]:
    out = {}
    with np.load(path) as z:
        for k in z.files:
            key = k[:-4] if k.endswith(".npy") else k
            if ";" in key:
                key = key.split(";", 1)[1]
            out[key] = z[k].astype(np.float32)
    return out


def snapshot_sources(tgz) -> dict[str, str]:
    """Return {repo-relative path: source} for all .py files in a snapshot archive.

    `tgz` is a path or a binary stream; the archive is read in streaming mode.
    """
    files = {}
    kw = {"name": str(tgz)} if isinstance(tgz, (str, Path)) else {"fileobj": tgz}
    with tarfile.open(mode="r|gz", **kw) as tf:
        for m in tf:
            name = m.name[2:] if m.name.startswith("./") else m.name
            if not m.isfile() or not name.endswith(".py") or name.startswith(".git/"):
                continue
            f = tf.extractfile(m)
            if f is not None:
                files[name] = f.read().decode("utf-8", errors="replace")
    return files


def load_sources(data: Path, iid: str) -> dict[str, str]:
    cached = data / "sources" / f"{iid}.json.gz"
    if cached.exists():
        import gzip

        return json.loads(gzip.decompress(cached.read_bytes()))
    return snapshot_sources(data / "snapshots" / f"{iid}.tgz")


def graph_key(task) -> str:
    return f"{task['repo'].split('/')[1]}_{task['base_commit']}"


# ---------------------------------------------------------------- labels
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def changed_lines(patch: str) -> dict[str, set[int]]:
    """Pre-image line numbers touched per file (deletions/modifications, plus insertion points)."""
    out: dict[str, set[int]] = defaultdict(set)
    cur = None
    old_ln = 0
    for line in patch.splitlines():
        if line.startswith("--- "):
            p = line[4:].strip()
            cur = None if p == "/dev/null" else re.sub(r"^a/", "", p)
            continue
        if line.startswith("+++ "):
            continue
        m = HUNK.match(line)
        if m:
            old_ln = int(m.group(1))
            continue
        if cur is None:
            continue
        if line.startswith("-"):
            out[cur].add(old_ln)
            old_ln += 1
        elif line.startswith("+"):
            out[cur].add(max(old_ln - 1, 1))
            out[cur].add(old_ln)
        elif line.startswith(" ") or line == "":
            old_ln += 1
    return {f: s for f, s in out.items() if f.endswith(".py") and not TEST_PART.search(f)}


def module_name(path: str) -> str:
    p = path[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    for pre in ("src/",):
        if p.startswith(pre):
            p = p[len(pre):]
    return p.replace("/", ".")


def defs_with_spans(src: str, mod: str):
    """Yield (qualified name, start, end) for module, classes, functions."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    n_lines = src.count("\n") + 1
    yield mod, 1, n_lines

    def walk(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{ch.name}"
                start = min([ch.lineno] + [d.lineno for d in ch.decorator_list])
                yield q, start, ch.end_lineno
                yield from walk(ch, q)

    yield from walk(tree, mod)


def gold_nodes(task, sources: dict[str, str], id_set: set[str]):
    lines = changed_lines(task["patch"])
    gold_files = {f for f in lines if f in sources}
    gold = set()
    node_file = {}
    for f, src in sources.items():
        mod = module_name(f)
        spans = list(defs_with_spans(src, mod))
        for q, s, e in spans:
            if q in id_set:
                node_file.setdefault(q, f)
        if f not in lines:
            continue
        # innermost matching definitions (exclude the module node unless nothing else matches)
        hit = []
        for q, s, e in spans:
            if q == mod:
                continue
            if any(s <= ln <= e for ln in lines[f]):
                hit.append((e - s, q))
        hit_ids = [q for _, q in sorted(hit) if q in id_set]
        if hit_ids:
            # keep the innermost (smallest-span) node for each changed line
            for ln in lines[f]:
                inner = [
                    (e - s, q) for q, s, e in spans if q != mod and s <= ln <= e and q in id_set
                ]
                if inner:
                    gold.add(min(inner)[1])
        elif mod in id_set:
            gold.add(mod)
    return gold_files, gold, node_file


# ---------------------------------------------------------------- methods
def is_test_node(n: str) -> bool:
    low = n.lower()
    return low.startswith(("test.", "tests.")) or ".test_" in low


def keywords(issue: str, n: int = 5) -> list[str]:
    spans = re.findall(r"`([^`\n]{2,80})`", issue)
    kws = []
    for s in spans:
        for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]*", s):
            t = t.strip(".")
            if len(t) >= 3 and t.lower() not in STOP and t not in kws:
                kws.append(t)
    if not kws:
        toks = sorted(
            {t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]+", issue) if t.lower() not in STOP},
            key=lambda t: (-len(t), t),
        )
        kws = toks
    return kws[:n]


def ppr(adj: list[list[int]], pers: np.ndarray, alpha: float = 0.15, iters: int = 30):
    n = len(adj)
    deg = np.array([max(len(a), 1) for a in adj], dtype=float)
    p = pers / pers.sum() if pers.sum() > 0 else np.full(n, 1.0 / n)
    r = p.copy()
    for _ in range(iters):
        nxt = np.zeros(n)
        share = r / deg
        for i, nb in enumerate(adj):
            if nb:
                nxt[nb] += share[i]
            else:
                nxt += share[i] / n
        r = alpha * p + (1 - alpha) * nxt
    return r


def degree_preserving_swap(edges: list[tuple[int, int]], rng, n_swaps: int):
    e = list(edges)
    es = set(e)
    m = len(e)
    if m < 2:
        return e
    for _ in range(n_swaps):
        i, j = rng.integers(m), rng.integers(m)
        (a, b), (c, d) = e[i], e[j]
        if len({a, b, c, d}) < 4 or (a, d) in es or (c, b) in es:
            continue
        es -= {(a, b), (c, d)}
        es |= {(a, d), (c, b)}
        e[i], e[j] = (a, d), (c, b)
    return e


def rank_of(order: list[str], gold: set[str]) -> int | None:
    for i, n in enumerate(order):
        if n in gold:
            return i + 1
    return None


def file_rank(order: list[str], node_file: dict[str, str], gold_files: set[str]):
    seen = []
    for n in order:
        f = node_file.get(n)
        if f and f not in seen:
            seen.append(f)
            if f in gold_files:
                return len(seen)
    return None


# ---------------------------------------------------------------- main
def import_harness_graph():
    """Import swegemma.graph (the code behind search_similar_code) from the harness wheel.

    The package __init__ pulls in the full eval stack; the graph module only needs numpy and
    networkx, so fall back to loading the subpackage under a bare parent package.
    """
    try:
        from swegemma import graph as sg
        return sg
    except ImportError:
        import importlib
        import importlib.util
        import sys
        import types

        spec = importlib.util.find_spec("swegemma")
        if spec is None or not spec.submodule_search_locations:
            raise
        sys.modules.pop("swegemma", None)
        pkg = types.ModuleType("swegemma")
        pkg.__path__ = list(spec.submodule_search_locations)
        sys.modules["swegemma"] = pkg
        return importlib.import_module("swegemma.graph")


def run(data: Path, out: Path, n_ctrl: int = 5):
    sg = import_harness_graph()

    tasks = [json.loads(l) for l in (data / "tasks.jsonl").open()]
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    label_log = []
    for t in tasks:
        iid = t["instance_id"]
        ids, texts, edges = load_graph(data / "graphs" / f"{graph_key(t)}.json")
        emb = load_embeddings(data / "embeddings" / f"{graph_key(t)}.npz")
        sources = load_sources(data, iid)
        id_set = set(ids)
        gold_files, gold, node_file = gold_nodes(t, sources, id_set)
        cand = [i for i, n in enumerate(ids) if not is_test_node(n)]
        cids = [ids[i] for i in cand]
        label_log.append(
            dict(
                instance_id=iid, repo=t["repo"], n_nodes=len(ids), n_cand=len(cand),
                n_edges=len(edges), gold_files=sorted(gold_files), gold_nodes=sorted(gold),
                emb_coverage=float(np.mean([n in emb for n in cids])) if cids else 0.0,
                files_mapped=sum(1 for n in cids if n in node_file),
            )
        )
        if not gold:
            continue
        issue = t["problem_statement"]
        res: dict[str, list[str]] = {}

        # --- shipped tool, as the prompt suggests
        def tool(q, k=50):
            try:
                r = sg.get_similar_nodes(
                    node=q, repo_name=t["repo"], k=k, graph_dir=str(data / "graphs"),
                    embeddings_dir=str(data / "embeddings"), base_commit=t["base_commit"],
                )
            except Exception:
                return []
            return [x["node_name"] for x in r if not is_test_node(x["node_name"])]

        res["tool_issue"] = tool(issue)
        merged: dict[str, int] = {}
        for kw in keywords(issue):
            for r_, n in enumerate(tool(kw, 20)):
                merged[n] = min(merged.get(n, 10**9), r_)
        res["tool_kw"] = [n for n, _ in sorted(merged.items(), key=lambda x: (x[1], x[0]))]

        # --- BM25 seed
        docs = [tokenize(ids[i].replace(".", " ") + " " + texts[i]) for i in cand]
        bm = BM25(docs).scores(tokenize(issue))
        order_bm = np.lexsort((np.array(cids), -bm))
        res["bm25"] = [cids[i] for i in order_bm]

        # --- embedding expansion
        dim = next(iter(emb.values())).shape[0] if emb else 256
        E = np.stack([emb.get(n, np.zeros(dim, np.float32)) for n in cids])

        def emb_score(Emat):
            nrm = np.linalg.norm(Emat, axis=1, keepdims=True)
            nrm[nrm == 0] = 1e-12
            En = Emat / nrm
            seeds = order_bm[:5]
            sim = (En @ En[seeds].T).max(axis=1)
            s = zscore(bm) + 0.5 * sim
            return [cids[i] for i in np.lexsort((np.array(cids), -s))]

        res["bm25+emb"] = emb_score(E)
        for sd in range(1, n_ctrl + 1):
            perm = np.random.default_rng(sd).permutation(len(cids))
            res[f"ctrl_emb_shuffle_s{sd}"] = emb_score(E[perm])

        # --- graph expansion
        pos = {n: i for i, n in enumerate(cids)}
        und = sorted({(min(pos[a], pos[b]), max(pos[a], pos[b]))
                      for a, b, _ in edges if a in pos and b in pos and a != b})

        def graph_score(elist):
            adj = [[] for _ in cids]
            for a, b in elist:
                adj[a].append(b)
                adj[b].append(a)
            pers = np.zeros(len(cids))
            top = order_bm[:20]
            pers[top] = np.maximum(bm[top], 0)
            pr = ppr(adj, pers)
            s = zscore(bm) + 0.5 * zscore(pr)
            return [cids[i] for i in np.lexsort((np.array(cids), -s))]

        res["bm25+graph"] = graph_score(und)
        for sd in range(1, n_ctrl + 1):
            sw = degree_preserving_swap(und, np.random.default_rng(sd), 10 * len(und))
            res[f"ctrl_graph_swap_s{sd}"] = graph_score(sw)

        for m, order in res.items():
            rows.append(
                dict(instance_id=iid, repo=t["repo"], method=m,
                     node_rank=rank_of(order, gold),
                     file_rank=file_rank(order, node_file, gold_files),
                     n_returned=len(order))
            )
        print(iid, {m: rank_of(o, gold) for m, o in res.items() if not m.startswith("ctrl")}, flush=True)

    (out / "labels.json").write_text(json.dumps(label_log, indent=1))
    (out / "ranks.json").write_text(json.dumps(rows, indent=1))
    summarize(rows, out)


def summarize(rows, out: Path):
    by = defaultdict(dict)
    for r in rows:
        by[r["method"]][r["instance_id"]] = r
    base = by["bm25"]
    tasks = sorted(base)

    def rr(r):
        return 1.0 / r["node_rank"] if r and r["node_rank"] else 0.0

    def stats(m):
        d = by[m]
        rk = [d[t]["node_rank"] for t in tasks if t in d]
        fr = [d[t]["file_rank"] for t in tasks if t in d]
        hit = lambda xs, k: float(np.mean([x is not None and x <= k for x in xs]))
        return dict(n=len(rk), hit1=hit(rk, 1), hit5=hit(rk, 5), hit10=hit(rk, 10),
                    mrr=float(np.mean([1 / x if x else 0 for x in rk])),
                    file_hit1=hit(fr, 1), file_hit5=hit(fr, 5))

    rng = np.random.default_rng(0)
    summary = {}
    for m in by:
        s = stats(m)
        if m != "bm25":
            diff = np.array([rr(by[m].get(t)) - rr(base[t]) for t in tasks])
            boots = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(10000)]
            wins, losses = int((diff > 0).sum()), int((diff < 0).sum())
            s.update(d_mrr=float(diff.mean()), ci95=[float(np.percentile(boots, 2.5)),
                     float(np.percentile(boots, 97.5))], wins=wins, losses=losses,
                     sign_p=sign_test(wins, losses))
        summary[m] = s
    # control aggregates
    for pre in ("ctrl_emb_shuffle", "ctrl_graph_swap"):
        ks = [m for m in summary if m.startswith(pre)]
        if ks:
            summary[pre + "_mean"] = {k: float(np.mean([summary[m][k] for m in ks]))
                                      for k in ("hit1", "hit5", "hit10", "mrr", "file_hit1", "file_hit5")}
    per_repo = defaultdict(dict)
    for m in ("tool_issue", "tool_kw", "bm25", "bm25+emb", "bm25+graph"):
        for repo in sorted({base[t]["repo"] for t in tasks}):
            ts = [t for t in tasks if base[t]["repo"] == repo]
            rk = [by[m][t]["node_rank"] for t in ts if t in by[m]]
            per_repo[m][repo] = dict(n=len(rk), hit10=float(np.mean([x is not None and x <= 10 for x in rk])),
                                     mrr=float(np.mean([1 / x if x else 0 for x in rk])))
    summary["per_repo"] = per_repo
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_repo"}, indent=1))


def sign_test(w: int, l: int) -> float:
    n = w + l
    if n == 0:
        return 1.0
    k = min(w, l)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    run(a.data, a.out)
