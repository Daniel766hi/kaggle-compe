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
