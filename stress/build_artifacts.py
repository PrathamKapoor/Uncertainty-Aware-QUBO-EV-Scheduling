"""Split artifacts/stage7_run.json into the 8 required Stage 7 artifact files."""
from __future__ import annotations
import json
from pathlib import Path


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


def build(in_path: str = "artifacts/stage7_run.json", out_dir: str = "artifacts") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(in_path).read_text())

    # 1) synthetic_recovery_tests.json
    srt = data.get("part_d_synthetic_recovery", {})
    (out / "synthetic_recovery_tests.json").write_text(json.dumps(_tuples_to_str(srt), indent=2))

    # 2) directionality_tests.json
    d = data.get("part_e_directionality", {})
    (out / "directionality_tests.json").write_text(json.dumps(_tuples_to_str(d), indent=2))

    # 3) penalty_scale_analysis.json
    p = data.get("part_f_penalty_scale", {})
    (out / "penalty_scale_analysis.json").write_text(json.dumps(_tuples_to_str(p), indent=2))

    # 4) distribution_shift_tests.json
    ds = data.get("part_h_distribution_shift", {})
    (out / "distribution_shift_tests.json").write_text(json.dumps(_tuples_to_str(ds), indent=2))

    # 5) adopt_effect_analysis.json
    ae = data.get("part_c_adopt_effect", {})
    (out / "adopt_effect_analysis.json").write_text(json.dumps(_tuples_to_str(ae), indent=2))

    # 6) final_experiment_config.json (frozen configuration)
    final = {
        "stage": "Final Experiment Freeze (Stage 7 Part J)",
        "instance": data.get("instance", "toy_B_3x4"),
        "uncertainty_definitions": {
            "Delta_d": "requested_departure - actual_disconnect (positive = early departure)",
            "Delta_E": "E_delivered - E_requested (positive = over-delivery, negative = unmet demand)",
            "stress_model_scenario": "E_req_scenario = E_req + Delta_E (Delta_E < 0 lowers the per-scenario R_i; this is the correct sign per Stage 1 §4.2 and Stage 6 Part A)",
        },
        "Delta_d_transformation": "Corrected model: variable set fixed; per-scenario diagonal penalty M_window applied to out-of-window slots; R_i = ceil((E_req + Delta_E) / (P_max * Delta)) (no auxiliary variables, pure QUBO)",
        "K": 8,
        "alpha": 1.0,
        "gamma_pre_registration_locked": True,
        "scenario_weighting": "uniform p_s = 1/K",
        "M_window": data.get("M_window", 1e6),
        "rho_d": 1.0,
        "rho_p": 0.1,
        "rho_cap": 0.5,
        "P_target_kW": 6.6,
        "P_site_max_kW": 9.9,
        "feasibility_definition": "Four separate metrics: qubo_feasible, energy_feasible, site_feasible, deadline_feasible. Aggregate = AND. Frozen at Stage 4.",
        "QAOA_p": 1,
        "QAOA_optimizer": "COBYLA (scipy.optimize.minimize)",
        "QAOA_seeds": [0, 1, 2],
        "QAOA_shots": 1024,
        "instance_generation": "toy_B_3x4: 3 EVs, 4 slots, Delta = 15 min, 11 logical qubits after availability pruning",
        "calibration_window_UTC": "2018-05-01T00:00:00+00:00 to 2019-07-01T00:00:00+00:00 (exclusive end)",
        "held_out_window_UTC": "2019-07-01T00:00:00+00:00 to 2020-01-01T00:00:00+00:00 (exclusive end)",
        "DATA_MODE_current": "SYNTHETIC (ACN_API_TOKEN unavailable)",
        "DATA_MODE_target": "REAL (requires ACN_API_TOKEN environment variable)",
        "immutability_rule": ("No parameter in this file may be modified based on "
                              "held-out results. Any change must be recorded as a "
                              "new versioned configuration (stage7.v2, etc.) with explicit "
                              "documentation of the reason and the data state at the time of the change."),
        "version": "stage7.v1",
    }
    (out / "final_experiment_config.json").write_text(json.dumps(_tuples_to_str(final), indent=2))

    # 7) real_data_switch_test.json
    rdt = data.get("part_k_real_data_switch", {})
    (out / "real_data_switch_test.json").write_text(json.dumps(_tuples_to_str(rdt), indent=2))

    # 8) stage7_run.json: full output (already on disk; nothing to do)
    print("Wrote:")
    for f in ["synthetic_recovery_tests.json", "directionality_tests.json",
              "penalty_scale_analysis.json", "distribution_shift_tests.json",
              "adopt_effect_analysis.json", "final_experiment_config.json",
              "real_data_switch_test.json"]:
        print(f"  artifacts/{f}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", default="artifacts/stage7_run.json")
    p.add_argument("--out_dir", default="artifacts")
    args = p.parse_args()
    build(args.in_path, args.out_dir)
