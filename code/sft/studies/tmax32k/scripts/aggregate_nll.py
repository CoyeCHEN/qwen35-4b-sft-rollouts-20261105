"""Aggregate retained scalar NLLs; macro and token weighted denominators differ."""

import collections
import csv
import gzip
import json
import os
from pathlib import Path

R = Path(os.environ["TMAX_ABLATION_ROOT"])


def main():
    if any(
        (R / n).exists()
        for n in ["REGION_NLL_RESULTS.csv", "REGION_NLL_COMPARISON.csv"]
    ):
        raise RuntimeError("Existing derived report; use a new output runtime")
    groups = collections.defaultdict(
        lambda: [0.0, 0, 0.0, 0, collections.defaultdict(lambda: [0.0, 0])]
    )
    coverage = json.loads((R / "numerical/TRAJECTORY_COVERAGE_INDEX.json").read_text())[
        "calls"
    ]
    for p in sorted((R / "numerical").glob("*-region-nll-v2.jsonl.gz")):
        with gzip.open(p, "rt") as f:
            for line in f:
                row = json.loads(line)
                length = row["input_tokens"]
                bucket = (
                    "<=8K"
                    if length <= 8192
                    else "8K-32K"
                    if length <= 32768
                    else ">32K"
                )
                for paired, prefix in [(False, ""), (True, "paired_")]:
                    sums = row[prefix + "region_nll_sum"]
                    counts = row[prefix + "region_counts"]
                    for region, total in sums.items():
                        n = counts[region]
                        if not n:
                            continue
                        quartile = coverage[row["call_id"]]["quartile"]
                        for b in ["all", bucket]:
                            for q in ["all", quartile]:
                                key = (
                                    row["model"],
                                    row["split"],
                                    row["condition"],
                                    region,
                                    paired,
                                    b,
                                    q,
                                )
                                g = groups[key]
                                g[0] += total
                                g[1] += n
                                g[2] += total / n
                                g[3] += 1
                                task = g[4][row["task_id"]]
                                task[0] += total
                                task[1] += n
    with (R / "REGION_NLL_RESULTS.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "model",
                "split",
                "condition",
                "region",
                "paired_identical_target_suffix",
                "input_length_bucket",
                "trajectory_quartile",
                "call_macro_nll",
                "token_weighted_nll",
                "supervised_tokens",
                "calls",
                "task_macro_nll",
                "independent_tasks",
                "status",
            ]
        )
        for key, g in sorted(groups.items()):
            w.writerow(
                [
                    *key,
                    g[2] / g[3],
                    g[0] / g[1],
                    g[1],
                    g[3],
                    sum(v[0] / v[1] for v in g[4].values()) / len(g[4]),
                    len(g[4]),
                    "OBSERVED",
                ]
            )
    (R / "REGION_NLL_COMPARISON.csv").write_bytes(
        (R / "REGION_NLL_RESULTS.csv").read_bytes()
    )


if __name__ == "__main__":
    main()
