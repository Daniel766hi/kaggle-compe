"""Build the Kaggle notebook that trains a LoRA adapter on validated agent trajectories.

    python gemma4_lora/build_train_notebook.py --out <kernel dir> [--holdout-file ids.json]

Data: `trajectories.jsonl` from the oracle-trajectory notebook (attached as a kernel source),
keeping only runs where both the oracle and the gold patch resolve the task. Tasks listed in
the holdout file are excluded so they can be used for an honest end-to-end comparison later.

Model: gemma-4-31b-it-qat-q4_0-unquantized (the QAT weights the scored w4a16 checkpoint is built
from), loaded in 4-bit with Unsloth on 2x T4. Loss is computed only on the agent's own turns
(token spans found by diffing rendered prefixes). The adapter is saved with the tensor naming
that the official vLLM server is known to load (base_model.model.model.language_model.layers.*),
and a validated submission.zip (Budget-Fit agent + adapter) is written to /kaggle/working.
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENT = HERE.parent / "gemma4_paper" / "agent" / "baseline"

SETUP = r'''
import glob, json, os, re, shutil, subprocess, sys, time, hashlib, random
from pathlib import Path
assert shutil.which('nvidia-smi'), 'Attach GPU T4 x2'
wheels = sorted(glob.glob('/kaggle/input/**/adk_submission-*.whl', recursive=True))
assert wheels, 'attach metric/gemma-4-developer-agent-wheelhouse'
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--disable-pip-version-check',
                'unsloth==2026.9.11', 'unsloth_zoo==2026.9.7', 'transformers==5.5.0', 'trl==0.24.0',
                'google-adk==1.36.1', wheels[0]], check=True)
# Test-only packages missing from the subprocess sandbox (credit: Kevin Diaz Cordova). Saved as
# wheels so the offline L4 evaluation notebook can install them.
TEST_DEPS = ['inline-snapshot', 'dirty-equals', 'pytest-httpbin', 'trustme', 'pysocks', 'flask', 'pyjwt',
             'passlib[bcrypt]', 'pwdlib', 'orjson', 'ujson', 'email-validator', 'python-multipart',
             'sqlmodel', 'trio']
r = subprocess.run([sys.executable, '-m', 'pip', 'download', '-q', '-d', '/kaggle/working/testdeps',
                    '--python-version', '3.12', '--only-binary=:all:', '--platform', 'manylinux2014_x86_64',
                    '--platform', 'manylinux_2_17_x86_64', '--platform', 'any', *TEST_DEPS],
                   capture_output=True, text=True)
print('test dep wheels:', len(list(Path('/kaggle/working/testdeps').glob('*'))), r.stderr[-500:])
'''

DATA = r'''
SEED = 3407
random.seed(SEED)
traj_files = sorted(glob.glob('/kaggle/input/**/trajectories.jsonl', recursive=True))
schema_files = sorted(glob.glob('/kaggle/input/**/tool_schemas.json', recursive=True))
assert traj_files, 'attach the oracle-trajectories notebook output'
rows = [json.loads(l) for l in open(traj_files[0])]
recs = {r['instance_id']: r for r in rows if r.get('instance_id') and r.get('messages')}
good = [r for r in recs.values() if r.get('resolved') and r.get('gold_resolved')]
train_rows = [r for r in good if r['instance_id'] not in HOLDOUT]
print('trajectories', len(rows), 'validated', len(good), 'train (holdout removed)', len(train_rows))

if schema_files:
    TOOLS = json.load(open(schema_files[0]))
else:
    TOOLS = next((r for r in rows if r.get('instance_id') == 'tool_schemas'), {}).get('value') or []

def fix_schema(s):
    """Gemma's template wants plain JSON schema: turn any_of [T, null] into nullable T."""
    if isinstance(s, dict):
        if 'any_of' in s or 'anyOf' in s:
            opts = [fix_schema(o) for o in (s.get('any_of') or s.get('anyOf')) if o.get('type') not in ('null', 'NULL')]
            base = dict(opts[0]) if opts else {'type': 'string'}
            base['nullable'] = True
            for k, v in s.items():
                if k not in ('any_of', 'anyOf'):
                    base[k] = fix_schema(v)
            return base
        return {k: fix_schema(v) for k, v in s.items()}
    if isinstance(s, list):
        return [fix_schema(x) for x in s]
    if isinstance(s, str) and s.isupper():
        return s.lower()
    return s

TOOLS = [{'type': 'function', 'function': fix_schema(t)} for t in TOOLS]
print('tools', [t['function'].get('name') for t in TOOLS])

def to_hf(msgs):
    """Harness messages -> HF chat format. The oracle's short thought becomes the thinking
    channel (the Gemma 4 template keeps reasoning for every turn after the last user turn,
    and the scorer serves with thinking enabled)."""
    out = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    for m in msgs:
        if m['role'] == 'assistant' and m.get('tool_calls'):
            out.append({'role': 'assistant', 'content': '', 'reasoning': (m.get('content') or '').strip() or None,
                        'tool_calls': [{'type': 'function', 'function': {'name': c['name'], 'arguments': c['arguments']}}
                                       for c in m['tool_calls']]})
        elif m['role'] == 'tool':
            out.append({'role': 'tool', 'name': m.get('name', ''), 'content': m['content']})
        else:
            out.append({'role': m['role'], 'content': m['content']})
    return out
'''

MODEL = r'''
from unsloth import FastModel
import torch
cands = sorted(Path(p).parent for p in glob.glob('/kaggle/input/**/config.json', recursive=True)
               if 'qat-q4_0-unquantized' in p and '31b' in p.lower())
assert cands, 'attach model google/gemma-4/transformers/gemma-4-31b-it-qat-q4_0-unquantized'
MODEL_DIR = str(cands[0])
print('base', MODEL_DIR)
MAX_LEN = 8192
model, tokenizer = FastModel.from_pretrained(model_name=MODEL_DIR, max_seq_length=MAX_LEN, load_in_4bit=True,
                                             full_finetuning=False, device_map='balanced', use_exact_model_name=True)
tok = getattr(tokenizer, 'tokenizer', tokenizer)
model = FastModel.get_peft_model(model, finetune_vision_layers=False, finetune_language_layers=True,
                                 finetune_attention_modules=True, finetune_mlp_modules=True,
                                 r=16, lora_alpha=16, lora_dropout=0, bias='none', random_state=SEED,
                                 use_gradient_checkpointing='unsloth')

def render(msgs, gen=False):
    return tokenizer.apply_chat_template(msgs, tools=TOOLS, tokenize=False, add_generation_prompt=gen,
                                         enable_thinking=True)

def build_example(rec):
    """Token ids + labels; only characters the model itself must produce are trained
    (thinking, tool calls and the <|tool_response> stop marker), never turn headers,
    the issue, or tool outputs."""
    msgs = to_hf(rec['messages'])
    spans, prev = [], render(msgs[:1])
    for i in range(2, len(msgs) + 1):
        text = render(msgs[:i])
        if not text.startswith(prev):
            return None
        if msgs[i - 1]['role'] == 'assistant':
            start = len(prev)
            if text.startswith('<|turn>model\n', start):
                start += len('<|turn>model\n')
            spans.append((start, len(text)))
        prev = text
    full = prev
    enc = tok(full, add_special_tokens=False, return_offsets_mapping=True)
    ids, labels = enc['input_ids'], []
    j = 0
    for (a, b), t in zip(enc['offset_mapping'], ids):
        while j < len(spans) and spans[j][1] <= a:
            j += 1
        inside = j < len(spans) and spans[j][0] <= a < spans[j][1]
        labels.append(t if inside else -100)
    if len(ids) > MAX_LEN or not any(l != -100 for l in labels):
        return None
    return {'input_ids': ids, 'attention_mask': [1] * len(ids), 'labels': labels}

examples, skipped = [], []
for r in train_rows:
    ex = build_example(r)
    (examples.append(ex) if ex else skipped.append(r['instance_id']))
lens = sorted(len(e['input_ids']) for e in examples)
print('examples', len(examples), 'skipped', len(skipped), 'len median', lens[len(lens)//2] if lens else None,
      'max', lens[-1] if lens else None)
assert len(examples) >= 20
print(render(to_hf(train_rows[0]['messages'])[:3])[:3000])
'''

TRAIN = r'''
from datasets import Dataset
from trl import SFTConfig, SFTTrainer
random.shuffle(examples)
ds = Dataset.from_list(examples)
trainer = SFTTrainer(model=model, tokenizer=tokenizer, train_dataset=ds,
    args=SFTConfig(output_dir='/kaggle/working/ckpt', per_device_train_batch_size=1, gradient_accumulation_steps=4,
                   num_train_epochs=2, learning_rate=1e-4, lr_scheduler_type='cosine', warmup_ratio=0.05,
                   optim='adamw_8bit', logging_steps=1, save_strategy='no', report_to='none', seed=SEED,
                   max_length=MAX_LEN, bf16=False, fp16=True, dataset_kwargs={'skip_prepare_dataset': True},
                   remove_unused_columns=False))
for cb in tuple(trainer.callback_handler.callbacks):
    if type(cb).__name__ == 'NotebookProgressCallback':
        trainer.remove_callback(type(cb))
t0 = time.time()
stats = trainer.train()
print('train loss', stats.training_loss, 'seconds', round(time.time() - t0))
'''

SAVE = r'''
import zipfile
from safetensors import safe_open
from safetensors.torch import save_file
OUT = Path('/kaggle/working/agent_lora'); shutil.rmtree(OUT, ignore_errors=True)
for rel, text in AGENT_FILES.items():
    p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
y = (OUT / 'agent.yaml').read_text()
if 'adapter:' not in y:
    y = y.replace('model: gemma-4-31b-it-qat-w4a16-ct\n', 'model: gemma-4-31b-it-qat-w4a16-ct\nadapter: main_lora\n')
(OUT / 'agent.yaml').write_text(y)
tmp = Path('/kaggle/working/raw_adapter'); shutil.rmtree(tmp, ignore_errors=True)
model.save_pretrained(tmp, safe_serialization=True)
ADP = OUT / 'adapters' / 'main_lora'; ADP.mkdir(parents=True)
pat = re.compile(r'^base_model\.model\.model\.language_model\.layers\.\d+\.(self_attn|mlp)\.(q|k|v|o|gate|up|down)_proj\.lora_[AB]\.weight$')
kept, dropped = {}, []
with safe_open(str(tmp / 'adapter_model.safetensors'), framework='pt', device='cpu') as f:
    for k in f.keys():
        k2 = k
        if not k2.startswith('base_model.model.model.language_model.') and k2.startswith('base_model.model.language_model.'):
            k2 = k2.replace('base_model.model.language_model.', 'base_model.model.model.language_model.', 1)
        if pat.match(k2):
            kept[k2] = f.get_tensor(k).to(torch.bfloat16).contiguous()
        else:
            dropped.append(k)
assert len(kept) > 200, (len(kept), dropped[:5])
save_file(kept, str(ADP / 'adapter_model.safetensors'))
cfg = json.loads((tmp / 'adapter_config.json').read_text())
targets = sorted({re.search(r'\.(\w+_proj)\.lora', k).group(1) for k in kept})
cfg.update(base_model_name_or_path='google/gemma-4-31b-it-qat-w4a16-ct', target_modules=targets,
           modules_to_save=None, inference_mode=True, task_type='CAUSAL_LM')
for k in ('target_parameters', 'layers_to_transform', 'exclude_modules'):
    cfg.pop(k, None)
(ADP / 'adapter_config.json').write_text(json.dumps(cfg, indent=2))
print('adapter tensors', len(kept), 'dropped', len(dropped), 'targets', targets, 'r', cfg.get('r'),
      'MB', round((ADP / 'adapter_model.safetensors').stat().st_size / 1e6, 1))
from adk_submission import validate_directory, discover_adapters, discover_declared_models
validate_directory(OUT)
print('declared', sorted(discover_declared_models(OUT)), 'adapters', discover_adapters(str(OUT), adapter_extensions=frozenset({'.safetensors'})))
with zipfile.ZipFile('/kaggle/working/submission.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(OUT).as_posix())
print('submission.zip', round(Path('/kaggle/working/submission.zip').stat().st_size / 1e6, 1), 'MB')
shutil.rmtree(tmp, ignore_errors=True); shutil.rmtree('/kaggle/working/ckpt', ignore_errors=True)
json.dump({'train_ids': sorted(r['instance_id'] for r in train_rows), 'holdout': sorted(HOLDOUT),
           'examples': len(examples), 'skipped': skipped, 'train_loss': stats.training_loss},
          open('/kaggle/working/train_manifest.json', 'w'), indent=1)
'''


def md(t):
    return {"cell_type": "markdown", "metadata": {}, "source": t}


def code(t):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-file", type=Path, help="JSON list of instance ids to keep out of training")
    ap.add_argument("--slug", default="gemma4-lora-train")
    ap.add_argument("--user", default="danielaijdkx")
    ap.add_argument("--oracle-kernel", default="danielaijdkx/gemma4-oracle-trajectories")
    a = ap.parse_args()
    holdout = json.loads(a.holdout_file.read_text()) if a.holdout_file else []
    files = {str(p.relative_to(AGENT)): p.read_text() for p in sorted(AGENT.rglob("*")) if p.is_file()}
    system = files["prompts/system.md"]
    head = ("HOLDOUT = set(" + json.dumps(holdout) + ")\nSYSTEM_PROMPT = " + json.dumps(system)
            + "\nAGENT_FILES = " + json.dumps(files, indent=1) + "\n")
    nb = {"cells": [
        md("# LoRA on validated trajectories (Gemma 4 31B QAT)\n\nTrajectories: copy of Kevin Diaz Cordova's "
           "oracle-trajectory notebook (Apache 2.0). Training recipe adapted from Den Pugovkin's QLoRA study. "
           "Adapter naming per Dmitrii Gluzdov's serving verification kit. Agent: Budget-Fit Single Agent "
           "(verracodeguacas)."),
        code(SETUP), code(head + DATA), code(MODEL), code(TRAIN), code(SAVE)],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    meta = {"id": f"{a.user}/{a.slug}", "title": "Gemma4 LoRA Train", "code_file": f"{a.slug}.ipynb",
            "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": True,
            "enable_tpu": False, "enable_internet": True,
            "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
            "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": [a.oracle_kernel],
            "model_sources": ["google/gemma-4/Transformers/gemma-4-31b-it-qat-q4_0-unquantized/2"],
            "machine_shape": "NvidiaTeslaT4"}
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
    print("holdout", len(holdout))


if __name__ == "__main__":
    main()
