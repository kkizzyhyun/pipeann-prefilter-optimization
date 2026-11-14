#!/usr/bin/env python3
"""Paired A/B benchmark; existing formal results and indexes remain untouched."""
import argparse
import csv
import hashlib
import json
import os
import platform
import random
import statistics
import subprocess
import time
from datetime import datetime
from pathlib import Path


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pairs", type=int, default=7)
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--buckets", nargs="+", default=["medium", "low", "high"])
    parser.add_argument("--cpu", type=int)
    args = parser.parse_args()
    if args.pairs < 3 or not 0 < args.threshold <= 1:
        parser.error("At least three pairs and a threshold in (0, 1] are required")
    root = args.course_root.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    repo = root / "systems/PipeANN_prefilter_verified"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    manifest = {
        "start_local": datetime.now().astimezone().isoformat(),
        "platform": platform.platform(), "cpu_affinity": args.cpu,
        "pairs": args.pairs, "threshold": args.threshold, "buckets": args.buckets,
        "warmup": "One discarded process per variant and bucket before measured pairs",
        "cache_protocol": "No cache dropping; application cache unchanged; both arms warmed",
        "controls": {"L": 40, "k": 10, "threads": 1, "beamwidth": 8, "mem_L": 0},
        "commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "binary_sha256": sha256(repo / "build/tests/search_disk_index_filtered"),
        "runs": [],
    }
    diff = subprocess.check_output(["git", "-C", str(repo), "diff"])
    (output / "source.patch").write_bytes(diff)
    manifest["patch_sha256"] = hashlib.sha256(diff).hexdigest()
    for name, command in {
        "lscpu": ["lscpu"], "memory": ["free", "-h"],
        "compiler": ["c++", "--version"], "filesystem": ["df", "-T", str(root)],
    }.items():
        manifest[name] = subprocess.check_output(command, text=True)

    def run(variant, bucket, pair, warmup=False):
        run_id = f"prefilter-{stamp}-{variant}-{'warmup' if warmup else 'p' + str(pair)}"
        command = ["python3", str(root / "adapters/pipeann_adapter.py"), "search",
                   "--repo", str(repo), "--dataset-root", str(root / "datasets/yfcc_course_v1"),
                   "--tier", "formal", "--run-root", str(root / "course_runs"),
                   "--bucket", bucket, "--L", "40", "--threads", "1", "--beamwidth", "8",
                   "--k", "10", "--mem-L", "0", "--run-id", run_id]
        if args.cpu is not None:
            command = ["taskset", "-c", str(args.cpu)] + command
        env = dict(os.environ)
        env["FVS_PREFILTER_MAX_SELECTIVITY"] = "0" if variant == "A" else str(args.threshold)
        logname = f"{variant}-{bucket}-{'warmup' if warmup else pair}.log"
        started = time.monotonic()
        with (output / logname).open("w") as log:
            subprocess.run(command, env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True)
        result_dir = root / "course_runs/results/pipeann/formal_1000000" / bucket / run_id
        with (result_dir / "results.csv").open(newline="") as f:
            values = list(csv.DictReader(f))
        if len(values) != 1 or int(values[0]["queries"]) != 200:
            raise RuntimeError("Unexpected query count or number of result rows")
        row = values[0]
        numeric = []
        for line in (result_dir / "run.log").read_text().splitlines():
            try:
                fields = [float(token) for token in line.split()]
            except ValueError:
                continue
            if len(fields) == 24 and fields[0] == 40 and fields[1] == 8:
                numeric.append(fields)
        if len(numeric) != 1:
            raise RuntimeError("Cannot identify the unique native performance row")
        fields = numeric[0]
        # The native per-route IO column also includes filter-index preparation.
        row["route_mean_ios_including_filter"] = sum(fields[c] * fields[c + 2] for c in (4, 10, 16)) / 200
        row.update(variant=variant, pair=pair, threshold=env["FVS_PREFILTER_MAX_SELECTIVITY"])
        record = {"variant": variant, "pair": pair, "bucket": bucket, "warmup": warmup,
                  "command": command, "env": {"FVS_PREFILTER_MAX_SELECTIVITY": env["FVS_PREFILTER_MAX_SELECTIVITY"]},
                  "raw_directory": str(result_dir), "wall_seconds": time.monotonic() - started}
        manifest["runs"].append(record)
        (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        print(f"{variant} {bucket} {'warmup' if warmup else pair}: "
              f"latency={row['mean_latency_us']}us recall={row['recall_percent']}% "
              f"IO={row['mean_ios']} pre={row['pre_filter_queries']}", flush=True)
        return row

    for bucket in args.buckets:
        for variant in ("A", "B"):
            run(variant, bucket, 0, True)
    rows = []
    rng = random.Random(20261114)
    for pair in range(1, args.pairs + 1):
        buckets = list(args.buckets)
        rng.shuffle(buckets)
        for bucket in buckets:
            for variant in (("A", "B") if pair % 2 else ("B", "A")):
                rows.append(run(variant, bucket, pair))
                with (output / "results.csv").open("w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
    summaries = []
    for bucket in args.buckets:
        groups = {v: [r for r in rows if r["bucket"] == bucket and r["variant"] == v] for v in ("A", "B")}
        summary = {"bucket": bucket}
        for variant, records in groups.items():
            for metric in ("mean_latency_us", "qps", "recall_percent", "mean_ios", "route_mean_ios_including_filter", "peak_rss_kb", "filter_false_positives", "pre_filter_queries", "in_filter_queries"):
                vals = [float(r[metric]) for r in records]
                for stat, value in (("median", statistics.median(vals)), ("min", min(vals)), ("max", max(vals))):
                    summary[f"{variant}_{metric}_{stat}"] = value
        improvements = []
        wins = 0
        recall_deltas = []
        for pair in range(1, args.pairs + 1):
            a = next(r for r in groups["A"] if r["pair"] == pair)
            b = next(r for r in groups["B"] if r["pair"] == pair)
            improvement = 100 * (1 - float(b["mean_latency_us"]) / float(a["mean_latency_us"]))
            improvements.append(improvement)
            wins += improvement > 0
            recall_deltas.append(float(b["recall_percent"]) - float(a["recall_percent"]))
        summary["paired_latency_drop_percent_median"] = statistics.median(improvements)
        summary["paired_latency_drop_percent_min"] = min(improvements)
        summary["latency_wins"] = wins
        summary["minimum_paired_recall_delta_pp"] = min(recall_deltas)
        summary["latency_drop_percent"] = 100 * (1 - summary["B_mean_latency_us_median"] / summary["A_mean_latency_us_median"])
        summary["qps_gain_percent"] = 100 * (summary["B_qps_median"] / summary["A_qps_median"] - 1)
        summaries.append(summary)
    (output / "summary.json").write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
