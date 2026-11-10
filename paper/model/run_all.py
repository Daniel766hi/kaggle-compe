"""Run the whole pipeline in order.

Usage: python run_all.py [N_scenarios] [--from STEP]
  --from s03_ensemble.py   skips the steps before it (e.g. to resume after an interruption;
                           the ensemble itself resumes from its checkpoints).
"""
import subprocess
import sys

args = [a for a in sys.argv[1:]]
start = None
if "--from" in args:
    i = args.index("--from")
    start = args[i + 1]
    del args[i:i + 2]
n = args[0] if args else "400"
steps = [["seasonal_adjustment.py"], ["fit_suspensions.py"], ["fit_rollout.py"], ["s02_validation.py"], ["s01_baseline.py"], ["s03_ensemble.py", n], ["check_time_step.py"],
         ["s04_scenario_discovery.py"], ["s05_policy_comparison.py"], ["parameter_sheet.py"]]
if start:
    names = [s[0] for s in steps]
    steps = steps[names.index(start):]
for s in steps:
    print(f"\n========== {' '.join(s)} ==========", flush=True)
    subprocess.run([sys.executable, *s], check=True)
