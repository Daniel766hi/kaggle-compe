"""Build the L4x4 notebook that runs the agent itself on development tasks and keeps every trajectory.

    python gemma4_lora/build_collect_notebook.py --tasks <tasks.jsonl> --out <kernel dir> \
        --exclude-file gemma4_lora/holdout_pilot24.json --repeats 2 --concurrency 4

Purpose: (1) training data for rejection-sampling fine-tuning (the agent's own resolved runs, no
privileged information, unlike the scripted oracle trajectories) and (2) an accurate measurement of
the current agent, with the test-only packages installed. Runs execute concurrently against one vLLM
server; repeat 1 of every task is scheduled before repeat 2. Each run is saved to
/kaggle/working/collected/<config>__<task>__r<k>.json with the exact first user prompt and the trace.
With --max-time-minutes the prompt's "Time allowance" line shows that value; rewrite it to the deployed
value when turning runs into training examples.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gemma4_paper"))
import build_pilot_notebook as pilot  # noqa: E402

# The saved test-dependency wheels were downloaded with their dependencies, so installing all of them
# tries to upgrade pinned packages (pydantic) and pip refuses the whole set. Install only the
# distributions that are not present yet, without dependency resolution.
OLD_TESTDEPS = pilot.WRITE_AGENTS[pilot.WRITE_AGENTS.index("    freeze = subprocess.run"):
                                  pilot.WRITE_AGENTS.index("print({k: sorted")]
NEW_TESTDEPS = r'''    freeze = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=json'], capture_output=True, text=True).stdout
    norm = lambda s: re.sub(r'[-_.]+', '-', s).lower()
    have = {norm(p['name']) for p in json.loads(freeze)}
    pick = {}
    for w in whl:
        d = norm(Path(w).name.split('-')[0])
        if d not in have and (d not in pick or '-py3-none-any' in w):
            pick[d] = w
    if pick:
        r = subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *pick.values()],
                           capture_output=True, text=True)
        print('test deps installed:', sorted(pick), 'OK' if r.returncode == 0 else r.stderr[-800:])
    else:
        print('WARNING: no new test-dep wheels', len(whl))
'''
WRITE_AGENTS = pilot.WRITE_AGENTS.replace(OLD_TESTDEPS, NEW_TESTDEPS)
assert WRITE_AGENTS != pilot.WRITE_AGENTS

TOOL_SEQUENCE = pilot.RUN[pilot.RUN.index("def tool_sequence"):pilot.RUN.index("for idx, iid in enumerate(PILOT_TASKS")]
# Official scoring compacts every 5 events (HARNESS_README section 7.2); the paper pilot used 15.
_PILOT_RUN = pilot.RUN.replace("EventsCompactionConfig(compaction_interval=15,", "EventsCompactionConfig(compaction_interval=5,")
assert _PILOT_RUN != pilot.RUN
RUN = _PILOT_RUN[:_PILOT_RUN.index("OUT = WORK / 'pilot_results.jsonl'")] + TOOL_SEQUENCE + r'''
from swegemma.harness import agent_runner as _AR
PROMPTS = {}
_build_prompt = _AR.build_agent_prompt
def _capture_prompt(task, *args, **kwargs):
    p = _build_prompt(task, *args, **kwargs)
    PROMPTS[task.instance_id] = p
    return p
_AR.build_agent_prompt = _capture_prompt  # run_agent_sandbox looks it up in its module at call time

import dataclasses
reps = {}
for name, ev_ in evaluators.items():
    for k in range(1, REPEATS + 1):
        upd = dict(results_dir=WORK / 'results' / name / f'r{k}')
        if MAX_TIME_MINUTES:
            upd['max_time_minutes'] = float(MAX_TIME_MINUTES)  # __post_init__ rebuilds the budget from it
        reps[(name, k)] = Evaluator(dataclasses.replace(ev_.config, **upd))
print('budget', next(iter(reps.values())).config.budget, flush=True)
OUT = WORK / 'pilot_results.jsonl'
COL = WORK / 'collected'; COL.mkdir(exist_ok=True)
T0 = time.time()
STOP_AFTER_S = STOP_AFTER_HOURS * 3600
jobs = [(k, idx, iid, name) for k in range(1, REPEATS + 1) for idx, iid in enumerate(PILOT_TASKS, start=1) for name in AGENTS]
print(len(jobs), 'runs, concurrency', CONCURRENCY, 'max_time_minutes', MAX_TIME_MINUTES or 'agent default', flush=True)

async def one(sem, k, idx, iid, name):
    async with sem:
        if time.time() - T0 > STOP_AFTER_S:
            return
        t = all_tasks[iid]
        t1 = time.time()
        res = None
        try:
            res = await reps[(name, k)].evaluate_task(task=t, task_index=idx, total_tasks=len(PILOT_TASKS))
            seq = tool_sequence(res)
            row = dict(config=name, rep=k, instance_id=iid, repo=t.repo, resolved=bool(res.resolved),
                       tool_calls=res.tool_calls, duration_s=round(time.time() - t1, 1),
                       patch_chars=len(res.agent_patch or ''), test_exit_code=res.test_exit_code,
                       first_tool=(seq[0] if seq else None), tools=seq, error=getattr(res, 'error_message', None))
        except Exception as e:
            row = dict(config=name, rep=k, instance_id=iid, repo=t.repo, resolved=False, error=repr(e)[:500],
                       duration_s=round(time.time() - t1, 1))
        try:
            entries = [e.to_dict() for e in res.trace.entries] if res is not None and getattr(res, 'trace', None) else None
            if entries is None and res is not None and getattr(res, 'trace_path', None):
                entries = json.loads(Path(res.trace_path).read_text())
            (COL / f'{name}__{iid}__r{k}.json').write_text(json.dumps(dict(
                row=row, prompt=PROMPTS.get(iid), patch=(res.agent_patch if res is not None else None),
                trace=entries), ensure_ascii=False))
        except Exception as e:
            print('save failed', name, iid, k, repr(e)[:200], flush=True)
        with OUT.open('a') as f:
            f.write(json.dumps(row) + '\n')
        print(k, idx, name, iid, row.get('resolved'), row.get('tool_calls'), row.get('duration_s'), row.get('error'), flush=True)
        print('ROW ' + json.dumps(row), flush=True)

async def main_():
    sem = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(*(one(sem, *j) for j in jobs))

run_sync(main_)
print('elapsed h', round((time.time() - T0) / 3600, 2), 'prompts captured', len(PROMPTS))
'''

SUMMARY = r'''
import collections
rows = [json.loads(l) for l in OUT.read_text().splitlines()]
for name in AGENTS:
    rs = [r for r in rows if r['config'] == name]
    by_task = collections.defaultdict(list)
    for r in rs:
        by_task[r['instance_id']].append(bool(r['resolved']))
    print(name, 'runs', len(rs), 'resolved runs', sum(r['resolved'] for r in rs),
          'rep1', sum(r['resolved'] for r in rs if r.get('rep') == 1), '/', sum(r.get('rep') == 1 for r in rs),
          'tasks solved at least once', sum(any(v) for v in by_task.values()), '/', len(by_task))
    print('  errors', collections.Counter((r.get('error') or '')[:50] for r in rs).most_common(5))
shutil.make_archive(str(WORK / 'collected'), 'zip', root_dir=COL)
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--slug", default="gemma4-collect")
    ap.add_argument("--user", default="danielaijdkx")
    ap.add_argument("--configs", default="baseline")
    ap.add_argument("--input-agent", action="append", default=[],
                    help="name=glob of an agent.yaml in an attached kernel output, e.g. rft=/kaggle/input/**/agent_lora/agent.yaml")
    ap.add_argument("--exclude-file", type=Path, help="JSON list of task ids to leave out (the eval holdout)")
    ap.add_argument("--tasks-file", type=Path, help="JSON list of task ids to run (default: all minus excluded)")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--max-time-minutes", type=float, default=0, help="0 = the agent's eval_config value")
    ap.add_argument("--stop-after-hours", type=float, default=5.5, help="no new runs start after this")
    ap.add_argument("--kernel-source", action="append", default=["danielaijdkx/gemma4-offline-wheels"])
    ap.add_argument("--test-deps-glob", default="/kaggle/input/**/testdeps/*.whl")
    a = ap.parse_args()
    excluded = set(json.loads(a.exclude_file.read_text())) if a.exclude_file else set()
    if a.tasks_file:
        ids = json.loads(a.tasks_file.read_text())
    else:
        ids = [json.loads(l)["instance_id"] for l in a.tasks.open()]
    ids = [i for i in ids if i not in excluded]
    files = {c: pilot.agent_files(c) for c in a.configs.split(",") if c}
    nb = {
        "cells": [
            pilot.md("# Gemma 4 agent: collect own trajectories\n\n" + __doc__.split("\n\n", 2)[2]),
            pilot.code(pilot.SETUP),
            pilot.code("AGENT_FILES = " + json.dumps(files, indent=1) + "\nINPUT_AGENTS = " + json.dumps(dict(x.split("=", 1) for x in a.input_agent))
                       + "\nTEST_DEPS_GLOB = " + json.dumps(a.test_deps_glob) + "\nPILOT_TASKS = " + json.dumps(ids)
                       + f"\nREPEATS = {a.repeats}\nCONCURRENCY = {a.concurrency}\nMAX_TIME_MINUTES = {a.max_time_minutes or None}"
                       + f"\nSTOP_AFTER_HOURS = {a.stop_after_hours}"
                       + "\nprint(len(PILOT_TASKS), 'tasks')\n" + WRITE_AGENTS),
            pilot.code(pilot.SERVER),
            pilot.code(RUN),
            pilot.code(SUMMARY),
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / f"{a.slug}.ipynb").write_text(json.dumps(nb, indent=1))
    meta = json.loads(json.dumps({
        "id": f"{a.user}/{a.slug}", "title": a.slug.replace("-", " ").title(), "code_file": f"{a.slug}.ipynb",
        "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": True, "enable_tpu": False,
        "enable_internet": False, "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"],
        "competition_sources": ["gemma-4-developer-agent"], "kernel_sources": list(dict.fromkeys(a.kernel_source)),
        "model_sources": ["google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2"], "machine_shape": "NvidiaL4",
        "docker_image": "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"}))
    (a.out / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
    print(len(ids), "tasks x", a.repeats, "repeats x", len(files), "configs")


if __name__ == "__main__":
    main()
