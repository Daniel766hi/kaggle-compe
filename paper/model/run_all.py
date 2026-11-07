"""Run the whole pipeline in order.  Usage: python run_all.py [N_scenarios]"""
import subprocess
import sys

n = sys.argv[1] if len(sys.argv) > 1 else "400"
steps = [["s01_baseline.py"], ["s02_validation.py"], ["s03_ensemble.py", n],
         ["s04_scenario_discovery.py"], ["s05_policy_comparison.py"], ["parameter_sheet.py"]]
for s in steps:
    print(f"\n========== {' '.join(s)} ==========", flush=True)
    subprocess.run([sys.executable, *s], check=True)
