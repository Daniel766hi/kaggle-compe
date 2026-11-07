"""Extract every constant from the .mdl into a checklist (data/parameter_sheet.csv).

Fill in 'your_value', 'source' and 'justification' for each row; that table becomes the
parameter appendix of the paper. Rows tagged PLACEHOLDER/UNCERTAINTY/POLICY need attention first.
"""
import re

import pandas as pd

from common import DATA_DIR, MODEL_FILE, UNCERTAINTIES

text = MODEL_FILE.read_text().split("\\\\\\---///")[0].replace("{UTF-8}", "")
rows = []
for block in text.split("|"):
    m = re.match(r"\s*(.+?)=\s*\n\t(.+?)\n\t~\t(.*?)\n\t~\t(.*?)\s*$", block, re.S)
    if not m:
        continue
    name, expr, units, cmt = (x.strip() for x in m.groups())
    try:
        val = float(expr)
    except ValueError:
        continue
    tag = next((t for t in ("PLACEHOLDER", "UNCERTAINTY", "POLICY") if t in cmt), "")
    rng = UNCERTAINTIES.get(name)
    rows.append({"parameter": name, "model_value": val, "units": units, "tag": tag,
                 "ensemble_range": f"{rng[0]} to {rng[1]}" if rng else "", "comment": cmt,
                 "your_value": "", "source": "", "justification": ""})
df = pd.DataFrame(rows)
df.to_csv(DATA_DIR / "parameter_sheet.csv", index=False)
print(f"{len(df)} constants written to {DATA_DIR / 'parameter_sheet.csv'}; "
      f"{(df.tag != '').sum()} tagged for verification")
