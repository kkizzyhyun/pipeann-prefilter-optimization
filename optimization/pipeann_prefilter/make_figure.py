#!/usr/bin/env python3
"""Render the measured Medium results; no simulated data."""
import csv
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
with (root / "evidence/results.csv").open(newline="") as f:
    rows = [r for r in csv.DictReader(f) if r["bucket"] == "medium"]
fig, axes = plt.subplots(2, 2, figsize=(9, 6.5), constrained_layout=True)
metrics = [("mean_latency_us", "Mean query latency (us)", "{:.1f}"),
           ("qps", "Throughput (queries/s)", "{:.1f}"),
           ("recall_percent", "Recall@10 (%)", "{:.1f}"),
           ("mean_ios", "Logical query I/O (4 KiB units/query)", "{:.1f}")]
for axis, (metric, title, fmt) in zip(axes.flat, metrics):
    a = [float(r[metric]) for r in rows if r["variant"] == "A"]
    b = [float(r[metric]) for r in rows if r["variant"] == "B"]
    for av, bv in zip(a, b):
        axis.plot([0, 1], [av, bv], color="#b9c1ca", linewidth=1, alpha=.7, zorder=1)
    values = a + b
    span = max(values) - min(values)
    margin = max(span * .16, max(values) * .015)
    axis.set_ylim(min(values) - margin, max(values) + 2.8 * margin)
    for x, vals, color in [(0, a, "#355c85"), (1, b, "#20816d")]:
        median = statistics.median(vals)
        axis.scatter([x] * len(vals), vals, color=color, s=20, zorder=2)
        axis.errorbar(x, median, yerr=[[median - min(vals)], [max(vals) - median]],
                      fmt="_", color=color, markersize=25, capsize=5, linewidth=2, zorder=3)
        axis.text(x, max(vals) + .6 * margin, fmt.format(median), ha="center", fontsize=11, fontweight="bold", color=color)
    axis.set_title(title, loc="left", fontsize=11)
    axis.set_xticks([0, 1], ["A  Original routing", "B  Calibrated routing"])
    axis.set_xlim(-.35, 1.35)
    axis.grid(axis="y", color="#e5e8eb", linewidth=.7)
    axis.spines[["top", "right"]].set_visible(False)
fig.suptitle("PipeANN-Filter on Medium workload\n7 paired runs; bold values are medians; whiskers show min–max", fontsize=13)
out = root / "figures"
out.mkdir(exist_ok=True)
fig.savefig(out / "medium_ab.png", dpi=180)
fig.savefig(out / "medium_ab.svg")
print(out / "medium_ab.png")
