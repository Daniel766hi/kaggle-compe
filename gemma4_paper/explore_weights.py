"""Exploratory (post hoc) follow-up to the frozen study; reported separately.

The frozen bm25+emb added a raw max-cosine term whose spread is tiny (the embeddings are
anisotropic), so it could not move rankings. Here both expansion terms are z-scored and the
weight is chosen by 2-fold cross-validation across repositories (fold 1: fastapi+requests+httpx,
fold 2: rich), so each reported number is on tasks not used to choose its weight.
Also recomputes embedding cosine over *all* call edges (not a pair sample).

    python gemma4_paper/explore_weights.py --data <dir> --out <dir>
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from run_study import (BM25, degree_preserving_swap, gold_nodes, graph_key, is_test_node,
                       load_embeddings, load_graph, load_sources, ppr, rank_of, sign_test,
                       tokenize, zscore)

WEIGHTS = [0.1, 0.25, 0.5, 1.0, 2.0]


def main(data: Path, out: Path):
    tasks = [json.loads(l) for l in (data / "tasks.jsonl").open()]
    ranks = defaultdict(dict)  # method -> iid -> rank
    repo_of = {}
    edge_cos, rand_cos = [], []
    seen_snap = set()
    for t in tasks:
        iid = t["instance_id"]
        ids, texts, edges = load_graph(data / "graphs" / f"{graph_key(t)}.json")
        emb = load_embeddings(data / "embeddings" / f"{graph_key(t)}.npz")
        gold_files, gold, _ = gold_nodes(t, load_sources(data, iid), set(ids))
        cand = [i for i, n in enumerate(ids) if not is_test_node(n)]
        cids = [ids[i] for i in cand]
        E = np.stack([emb.get(n, np.zeros(256, np.float32)) for n in cids])
        En = E / np.maximum(np.linalg.norm(E, axis=1, keepdims=True), 1e-12)
        pos = {n: i for i, n in enumerate(cids)}
        und = sorted({(min(pos[a], pos[b]), max(pos[a], pos[b]))
                      for a, b, _ in edges if a in pos and b in pos and a != b})
        if graph_key(t) not in seen_snap and und:
            seen_snap.add(graph_key(t))
            ea, eb = np.array(und).T
            edge_cos.append(float((En[ea] * En[eb]).sum(1).mean()))
            rng = np.random.default_rng(0)
            ra, rb = rng.integers(0, len(cids), 5000), rng.integers(0, len(cids), 5000)
            keep = ra != rb
            rand_cos.append(float((En[ra[keep]] * En[rb[keep]]).sum(1).mean()))
        if not gold:
            continue
        repo_of[iid] = t["repo"]
        bm = BM25([tokenize(ids[i].replace(".", " ") + " " + texts[i]) for i in cand]).scores(
            tokenize(t["problem_statement"]))
        order_bm = np.lexsort((np.array(cids), -bm))
        zb = zscore(bm)
        names = np.array(cids)

        def rk(score):
            return rank_of([cids[i] for i in np.lexsort((names, -score))], gold)

        ranks["bm25"][iid] = rank_of([cids[i] for i in order_bm], gold)
        sim = (En @ En[order_bm[:5]].T).max(axis=1)
        perm = np.random.default_rng(1).permutation(len(cids))
        Ep = En[perm]
        sim_ctrl = (Ep @ Ep[order_bm[:5]].T).max(axis=1)

        def pr_for(elist):
            adj = [[] for _ in cids]
            for a_, b_ in elist:
                adj[a_].append(b_)
                adj[b_].append(a_)
            pers = np.zeros(len(cids))
            top = order_bm[:20]
            pers[top] = np.maximum(bm[top], 0)
            return zscore(ppr(adj, pers))

        zpr = pr_for(und)
        zpr_ctrl = pr_for(degree_preserving_swap(und, np.random.default_rng(1), 10 * len(und)))
        for w in WEIGHTS:
            ranks[f"emb_z_w{w}"][iid] = rk(zb + w * zscore(sim))
            ranks[f"emb_ctrl_w{w}"][iid] = rk(zb + w * zscore(sim_ctrl))
            ranks[f"graph_w{w}"][iid] = rk(zb + w * zpr)
            ranks[f"graph_ctrl_w{w}"][iid] = rk(zb + w * zpr_ctrl)
        print(iid, ranks["bm25"][iid], ranks["emb_z_w1.0"][iid], ranks["graph_w1.0"][iid], flush=True)

    def mrr(m, ids_):
        return float(np.mean([1 / ranks[m][i] if ranks[m][i] else 0 for i in ids_]))

    def hit(m, ids_, k):
        return float(np.mean([ranks[m][i] is not None and ranks[m][i] <= k for i in ids_]))

    folds = {
        "rich": [i for i in repo_of if repo_of[i] == "Textualize/rich"],
        "fastapi+requests+httpx": [i for i in repo_of if repo_of[i] != "Textualize/rich"],
    }
    report = {"embedding_cos_over_all_edges": float(np.mean(edge_cos)),
              "embedding_cos_random_pairs": float(np.mean(rand_cos)),
              "n_snapshots": len(edge_cos), "cv": {}}
    for fam in ("emb_z", "emb_ctrl", "graph", "graph_ctrl"):
        pooled = {}
        chosen = {}
        for test_name, test_ids in folds.items():
            train_ids = [i for i in repo_of if i not in set(test_ids)]
            # control families reuse the weight chosen for their real counterpart
            sel_fam = fam.replace("_ctrl", "_z") if fam == "emb_ctrl" else fam.replace("_ctrl", "")
            w = max(WEIGHTS, key=lambda w_: mrr(f"{sel_fam}_w{w_}", train_ids))
            chosen[test_name] = w
            for i in test_ids:
                pooled[i] = ranks[f"{fam}_w{w}"][i]
        ranks[f"{fam}_cv"] = pooled
        ids_ = sorted(pooled)
        d = np.array([(1 / pooled[i] if pooled[i] else 0) - (1 / ranks["bm25"][i] if ranks["bm25"][i] else 0)
                      for i in ids_])
        rng = np.random.default_rng(0)
        boots = [d[rng.integers(0, len(d), len(d))].mean() for _ in range(10000)]
        w_, l_ = int((d > 0).sum()), int((d < 0).sum())
        report["cv"][fam] = dict(weights=chosen, hit1=hit(f"{fam}_cv", ids_, 1), hit5=hit(f"{fam}_cv", ids_, 5),
                                 hit10=hit(f"{fam}_cv", ids_, 10), mrr=mrr(f"{fam}_cv", ids_),
                                 d_mrr_vs_bm25=float(d.mean()),
                                 ci95=[float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
                                 wins=w_, losses=l_, sign_p=sign_test(w_, l_))
    ids_ = sorted(repo_of)
    report["bm25"] = dict(hit1=hit("bm25", ids_, 1), hit5=hit("bm25", ids_, 5), hit10=hit("bm25", ids_, 10),
                          mrr=mrr("bm25", ids_), n=len(ids_))
    report["weight_grid_mrr_all_tasks"] = {m: mrr(m, ids_) for m in ranks if "_w" in m}
    out.mkdir(parents=True, exist_ok=True)
    (out / "explore_weights.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k != "weight_grid_mrr_all_tasks"}, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    main(a.data, a.out)
