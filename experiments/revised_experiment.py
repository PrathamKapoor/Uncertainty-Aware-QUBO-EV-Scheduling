"""Exploratory departure-only experiment on a fixed synthetic single-EV instance.

This is not a reconstruction of historical schedules. The live path uses only
inputs with timestamps no later than connection and excludes undated inputs.
"""
from itertools import product
import math
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from qiskit import transpile

from scheduling.ev_scheduling import EV, Instance, QUBO, realized_availability_mask, decode_feasibility
from scheduling.revised_qubo import build_revised_qubo, physical_objective, scenario_qubo_with_recourse
from quantum.qaoa import QAOAConfig, qubo_to_ising, run_qaoa, _build_qaoa_ansatz
from experiments.real_experiment import evaluate_departures_v2, paired_records_v2
from experiments.real_experiment import apply_cleaning_to_live
from uncertainty.uncertainty import load_real_uncertainty


def _best_for_decisions(model, decisions):
    """Exactly minimize auxiliary bits for fixed schedule in a small model."""
    count = model.n - len(decisions)
    return min((physical_objective(model, np.array((*decisions, *slack))), slack)
               for slack in product((0, 1), repeat=count))


def reliability_buffer_minutes(calibration_shifts, quantile):
    """Empirical linear-interpolated quantile of positive early shifts."""
    values = np.asarray(calibration_shifts, dtype=float)
    if not len(values) or not np.all(np.isfinite(values)) or not 0 <= quantile <= 1:
        raise ValueError("finite calibration observations and quantile in [0, 1] required")
    return float(np.quantile(np.maximum(values, 0), quantile, method="linear"))


def buffered_schedule(buffer_minutes):
    """Exact toy solution with a hard conservative-deadline restriction."""
    if not math.isfinite(buffer_minutes) or buffer_minutes < 0:
        raise ValueError("buffer must be finite and nonnegative")
    ev = EV("synthetic_ev", 0, 1, 1.0, 0.25)
    mask = realized_availability_mask(ev, buffer_minutes, 15)
    model = build_revised_qubo([1], [1], [mask], 1, [1.0, 0.5], .25, 5, 5)
    legal = [x for x in product((0, 1), repeat=2)
             if all(not x[t] or mask & (1 << t) for t in range(2))]
    return min(legal, key=lambda x: (_best_for_decisions(model, x)[0], x))


def earliest_feasible_schedule(availability, required_slots):
    """Greedily use available slots in chronological order."""
    if required_slots < 0 or int(required_slots) != required_slots:
        raise ValueError("required_slots must be a nonnegative integer")
    remaining = required_slots
    result = []
    for available in availability:
        use = bool(available) and remaining > 0
        result.append(int(use))
        remaining -= int(use)
    return tuple(result)


def run_experiment(samples, *, scenario_count=2, weighting="empirical", shots=64, maxiter=8):
    """Fit departure scenarios on calibration records; evaluate aligned held-out records."""
    if weighting not in ("uniform", "empirical") or scenario_count < 1:
        raise ValueError("invalid scenario configuration")
    samples = list(samples)
    ids = [s.session_id for s in samples]
    if len(set(ids)) != len(ids):
        raise ValueError("session IDs must be unique across both splits")
    calibration = [float(s.delta_d_minutes) for s in samples if s.calibration
                   and s.delta_d_minutes is not None and np.isfinite(s.delta_d_minutes)]
    evaluation = [s for s in samples if not s.calibration]
    if len(calibration) < scenario_count:
        raise ValueError("insufficient eligible calibration observations")
    groups = np.array_split(np.sort(calibration), scenario_count)
    centers = [float(g.mean()) for g in groups]
    frequencies = [len(g) for g in groups]
    weights = np.array(frequencies if weighting == "empirical" else [1] * scenario_count, dtype=float)
    weights /= weights.sum()
    ev = EV("synthetic_ev", 0, 1, 1.0, 0.25)
    inst = Instance("synthetic_counterfactual", [ev], 2, 1, 1, [1.0, 0.5], Delta_min=15)
    def model(mask):
        return build_revised_qubo([1], [1], [mask], 1, inst.c_per_slot, inst.Delta_hours, 5, 5,
                                  penalize_unavailable=False)
    nominal = model(realized_availability_mask(ev, 0, 15))
    scenarios = [model(realized_availability_mask(ev, s, 15)) for s in centers]
    robust_qubo = scenario_qubo_with_recourse(scenarios, frequencies, weighting)
    decisions = list(product((0, 1), repeat=2))
    f0_bits = min(decisions, key=lambda x: (_best_for_decisions(nominal, x)[0], x))
    f1_bits = min(decisions, key=lambda x: (sum(w * _best_for_decisions(m, x)[0]
                                                  for w, m in zip(weights, scenarios)), x))
    methods = {}
    buffers = {level: reliability_buffer_minutes(calibration, level) for level in (0.8, 0.9, 0.95)}
    candidates = [("F0", f0_bits), ("F1", f1_bits), ("F_early", earliest_feasible_schedule([True, True], 1))] + [(f"buffer_{int(level * 100)}", buffered_schedule(buffer)) for level, buffer in buffers.items()]
    for name, bits in candidates:
        schedule = {(0, t): int(bits[t]) for t in range(2)}
        evaluation_result = evaluate_departures_v2(inst, schedule, evaluation, target_ev_id=ev.ev_id)
        methods[name] = {"schedule": list(bits), "evaluation": evaluation_result}
    paired = paired_records_v2(methods["F1"]["evaluation"]["records"],
                               methods["F0"]["evaluation"]["records"], n_boot=1000, seed=0)
    qubo = QUBO(nominal.Q, nominal.c, {(0, i): i for i in range(nominal.n)})
    optimum = min(qubo.evaluate(np.array(x)) for x in product((0, 1), repeat=nominal.n))
    ising = qubo_to_ising(qubo.Q, qubo.c, qubo.var_index)
    config = QAOAConfig("revised_fixture_F0", nominal.n, 1, shots, 0, "COBYLA", maxiter, 1e-5, "small_random")
    run = run_qaoa(qubo, ising, config)
    records = run["sampled_records"]
    total = run["sampled_total_count"]
    def physically_feasible(bits):
        return decode_feasibility(inst, {(0, t): int(bits[t]) for t in range(2)},
                                  realized_early_minutes={})["feasible"]
    states = list(product((0, 1), repeat=nominal.n))
    circuit, _ = _build_qaoa_ansatz(ising.to_qiskit_op(), 1)
    compiled = transpile(circuit, basis_gates=["rz", "sx", "x", "cx"], optimization_level=1, seed_transpiler=0)
    buffer_mask = realized_availability_mask(ev, buffers[0.9], 15)
    buffer_model = build_revised_qubo([1], [1], [buffer_mask], 1, inst.c_per_slot, inst.Delta_hours, 5, 5)
    buffer_qubo = QUBO(buffer_model.Q, buffer_model.c, {(0, i): i for i in range(buffer_model.n)})
    buffer_optimum = min(buffer_qubo.evaluate(np.array(x)) for x in states)
    buffer_ising = qubo_to_ising(buffer_qubo.Q, buffer_qubo.c, buffer_qubo.var_index)
    buffer_run = run_qaoa(buffer_qubo, buffer_ising, config)
    buffer_records = buffer_run["sampled_records"]
    buffer_total = buffer_run["sampled_total_count"]
    legal = lambda x: all(not x[t] or bool(buffer_mask & (1 << t)) for t in range(2))
    if any(not legal(s) for s in states if math.isclose(buffer_qubo.evaluate(np.array(s)), buffer_optimum, abs_tol=1e-8)):
        raise RuntimeError("buffer QUBO penalty admits an inadmissible global optimum")
    return {"scope": "exploratory synthetic schedule, calibrated on supplied departure shifts",
            "counts": {"calibration_total": sum(bool(s.calibration) for s in samples),
                       "calibration_eligible": len(calibration), "evaluation_total": len(evaluation),
                       "evaluation_eligible": methods["F0"]["evaluation"]["n"]},
            "scenarios": {"centers_minutes": centers, "frequencies": frequencies,
                          "weights": weights.tolist(), "weighting": weighting,
                          "qubo_variables": robust_qubo.n(), "slack": "separate per scenario"},
            "methods": methods, "buffers_minutes": {str(k): v for k, v in buffers.items()}, "paired_F1_minus_F0": paired,
            "quantum_buffer_90": {"qubits": buffer_model.n, "shots_observed": buffer_total,
                                  "classical_optimum": buffer_optimum, "run": buffer_run,
                                  "best_sampled_gap": buffer_run["best_qubo_energy"] - buffer_optimum,
                                  "p_optimal": sum(r["count"] for r in buffer_records if math.isclose(r["qubo_energy"], buffer_optimum, abs_tol=1e-8)) / buffer_total,
                                  "p_buffer_admissible": sum(r["count"] for r in buffer_records if legal(r["x"])) / buffer_total,
                                  "p_service_and_buffer_admissible": sum(r["count"] for r in buffer_records if legal(r["x"]) and physically_feasible(r["x"])) / buffer_total},
            "quantum": {"qubits": nominal.n, "shots_observed": total,
                        "classical_optimum": optimum, "run": run,
                        "p_optimal": sum(r["count"] for r in records if math.isclose(r["qubo_energy"], optimum, abs_tol=1e-8)) / total,
                        "p_physical_feasible": sum(r["count"] for r in records if physically_feasible(r["x"])) / total,
                        "uniform_random_p_optimal": sum(math.isclose(qubo.evaluate(np.array(s)), optimum, abs_tol=1e-8) for s in states) / len(states),
                        "uniform_random_p_feasible": sum(physically_feasible(s) for s in states) / len(states),
                        "sampled_mean_energy": sum(r["count"] * r["qubo_energy"] for r in records) / total,
                        "best_sampled_gap": run["best_qubo_energy"] - optimum,
                        "transpiled_depth": compiled.depth(), "transpiled_cx": compiled.count_ops().get("cx", 0)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["fixture", "live"], default="fixture")
    parser.add_argument("--output", default=None)
    parser.add_argument("--scenarios", type=int, default=2)
    parser.add_argument("--weighting", choices=["uniform", "empirical"], default="empirical")
    args = parser.parse_args()
    if args.source == "live":
        samples, status = load_real_uncertainty(as_of_connection=True)
        if status.get("source") != "live_api" or not samples:
            raise SystemExit("ACN acquisition unavailable; configure ACN_API_TOKEN locally and retry.")
        samples, cleaning = apply_cleaning_to_live(samples)
    else:
        samples = [SimpleNamespace(session_id=f"fixture_{i}", calibration=i < 4, delta_d_minutes=shift)
                   for i, shift in enumerate([0, 15, 15, 30, 0, 15, 30, None])]
        status = {"source": "synthetic_fixture"}
        cleaning = {"note": "fixture contains one missing departure shift"}
    result = run_experiment(samples, scenario_count=args.scenarios, weighting=args.weighting)
    result["data_source"] = status
    result["cleaning"] = cleaning
    # Session identifiers are not necessary to distribute per-record metrics.
    for method in result["methods"].values():
        for row in method["evaluation"]["records"]:
            row.pop("session_id", None)
    target = Path(args.output or f"artifacts/revised_v2/integrated_{args.source}.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {target}; source={args.source}; eligible={result['counts']['evaluation_eligible']}")


if __name__ == "__main__":
    main()
