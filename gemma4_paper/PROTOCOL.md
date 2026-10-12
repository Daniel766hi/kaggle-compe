# Query-gap study: frozen protocol (v1)

Written 2026-10-12, before any retrieval result was computed.

## Question

The harness exposes `search_similar_code(query)` over precomputed 256-d node
embeddings and tells the agent it finds code "by keyword". Offline there is no
text encoder: a query that is not a graph symbol cannot be embedded, and the
tool falls back to a substring count. We ask:

1. How well does the tool, used as the prompt suggests (issue text or keywords),
   localize the code a fix touches?
2. Does a lexical seed step (BM25 over node source) close the gap?
3. Do the provided embeddings and call graph add anything on top of the seed,
   and does any gain depend on the real embeddings/edges (vs. shuffled controls)?

## Data

The 129 public development tasks (`tasks.jsonl`) with their graphs and
embeddings. Query = `problem_statement` only. `hints_text`, `patch` and
`test_patch` are never used for ranking. The gold patch is used only to build
labels.

## Labels

Gold files: non-test `.py` files modified by `patch` (paths containing a
`tests/`/`test/`/`docs/`/`docs_src/` component or named `test_*.py` are excluded).
Gold nodes: graph nodes whose source span in the base snapshot overlaps a
changed pre-image line of a gold file. Tasks whose patch only adds new files,
or whose changed lines map to no graph node, have no node label; they are
reported, not dropped silently.

## Candidate set

All graph nodes of the task's snapshot, excluding test nodes (id starting
`tests.`/`test.` or containing `.test_`), i.e. the same rule the tool uses.

## Methods (all parameters fixed here, no tuning)

- `tool_issue`: the shipped `get_similar_nodes(node=<problem_statement>)`.
- `tool_kw`: the shipped function called once per keyword, keywords = the first
  5 distinct identifier-like tokens from backticks / code spans in the issue
  (fallback: 5 longest distinct tokens); results merged by best rank.
- `bm25`: BM25 (k1=1.2, b=0.75) over node id + source, code-aware tokenization
  (split snake_case/camelCase, lowercase, drop tokens < 2 chars and English
  stopwords).
- `bm25+emb`: score = z(bm25) + 0.5 * max cosine to the top-5 BM25 seeds.
- `bm25+graph`: score = z(bm25) + 0.5 * z(personalized PageRank on the
  undirected call graph, restart 0.15, 30 iterations, personalization = top-20
  BM25 scores).
- Controls: `bm25+emb` with embeddings permuted across nodes (seeds 1-5);
  `bm25+graph` with degree-preserving edge swaps (seeds 1-5).

`z()` is a per-task z-score over candidates.

## Metrics

Node Hit@1/5/10 (any gold node in top k), node MRR, file Hit@1/5 (a file's rank is
its best node's rank). Paired comparison against `bm25` with a two-sided sign test
on per-task reciprocal rank and a 10,000-sample paired bootstrap 95% CI. Results are
also broken down per repository. Every number in the writeup comes from
`run_study.py` output.
