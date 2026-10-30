"""Small, entirely modeled two-EV capacity and scenario comparison."""
from itertools import product
import json
import time
from pathlib import Path
import numpy as np
from qiskit import transpile
from scheduling.ev_scheduling import EV, Instance, QUBO, decode_feasibility
from scheduling.revised_qubo import build_revised_qubo, scenario_qubo_with_recourse
from quantum.qaoa import QAOAConfig, qubo_to_ising, run_qaoa, _build_qaoa_ansatz


def build_case():
    return Instance("two_ev", [EV("a", 0, 1, 1, .25), EV("b", 0, 1, 1, .25)],
                    2, 1, 1, [1.0, .5], Delta_min=15)


def make_model(masks, penalize=True):
    return build_revised_qubo([1, 1], [1, 1], masks, 1, [1, .5], .25, 5, 5,
                              penalize_unavailable=penalize)


def qubo_for(model):
    return QUBO(model.Q, model.c, {(0, i): i for i in range(model.n)})


def exact(qubo):
    return min((qubo.evaluate(np.array(bits)), bits) for bits in product((0, 1), repeat=qubo.n()))


def evaluate_schedule(case, decisions, masks):
    schedule = {(i, t): decisions[i * 2 + t] for i in range(2) for t in range(2)}
    shifts = {case.evs[i].ev_id: 15 * (2 - int(masks[i]).bit_length()) for i in range(2)}
    return decode_feasibility(case, schedule, realized_early_minutes=shifts)


def earliest_multi_ev(case):
    """Greedy time-first allocation, with ties broken by EV declaration order."""
    decisions = [0] * (len(case.evs) * case.T)
    remaining = [int(np.ceil(ev.E_req_kWh / (ev.P_max_kW * case.Delta_hours))) for ev in case.evs]
    for t in range(case.T):
        load = 0.0
        for i, ev in enumerate(case.evs):
            if ev.a_slot <= t <= ev.d_slot and remaining[i] and load + ev.P_max_kW <= case.P_site_max_kW + 1e-9:
                decisions[i * case.T + t] = 1
                remaining[i] -= 1
                load += ev.P_max_kW
    return tuple(decisions)


def solve_methods(case):
    nominal = qubo_for(make_model([3, 3]))
    buffer = qubo_for(make_model([1, 3]))
    scenario = scenario_qubo_with_recourse([make_model([3, 3], False), make_model([1, 3], False)], [1, 1], "empirical")
    methods = {}
    for name, q in [("F0", nominal), ("F1", scenario), ("F_buffer", buffer)]:
        energy, bits = exact(q)
        methods[name] = {"decisions": tuple(bits[:4]), "energy": energy, "bits": bits, "qubo": q}
    methods["F_early"] = {"decisions": earliest_multi_ev(case)}
    return methods


def run_study():
    case = build_case()
    methods = solve_methods(case)
    scenarios = [(3, 3), (1, 3)]
    output = {"description": "synthetic two-EV, two-slot, 1 kW site; equally weighted modeled scenarios, not historical schedules",
              "scenario_masks": scenarios, "methods": {}, "quantum": {}}
    for name, entry in methods.items():
        metrics = [evaluate_schedule(case, entry["decisions"], masks) for masks in scenarios]
        output["methods"][name] = {"decisions": entry["decisions"],
            "mean_feasibility": float(np.mean([m["feasible"] for m in metrics])),
            "mean_unmet_kWh": float(np.mean([m["unmet_kWh"] for m in metrics])),
            "mean_cost": float(np.mean([m["cost"] for m in metrics])),
            "mean_delivered_kWh": float(np.mean([sum(e["e_delivered_kWh"] for e in m["per_ev"]) for m in metrics])),
            "nominal_energy_cost": float(metrics[0]["cost"]),
            "nominal_site_feasible": bool(metrics[0]["site_feasible"]),
            "exact_qubo_energy": entry.get("energy")}
    for name in ("F0", "F1", "F_buffer"):
        q = methods[name]["qubo"]
        best = methods[name]["energy"]
        ising = qubo_to_ising(q.Q, q.c, q.var_index)
        states = list(product((0, 1), repeat=q.n()))
        assert all(abs(q.evaluate(np.array(bits)) - ising.evaluate(1 - 2 * np.array(bits))) < 1e-8 for bits in states)
        output["quantum"][name] = {"qubits": q.n(), "decision_qubits": 4,
            "slack_qubits": q.n() - 4, "classical_optimum": best, "runs": []}
        for depth in (1, 2):
            circuit, _ = _build_qaoa_ansatz(ising.to_qiskit_op(), depth)
            trans = transpile(circuit, basis_gates=["rz", "sx", "x", "cx"], optimization_level=1, seed_transpiler=0)
            for seed in range(5):
                config = QAOAConfig(name, q.n(), depth, 128, seed, "COBYLA", 12, 1e-5, "small_random")
                run = run_qaoa(q, ising, config)
                records, total = run["sampled_records"], run["sampled_total_count"]
                output["quantum"][name]["runs"].append({"p": depth, "seed": seed, "shots": total,
                    "evals": run["n_function_evals"], "runtime_s": run["runtime_s"],
                    "p_optimal": sum(r["count"] for r in records if abs(r["qubo_energy"] - best) < 1e-8) / total,
                    "p_nominal_physical_feasible": sum(r["count"] for r in records if evaluate_schedule(case, r["x"][:4], (3, 3))["feasible"]) / total,
                    "best_gap": run["best_qubo_energy"] - best,
                    "mean_energy": sum(r["count"] * r["qubo_energy"] for r in records) / total,
                    "transpiled_depth": trans.depth(), "cx": int(trans.count_ops().get("cx", 0))})
    return output


if __name__ == "__main__":
    result = run_study()
    path = Path("artifacts/revised_v2/multi_ev_comparison.json")
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {path}")
