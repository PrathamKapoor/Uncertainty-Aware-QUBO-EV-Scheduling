"""Exploratory synthetic scheduling stress test using public connection durations.

No declared departure or requested energy is observed in this dataset. A fixed
30-minute nominal horizon and 0.25 kWh target are synthetic assumptions.
"""
import argparse
import hashlib
import json
import gzip
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from experiments.revised_experiment import run_experiment


def prepare_sessions(frame):
    start = pd.to_datetime(frame["StartDatetime"], errors="coerce", format="mixed")
    end = pd.to_datetime(frame["EndDatetime"], errors="coerce", format="mixed")
    durations = (end - start).dt.total_seconds() / 60
    valid = start.notna() & end.notna() & (durations > 0) & np.isfinite(durations)
    # First 9 months calibrate; last 3 months evaluate. Fixed before this run.
    split = pd.Timestamp("2022-07-01")
    crossing = valid & (start < split) & (end >= split)
    valid = valid & ~crossing
    samples = [SimpleNamespace(session_id=str(i), calibration=bool(start.iloc[i] < split),
                               block_day=start.iloc[i].date().isoformat(),
                               delta_d_minutes=float(30 - durations.iloc[i]))
               for i in range(len(frame)) if valid.iloc[i]]
    return samples, {"raw": len(frame), "invalid_duration": int((~valid).sum() - crossing.sum()),
                     "calibration_crossing_split": int(crossing.sum()),
                     "eligible": int(valid.sum()), "duplicate_rows": int(frame.duplicated().sum()),
                     "min_start": str(start.min()), "max_start": str(start.max()),
                     "split": str(split), "timestamp_timezone": "not established; treated as naive local timestamps"}


def day_block_interval(a, b, days, *, seed=0, repetitions=2000):
    """Percentile bootstrap over whole calendar-day clusters, weighted by sessions."""
    a, b, days = np.asarray(a, float), np.asarray(b, float), np.asarray(days)
    if len(a) == 0 or len(a) != len(b) or len(a) != len(days) or repetitions < 1:
        raise ValueError("paired nonempty aligned observations required")
    _, inverse = np.unique(days, return_inverse=True)
    sizes = np.bincount(inverse)
    sums = np.bincount(inverse, weights=a-b)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(sizes), size=(repetitions, len(sizes)))
    differences = sums[draws].sum(axis=1) / sizes[draws].sum(axis=1)
    lo, hi = np.quantile(differences, [0.025, 0.975])
    return {"difference": float(np.mean(a-b)), "n_sessions": len(a), "n_days": len(sizes),
            "ci_95": [float(lo), float(hi)], "method": "paired day-block percentile bootstrap",
            "seed": seed, "repetitions": repetitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/revised_v2/public_duration_stress.json.gz"))
    args = parser.parse_args()
    raw = args.csv.read_bytes()
    frame = pd.read_csv(args.csv)
    samples, counts = prepare_sessions(frame)
    result = run_experiment(samples, scenario_count=8, weighting="empirical", shots=256, maxiter=20)
    days = [s.block_day for s in samples if not s.calibration]
    baseline = result["methods"]["F0"]["evaluation"]["records"]
    candidate = result["methods"]["buffer_90"]["evaluation"]["records"]
    result["buffer90_vs_F0_day_block"] = day_block_interval(
        [r["feasible"] for r in candidate], [r["feasible"] for r in baseline], days)
    result["dataset"] = {"citation": "10.1038/s41597-024-02942-9", "data_doi": "10.6084/m9.figshare.22495141.v1",
                         "sha256": hashlib.sha256(raw).hexdigest(), "counts": counts,
                         "missing_by_column": frame.isna().sum().astype(int).to_dict(),
                         "scope": "Observed connection duration; nominal deadline and target energy are simulated. Not observed driver forecasts or demand."}
    for method in result["methods"].values():
        for row in method["evaluation"]["records"]:
            row.pop("session_id", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.output, "wt", encoding="utf-8") as output:
        json.dump(result, output, separators=(",", ":"))
    print(json.dumps({"dataset": counts, "counts": result["counts"], "buffers": result["buffers_minutes"],
                      "methods": {k: {"schedule": v["schedule"], "feasibility": v["evaluation"]["feasibility_rate"],
                                      "mean_unmet_kWh": v["evaluation"]["mean_unmet_kWh"]}
                                  for k, v in result["methods"].items()}}, indent=2))


if __name__ == "__main__":
    main()
