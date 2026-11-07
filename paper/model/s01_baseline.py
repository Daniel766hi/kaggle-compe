"""Step 1: baseline run vs no-programme counterfactual, plus behaviour plots.

Output: figure of programme roll-out, supply response, prices and household consumption.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import CF_COLS, OUT_DIR, compute_outcomes, run, save_table, stamp

base = run()
counter = run({"Programme start time": 10_000})

fig, ax = plt.subplots(2, 3, figsize=(14, 7.5))
panels = [
    ("Programme coverage", "Programme coverage (share of target)"),
    ("MBG egg demand", "MBG egg demand (t/week)"),
    ("Laying hens", "Laying hens (birds)"),
    ("Relative egg price", "Egg price relative to baseline"),
    ("Relative chicken price", "Chicken price relative to baseline"),
    ("Household egg consumption ratio", "Household egg consumption (relative)"),
]
for a, (col, title) in zip(ax.flat, panels):
    a.plot(base.index, base[col], label="With MBG (baseline policy)")
    a.plot(counter.index, counter[col], "--", label="No programme")
    a.axvline(52, color="grey", lw=0.8, ls=":")
    a.set_title(title, fontsize=10)
    a.set_xlabel("Week (0 = Jan 2024)")
ax.flat[0].legend(fontsize=8)
fig.tight_layout(rect=(0, 0.02, 1, 1))
stamp(fig)
fig.savefig(OUT_DIR / "fig_baseline_dynamics.png", dpi=150)

save_table(base, "baseline_timeseries.csv")
o = compute_outcomes(base, counter[CF_COLS])
print("Baseline outcome indicators:")
for k, v in o.items():
    print(f"  {k:32s} {v:,.4f}")
print("saved", OUT_DIR / "fig_baseline_dynamics.png")
