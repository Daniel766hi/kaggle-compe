"""Build the offline L4x4 LoRA training notebook (no Unsloth, no Internet).

    python gemma4_lora/build_train_l4.py --out <kernel dir> --holdout-file gemma4_lora/holdout_pilot24.json

Why L4: on T4 Gemma 4 is forced to float32 and the trajectories (median ~6.5k tokens, ~4k of
fixed prompt) do not fit. L4 runs bf16. Packages: the official wheelhouse (transformers,
bitsandbytes) plus peft/accelerate wheels from the gemma4-offline-wheels notebook.
Data handling, masking and adapter export are shared with build_train_notebook.py.
"""

import argparse
import json
from pathlib import Path

import build_train_notebook as base

SETUP = r'''
import glob, json, os, re, shutil, subprocess, sys, time, hashlib, random, math
from pathlib import Path
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
WH = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WH.exists():
    WH = Path('/kaggle/input/gemma-4-developer-agent-wheelhouse')
want = ['transformers-', 'bitsandbytes-', 'safetensors-', 'compressed_tensors-', 'adk_submission-', 'google_adk-',
        'adk_eval_core-', 'swegemma-', 'tokenizers-', 'huggingface_hub-', 'google_genai-']
whl = [str(w) for w in WH.glob('*.whl') if any(w.name.startswith(p) for p in want)]
extra = sorted(w for w in glob.glob('/kaggle/input/**/wheels/*.whl', recursive=True) if 'gemma4-offline-wheels' in w)
print('wheelhouse picks', sorted(Path(w).name for w in whl)); print('extra', [Path(w).name for w in extra])
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *whl, *extra], check=True)
import torch, transformers, peft, accelerate, bitsandbytes
print('torch', torch.__version__, 'transformers', transformers.__version__, 'peft', peft.__version__,
      'bnb', bitsandbytes.__version__, 'gpus', torch.cuda.device_count(), torch.cuda.get_device_name(0))
'''

MODEL = r'''
from transformers import AutoTokenizer, AutoConfig, BitsAndBytesConfig
import transformers as T
cands = sorted(Path(p).parent for p in glob.glob('/kaggle/input/**/config.json', recursive=True)
               if 'qat-q4_0-unquantized' in p and '31b' in p.lower())
assert cands, 'attach model gemma-4-31b-it-qat-q4_0-unquantized'
MODEL_DIR = str(cands[0]); print('base', MODEL_DIR)
MAX_LEN = 8192
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR); tok = tokenizer
cfg = AutoConfig.from_pretrained(MODEL_DIR)
cls = getattr(T, cfg.architectures[0])
print('architecture', cfg.architectures[0])
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_compute_dtype=torch.bfloat16,
                         bnb_4bit_use_double_quant=True,
                         llm_int8_skip_modules=['lm_head', 'vision_tower', 'audio_tower', 'embed_vision', 'embed_audio',
                                                'multi_modal_projector'])
n = torch.cuda.device_count()
model = cls.from_pretrained(MODEL_DIR, quantization_config=bnb, dtype=torch.bfloat16, device_map='auto',
                            max_memory={i: '20GiB' for i in range(n)}, attn_implementation='sdpa')
print('loaded; mem GiB', [round(torch.cuda.memory_allocated(i) / 2**30, 1) for i in range(n)])
from peft import LoraConfig, get_peft_model
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False})
model.enable_input_require_grads()
model.config.use_cache = False
lcfg = LoraConfig(r=16, lora_alpha=16, lora_dropout=0.0, bias='none', task_type='CAUSAL_LM',
                  target_modules=r'.*language_model.*\.(q_proj|k_proj|v_proj|o_proj|gate_proj|up_proj|down_proj)')
model = get_peft_model(model, lcfg)
model.print_trainable_parameters()
''' + base.MODEL[base.MODEL.index('def render'):base.MODEL.index("assert len(examples) >= 20")] + r'''
assert len(examples) >= 20, len(examples)
'''

TRAIN = r'''
inner = model.base_model.model           # Gemma4ForConditionalGeneration
backbone = inner.model                   # returns hidden states
lm_head = inner.lm_head
cap = getattr(cfg.get_text_config(), 'final_logit_softcapping', None)
dev0 = inner.get_input_embeddings().weight.device
params = [p for p in model.parameters() if p.requires_grad]
opt = torch.optim.AdamW(params, lr=1e-4, weight_decay=0.0, betas=(0.9, 0.99))
EPOCHS, ACCUM, WARM = 2, 4, 2
order = [i for _ in range(EPOCHS) for i in random.sample(range(len(examples)), len(examples))]
total = math.ceil(len(order) / ACCUM)
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / WARM) * 0.5 * (1 + math.cos(math.pi * min(s, total) / total)))
model.train(); t0 = time.time(); losses = []; step = 0; TIME_LIMIT = 9 * 3600
for k, idx in enumerate(order):
    ex = examples[idx]
    ids = torch.tensor([ex['input_ids']], device=dev0)
    lab = torch.tensor(ex['labels'], device=dev0)
    h = backbone(input_ids=ids, attention_mask=torch.ones_like(ids)).last_hidden_state[0]
    sel = (lab[1:] != -100).nonzero(as_tuple=True)[0]
    hs = h[:-1].index_select(0, sel.to(h.device))
    logits = lm_head(hs.to(lm_head.weight.device)).float()
    if cap:
        logits = torch.tanh(logits / cap) * cap
    loss = torch.nn.functional.cross_entropy(logits, lab[1:].index_select(0, sel).to(logits.device))
    (loss / ACCUM).backward(); losses.append(loss.item())
    if (k + 1) % ACCUM == 0 or k == len(order) - 1:
        torch.nn.utils.clip_grad_norm_(params, 1.0); opt.step(); sched.step(); opt.zero_grad(set_to_none=True); step += 1
        print(f'step {step}/{total} loss {sum(losses[-ACCUM:]) / len(losses[-ACCUM:]):.4f} len {len(ex["input_ids"])} '
              f'elapsed {time.time() - t0:.0f}s mem {[round(torch.cuda.max_memory_allocated(i) / 2**30, 1) for i in range(n)]}', flush=True)
    if time.time() - t0 > TIME_LIMIT:
        print('time limit reached; stopping early'); break
train_loss = sum(losses) / max(len(losses), 1)
print('train loss', train_loss, 'first-epoch', sum(losses[:len(examples)]) / max(min(len(losses), len(examples)), 1),
      'last 20', sum(losses[-20:]) / max(len(losses[-20:]), 1), 'seconds', round(time.time() - t0))
model.eval()
'''

SAVE = base.SAVE.replace("'train_loss': stats.training_loss", "'train_loss': train_loss")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-file", type=Path)
    ap.add_argument("--slug", default="gemma4-lora-train-l4")
    ap.add_argument("--user", default="danielaijdkx")
    a = ap.parse_args()
    holdout = json.loads(a.holdout_file.read_text()) if a.holdout_file else []
    files = {str(p.relative_to(base.AGENT)): p.read_text() for p in sorted(base.AGENT.rglob("*")) if p.is_file()}
    head = ("HOLDOUT = set(" + json.dumps(holdout) + ")\nSYSTEM_PROMPT = " + json.dumps(files["prompts/system.md"])
            + "\nAGENT_FILES = " + json.dumps(files, indent=1) + "\n")
    nb = {"cells": [base.md("# LoRA on validated trajectories, Gemma 4 31B QAT, offline L4x4\n\nCredits as in the T4 "
                            "notebook (Kevin Diaz Cordova, Den Pugovkin, Dmitrii Gluzdov, verracodeguacas)."),
                    base.code(SETUP), base.code(head + base.DATA), base.code(MODEL), base.code(TRAIN), base.code(SAVE)],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    (a.out / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{a.user}/{a.slug}", "title": "Gemma4 LoRA Train L4", "code_file": f"{a.slug}.ipynb", "language": "python",
        "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_tpu": False, "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"], "competition_sources": ["gemma-4-developer-agent"],
        "kernel_sources": ["danielaijdkx/gemma4-oracle-trajectories", "danielaijdkx/gemma4-offline-wheels"],
        "model_sources": ["google/gemma-4/Transformers/gemma-4-31b-it-qat-q4_0-unquantized/2"],
        "machine_shape": "NvidiaL4",
        "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"}, indent=1))
    print("holdout", len(holdout))


if __name__ == "__main__":
    main()
