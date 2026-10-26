# The Query Gap: code for the Gemma 4 Developer Agent paper

Paper: `WRITEUP.md` (the Kaggle Writeup text). Frozen protocol: `PROTOCOL.md`, written before the
first result was computed. The competition data is not included; join
[the competition](https://www.kaggle.com/competitions/gemma-4-developer-agent) and download it.

## Reproduce (CPU only)

```bash
pip install numpy networkx cachetools
# harness code behind search_similar_code (from the official wheelhouse dataset)
kaggle datasets download metric/gemma-4-developer-agent-wheelhouse -f swegemma-0.2.11-py3-none-any.whl
pip install --no-deps swegemma-0.2.11-py3-none-any.whl

kaggle competitions download gemma-4-developer-agent   # ~22 GB, mostly snapshots
unzip gemma-4-developer-agent.zip 'graphs/*' 'embeddings/*' tasks.jsonl -d data
python gemma4_paper/extract_sources.py --zip gemma-4-developer-agent.zip --data data  # .py sources only

python gemma4_paper/run_study.py        --data data --out out   # Table 1 (frozen protocol)
python gemma4_paper/probe_embeddings.py --data data --out out   # Table 2
python gemma4_paper/explore_weights.py  --data data --out out   # Table 3 (exploratory)
```

The aggregate outputs we obtained are in `results/`.

## End-to-end pilot (Kaggle L4×4)

`agent/baseline` is the public Budget-Fit Single Agent bundle by verracodeguacas, unchanged.
`agent/locate` adds the `locate-code` skill and one prompt line.
`build_pilot_notebook.py` builds the notebook that runs both configs on the 24 pilot tasks;
`results/pilot_v2_runs.txt` holds the per-run lines from that session's log
(`index config task resolved tool_calls seconds error`).

## Files

| File | Purpose |
|---|---|
| `run_study.py` | Labels from reference patches; tool vs. BM25 vs. BM25+embedding/graph, controls, statistics |
| `probe_embeddings.py` | What the 256-d node embeddings encode |
| `explore_weights.py` | Post hoc: z-scored terms, weights chosen by cross-validation across repositories |
| `agent/locate/skills/locate-code/` | The skill (standard library only) |
| `build_pilot_notebook.py` | Kaggle notebook for the paired pilot |

## Leaderboard submissions (main competition)

| Ref | Config | Result |
|---|---|---|
| 57131199 | `agent/locate` (31B + locate-code skill) | public 0.20 (rank 59 / 2,747 on 2026-10-14) |
| 57186550 | `agent/locate_12b` (12B, same agent) | failed: "notebook hit an unhandled error while rerunning"; not GPU-tested beforehand, likely the 12B vLLM start-up issue reported on the forum. Do not resubmit without a GPU smoke test. |
| 57627856 | `agent/verify36` (reproduce before/after + related test file, 36 tool calls, 8 min) | failed: "exceeded the allowed runtime" (12 h for all tasks). Not GPU-tested beforehand. The longer budget plus the extra verification steps do not fit; keep 28 calls and measure the mean time per task sequentially before resubmitting. |
