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
