#!/usr/bin/env python3
"""Make this small evidence directory portable without copying data or indexes."""
import argparse
import csv
import json
import shutil
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--course-root", required=True, type=Path)
args = parser.parse_args()
course = args.course_root.resolve()
here = Path(__file__).resolve().parent
evidence = here / "evidence"
manifest = json.loads((evidence / "manifest.json").read_text())
for run in manifest["runs"]:
    name = f"{run['variant']}-{run['bucket']}-{'warmup' if run['warmup'] else run['pair']}"
    destination = evidence / "raw" / name
    destination.mkdir(parents=True, exist_ok=True)
    for source in Path(run["raw_directory"]).iterdir():
        if source.is_file() and source.suffix in (".json", ".csv", ".log"):
            shutil.copy2(source, destination / source.name)
source = course / "systems/PipeANN_prefilter_verified/src/search/spec_filter_search.cpp"
(here / "modified_source").mkdir(exist_ok=True)
shutil.copy2(source, here / "modified_source/spec_filter_search.cpp")
shutil.copy2(course / "systems/PipeANN_prefilter_verified/LICENSE", here / "modified_source/LICENSE")
shutil.copy2(course / "prefilter_build.log", evidence / "build.log")
original = course / "course_runs/experiments/20260924-150134"
retained = evidence / "original_report"
retained.mkdir(exist_ok=True)
for name in ("results.csv", "environment.txt"):
    shutil.copy2(original / name, retained / name)
with (original / "results.csv").open(newline="") as f:
    rows = list(csv.DictReader(f))
groups = sorted({(r["system"], r["bucket"], int(r["L"])) for r in rows})
summaries = []
for system, bucket, budget in groups:
    selected = [r for r in rows if (r["system"], r["bucket"], int(r["L"])) == (system, bucket, budget)]
    record = {"system": system, "bucket": bucket, "L": budget, "repeats": len(selected)}
    for metric in ("mean_latency_us", "qps", "recall_percent", "mean_ios", "peak_rss_kb",
                   "pre_filter_queries", "in_filter_queries", "filter_false_positives", "filter_skips",
                   "io_time_us", "tunnel_time_us", "process_time_us"):
        vals = [float(r[metric]) for r in selected if r[metric] != ""]
        for stat, value in (("median", statistics.median(vals) if vals else ""),
                            ("min", min(vals) if vals else ""), ("max", max(vals) if vals else "")):
            record[f"{metric}_{stat}"] = value
    summaries.append(record)
with (evidence / "original_summary.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(summaries[0]))
    writer.writeheader()
    writer.writerows(summaries)
print("Archived", len(manifest["runs"]), "runs and", len(summaries), "original summary groups")
