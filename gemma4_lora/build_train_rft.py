"""Build the offline L4x4 LoRA notebook trained on the agent's OWN resolved runs (rejection sampling).

    python gemma4_lora/build_train_rft.py --out <kernel dir> --holdout-file gemma4_lora/holdout_pilot24.json

Data: /kaggle/input/**/collected/*.json from the gemma4-collect notebook, resolved runs only, holdout
tasks removed, at most --per-task runs per task. Unlike the scripted oracle trajectories (which taught
the adapter to edit without exploring, 0/24 vs 3/24), these runs use no privileged information.

Differences from build_train_l4.py:
- ADK sends earlier reasoning back as reasoning_content and the Gemma 4 template renders it, so whole
  runs are trained with every turn's reasoning; runs are ~2-3x longer. Longer runs are truncated at
  the end instead of dropped. MAX_LEN stays 8192: Gemma 4's global layers have head_dim 512, which
  the fused SDPA kernels do not support, so attention falls back to a full score matrix that grows
  with the square of the length (v1 at 16k ran out of memory on every example). Tool outputs, which
  are context only, are cut to 600 characters to keep more of each run inside 8192 tokens.
- The cross-entropy over the 262k vocabulary is computed in checkpointed chunks of positions.
- An out-of-memory example is skipped instead of ending the run.
"""

import argparse
import json
from pathlib import Path

import build_train_l4 as l4
import build_train_notebook as base

DATA = r'''
SEED = 3407
random.seed(SEED)
DEPLOYED_MINUTES = float(DEPLOYED_EVAL['max_time_minutes'])
schema_files = sorted(glob.glob('/kaggle/input/**/tool_schemas.json', recursive=True))
assert schema_files, 'attach the oracle-trajectories notebook output (tool schemas)'
TOOLS = json.load(open(schema_files[0]))

def fix_schema(s):
    """Gemma's template wants plain JSON schema: turn any_of [T, null] into nullable T."""
    if isinstance(s, dict):
        if 'any_of' in s or 'anyOf' in s:
            opts = [fix_schema(o) for o in (s.get('any_of') or s.get('anyOf')) if o.get('type') not in ('null', 'NULL')]
            b = dict(opts[0]) if opts else {'type': 'string'}
            b['nullable'] = True
            for k, v in s.items():
                if k not in ('any_of', 'anyOf'):
                    b[k] = fix_schema(v)
            return b
        return {k: fix_schema(v) for k, v in s.items()}
    if isinstance(s, list):
        return [fix_schema(x) for x in s]
    if isinstance(s, str) and s.isupper():
        return s.lower()
    return s

TOOLS = [{'type': 'function', 'function': fix_schema(t)} for t in TOOLS]

def trace_to_messages(prompt, entries):
    """Recorded ADK events -> HF chat messages, one assistant message per model response
    (its thinking, text and tool calls), one tool message per tool response."""
    out, cur = [{'role': 'system', 'content': SYSTEM_PROMPT}, {'role': 'user', 'content': prompt}], None
    def flush():
        nonlocal cur
        if cur is not None:
            m = {'role': 'assistant', 'content': cur['text'].strip()}
            if cur['reasoning'].strip():
                m['reasoning'] = cur['reasoning'].strip()
            if cur['calls']:
                m['tool_calls'] = [{'type': 'function', 'function': {'name': n, 'arguments': a}} for n, a in cur['calls']]
            out.append(m)
        cur = None
    for e in entries:
        t = e.get('type')
        if t in ('thinking', 'text', 'final', 'tool_call'):
            if cur is None:
                cur = {'reasoning': '', 'text': '', 'calls': []}
            elif cur['calls'] and t != 'tool_call':
                flush(); cur = {'reasoning': '', 'text': '', 'calls': []}
            if t == 'thinking':
                cur['reasoning'] += ('\n' if cur['reasoning'] else '') + (e.get('content') or '')
            elif t == 'tool_call':
                cur['calls'].append((e.get('tool') or '', e.get('args') or {}))
            else:
                cur['text'] += ('\n' if cur['text'] else '') + (e.get('content') or '')
        elif t == 'tool_response':
            flush()
            c = e.get('result') or ''
            if len(c) > TOOL_CHARS:  # context only (never trained); keep head and tail
                c = c[:TOOL_CHARS - 300] + '\n...[truncated]...\n' + c[-300:]
            out.append({'role': 'tool', 'name': e.get('tool') or '', 'content': c})
    flush()
    return out

TOOL_CHARS = 600
files = sorted(glob.glob('/kaggle/input/**/collected/*.json', recursive=True))
runs = [json.load(open(f)) for f in files]
print('collected runs', len(runs), 'resolved', sum(bool(r['row'].get('resolved')) for r in runs))
by_task = {}
for r in runs:
    row = r['row']
    if row.get('resolved') and r.get('prompt') and isinstance(r.get('trace'), list) and row['instance_id'] not in HOLDOUT:
        by_task.setdefault(row['instance_id'], []).append(r)
train_rows = []
for iid, rs in sorted(by_task.items()):
    rs.sort(key=lambda r: r['row'].get('tool_calls') or 0)  # prefer the shorter solution
    for r in rs[:PER_TASK]:
        prompt = re.sub(r'Time allowance: [0-9.]+ minutes', f'Time allowance: {DEPLOYED_MINUTES} minutes', r['prompt'])
        train_rows.append({'instance_id': iid, 'messages': trace_to_messages(prompt, r['trace'])})
print('train tasks', len(by_task), 'train runs', len(train_rows))
assert train_rows, 'no resolved runs found'
m0 = train_rows[0]['messages']
print('roles', [m['role'] for m in m0][:12], '| first call', next((m['tool_calls'][0]['function']['name'] for m in m0 if m.get('tool_calls')), None))
to_hf = lambda msgs: msgs  # trace_to_messages already returns HF chat format
'''

MODEL = l4.MODEL.replace(
    "    if len(ids) > MAX_LEN or not any(l != -100 for l in labels):\n        return None\n",
    "    ids, labels = ids[:MAX_LEN], labels[:MAX_LEN]  # long runs: keep the start, drop the end\n"
    "    if not any(l != -100 for l in labels):\n        return None\n").replace(
    "assert len(examples) >= 20, len(examples)", "assert len(examples) >= 10, len(examples)")
assert "MAX_LEN = 8192" in MODEL and "keep the start" in MODEL and "len(examples) >= 10" in MODEL

OLD_LOSS = l4.TRAIN[l4.TRAIN.index("    hs = h[:-1]"):l4.TRAIN.index("    (loss / ACCUM).backward()")]
NEW_LOSS = r'''    hs = h[:-1].index_select(0, sel.to(h.device))
    ys = lab[1:].index_select(0, sel)
    def chunk_loss(hc, yc):
        lg = lm_head(hc.to(lm_head.weight.device)).float()
        if cap:
            lg = torch.tanh(lg / cap) * cap
        return torch.nn.functional.cross_entropy(lg, yc.to(lg.device), reduction='sum')
    tot = 0.0
    for s0 in range(0, hs.shape[0], 1024):
        tot = tot + torch.utils.checkpoint.checkpoint(chunk_loss, hs[s0:s0 + 1024], ys[s0:s0 + 1024], use_reentrant=False)
    loss = tot / hs.shape[0]
'''
TRAIN = l4.TRAIN.replace(OLD_LOSS, NEW_LOSS)
# skip an example that does not fit instead of ending the run
TRAIN = TRAIN.replace("    ex = examples[idx]\n", "    ex = examples[idx]\n    try:\n", 1)
_a = TRAIN.index("    ids = torch.tensor([ex['input_ids']]")
_b = TRAIN.index("    if (k + 1) % ACCUM == 0")
TRAIN = (TRAIN[:_a] + "".join("    " + l + "\n" for l in TRAIN[_a:_b].rstrip("\n").split("\n"))
         + "    except torch.cuda.OutOfMemoryError:\n        print('OOM, skipped example', idx, len(ex['input_ids']), flush=True)\n"
         "        ids = lab = h = sel = hs = ys = loss = tot = None; opt.zero_grad(set_to_none=True)\n"
         "        import gc; gc.collect(); torch.cuda.empty_cache(); oom += 1\n"
         "        if oom > 8:\n            raise RuntimeError('too many out-of-memory examples; lower MAX_LEN')\n"
         "        continue\n"
         + TRAIN[_b:])
TRAIN = TRAIN.replace("model.train(); t0 = time.time()", "oom = 0\nmodel.train(); t0 = time.time()")
TRAIN = TRAIN.replace("print('train loss', train_loss,", "print('OOM skipped', oom); print('train loss', train_loss,")
assert "chunk_loss" in TRAIN and "OOM, skipped" in TRAIN
TRAIN = TRAIN.replace("TIME_LIMIT = 9 * 3600", "TIME_LIMIT = 5 * 3600")  # weekly GPU quota
assert "TIME_LIMIT = 5 * 3600" in TRAIN

SAVE = l4.SAVE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-file", type=Path)
    ap.add_argument("--per-task", type=int, default=2)
    ap.add_argument("--slug", default="gemma4-lora-rft")
    ap.add_argument("--user", default="danielaijdkx")
    ap.add_argument("--collect-source", default="danielaijdkx/gemma4-collect")
    a = ap.parse_args()
    holdout = json.loads(a.holdout_file.read_text()) if a.holdout_file else []
    files = {str(p.relative_to(base.AGENT)): p.read_text() for p in sorted(base.AGENT.rglob("*")) if p.is_file()}
    import yaml
    ev = yaml.safe_load(files["eval_config.yaml"])["evaluation"]
    head = ("HOLDOUT = set(" + json.dumps(holdout) + ")\nSYSTEM_PROMPT = " + json.dumps(files["prompts/system.md"])
            + "\nAGENT_FILES = " + json.dumps(files, indent=1) + f"\nPER_TASK = {a.per_task}\nDEPLOYED_EVAL = "
            + json.dumps(ev) + "\n")
    nb = {"cells": [base.md("# LoRA on the agent's own resolved runs (rejection sampling), Gemma 4 31B, offline L4x4\n\n"
                            + __doc__.split("\n\n", 2)[2]),
                    base.code(l4.SETUP), base.code(head + DATA), base.code(MODEL), base.code(TRAIN), base.code(SAVE)],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    (a.out / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{a.user}/{a.slug}", "title": a.slug.replace("-", " ").title(), "code_file": f"{a.slug}.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_tpu": False,
        "enable_internet": False, "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"],
        "kernel_sources": [a.collect_source, "danielaijdkx/gemma4-oracle-trajectories", "danielaijdkx/gemma4-offline-wheels"],
        "model_sources": ["google/gemma-4/Transformers/gemma-4-31b-it-qat-q4_0-unquantized/2"],
        "machine_shape": "NvidiaL4",
        "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"}, indent=1))
    print("holdout", len(holdout))


if __name__ == "__main__":
    main()
