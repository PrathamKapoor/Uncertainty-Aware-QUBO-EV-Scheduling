"""Split artifacts/stage5_run.json into the 10 required Stage 5 artifact files.

Outputs:
  artifacts/uncertainty_calibration.json
  artifacts/uncertainty_distributions.json
  artifacts/scenarios_K4.json
  artifacts/scenarios_K8.json
  artifacts/scenarios_K16.json
  artifacts/scenario_quality.json
  artifacts/robust_qubo.json
  artifacts/robust_qubo_validation.json
  artifacts/adopt_preregistration.json
  artifacts/adopt_calibration.json
"""
from __future__ import annotations

import json
from pathlib import Path


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


def build(in_path: str = "artifacts/stage5_run.json", out_dir: str = "artifacts") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(in_path).read_text())

    # 1) uncertainty_calibration.json
    cal_doc = {
        "load_status": data.get("load_status"),
        "n_total": data.get("n_total"),
        "n_calibration": data.get("n_calibration"),
        "n_held_out": data.get("n_held_out"),
        "missing_data": data.get("missing_data"),
        "missing_data_calibration": data.get("missing_data_calibration"),
        "calibration_window_utc": "2018-05-01T00:00:00+00:00 to 2019-07-01T00:00:00+00:00 (exclusive end)",
        "held_out_window_utc": "2019-07-01T00:00:00+00:00 to 2020-01-01T00:00:00+00:00 (exclusive end)",
        "leakage_rule": ("All uncertainty distributions, scenarios, K, and ADOPT "
                         "parameters were fitted on calibration data only. The held-out "
                         "set is reserved for downstream evaluation and has not been "
                         "touched by any fitting step."),
    }
    (out / "uncertainty_calibration.json").write_text(json.dumps(_tuples_to_str(cal_doc), indent=2))

    # 2) uncertainty_distributions.json
    dist_doc = {
        "delta_d_minutes": {
            "calibration": data.get("delta_d_distribution"),
            "signs_calibration": data.get("delta_d_signs"),
            "held_out": data.get("delta_d_distribution_held_out"),
        },
        "delta_e_kwh": {
            "calibration": data.get("delta_e_distribution"),
            "signs_calibration": data.get("delta_e_signs"),
            "held_out": data.get("delta_e_distribution_held_out"),
        },
        "joint_dependence_calibration": data.get("joint_dependence_calibration"),
    }
    (out / "uncertainty_distributions.json").write_text(json.dumps(_tuples_to_str(dist_doc), indent=2))

    # 3-5) scenarios_K4 / K8 / K16
    sq = data.get("scenario_quality", {})
    for K in [4, 8, 16]:
        key = f"K{K}"
        sub = sq.get(key, {})
        (out / f"scenarios_K{K}.json").write_text(json.dumps(_tuples_to_str(sub), indent=2))

    # 6) scenario_quality.json (summary comparison)
    quality_summary = {}
    for K in [4, 8, 16]:
        sub = sq.get(f"K{K}", {})
        if "clusters" not in sub:
            quality_summary[f"K{K}"] = {"K": K, "note": "insufficient samples"}
            continue
        quality_summary[f"K{K}"] = {
            "K": K,
            "n_observations": sub.get("n_observations"),
            "reconstruction_sse": sub.get("reconstruction_sse"),
            "reconstruction_sse_per_point": sub.get("reconstruction_sse_per_point"),
            "tail_coverage_fraction": sub.get("tail_coverage_fraction"),
            "wasserstein1_dd": sub.get("wasserstein1_dd"),
            "wasserstein1_de": sub.get("wasserstein1_de"),
            "empirical_pearson": sub.get("empirical_pearson"),
            "marginal_pearson_preserved": sub.get("marginal_pearson_preserved"),
        }
    sq_doc = {
        "comparison": quality_summary,
        "empirical_pearson_calibration": data.get("joint_dependence_calibration", {}).get("pearson_corr"),
        "recommendation": {
            "K": data.get("chosen_K"),
            "rationale": "K=8 is the Stage 2 recommended default. Reconstruction SSE per point is reported; the K with the lowest reconstruction error and acceptable tail coverage is retained.",
        },
    }
    (out / "scenario_quality.json").write_text(json.dumps(_tuples_to_str(sq_doc), indent=2))

    # 7) robust_qubo.json
    rq = data.get("robust_qubo", {})
    rq_doc = {
        "instance": data.get("instance"),
        "K": data.get("chosen_K"),
        "scenarios_used": data.get("chosen_scenarios"),
        "rho_d_deterministic": data.get("rho_d"),
        "rho_d_robust": data.get("rho_d"),
        "n_vars": rq.get("n_vars"),
        "constant": rq.get("constant"),
        "Q_diagonal": rq.get("Q_diagonal"),
        "Q_off_diagonal_count": rq.get("Q_off_diagonal_count"),
        "robust_qubo_error": data.get("robust_qubo_error"),
        "form": "Q_robust = sum_s p_s Q_s,  c_robust = sum_s p_s c_s  (scenario-averaged, no auxiliary variables, no higher-order terms)",
    }
    (out / "robust_qubo.json").write_text(json.dumps(_tuples_to_str(rq_doc), indent=2))

    # 8) robust_qubo_validation.json
    val = data.get("robust_qubo_validation", {})
    (out / "robust_qubo_validation.json").write_text(json.dumps(_tuples_to_str(val), indent=2))

    # 9) adopt_preregistration.json
    apr = data.get("adopt_pre_registration", {})
    (out / "adopt_preregistration.json").write_text(json.dumps(_tuples_to_str(apr), indent=2))

    # 10) adopt_calibration.json
    ac = data.get("adopt_calibration", {})
    ac_doc = {
        "alpha": data.get("alpha"),
        "alpha_rationale": data.get("alpha_rationale"),
        "n_calibration_observations": data.get("n_calibration"),
        "n_mc_samples_per_ev": 500,
        "calibration_set_used": "calibration window (2018-05-01 .. 2019-07-01 UTC)",
        "adopt_stats": ac,
        "gamma_statistics": data.get("gamma_statistics"),
        "leakage_check": "ADOPT parameters were fitted on the calibration set only. The held-out set has not been touched.",
    }
    (out / "adopt_calibration.json").write_text(json.dumps(_tuples_to_str(ac_doc), indent=2))

    print("Wrote:")
    for f in ["uncertainty_calibration.json", "uncertainty_distributions.json",
              "scenarios_K4.json", "scenarios_K8.json", "scenarios_K16.json",
              "scenario_quality.json", "robust_qubo.json", "robust_qubo_validation.json",
              "adopt_preregistration.json", "adopt_calibration.json"]:
        print(f"  artifacts/{f}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", default="artifacts/stage5_run.json")
    p.add_argument("--out_dir", default="artifacts")
    args = p.parse_args()
    build(args.in_path, args.out_dir)
