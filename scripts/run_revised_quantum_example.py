"""Run the exploratory synthetic 2-EV example; no ACN observations are used."""
import json
import platform
import importlib.metadata
import sys
import subprocess
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from qiskit import transpile
from scheduling.ev_scheduling import QUBO
from scheduling.revised_qubo import build_revised_qubo
from quantum.qaoa import QAOAConfig, _build_qaoa_ansatz, qubo_to_ising, run_qaoa


def main():
    out = Path("artifacts/revised_v2")
    out.mkdir(parents=True, exist_ok=True)
    model = build_revised_qubo([1, 1], [1, 1], [3, 3], 1, [0.5, 1.0], 1, 5, 5)
    experiment_config = {"version": "revised_v2_synthetic_pilot", "scope": "exploratory",
                         "power_kW": [1, 1], "required_slots": [1, 1],
                         "availability_masks": [3, 3], "capacity_kW": 1,
                         "price_per_kWh": [0.5, 1.0], "slot_hours": 1,
                         "energy_penalty": 5, "capacity_penalty": 5,
                         "qaoa": {"depths": [1, 2], "shots": 256, "seeds": [0, 1], "optimizer": "COBYLA", "maxiter": 20}}
    (out / "experiment_config.json").write_text(json.dumps(experiment_config, indent=2), encoding="utf-8")
    index = {(0, i): i for i in range(model.n)}
    qubo = QUBO(model.Q, model.c, index)
    ising = qubo_to_ising(model.Q, model.c, index)
    energies = [(qubo.evaluate(np.array(bits)), bits) for bits in product((0, 1), repeat=model.n)]
    optimum = min(e for e, _ in energies)
    def feasible(x):
        return (x[0] + x[1] == 1 and x[2] + x[3] == 1
                and x[0] + x[2] <= 1 and x[1] + x[3] <= 1)
    runs = []
    for depth in (1, 2):
        circuit, _ = _build_qaoa_ansatz(ising.to_qiskit_op(), depth)
        (out / f"circuit_p{depth}.txt").write_text(str(circuit.draw(output="text")), encoding="utf-8")
        for seed in (0, 1):
            compiled = transpile(circuit, basis_gates=["rz", "sx", "x", "cx"], optimization_level=1, seed_transpiler=seed)
            config = QAOAConfig("synthetic_2ev", model.n, depth, 256, seed, "COBYLA", 20, 1e-5, "small_random")
            run = run_qaoa(qubo, ising, config)
            records = run["sampled_records"]
            total = run["sampled_total_count"]
            runs.append({"p": depth, "seed": seed, "qaoa": run,
                         "p_optimal": sum(r["count"] for r in records if abs(r["qubo_energy"] - optimum) < 1e-8) / total,
                         "p_physical_feasible": sum(r["count"] for r in records if feasible(r["x"])) / total,
                         "sampled_mean_energy": sum(r["count"] * r["qubo_energy"] for r in records) / total,
                         "transpiled_depth": compiled.depth(), "transpiled_cx": compiled.count_ops().get("cx", 0)})
    result = {"scope": "exploratory synthetic example; no ACN observations or quantum hardware",
              "python": platform.python_version(),
              "source_base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
              "dependencies": {p: importlib.metadata.version(p) for p in ("numpy", "scipy", "qiskit", "qiskit-aer")},
              "qubits": model.n,
              "classical_optimum": optimum, "runs": runs}
    (out / "synthetic_quantum_example.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"classical_optimum": optimum, "runs": [{k: v for k, v in r.items() if k != "qaoa"} for r in runs]}, indent=2))


if __name__ == "__main__":
    main()
