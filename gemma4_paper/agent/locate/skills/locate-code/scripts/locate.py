"""Rank the repository's functions/classes against an issue text with BM25.

Usage (from the agent): run_skill_script(skill_name="locate-code",
    file_path="scripts/locate.py", args={"query": "<issue text>"})

Prints the top functions as `path:line  qualified.name` and the top files.
Standard library only; reads Python sources under /workspace (tests excluded).
"""

import argparse
import ast
import math
import os
import re
from collections import Counter

STOP = set(
    """a an the and or of to in on for is are was were be been it this that with as at by
    from not no but if when then else so do does did can could should would will have has had
    i we you they he she my our your their its there here what which who how why where all any
    some more most also just only than too very into out up down over under use used using get
    got like want need one two new same other such see seems seem way make made return returns
    true false none self cls def class import""".split()
)
SKIP_DIRS = {".git", "tests", "test", "node_modules", "__pycache__", ".venv", "venv", "build", "dist"}


def split_ident(tok):
    parts = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tok).replace("_", " ").split()
    return [p.lower() for p in parts]


def tokenize(text):
    out = []
    for raw in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text):
        pieces = split_ident(raw)
        if len(pieces) > 1:
            out.append(raw.lower())
        out.extend(pieces)
    return [t for t in out if len(t) >= 2 and t not in STOP]


def module_name(rel):
    p = rel[:-3]
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    if p.startswith("src/"):
        p = p[4:]
    return p.replace("/", ".")


def collect(root):
    units = []  # (qualname, rel path, line, tokens)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py") or fn.startswith("test_") or fn.endswith("_test.py") or fn == "conftest.py":
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            try:
                src = open(path, encoding="utf-8", errors="replace").read()
                tree = ast.parse(src)
            except (SyntaxError, ValueError, OSError):
                continue
            lines = src.splitlines()
            mod = module_name(rel)

            def walk(node, prefix):
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        q = f"{prefix}.{ch.name}"
                        body = "\n".join(lines[ch.lineno - 1: ch.end_lineno])
                        units.append((q, rel, ch.lineno, tokenize(q.replace(".", " ") + " " + body)))
                        walk(ch, q)

            walk(tree, mod)
    return units


def bm25(docs, query, k1=1.2, b=0.75):
    tfs = [Counter(d) for d in docs]
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(n, 1)
    df = Counter(t for tf in tfs for t in tf)
    q = set(query)
    idf = {t: math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in q if t in df}
    scores = []
    for tf, d in zip(tfs, docs):
        norm = k1 * (1 - b + b * len(d) / avg)
        s = 0.0
        for t, w in idf.items():
            f = tf.get(t, 0)
            if f:
                s += w * f * (k1 + 1) / (f + norm)
        scores.append(s)
    return scores


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--root", default="/workspace")
    ap.add_argument("--k", type=int, default=12)
    a = ap.parse_args()
    units = collect(a.root)
    if not units:
        print("No Python definitions found under", a.root)
        return
    scores = bm25([u[3] for u in units], tokenize(a.query))
    order = sorted(range(len(units)), key=lambda i: (-scores[i], units[i][0]))
    print("Top functions/classes for the issue (BM25 over source; verify by reading):")
    for i in order[: a.k]:
        if scores[i] <= 0:
            break
        q, rel, line, _ = units[i]
        print(f"  {rel}:{line}  {q}  (score {scores[i]:.1f})")
    files = []
    for i in order:
        if units[i][1] not in files:
            files.append(units[i][1])
        if len(files) == 5:
            break
    print("Top files:", ", ".join(files))


if __name__ == "__main__":
    main()
