# LoRA result (2026-10-24): negative

Adapter: r=16 on all language-model projections of Gemma 4 31B (QAT bf16 base, 4-bit NF4 during training),
63 oracle trajectories (18 longer than 8,192 tokens dropped), 2 epochs, train loss 0.51 -> 0.18
(`gemma4-lora-train-l4` v3). Eval: `gemma4-lora-eval` v2, the 24 held-out pilot tasks, same agent with
and without the adapter (`lora_eval_holdout24_rows.jsonl`, one `ROW` per run).

| | resolved | non-empty patch | budget/time-outs | tool calls (edit_file / run_command) |
|---|---|---|---|---|
| baseline | 3 / 24 | 20 | 1 | 59 / 226 |
| + LoRA | 0 / 24 | 0 | 20 | 559 / 0 |

Paired: 3 tasks only baseline solved, 0 only LoRA. Test-dependency wheels failed to install
(pydantic conflict), which affects both arms equally.

Why: the oracle trajectories are scripted from the reference patch (read the file, apply the known
edit, import check, submit). The adapter learned to edit immediately without exploring or running
anything; without the answer its edits do not apply, and it retries edit_file until the budget runs out.
Imitating trajectories that use privileged information teaches the shortcut, not the search.
Not submitted.

# Collection run (2026-10-24): the agent's own trajectories

`gemma4-collect` v1: baseline agent, 105 non-holdout tasks x 2 repeats (191 of 210 runs started
before the 5.5 h cut-off), 4 concurrent runs, 16-minute time limit (8 in the submitted agent), test-only
packages installed (`collect_v1_rows.jsonl`).

- Repeat 1: 36 / 105 resolved (34%). Earlier local runs without the test packages: ~12%.
- 62 resolved runs over 40 distinct tasks (22 tasks solved in both repeats): the RFT training set.
- Outcomes: 62 resolved, 115 wrong patch, 12 no patch, 5 time-outs, 2 turn-budget stops.
- 80 / 191 runs used all 28 tool calls; 56% of wrong-patch runs did, 29% of resolved runs did.
- 9 of the 53 runs longer than 8 minutes were resolved; with the submitted 8-minute limit (and runs one
  at a time instead of four) the rate would be lower.

Caveat: this run used ADK compaction every 15 events; official scoring uses 5 (HARNESS_README 7.2).
The builder now uses 5.

# Failure analysis of the collected runs (2026-10-25, `gemma4-rft-dryrun`, CPU)

| outcome | runs | tool calls | used all 28 | tests run after last edit | repro commands |
|---|---|---|---|---|---|
| resolved | 62 | 19.9 | 29% | 84% | 2.95 |
| right file, wrong fix | 85 | 23.1 | 51% | 67% | 1.65 |
| wrong file | 30 | 25.9 | 70% | 47% | 1.93 |
| no patch | 14 | 26.4 | 79% | 0% | 0.14 |

- File-level localisation is good: 143 / 177 patches touch a file the reference patch edits.
- Only 3% of run_command calls run pytest (911 grep, 487 python3). The baseline prompt discourages tests
  ("existing tests may be broken"), written for an environment without the test-only packages.
- Resolved runs reproduce and re-check more often (correlation only). This motivates `agent/verify36`:
  reproduce before and after the edit, then run the related existing test file, with 36 tool calls.
- RFT data: 62 examples (40 tasks), length median 13,982 tokens, 17 longer than 16,384 (cut at the end),
  39% of tokens trained, 831,772 tokens after the cut.

# RFT result (2026-11-01): not better, slower; not submitted

`gemma4-lora-rft` v2: LoRA r=16 on the 62 resolved collected runs (40 tasks), MAX_LEN 8192 (v1 at 16k ran
out of memory on every example: head_dim 512 attention falls back to a full score matrix), tool outputs
cut to 600 characters. Nearly every run was cut at 8,192 tokens (median length 8,192), so training saw
mostly the first half of each run. Train loss 0.23 -> 0.18, 0 OOM.

`gemma4-eval-v3`, 24 held-out tasks, runs one at a time, official compaction (5), test packages installed
(`eval_v3_holdout24_rows.jsonl`):

| config | resolved | mean s/task | 8-min time-outs |
|---|---|---|---|
| baseline | 4 / 24 | 299 | 4 |
| v6_public | 4 / 24 | 298 | 5 |
| RFT | 3 / 24 | 349 | 9 |

Paired: baseline vs RFT 1 vs 0 discordant; baseline vs v6 0 vs 0. RFT is 17% slower per task, which
risks the 12-hour limit; with the cut at 8k it learned to explore but not to finish.

# RFT v3 result (2026-11-08): same resolve count, much slower; not submitted

`gemma4-lora-rft` v3: older tool outputs cut to 200 characters (last three to 600) and one extra
"ending" example per run (older turns without reasoning, only the last 4 turns trained): 113 examples
(11 endings had no trained token inside 8,192), stopped at the 5-hour cap (~1.5 epochs), loss 0.33 -> 0.22.

`gemma4-eval-v4`, same 24 held-out tasks, one at a time (`eval_v4_holdout24_rows.jsonl`):

| config | resolved | mean s/task | 8-min time-outs | called submit_patch |
|---|---|---|---|---|
| baseline | 4 / 24 | 262 | 2 | 21 |
| RFT v3 | 4 / 24 | 372 | 11 | 14 |

No discordant pairs. The adapter is 42% slower per task and reaches the time cap in almost half the runs,
which the 12-hour limit cannot absorb. Both RFT attempts made the agent slower without solving more;
we stop the LoRA line here.
