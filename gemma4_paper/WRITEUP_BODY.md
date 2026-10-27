## Abstract

The Gemma 4 Developer Agent harness gives the agent three code-intelligence tools backed by a
precomputed call graph and 256-dimensional node embeddings. The tool prompt says
`search_similar_code` finds code "by keyword". We show this is not true offline. The harness has
no text encoder, so a natural-language query cannot be embedded. The tool then falls back to a
substring count over symbol names and source. On the 129 public development tasks, 116 have
gold functions recoverable from the reference patch. Used as the prompt suggests, with keywords
from the issue, the tool puts a gold function in its top 10 for 25.9% of those tasks. Given the
whole issue text it reaches 33.6%. Plain BM25 over function source, using the same issue text
and no model, reaches 55.2% (79 wins and 27 losses against the tool on per-task reciprocal
rank, sign test p = 4.3e-7). The precomputed signals add nothing on top of BM25 at the function
level. The embeddings are strongly anisotropic: two random nodes have mean cosine 0.86. Nearest
neighbours mostly share a module (63.6% vs. 9.3% at random), and cosine tracks lexical overlap
only weakly (Spearman 0.14). This points to structural rather than semantic embeddings.
Personalized PageRank over the call graph does not improve function ranking. In a
cross-validated exploratory analysis, a degree-preserving rewired graph does as well as the real
one. We ship the lexical bridge as a standard-library ADK skill that runs in under a second, and test
it end to end with Gemma 4 31B on Kaggle L4×4. A 24-task pilot favoured the skill (5 vs. 3
resolved), but the pre-registered extension did not replicate it: over 70 completed pairs the
arms resolve 17 and 19 tasks (3 vs. 5 discordant pairs, exact sign test p = 0.73), and the agent
called the skill in only 8 of 46 extension runs. A text entry point fixes retrieval; getting the
agent to use it is the open problem.

## 1. Introduction

Small local models struggle most with *where* to edit, not *how*. In the Gemma 4 Developer Agent
competition, the base model (`gemma-4-31b-it-qat-w4a16-ct`) works inside a sandbox with shell and
file tools. When precomputed artifacts exist for a repository, the harness also exposes three
graph tools: `get_code_neighbors`, `get_code_subgraph` and `search_similar_code`. The organizers
encourage using these artifacts. Yet community reports say the strongest public agents disable
the graph tools, and that semantic searches "usually return nothing".

We explain why, using the harness source (`swegemma` 0.2.11) and the released data:

1. **An interface mismatch.** The agent prompt describes `search_similar_code(query)` as finding
   code "by keyword". The function itself resolves `query` against node names. Free text has no
   embedding offline and falls through to an unweighted substring count (Section 3).
2. **A measured localization gap.** On the 116 labelled development tasks, the tool used as
   described trails a model-free BM25 baseline by 21–29 points of Hit@10 (Section 5).
3. **What the precomputed signals encode.** The embeddings reflect where code sits (module, call
   neighbourhood) more than what it says. Under a frozen protocol, neither the embeddings nor the
   call graph improves BM25's function ranking (Sections 5–6).
4. **A drop-in fix.** A 130-line standard-library skill packages the BM25 bridge in the
   competition's skill format. We test it end to end in a paired pilot and a pre-registered extension (Section 7).

All numbers come from scripts in our public repository and were computed under a protocol
written before any result was seen (Section 4). Exploratory analyses run afterwards are labelled
as such.

## 2. Related work

Issue localization is the first stage of most repository-level repair systems. Agentless
(Xia et al., 2024; arXiv:2407.01489) localizes hierarchically from files to functions to lines
before repairing. AutoCodeRover (Zhang et al., 2024; arXiv:2404.05427) searches over class and
method structure. SWE-agent (Yang et al., 2024; arXiv:2405.15793) shows that the design of the
agent–computer interface strongly changes agent behaviour. Our finding is a concrete instance:
a tool whose contract the agent cannot satisfy. Graph-based methods represent the repository
explicitly. RepoGraph (Ouyang et al., ICLR 2025; arXiv:2410.14684) adds a line-level code graph
as a plug-in. CodexGraph (Liu et al., NAACL 2025; arXiv:2408.03910) lets agents query a graph
database. LocAgent (Chen et al., ACL 2025; arXiv:2503.09089) has agents traverse a heterogeneous
code graph for localization. These systems pair the graph with a working entry point from text:
LLM-written queries, BM25 or a text encoder. Our audit shows what happens when that entry point
is missing. Benchmarks follow
SWE-bench (Jimenez et al., 2024; arXiv:2310.06770). Embedding anisotropy, where vectors sit in a
narrow cone, was characterized for contextual language models by Ethayarajh (2019;
arXiv:1909.00512). We observe the same geometry in the competition's node embeddings and show
its practical cost for retrieval.

## 3. How the harness tools behave

We read `swegemma/tools/graph.py` and `swegemma/graph/{retrieval,embedding}_utils.py`.

- **`search_similar_code(query, k)`** calls `get_similar_nodes(node=query)`. If `query` resolves
  to a node name, possibly by suffix, it returns the top-k nodes by cosine similarity to that
  node's precomputed vector. Otherwise `embed(query)` is attempted. Offline, `embed` is a lookup
  over the `.npz` keys and node texts, not an encoder. A sentence therefore gets no vector.
- **The fallback** splits the lower-cased query into alphanumeric tokens of length 2 or more. It
  scores each node +3 when a token is a substring of its name and +1 when a token is a substring
  of its source, plus a small bonus for non-test nodes. Common words such as "the", "is" and
  "in" count like rare identifiers, and partial matches count fully (`in` matches `print`).
- **The prompt.** The harness appends: "`search_similar_code(query)`: Find semantically similar
  functions/classes by keyword." The harness README itself says to "pass a class, function, or
  module symbol name … rather than a free-form natural language sentence."

The semantic path is therefore usable only once the agent already knows a relevant symbol, which
is the hard part of localization. The keyword path is an unweighted substring count.

## 4. Data and frozen protocol

**Tasks.** The 129 public development tasks: 67 FastAPI, 48 Rich, 13 Requests and 1 HTTPX.
Each task has a snapshot at `base_commit`, a graph, embeddings, the issue text and the reference
patch.

**Labels.** Gold files are the non-test Python files the reference patch modifies. Gold
functions are the innermost graph nodes (function, method or class) whose source span in the
base snapshot contains a changed pre-image line. Spans come from parsing the snapshot with
Python's `ast`; qualified names are matched to graph ids. 116 tasks have at least one gold node.
The other 13 only add files, only touch documentation or module-level code, or change code with
no graph node. They are excluded from ranking metrics and listed in the repository.

**Query and candidates.** The query is `problem_statement` only. Hints, tests and the patch are
never used for ranking. Candidates are all non-test graph nodes, using the harness's own test
rule (median 1,150 per task).

**Methods** (all parameters fixed before results):
- `tool_issue`: the shipped `get_similar_nodes` with the full issue text.
- `tool_kw`: the shipped function called on up to 5 identifiers taken from code spans in the
  issue, with results merged by best rank. This is the usage the prompt suggests.
- `bm25`: BM25 (k1 = 1.2, b = 0.75) over node id plus source, with snake/camel-case splitting
  and stopwords removed.
- `bm25+emb`: z(BM25) + 0.5 × the maximum cosine to the top-5 BM25 seeds.
- `bm25+graph`: z(BM25) + 0.5 × z(personalized PageRank) on the undirected call graph (restart
  0.15, 30 iterations, seeded with the top-20 BM25 scores).
- Controls: embeddings permuted across nodes, and degree-preserving edge swaps; 5 seeds each.

**Metrics.** Function Hit@k, mean reciprocal rank (MRR), and file Hit@k (a file ranks at its best
node). Paired comparisons with BM25 use a sign test on per-task reciprocal rank and a 10,000-sample
paired bootstrap.

## 5. Results: localization

| Method | Hit@1 | Hit@5 | Hit@10 | MRR | File Hit@1 | File Hit@5 |
|---|---|---|---|---|---|---|
| `tool_kw` (prompt's usage) | 7.8 | 19.0 | 25.9 | 0.129 | 20.7 | 50.9 |
| `tool_issue` | 13.8 | 27.6 | 33.6 | 0.211 | 24.1 | 61.2 |
| **`bm25`** | **16.4** | **44.0** | **55.2** | **0.300** | 32.8 | 65.5 |
| `bm25+emb` | 16.4 | 44.0 | 55.2 | 0.300 | 32.8 | 65.5 |
| `bm25+graph` | 16.4 | 41.4 | 53.4 | 0.288 | **37.9** | **68.1** |
| control: shuffled embeddings | 16.4 | 44.0 | 55.3 | 0.300 | 32.8 | 65.3 |
| control: rewired graph | 16.4 | 41.9 | 53.1 | 0.287 | 32.1 | 66.7 |

*Table 1. 116 labelled tasks; percentages except MRR; control rows are means over 5 seeds.*

BM25 beats the tool in both usages. Against `tool_issue`, its MRR is 0.088 higher (95% CI
[0.020, 0.157]); BM25 wins on 79 tasks and loses on 27 (p = 4.3e-7). Against `tool_kw` the gap is
0.170 [0.097, 0.245] (93 vs. 19, p = 6.8e-13). Following the prompt's advice, keywords instead of
the issue, makes the tool worse. Per repository, BM25 Hit@10 is 47.5% on FastAPI (n = 59), 57.8%
on Rich (45) and 81.8% on Requests (11); the tool's figures are 30.5%, 28.9% and 63.6%.

Under the frozen weights, `bm25+emb` is identical to BM25 at every reported cutoff. The raw
cosine term barely varies across candidates (Section 6), so it only reorders deep ranks (19 wins,
6 losses, MRR change below 0.001). `bm25+graph` slightly lowers function MRR (−0.012, CI
[−0.051, 0.030]). It raises file Hit@1 by 5.1 points while the rewired control does not (32.1%), but the
exploratory analysis in Section 6 finds no consistent benefit from the real edges, so we do not
read this as evidence that the call graph helps.

## 6. What the embeddings encode

Across the 127 distinct snapshots (mean 1,108 non-test nodes), we compared embedding cosine with
structure and text, using 20,000 random node pairs per snapshot:

| Quantity | Value |
|---|---|
| Mean cosine, random pairs | 0.864 |
| Mean cosine, call-graph neighbours | 0.989 |
| Nearest neighbour is in the same module | 63.6% (random: 9.3%) |
| Nearest neighbour is a call-graph neighbour | 9.0% (random: 0.2%) |
| Spearman(cosine, token Jaccard of source) | 0.14 |

*Table 2. Means over 127 snapshots.*

The vectors sit in a narrow cone. Call neighbours are nearly collinear, and the nearest
neighbour is usually in the same module. Cosine correlates only weakly with what the code says.
This geometry explains Section 5: the embeddings separate *regions* of the repository, but a
max-cosine term at a fixed scale barely moves the ranking. It also means that, even with a text
encoder, similar vectors would mean "nearby code", not "code about the same thing".
Measured over *all* call edges instead of sampled pairs, the mean neighbour cosine is 0.989, against
0.865 for random pairs (127 snapshots).

**Exploratory follow-up (post hoc).** The frozen `bm25+emb` gave the cosine term a raw scale. A
fairer test z-scores both terms and picks the weight from {0.1, 0.25, 0.5, 1, 2} by
cross-validation across repositories: the weight is chosen on Rich and applied to the other
three, and vice versa. Every reported task is therefore scored with a weight chosen elsewhere.

| Method (cross-validated weight) | Hit@1 | Hit@10 | MRR | ΔMRR vs. BM25 [95% CI] | W/L |
|---|---|---|---|---|---|
| BM25 | 16.4 | 55.2 | 0.300 | – | – |
| + z(embedding) | 16.4 | 54.3 | 0.299 | −0.000 [−0.002, 0.001] | 31/17 |
| + z(embedding), shuffled | 16.4 | 55.2 | 0.299 | −0.001 [−0.003, 0.001] | 29/25 |
| + z(PageRank), real graph | 15.5 | 56.9 | 0.280 | −0.019 [−0.055, 0.017] | 36/50 |
| + z(PageRank), rewired graph | 19.8 | 56.9 | 0.315 | +0.015 [−0.015, 0.046] | 41/34 |

*Table 3. 116 tasks, exploratory.*

Two observations. First, even a z-scored embedding term barely moves the top of the list: BM25's
top-10 scores sit 3–7 standard deviations above the mean, so the term swaps at most one or two of
the top 10, and those swaps do not help. Second, diffusion over a degree-preserving *rewired*
graph does at least as well as diffusion over the real call graph; across the weight grid the
rewired graph is never worse. Whatever PageRank adds is a degree (hub) prior, not information
carried by the actual call edges. Neither difference is significant, and we do not claim
either way that the call graph helps localization.

## 7. A lexical bridge as a skill, and an end-to-end pilot

`locate-code` is a skill directory: `SKILL.md` plus `scripts/locate.py`, standard library only.
The agent calls `run_skill_script` with the issue text. The script parses every non-test Python
file under `/workspace` with `ast`, scores functions and classes with BM25, and prints the top
12 as `path:line qualified.name` plus the top 5 files. It runs in at most 1.04 s per task. We ran
it through the real ADK skill wrapper (`_SkillScriptCodeExecutor`) on materialized snapshots. On
the 116 labelled tasks it reaches function Hit@10 = 52.6% and file Hit@5 = 67.2%. This is close
to the graph-node BM25 of Section 5; the gap comes from slightly different candidate sets.

**Pilot design** (fixed before running). A is the public Budget-Fit Single Agent bundle (0.18
public leaderboard), unchanged. B is A plus the skill and one prompt line asking the agent to run
it first. Both use 28 tool calls, 8 minutes and thinking budget 4,096. The 24 tasks come from the
labelled set ordered by SHA-256 of the instance id, stratified 12/9/2/1 across FastAPI, Rich,
Requests and HTTPX. Each task runs A then B on the same vLLM server (Kaggle L4×4).

**Pilot results.** All 24 pairs completed in one Kaggle session.

| | Baseline (A) | + `locate-code` (B) |
|---|---|---|
| Resolved | 3 / 24 (12.5%) | 5 / 24 (20.8%) |
| Resolved only by this arm | 0 | 2 (`rich_4079`, `rich_3470`) |
| Mean tool calls | 21.0 | 21.8 |
| Mean wall time per task | 276 s | 317 s |
| Stopped by the 8-minute cap | 4 | 4 |

*Table 4. Paired pilot, one run per arm per task. Wall time excludes grading.*

B solved every task A solved, plus two more, both on Rich, where BM25 most improves on the tool
(Section 5). With two discordant pairs the exact sign test gives p = 0.50. B cost about 41 s more
per task. (The pilot's skill counter also matched prompt text, so we report adoption only below.)

**Pre-registered extension.** A protocol addendum, committed before any extension run, fixes the
primary analysis: all completed pairs, exact sign test. Two of four extension shards (46 tasks)
ran within our GPU quota; shards 3–4 did not run, and no task was replaced. Over the 70 completed
pairs A resolves 17 and B 19, with 3 vs. 5 discordant pairs (p = 0.73). Adoption, now counted from
tool-call events, is low: B called the skill in 8 of 46 extension runs, 7 times as its first call.
The pilot's advantage does not replicate; with this little use, the comparison tests the prompt
line as much as the retriever. On the public leaderboard B scored 0.20 and A's public
bundle 0.18, one unpaired submission each.

## 8. Limitations

The labels assume that the edited functions are the ones to localize. Some fixes legitimately
touch other places. There are 129 tasks from four repositories, dominated by FastAPI and Rich.
Hit@k on graph nodes is not resolve rate; only Section 7 measures resolution, and with 70 pairs
it can detect only large effects. The hidden test set is built by the same pipeline but is
unseen. Our end-to-end runs used the subprocess sandbox without the repositories' test-only packages
(for example `inline-snapshot`, `dirty-equals`). With them installed, the same baseline later
resolved 36 of 105 development tasks on first try (16-minute limit), so the absolute rates in Section 7 are
underestimates for both arms; whether the handicap interacts with the skill is untested. We did
not tune BM25. A tuned retriever, or one that also uses hints, would likely do
better, so our gap is a lower bound on what a working text entry point can add.

## 9. Recommendations

For agent builders: do not pass sentences to `search_similar_code`. Use a lexical shortlist
first, then the graph tools on the resulting symbols. For the harness: either ship a small text
encoder with the embeddings, or change the tool description to "pass an exact symbol name" and
make the fallback IDF-weighted on whole tokens.

## Reproducibility

Code, frozen protocol and aggregate results:
https://github.com/Daniel766hi/kaggle-compe/tree/gemma4-paper/gemma4_paper (`README.md` lists
the commands). `PROTOCOL.md` was committed before the first result was computed. The
localization study needs only a CPU and the competition data; the pilot notebook
(attached in Project Links) needs Kaggle L4×4. The baseline agent is the public Budget-Fit Single
Agent bundle by verracodeguacas, used unchanged. AI assistance was used for implementation and
writing; every number comes from executed scripts.

## References

- Jimenez et al. SWE-bench: Can Language Models Resolve Real-World GitHub Issues? arXiv:2310.06770.
- Yang et al. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024, arXiv:2405.15793.
- Xia et al. Agentless: Demystifying LLM-based Software Engineering Agents. arXiv:2407.01489.
- Zhang et al. AutoCodeRover: Autonomous Program Improvement. ISSTA 2024, arXiv:2404.05427.
- Ouyang et al. RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph. ICLR 2025, arXiv:2410.14684.
- Liu et al. CodexGraph: Bridging Large Language Models and Code Repositories via Code Graph Databases. NAACL 2025, arXiv:2408.03910.
- Chen et al. LocAgent: Graph-Guided LLM Agents for Code Localization. ACL 2025, arXiv:2503.09089.
- Ethayarajh. How Contextual are Contextualized Word Representations? EMNLP 2019, arXiv:1909.00512.
- Robertson and Zaragoza. The Probabilistic Relevance Framework: BM25 and Beyond. FnTIR 2009.
