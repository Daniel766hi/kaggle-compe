"""What do the provided 256-d node embeddings encode?

For each distinct snapshot, sample node pairs and relate embedding cosine to
(a) call-graph adjacency, (b) lexical overlap of source (token Jaccard),
(c) same module. Also reports how often a node's embedding nearest neighbour is a
graph neighbour / same-module node, against a random baseline.

    python gemma4_paper/probe_embeddings.py --data <dir> --out <dir>
"""

import argparse
import json
from pathlib import Path

import numpy as np

from run_study import graph_key, is_test_node, load_embeddings, load_graph, tokenize


def spearman(x, y):
    rx = np.argsort(np.argsort(x))
    ry = np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def module_of(n: str, ids: set[str]) -> str:
    parts = n.split(".")
    for i in range(len(parts) - 1, 0, -1):
        p = ".".join(parts[:i])
        if p in ids or i == 1:
            return p
    return parts[0]


def main(data: Path, out: Path, pairs: int = 20000):
    tasks = [json.loads(l) for l in (data / "tasks.jsonl").open()]
    seen = {}
    for t in tasks:
        seen.setdefault(graph_key(t), t["repo"])
    rows = []
    for key, repo in sorted(seen.items()):
        ids, texts, edges = load_graph(data / "graphs" / f"{key}.json")
        emb = load_embeddings(data / "embeddings" / f"{key}.npz")
        keep = [i for i, n in enumerate(ids) if not is_test_node(n) and n in emb]
        names = [ids[i] for i in keep]
        if len(names) < 50:
            continue
        E = np.stack([emb[n] for n in names])
        E = E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-12)
        toks = [set(tokenize(texts[i])) for i in keep]
        pos = {n: j for j, n in enumerate(names)}
        adj = set()
        for a, b, _ in edges:
            if a in pos and b in pos and a != b:
                adj.add((pos[a], pos[b]))
                adj.add((pos[b], pos[a]))
        idset = set(ids)
        mods = [module_of(n, idset) for n in names]
        rng = np.random.default_rng(0)
        n = len(names)
        i = rng.integers(0, n, pairs)
        j = rng.integers(0, n, pairs)
        m = i != j
        i, j = i[m], j[m]
        cos = (E[i] * E[j]).sum(1)
        jac = np.array([len(toks[a] & toks[b]) / max(len(toks[a] | toks[b]), 1) for a, b in zip(i, j)])
        same_mod = np.array([mods[a] == mods[b] for a, b in zip(i, j)])
        is_adj = np.array([(a, b) in adj for a, b in zip(i, j)])
        # nearest neighbour agreement
        S = E @ E.T
        np.fill_diagonal(S, -np.inf)
        nn = S.argmax(1)
        nn_adj = float(np.mean([(a, int(b)) in adj for a, b in enumerate(nn)]))
        nn_mod = float(np.mean([mods[a] == mods[int(b)] for a, b in enumerate(nn)]))
        nn_jac = float(np.mean([len(toks[a] & toks[int(b)]) / max(len(toks[a] | toks[int(b)]), 1)
                                for a, b in enumerate(nn)]))
        deg = np.zeros(n)
        for a, _ in adj:
            deg[a] += 1
        rand_adj = float(deg.sum() / (n * (n - 1)))
        rand_mod = float(np.mean(same_mod))
        rows.append(dict(
            snapshot=key, repo=repo, n_nodes=n, n_edges=len(adj) // 2,
            spearman_cos_jaccard=spearman(cos, jac),
            mean_cos_adjacent=float(cos[is_adj].mean()) if is_adj.any() else None,
            mean_cos_nonadjacent=float(cos[~is_adj].mean()),
            mean_cos_same_module=float(cos[same_mod].mean()) if same_mod.any() else None,
            mean_cos_diff_module=float(cos[~same_mod].mean()),
            nn_is_graph_neighbor=nn_adj, random_is_graph_neighbor=rand_adj,
            nn_same_module=nn_mod, random_same_module=rand_mod,
            nn_jaccard=nn_jac, random_jaccard=float(jac.mean()),
        ))
        print(key, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items()
                    if k not in ("snapshot", "repo")}, flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "embedding_probe.json").write_text(json.dumps(rows, indent=1))
    agg = {k: float(np.mean([r[k] for r in rows if r[k] is not None]))
           for k in rows[0] if k not in ("snapshot", "repo")}
    agg["n_snapshots"] = len(rows)
    (out / "embedding_probe_summary.json").write_text(json.dumps(agg, indent=1))
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    main(a.data, a.out)
