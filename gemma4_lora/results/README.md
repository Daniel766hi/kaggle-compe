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
