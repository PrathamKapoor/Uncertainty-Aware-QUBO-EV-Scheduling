"""Build the required Stage 4 artifacts from the stage4_run.json output.

Outputs (matching the Stage 4 spec):
  artifacts/qaoa_config.json        -- All experimental configuration
  artifacts/qaoa_results.json       -- Per-seed QAOA results table (Part I/J)
  artifacts/ising_validation.json   -- QUBO->Ising validation report (Part D)
  artifacts/qaoa_seed_results.json  -- Per-(p, shots) seed-aggregated results (Part H)
  artifacts/qaoa_depth_results.json -- p=1 vs p=2 comparison (Part L)
  artifacts/qaoa_shot_results.json  -- Shot sensitivity (Part K)
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def build_artifacts(in_path: str = "artifacts/stage4_run.json", out_dir: str = "artifacts") -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads(Path(in_path).read_text())

    # 1) qaoa_config.json
    config_doc = {
        "stage": "Stage 4",
        "qa_framework": "Qiskit 2.5.1 + qiskit-aer (statevector simulator via SamplerV2)",
        "ansatz": "Hand-rolled standard QAOA: H^\\otimes n initial state, alternating UC(gamma_k) = exp(-i*gamma_k*H_C) and UB(beta_k) = exp(-i*beta_k*H_B) with H_B = sum_i X_i. Parameters ordered [gamma_1..p, beta_1..p].",
        "circuit_depth_per_p": {
            1: "1 cost layer + 1 mixer layer",
            2: "2 cost layers + 2 mixer layers",
        },
        "transpilation": "Aer's basis_gates = ['rz', 'sx', 'x', 'cx']; optimization_level = 1; seed_transpiler = config.seed",
        "initial_state": "|+\\rangle^{\\otimes n}",
        "mixer": "X mixer (sum_i X_i); exp(-i*beta*H_B) decomposed as R_X(2*beta) on each qubit",
        "cost_hamiltonian": "Ising H = sum_{i<j} J_ij Z_i Z_j + sum_i h_i Z_i + offset, derived from the QUBO via x_i = (1 - z_i)/2 (see stage4/qaoa.py qubo_to_ising).",
        "optimizer": data.get("optimizer_used", "COBYLA via scipy.optimize.minimize"),
        "optimizer_settings": {
            "maxiter": data.get("optimizer_max_iter", 40),
            "tol": data.get("optimizer_tol", 1e-5),
            "rhobeg": 0.05,
            "catol": 0.002,
            "method": "COBYLA",
        },
        "init_strategy": data.get("init_strategy", "small_random: uniform in [-0.1, 0.1]"),
        "seeds": data.get("seeds", [0, 1, 2]),
        "shot_counts": data.get("shot_values", [256, 1024, 4096]),
        "depths_tested": data.get("p_values", [1, 2]),
        "instance_set": list(data.get("qaoa_results", {}).keys()),
        "qubo_per_instance": {name: info["qubo_optimum"] for name, info in data.get("qaoa_results", {}).items()},
        "rho_d": data.get("rho_d", 1.0),
        "rho_p": data.get("rho_p", 0.1),
        "rho_cap": data.get("rho_cap", 0.5),
        "site_cap_form": "AMENDED to smooth two-sided (Stage 4 Part A reconciliation, recorded in Stage 1 §3.2)",
        "feasibility_semantics": "Four separate metrics: qubo_feasible, energy_feasible, site_feasible, deadline_feasible (Stage 4 Part B)",
        "reproducibility": {
            "python": "3.13.14",
            "qiskit": "2.5.1",
            "qiskit_aer": "bundled with qiskit 2.5.1",
            "numpy": "2.5.2",
            "scipy": "1.17.1",
            "shots_for_expectation": "Each QAOA evaluation samples the ansatz with config.shots; the expectation is the sample mean of the cost operator.",
            "variable_to_qubit_mapping": "Outer loop over EVs in declaration order, inner loop over slots in the EV's available window W_i; preserved across QUBO, Ising, and QAOA.",
        },
    }
    (out / "qaoa_config.json").write_text(json.dumps(_tuples_to_str(config_doc), indent=2))

    # 2) qaoa_results.json: per-seed results table (Part I/J)
    rows = []
    for inst_name, by_p in data.get("shot_results", {}).items():
        for p_str, by_shots in by_p.items():
            for shots_str, rec in by_shots.items():
                for sm in rec["per_seed"]:
                    rows.append({
                        "instance": inst_name,
                        "n_qubits": inst_name_to_n_qubits(inst_name, data),
                        "p": int(p_str),
                        "shots": int(shots_str),
                        "seed": sm["seed"],
                        "exact_optimum": sm.get("qubo_optimum"),
                        "best_qubo_energy": sm.get("best_qubo_energy"),
                        "approximation_ratio": sm.get("approximation_ratio"),
                        "absolute_gap": sm.get("absolute_gap"),
                        "P_opt": sm.get("P_opt"),
                        "P_feasible": sm.get("P_feasible"),
                        "P_qubo_feasible": sm.get("P_qubo_feasible"),
                        "P_energy_feasible": sm.get("P_energy_feasible"),
                        "P_site_feasible": sm.get("P_site_feasible"),
                        "P_deadline_feasible": sm.get("P_deadline_feasible"),
                        "n_shots_total": sm.get("n_shots_total"),
                        "n_optimum_samples": sm.get("n_optimum_samples"),
                    })
    (out / "qaoa_results.json").write_text(json.dumps(_tuples_to_str(rows), indent=2))

    # 3) ising_validation.json
    iv = data.get("ising_validation", {})
    (out / "ising_validation.json").write_text(json.dumps(_tuples_to_str(iv), indent=2))

    # 4) qaoa_seed_results.json: aggregate per (instance, p, shots)
    seed_agg = {}
    for inst_name, by_p in data.get("shot_results", {}).items():
        seed_agg[inst_name] = {}
        for p_str, by_shots in by_p.items():
            for shots_str, rec in by_shots.items():
                key = f"p{p_str}_shots{shots_str}"
                seed_agg[inst_name][key] = {
                    "p": int(p_str),
                    "shots": int(shots_str),
                    "n_seeds": rec["n_seeds"],
                    "seeds": [sm["seed"] for sm in rec["per_seed"]],
                    "P_opt_mean": rec["aggregate"]["P_opt_mean"],
                    "P_opt_std": rec["aggregate"]["P_opt_std"],
                    "P_opt_median": rec["aggregate"]["P_opt_median"],
                    "P_feasible_mean": rec["aggregate"]["P_feasible_mean"],
                    "P_feasible_std": rec["aggregate"]["P_feasible_std"],
                    "P_feasible_median": rec["aggregate"]["P_feasible_median"],
                    "AR_mean": rec["aggregate"]["AR_mean"],
                    "AR_std": rec["aggregate"]["AR_std"],
                    "AR_median": rec["aggregate"]["AR_median"],
                    "AR_best": rec["aggregate"]["AR_best"],
                    "AR_worst": rec["aggregate"]["AR_worst"],
                }
    (out / "qaoa_seed_results.json").write_text(json.dumps(_tuples_to_str(seed_agg), indent=2))

    # 5) qaoa_depth_results.json: p=1 vs p=2 per (instance, shots)
    depth_agg = {}
    for inst_name, by_p in data.get("depth_results", {}).items():
        depth_agg[inst_name] = {}
        for shots_str, by_p_inner in by_p.items():
            depth_agg[inst_name][f"shots_{shots_str}"] = {}
            for p_str, rec in by_p_inner.items():
                depth_agg[inst_name][f"shots_{shots_str}"][f"p_{p_str}"] = {
                    "p": int(p_str),
                    "n_parameters": 2 * int(p_str),
                    "n_seeds": rec["n_seeds"],
                    "P_opt_mean": rec["aggregate"]["P_opt_mean"],
                    "P_feasible_mean": rec["aggregate"]["P_feasible_mean"],
                    "AR_mean": rec["aggregate"]["AR_mean"],
                    "AR_median": rec["aggregate"]["AR_median"],
                    "AR_best": rec["aggregate"]["AR_best"],
                }
    (out / "qaoa_depth_results.json").write_text(json.dumps(_tuples_to_str(depth_agg), indent=2))

    # 6) qaoa_shot_results.json: shot sensitivity per (instance, p)
    shot_agg = {}
    for inst_name, by_p in data.get("shot_results", {}).items():
        shot_agg[inst_name] = {}
        for p_str, by_shots in by_p.items():
            shot_agg[inst_name][f"p_{p_str}"] = {}
            for shots_str, rec in by_shots.items():
                shot_agg[inst_name][f"p_{p_str}"][f"shots_{shots_str}"] = {
                    "shots": int(shots_str),
                    "n_seeds": rec["n_seeds"],
                    "P_opt_mean": rec["aggregate"]["P_opt_mean"],
                    "P_feasible_mean": rec["aggregate"]["P_feasible_mean"],
                    "AR_mean": rec["aggregate"]["AR_mean"],
                }
    (out / "qaoa_shot_results.json").write_text(json.dumps(_tuples_to_str(shot_agg), indent=2))

    print("Wrote:")
    for f in ["qaoa_config.json", "qaoa_results.json", "ising_validation.json",
              "qaoa_seed_results.json", "qaoa_depth_results.json", "qaoa_shot_results.json"]:
        print(f"  artifacts/{f}")


def inst_name_to_n_qubits(name: str, data: dict) -> int:
    iv = data.get("ising_validation", {})
    if name in iv:
        return int(iv[name].get("n_qubits", 0))
    return 0


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", default="artifacts/stage4_run.json")
    p.add_argument("--out_dir", default="artifacts")
    args = p.parse_args()
    build_artifacts(args.in_path, args.out_dir)
