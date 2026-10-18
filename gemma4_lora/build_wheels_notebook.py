"""CPU notebook (Internet on) that downloads Python 3.12 wheels the offline L4 notebooks need:
peft + accelerate for LoRA training, and the test-only packages the subprocess sandbox lacks.

    python gemma4_lora/build_wheels_notebook.py --out <kernel dir>
"""
import argparse, json
from pathlib import Path

CELL = r'''
import subprocess, sys
from pathlib import Path
out = Path('/kaggle/working/wheels'); out.mkdir(parents=True, exist_ok=True)
plat = ['--python-version', '3.12', '--only-binary=:all:', '--platform', 'manylinux2014_x86_64',
        '--platform', 'manylinux_2_17_x86_64', '--platform', 'manylinux_2_28_x86_64', '--platform', 'any']
def dl(pkgs, deps):
    cmd = [sys.executable, '-m', 'pip', 'download', '-q', '-d', str(out), *plat] + ([] if deps else ['--no-deps']) + pkgs
    r = subprocess.run(cmd, capture_output=True, text=True); print(pkgs[:3], 'rc', r.returncode, r.stderr[-400:])
dl(['peft==0.21.2', 'accelerate==1.10.1'], deps=False)
testdeps = Path('/kaggle/working/testdeps'); testdeps.mkdir(exist_ok=True)
TEST_DEPS = ['inline-snapshot', 'dirty-equals', 'pytest-httpbin', 'trustme', 'pysocks', 'flask', 'pyjwt',
             'passlib[bcrypt]', 'pwdlib', 'orjson', 'ujson', 'email-validator', 'python-multipart', 'sqlmodel', 'trio']
r = subprocess.run([sys.executable, '-m', 'pip', 'download', '-q', '-d', str(testdeps), *plat, *TEST_DEPS],
                   capture_output=True, text=True); print('testdeps rc', r.returncode, r.stderr[-400:])
print(sorted(p.name for p in out.iterdir())); print(len(list(testdeps.iterdir())), 'test dep wheels')
'''

ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, required=True)
a = ap.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
nb = {"cells": [{"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": CELL}],
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
      "nbformat": 4, "nbformat_minor": 5}
(a.out / "gemma4-offline-wheels.ipynb").write_text(json.dumps(nb, indent=1))
(a.out / "kernel-metadata.json").write_text(json.dumps({
    "id": "danielaijdkx/gemma4-offline-wheels", "title": "Gemma4 Offline Wheels", "code_file": "gemma4-offline-wheels.ipynb",
    "language": "python", "kernel_type": "notebook", "is_private": True, "enable_gpu": False, "enable_tpu": False,
    "enable_internet": True, "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": []}, indent=1))
