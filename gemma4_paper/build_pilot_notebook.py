"""Build the Kaggle notebook for the end-to-end pilot: baseline vs. baseline + locate-code skill.

    python gemma4_paper/build_pilot_notebook.py --tasks <tasks.jsonl> --out <kernel dir>

The two agent configs under gemma4_paper/agent/ are embedded in the notebook as text, so the
notebook needs only the competition data, the official wheelhouse and the Gemma 4 model.
Task subset (fixed before any run): tasks with a node label in the localization study,
ordered by sha256(instance_id), taking the first 12 fastapi, 9 rich, 2 requests, 1 httpx.
Each task runs A then B back to back, and results are appended to a JSONL file after
every run so a session timeout still leaves complete pairs.
"""

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
QUOTA = {"fastapi/fastapi": 12, "Textualize/rich": 9, "psf/requests": 2, "encode/httpx": 1}
# Tasks without a gold node label in the localization study (labels.json); excluded so the
# pilot and the retrieval study share one task population.
NO_LABEL = {
    "fastapi_15661", "fastapi_15023", "fastapi_14492", "fastapi_14487", "fastapi_14791",
    "fastapi_14303", "fastapi_13537", "fastapi_11194", "requests_6629", "requests_6592",
    "rich_3278", "rich_3105",
}


def pick_tasks(tasks_path: Path, labels_path: Path | None) -> list[str]:
    tasks = [json.loads(l) for l in tasks_path.open()]
    excluded = set(NO_LABEL)
    if labels_path and labels_path.exists():
        excluded = {x["instance_id"] for x in json.loads(labels_path.read_text()) if not x["gold_nodes"]}
    tasks = [t for t in tasks if t["instance_id"] not in excluded]
    tasks.sort(key=lambda t: hashlib.sha256(t["instance_id"].encode()).hexdigest())
    chosen, left = [], dict(QUOTA)
    for t in tasks:
        if left.get(t["repo"], 0) > 0:
            chosen.append(t["instance_id"])
            left[t["repo"]] -= 1
    return chosen


def agent_files(name: str) -> dict[str, str]:
    root = HERE / "agent" / name
    return {str(p.relative_to(root)): p.read_text() for p in sorted(root.rglob("*")) if p.is_file()}


SETUP = r'''
import glob, importlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

os.environ['LITELLM_LOCAL_MODEL_COST_MAP'] = 'True'
os.environ['TRANSFORMERS_NO_TF'] = '1'
os.environ['VLLM_WORKER_MULTIPROC_METHOD'] = 'spawn'
os.environ['VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS'] = '1'
os.environ['VLLM_ENGINE_READY_TIMEOUT_S'] = '1200'
os.environ['VLLM_NO_USAGE_STATS'] = '1'
os.environ['OTEL_SDK_DISABLED'] = 'true'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'

WHEELHOUSE_DIR = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WHEELHOUSE_DIR.exists():
    WHEELHOUSE_DIR = Path('/kaggle/input/gemma-4-developer-agent-wheelhouse')
for pth_pattern in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth',
                    '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pth_pattern):
        try:
            os.unlink(pth)
        except OSError:
            pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower():
        continue
    target = tmp_whl / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not target.exists():
        os.symlink(w, target)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels], check=True)
importlib.invalidate_caches()
print('installed', len(wheels), 'wheels')
'''

WRITE_AGENTS = r'''
WORK = Path('/kaggle/working')
AGENTS = {}
for name, files in AGENT_FILES.items():
    d = WORK / 'agents' / name
    if d.exists():
        shutil.rmtree(d)
    for rel, text in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    AGENTS[name] = d
print({k: sorted(str(p.relative_to(v)) for p in v.rglob('*') if p.is_file()) for k, v in AGENTS.items()})
'''

SERVER = r'''
import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
from swegemma.models.discovery import validate_single_declared_model
litellm.drop_params = True

DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
if not DATA_DIR.exists():
    DATA_DIR = Path('/kaggle/input/gemma-4-developer-agent')
TARGET_MODEL_NAME = 'gemma-4-31b-it-qat-w4a16-ct'
cands = sorted(glob.glob('/kaggle/input/**/gemma-4-31b-it-qat-w4a16-ct/**/config.json', recursive=True))
MODEL_PATH = Path(cands[0]).parent
print('model at', MODEL_PATH)

declared = {n: validate_single_declared_model(d) for n, d in AGENTS.items()}
assert set(declared.values()) == {TARGET_MODEL_NAME}, declared
adapters = discover_adapters(str(AGENTS['baseline']), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
gpu_count = torch.cuda.device_count()
tp_size = 4 if gpu_count >= 4 else (2 if gpu_count >= 2 else 1)
vllm_cfg = VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4',
    reasoning_parser='gemma4', max_model_len=32768,
    dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto',
    gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=True,
    max_loras=8, max_lora_rank=128, tensor_parallel_size=tp_size, startup_timeout=60 * 20,
)
server = VllmServer(vllm_cfg, adapter_manifest=adapters)
server.start()
models = server.create_model_registry(aliases=[TARGET_MODEL_NAME], model_prefix='openai/', api_key='EMPTY')
print('vLLM up, tp =', tp_size, 'gpus =', gpu_count)
'''

RUN = r'''
import asyncio, concurrent.futures, yaml
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig, build_submission_limits
from swegemma.evaluate import Evaluator
from swegemma.models import load_tasks

def run_sync(fn):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(fn())).result()
    return asyncio.run(fn())

TASKS_PATH = DATA_DIR / 'tasks.jsonl'
all_tasks = {t.instance_id: t for t in load_tasks(TASKS_PATH)}
limits, gen_constraints = build_submission_limits()
evaluators = {}
for name, d in AGENTS.items():
    ev = yaml.safe_load((d / 'eval_config.yaml').read_text())['evaluation']
    cfg = EvalConfig(
        tasks_path=TASKS_PATH, snapshots_dir=DATA_DIR / 'snapshots', results_dir=WORK / 'results' / name,
        submission_dir=d, models=models, sandbox='subprocess',
        timeout_seconds=int(ev['timeout_seconds']), max_time_minutes=float(ev['max_time_minutes']),
        max_tool_calls=int(ev['max_tool_calls']), max_turns=int(ev['max_turns']),
        limits=limits, generation_constraints=gen_constraints, adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                        token_threshold=14336, event_retention_size=5),
        graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'),
        wheels_dir=DATA_DIR / 'wheels', verbose=False,
    )
    evaluators[name] = Evaluator(cfg)

OUT = WORK / 'pilot_results.jsonl'
done = set()
if OUT.exists():
    done = {(r['config'], r['instance_id']) for r in map(json.loads, OUT.read_text().splitlines())}
T0 = time.time()
STOP_AFTER_S = 11.0 * 3600  # leave room to save outputs inside a 12 h session

def skill_calls(res):
    p = getattr(res, 'trace_path', None)
    try:
        txt = Path(p).read_text() if p else ''
    except OSError:
        txt = ''
    return txt.count('run_skill_script'), txt.count('search_similar_code')

for idx, iid in enumerate(PILOT_TASKS, start=1):
    for name in ('baseline', 'locate'):
        if (name, iid) in done:
            continue
        if time.time() - T0 > STOP_AFTER_S:
            break
        t = all_tasks[iid]
        t1 = time.time()
        try:
            res = run_sync(lambda: evaluators[name].evaluate_task(task=t, task_index=idx, total_tasks=len(PILOT_TASKS)))
            sk, sim = skill_calls(res)
            row = dict(config=name, instance_id=iid, repo=t.repo, resolved=bool(res.resolved),
                       tool_calls=res.tool_calls, duration_s=round(time.time() - t1, 1),
                       patch_chars=len(res.agent_patch or ''), test_exit_code=res.test_exit_code,
                       skill_mentions=sk, similar_code_mentions=sim,
                       error=getattr(res, 'error_message', None))
        except Exception as e:
            row = dict(config=name, instance_id=iid, repo=t.repo, resolved=False, error=repr(e)[:500],
                       duration_s=round(time.time() - t1, 1))
        with OUT.open('a') as f:
            f.write(json.dumps(row) + '\n')
        print(idx, name, iid, row.get('resolved'), row.get('tool_calls'), row.get('duration_s'), row.get('error'), flush=True)
'''

SUMMARY = r'''
rows = [json.loads(l) for l in OUT.read_text().splitlines()]
by = {}
for r in rows:
    by.setdefault(r['instance_id'], {})[r['config']] = r
pairs = [v for v in by.values() if 'baseline' in v and 'locate' in v]
a = sum(v['baseline']['resolved'] for v in pairs); b = sum(v['locate']['resolved'] for v in pairs)
only_a = sum(v['baseline']['resolved'] and not v['locate']['resolved'] for v in pairs)
only_b = sum(v['locate']['resolved'] and not v['baseline']['resolved'] for v in pairs)
summary = dict(pairs=len(pairs), baseline_resolved=a, locate_resolved=b, only_baseline=only_a, only_locate=only_b,
               locate_used_skill=sum(v['locate'].get('skill_mentions', 0) > 0 for v in pairs))
print(json.dumps(summary, indent=1))
(WORK / 'pilot_summary.json').write_text(json.dumps(summary, indent=1))
for name in AGENTS:
    shutil.make_archive(str(WORK / f'results_{name}'), 'zip', root_dir=WORK / 'results' / name)
'''

INTRO = """# Query-gap pilot: does a BM25 locate skill help Gemma 4 fix more bugs?

Paired pilot on 24 development tasks (fixed before running). **A** is the public Budget-Fit
Single Agent bundle (0.18 public LB; credit: verracodeguacas) unchanged. **B** is the same bundle
plus a `locate-code` skill (BM25 over the repository's functions, standard library only) and one
prompt line asking the agent to run it first. Everything else (sampling, budgets, tools) is identical.
Each task runs A then B back to back; results are appended to `pilot_results.jsonl` after every run.
"""


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--labels", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--slug", default="gemma4-query-gap-pilot")
    ap.add_argument("--user", default="danielaijdkx")
    a = ap.parse_args()
    pilot = pick_tasks(a.tasks, a.labels)
    files = {"baseline": agent_files("baseline"), "locate": agent_files("locate")}
    nb = {
        "cells": [
            md(INTRO),
            code(SETUP),
            code("AGENT_FILES = " + json.dumps(files, indent=1) + "\nPILOT_TASKS = " + json.dumps(pilot)
                 + "\nprint(len(PILOT_TASKS), 'tasks')\n" + WRITE_AGENTS),
            code(SERVER),
            code(RUN),
            code(SUMMARY),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    meta = {
        "id": f"{a.user}/{a.slug}",
        "title": "Gemma4 Query Gap Pilot",
        "code_file": f"{a.slug}.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_tpu": False,
        "enable_internet": False,
        "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"],
        "kernel_sources": [],
        "model_sources": ["google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2"],
        "machine_shape": "NvidiaL4",
        # same image as the official getting-started notebook (vLLM + harness wheels tested on it)
        "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461",
    }
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
    print("pilot tasks:", pilot)


if __name__ == "__main__":
    main()
