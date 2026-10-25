"""CPU notebook (no GPU quota): dry-run the RFT data on the real collected runs, and analyse failures.

    python gemma4_lora/build_rft_dryrun.py --out <kernel dir> --holdout-file gemma4_lora/holdout_pilot24.json

1. Builds the RFT training examples exactly as build_train_rft.py does (tokenizer only, no model) and
   prints how many there are, their lengths before/after the 16k cut, and the trained share.
2. For every collected run: did the edited files match the files the reference patch edits, were tests
   run after the last edit, how did the run end. Splits wrong-patch failures into "wrong place" and
   "right place, wrong fix".
"""

import argparse
import json
from pathlib import Path

import build_train_notebook as base
import build_train_rft as rft

SETUP = r'''
import glob, json, os, re, shutil, subprocess, sys, time, random, math, collections, statistics
from pathlib import Path
WH = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WH.exists():
    WH = Path('/kaggle/input/gemma-4-developer-agent-wheelhouse')
want = ['transformers-', 'tokenizers-', 'huggingface_hub-', 'safetensors-']
whl = [str(w) for w in WH.glob('*.whl') if any(w.name.startswith(p) for p in want)]
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *whl], check=True)
import transformers; print('transformers', transformers.__version__)
'''

TOKENIZE = r'''
from transformers import AutoTokenizer
cands = sorted(Path(p).parent for p in glob.glob('/kaggle/input/**/tokenizer_config.json', recursive=True)
               if 'qat-q4_0-unquantized' in p and '31b' in p.lower())
assert cands, 'attach model gemma-4-31b-it-qat-q4_0-unquantized'
tokenizer = tok = AutoTokenizer.from_pretrained(str(cands[0]))
''' + base.MODEL[base.MODEL.index('def render'):base.MODEL.index('examples, skipped = []')] + r'''
MAX_LEN = 10**9
full = [build_example(r) for r in train_rows]
L = sorted(len(e['input_ids']) for e in full if e)
print('examples', sum(e is not None for e in full), 'of', len(train_rows))
print('full length deciles', [L[int(q * (len(L) - 1))] for q in (0, .1, .25, .5, .75, .9, 1)])
print('longer than 16384:', sum(x > 16384 for x in L), '| longer than 12288:', sum(x > 12288 for x in L))
tr = [sum(l != -100 for l in e['labels']) / len(e['labels']) for e in full if e]
print('trained token share median', round(statistics.median(tr), 3))
cut = [e for e in full if e and len(e['input_ids']) > 16384]
lost = [sum(l != -100 for l in e['labels'][16384:]) / max(sum(l != -100 for l in e['labels']), 1) for e in cut]
print('share of trained tokens lost to the 16k cut, among cut runs:', [round(x, 2) for x in lost])
print('total tokens after cut', sum(min(x, 16384) for x in L))
print(render(train_rows[0]['messages'][:4])[-1500:])
'''

ANALYSE = r'''
tasks = {}
for p in glob.glob('/kaggle/input/**/tasks.jsonl', recursive=True):
    for l in open(p):
        t = json.loads(l); tasks[t['instance_id']] = t
    break
def files_of(patch):
    # reference patches have only ---/+++ headers, agent patches also have diff --git
    return {m for m in re.findall(r'^(?:\+\+\+ b/|--- a/)(\S+)', patch or '', re.M)}
def is_test(f):
    n = f.split('/')[-1]
    return n.startswith('test_') or n.endswith('_test.py') or '/tests/' in '/' + f or n == 'conftest.py'
out = []
for r in runs:
    row = r['row']; t = tasks.get(row['instance_id'], {})
    gold = {f for f in files_of(t.get('patch')) if not is_test(f)}
    mine = {f for f in files_of(r.get('patch')) if not is_test(f)}
    seq = row.get('tools') or []
    last_edit = max([i for i, x in enumerate(seq) if x in ('edit_file', 'write_file')], default=-1)
    tr = r.get('trace') if isinstance(r.get('trace'), list) else []
    cmds = [e.get('args', {}).get('command', '') for e in tr if e.get('type') == 'tool_call' and e.get('tool') == 'run_command']
    tests_after = any(x == 'run_command' for x in seq[last_edit + 1:]) if last_edit >= 0 else False
    kind = ('resolved' if row.get('resolved') else 'no_patch' if not row.get('patch_chars') else
            'wrong_place' if gold and not (mine & gold) else 'right_place_wrong_fix')
    out.append(dict(kind=kind, calls=row.get('tool_calls') or 0, hit=(row.get('tool_calls') or 0) >= 27,
                    tests_after=tests_after, pytest=sum('pytest' in c for c in cmds),
                    files_extra=len(mine - gold), files_gold=len(gold), overlap=bool(mine & gold),
                    repro=sum(('python -c' in c or 'reproduce' in c or 'repro' in c) for c in cmds),
                    n_submit=seq.count('submit_patch'), err=(row.get('error') or '')[:40]))
by = collections.defaultdict(list)
for o in out:
    by[o['kind']].append(o)
for k, v in sorted(by.items()):
    f = lambda key: round(sum(o[key] for o in v) / len(v), 2)
    print(f'{k:22s} n={len(v):3d} calls={f("calls")} hit28={f("hit")} tests_after_last_edit={f("tests_after")} '
          f'pytest_runs={f("pytest")} repro={f("repro")} extra_files={f("files_extra")} submits={f("n_submit")}')
print('file-level localisation among runs with a patch:',
      sum(o['overlap'] for o in out if o['kind'] != 'no_patch'), '/', sum(o['kind'] != 'no_patch' for o in out))
# command patterns: what the agent spends calls on
allc = [e.get('args', {}).get('command', '') for r in runs for e in (r.get('trace') if isinstance(r.get('trace'), list) else [])
        if e.get('type') == 'tool_call' and e.get('tool') == 'run_command']
heads = collections.Counter(re.sub(r'\s+', ' ', c).strip().split(' ')[0] if c else '' for c in allc)
print('run_command heads', heads.most_common(15))
print('pytest share of commands', round(sum('pytest' in c for c in allc) / max(len(allc), 1), 2))
# what the tool returns most often when a call is wasted
errs = collections.Counter()
for r in runs:
    for e in (r.get('trace') if isinstance(r.get('trace'), list) else []):
        if e.get('type') == 'tool_response':
            res = (e.get('result') or '')[:200].lower()
            for key in ('not found', 'no match', 'error', 'traceback', 'failed', 'timed out', 'budget'):
                if key in res:
                    errs[(e.get('tool'), key)] += 1
print('tool responses containing', errs.most_common(15))
json.dump(out, open('/kaggle/working/run_analysis.json', 'w'))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout-file", type=Path)
    ap.add_argument("--slug", default="gemma4-rft-dryrun")
    ap.add_argument("--user", default="danielaijdkx")
    a = ap.parse_args()
    holdout = json.loads(a.holdout_file.read_text()) if a.holdout_file else []
    files = {str(p.relative_to(base.AGENT)): p.read_text() for p in sorted(base.AGENT.rglob("*")) if p.is_file()}
    import yaml
    ev = yaml.safe_load(files["eval_config.yaml"])["evaluation"]
    head = ("HOLDOUT = set(" + json.dumps(holdout) + ")\nSYSTEM_PROMPT = " + json.dumps(files["prompts/system.md"])
            + "\nPER_TASK = 2\nDEPLOYED_EVAL = " + json.dumps(ev) + "\n")
    nb = {"cells": [base.md("# RFT data dry run and failure analysis (CPU)\n\n" + __doc__.split("\n\n", 2)[2]),
                    base.code(SETUP), base.code(head + rft.DATA), base.code(TOKENIZE), base.code(ANALYSE)],
          "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    (a.out / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{a.user}/{a.slug}", "title": a.slug.replace("-", " ").title(), "code_file": f"{a.slug}.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": False, "enable_tpu": False,
        "enable_internet": False, "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"],
        "kernel_sources": ["danielaijdkx/gemma4-collect", "danielaijdkx/gemma4-oracle-trajectories"],
        "model_sources": ["google/gemma-4/Transformers/gemma-4-31b-it-qat-q4_0-unquantized/2"],
        "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"}, indent=1))


if __name__ == "__main__":
    main()
