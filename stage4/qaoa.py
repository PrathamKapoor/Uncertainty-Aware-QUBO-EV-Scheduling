"""
Stage 4 — QAOA implementation, exact-solver validation, and baseline quantum experiment.

Implements (per docs/STAGE_4_QAOA.md):
  * QUBO -> Ising Hamiltonian mapping (with full documentation of the convention)
  * Exhaustive Ising-vs-QUBO validation
  * Standard QAOA ansatz (|+\\rangle^\\otimes n, alternating UC(gamma) and UB(beta))
  * Classical parameter optimization (COBYLA baseline, optional SPSA)
  * Multi-seed, multi-depth, multi-shot experiments
  * Aggregate metrics: AR, P(opt), P(feasible) for the four separate feasibility metrics

No noise model, no hardware execution, no adaptive QAOA, no uncertainty.
Token-gated items remain blocked.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Qiskit imports
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector, Operator
from qiskit_aer import AerSimulator
from qiskit_aer.primitives import SamplerV2 as AerSampler
from qiskit_algorithms import QAOA
from qiskit_algorithms.optimizers import COBYLA, SPSA
from qiskit_algorithms.utils import algorithm_globals
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter
from qiskit.circuit.library import PauliEvolutionGate

# ---------------------------------------------------------------------------
# Part C: QUBO -> Ising mapping
# ---------------------------------------------------------------------------
#
# Convention (Part C requirement: "explicitly equivalent convention"):
#   x_i in {0, 1}   <-->   z_i in {-1, +1},   x_i = (1 - z_i) / 2
# Substituting into the QUBO F(x) = x^T Q x + c:
#   F(z) = (1/4) z^T Q z - (1/2) (Q 1) . z + (1/4) 1^T Q 1 + c
# where 1 is the all-ones vector.
#
# In the standard Ising form:  H = sum_{i<j} J_ij Z_i Z_j + sum_i h_i Z_i + offset
#   J_ij (i < j)  =  (1/4) Q_ij
#   h_i           =  -(1/4) (Q_ii + sum_{j != i} Q_ij)   [from expanding Q z z into off-diagonal + diagonal Z terms]
#                   Equivalently:  h_i = -(1/2) * sum_k Q_ik / 2  +  -(1/4) Q_ii  from the linear-in-z term
#   offset        =  (1/4) 1^T Q 1 + c
#
# We document the full derivation in the docstring below and in docs/STAGE_4_QAOA.md.

@dataclass
class IsingModel:
    """Ising Hamiltonian: H(z) = sum_{i<j} J_ij Z_i Z_j + sum_i h_i Z_i + offset."""
    J: np.ndarray  # (n, n) symmetric; only upper triangle used; J_ii is NOT used (Pauli Z_i is i Z_i)
    h: np.ndarray  # (n,)
    offset: float
    var_index: Dict[Tuple[int, int], int]  # QUBO variable -> qubit index (preserved)
    description: Dict[str, Any] = field(default_factory=dict)

    def n(self) -> int:
        return self.h.shape[0]

    def evaluate(self, z: np.ndarray) -> float:
        """Evaluate H(z) for a +/-1 vector z of length n."""
        if z.ndim == 2 and z.shape[1] == 1:
            z = z.ravel()
        quad = 0.0
        for i in range(self.n()):
            for j in range(i + 1, self.n()):
                quad += float(self.J[i, j]) * float(z[i]) * float(z[j])
        # Correct form: 0.5 * z^T J z (using upper triangle) ... but J is stored as the actual coupling
        # strength, so we use a simple sum. Below we use the closed-form for speed.
        # For n=11 (our largest case), 121 entries; fine.
        linear = float(self.h @ z)
        return quad + linear + self.offset

    def to_qiskit_op(self) -> SparsePauliOp:
        """Convert to a Qiskit SparsePauliOp for QAOA.

        We build Z_i Z_j terms and Z_i terms directly. The offset is captured
        by the SparsePauliOp's constant (identity * coefficient).
        """
        n = self.n()
        pauli_list = []
        # Z_i terms
        for i in range(n):
            label = ["I"] * n
            label[n - 1 - i] = "Z"  # Qiskit little-endian
            pauli_list.append(("".join(label), float(self.h[i])))
        # Z_i Z_j terms
        for i in range(n):
            for j in range(i + 1, n):
                if abs(self.J[i, j]) < 1e-15:
                    continue
                label = ["I"] * n
                label[n - 1 - i] = "Z"
                label[n - 1 - j] = "Z"
                pauli_list.append(("".join(label), float(self.J[i, j])))
        if not pauli_list:
            pauli_list = [("I" * n, 0.0)]
        op = SparsePauliOp.from_list(pauli_list)
        return op


def qubo_to_ising(Q: np.ndarray, c: float, var_index: Dict[Tuple[int, int], int]) -> IsingModel:
    """Convert a QUBO F(x) = x^T Q x + c to an Ising H(z).

    Convention: x_i in {0, 1},  z_i in {-1, +1},  x_i = (1 - z_i) / 2.
    Q is symmetric. The QUBO sum is over ordered pairs (i, j), so each
    unordered pair (i < j) appears twice in the QUBO sum.

    Derivation (i == j, i < j cases handled separately to avoid double-counting):
        F = sum_i Q_{ii} x_i + sum_{i<j} 2 Q_{ij} x_i x_j + c    [from symmetric x^T Q x]
        For x_i = (1 - z_i) / 2:
            x_i = 1/2 - z_i/2
            x_i x_j = (1 - z_i - z_j + z_i z_j) / 4
        Plugging in:
            sum_i Q_{ii} (1/2 - z_i/2)
            + sum_{i<j} 2 Q_{ij} (1 - z_i - z_j + z_i z_j) / 4
            + c
          = sum_i Q_{ii}/2 - sum_i (Q_{ii}/2) z_i
            + sum_{i<j} (Q_{ij}/2) - sum_{i<j} (Q_{ij}/2) (z_i + z_j) + sum_{i<j} (Q_{ij}/2) z_i z_j
            + c
        Collect:
            offset = (1/2) sum_i Q_{ii} + (1/2) sum_{i<j} Q_{ij} + c
                   = (1/2) sum_{i,j} Q_{ij} + c
            h_i    = -Q_{ii}/2 - (1/2) sum_{j != i} Q_{ij}
                   = -(1/2) sum_j Q_{ij}                [since Q_{ii} is part of the sum]
            J_{ij} (i < j) = Q_{ij} / 2

    Note: the QUBO sum is over all (i, j) including i < j AND j < i (with the
    same Q_{ij}). Each unordered pair contributes 2 Q_{ij} to F. The Ising J_{ij}
    is for a single unordered pair (i < j), so it is Q_{ij}/2, not Q_{ij}/4.
    """
    Q = np.asarray(Q, dtype=float)
    n = Q.shape[0]
    h = -0.5 * Q.sum(axis=1)  # h_i = -(1/2) sum_j Q_{ij}
    J = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            J[i, j] = 0.5 * Q[i, j]   # NOT 0.25 -- see derivation above
    offset = 0.5 * Q.sum() + c
    return IsingModel(
        J=J,
        h=h,
        offset=float(offset),
        var_index=dict(var_index),
        description={
            "convention": "x_i = (1 - z_i) / 2  with  z_i in {-1, +1}",
            "h_i_formula": "-(1/2) * sum_j Q_ij",
            "J_ij_formula": "(1/2) * Q_ij  (i < j)  -- because the QUBO sum is over ordered pairs (i,j) including both (i,j) and (j,i), so each unordered pair contributes 2*Q_ij to F; the Ising J is for one unordered pair.",
            "offset_formula": "(1/2) * sum_{i,j} Q_ij + c",
        },
    )
def z_to_x(z: np.ndarray) -> np.ndarray:
    """Convert Ising z in {-1, +1}^n to QUBO x in {0, 1}^n via x = (1 - z) / 2."""
    return ((1 - z) // 2).astype(int)

def x_to_z(x: np.ndarray) -> np.ndarray:
    """Convert QUBO x in {0, 1}^n to Ising z in {-1, +1}^n via z = 1 - 2x."""
    return (1 - 2 * x).astype(int)


# ---------------------------------------------------------------------------
# Part D: Exhaustive Ising vs QUBO validation
# ---------------------------------------------------------------------------

def validate_ising_vs_qubo(ising: IsingModel, qubo, tol: float = 1e-7) -> Dict[str, Any]:
    """For every +/-1 vector, verify H_ising(z) = F_qubo(x) + C, where x = (1-z)/2.

    Returns the constant offset and the max deviation.
    """
    n = ising.n()
    diffs = []
    for bits in product([-1, 1], repeat=n):
        z = np.array(bits, dtype=float)
        x = z_to_x(z).astype(float)
        h_ising = ising.evaluate(z)
        f_qubo = qubo.evaluate(x)
        diffs.append(h_ising - f_qubo)
    diffs = np.array(diffs)
    mean_d = float(np.mean(diffs))
    std_d = float(np.std(diffs))
    max_abs = float(np.max(np.abs(diffs - mean_d)))
    return {
        "n_bitstrings": len(diffs),
        "n_qubits": n,
        "mean_offset": mean_d,
        "std_offset": std_d,
        "max_abs_deviation_from_mean": max_abs,
        "tolerance": tol,
        "passes": max_abs < tol,
        "diffs_sample_first5": diffs[:5].tolist(),
        "diffs_sample_last5": diffs[-5:].tolist(),
    }


# ---------------------------------------------------------------------------
# Part E: Standard QAOA
# ---------------------------------------------------------------------------

@dataclass
class QAOAConfig:
    instance_name: str
    n_qubits: int
    p: int
    shots: int
    seed: int
    optimizer: str
    optimizer_max_iter: int
    optimizer_tol: float
    init_strategy: str  # "small_random", "zeros", "fixed_seed"
    description: str = ""

def _build_qaoa_ansatz(cost_op: SparsePauliOp, p: int) -> Tuple[QuantumCircuit, List[Parameter]]:
    """Hand-roll the standard QAOA ansatz with classical measurements.

    H^\\otimes n initial state, then alternating UC(gamma_k) and UB(beta_k) for k=1..p,
    followed by measurement of all qubits into a single classical register.
    Returns (ansatz_circuit, parameter_list). Parameters are ordered
    [gamma_1, ..., gamma_p, beta_1, ..., beta_p].
    """
    n = cost_op.num_qubits
    ansatz = QuantumCircuit(n)
    # Initial state: H^\\otimes n |0> = |+>^\\otimes n
    for q in range(n):
        ansatz.h(q)
    params = []
    for k in range(p):
        gamma = Parameter(f"gamma_{k}")
        beta = Parameter(f"beta_{k}")
        params.extend([gamma, beta])
        # Cost evolution: exp(-i gamma H_C)  (no Trotter error: all Z terms commute)
        evolution = PauliEvolutionGate(cost_op, time=gamma)
        ansatz.append(evolution, range(n))
        # Mixer evolution: exp(-i beta H_B) with H_B = sum_i X_i
        # = R_X(2*beta) on each qubit
        for q in range(n):
            ansatz.rx(2 * beta, q)
    # Measurements: a single classical register 'meas' holding all n bits.
    ansatz.measure_all()
    return ansatz, params


def _expectation_from_counts(counts: Dict[str, int], cost_op: SparsePauliOp, n: int) -> float:
    """Compute the expectation value of cost_op from shot counts.

    For a diagonal cost operator (which is the case for our Ising model: all
    terms are products of Z's, hence diagonal in the computational basis),
    the expectation reduces to a weighted sum of eigenvalues.
    """
    total = sum(counts.values())
    if total == 0:
        return float("nan")
    exp_val = 0.0
    for bitstr, count in counts.items():
        # Convert bitstring (Qiskit little-endian, qubit 0 is rightmost) to a +/-1 vector
        # matching the Ising var_index ordering: our x[k] is the k-th declared variable,
        # which we mapped to qubit k, which is the (len-1-k)-th character of the bitstr.
        # In our construction above, the H^\\otimes n applied to qubit k in declaration order,
        # so the bitstring reading is: bitstr[k-th-from-right] corresponds to qubit k = our x[k].
        # Qiskit's get_counts() returns "qz_m" where rightmost char is qubit 0.
        # So bitstr[len-1-k] is our x[k].
        z = np.array([1 if bitstr[len(bitstr) - 1 - k] == '0' else -1 for k in range(n)])
        # Compute the cost_op eigenvalue for this z (since all terms are diagonal in Z)
        e = 0.0
        for pauli, coeff in zip(cost_op.paulis, cost_op.coeffs):
            label = str(pauli)
            # label uses Qiskit little-endian: 'IXY...' where the rightmost is qubit 0
            # The eigenvalue of a Z on qubit k is z[k] (where z is the +/-1 vector indexed by k)
            ev = 1
            for q in range(n):
                ch = label[len(label) - 1 - q]  # qubit q's character
                if ch == 'Z':
                    ev *= z[q]
                elif ch == 'X' or ch == 'Y':
                    ev = 0  # not diagonal, term vanishes in computational basis
                    break
            e += float(np.real(coeff)) * ev
        exp_val += (count / total) * e
    return float(exp_val)


def run_qaoa(qubo, ising: IsingModel, config: QAOAConfig,
             callback: Optional[Callable[[np.ndarray, float], None]] = None) -> Dict[str, Any]:
    """Run a single QAOA experiment with the given configuration.

    Hand-rolled standard QAOA: H^\\otimes n initial state, alternating
    UC(gamma_k) = exp(-i gamma_k H_C) and UB(beta_k) = exp(-i beta_k H_B)
    with H_B = sum_i X_i. Parameters ordered (gamma_1..p, beta_1..p).

    Returns a dict with: final_params, final_expectation, best_bitstring,
    best_qubo_energy, best_ising_energy, sampled_records, optimization_history.
    """
    from qiskit import transpile
    from qiskit.circuit import Parameter
    from qiskit.circuit.library import PauliEvolutionGate
    algorithm_globals.random_seed = config.seed
    n = ising.n()
    cost_op = ising.to_qiskit_op()
    # Build the QAOA ansatz
    ansatz_template, ansatz_params = _build_qaoa_ansatz(cost_op, config.p)
    # Transpile to Aer's basis gates
    basis_gates = ["rz", "sx", "x", "cx"]
    ansatz_transpiled_template = transpile(ansatz_template, basis_gates=basis_gates, optimization_level=1, seed_transpiler=config.seed)
    # Optimizer
    if config.optimizer == "COBYLA":
        from scipy.optimize import minimize as scipy_minimize
        optimizer_name = "COBYLA"
    elif config.optimizer == "SPSA":
        optimizer_name = "SPSA"
    else:
        raise ValueError(f"Unknown optimizer {config.optimizer}")
    # Sampler
    sampler = AerSampler(seed=config.seed)
    # Initial parameters
    if config.init_strategy == "small_random":
        rng = np.random.default_rng(config.seed)
        init_params = rng.uniform(-0.1, 0.1, size=2 * config.p).tolist()
    elif config.init_strategy == "zeros":
        init_params = [0.0] * (2 * config.p)
    elif config.init_strategy == "fixed_seed":
        init_params = [0.1 * (i + 1) for i in range(2 * config.p)]
    else:
        raise ValueError(f"Unknown init_strategy {config.init_strategy}")
    # Parameter binding helper
    def bind(params):
        d = {p: float(v) for p, v in zip(ansatz_params, params)}
        return ansatz_transpiled_template.assign_parameters(d)
    # Optimization loop: compute <H_C> for each candidate (gamma, beta) by sampling
    history = []
    def objective(params):
        circ = bind(params)
        job = sampler.run([circ], shots=config.shots)
        res = job.result()
        # Extract counts
        try:
            pub_result = res[0]
            counts = {}
            if hasattr(pub_result, "data"):
                data = pub_result.data
                if hasattr(data, "meas"):
                    counts = dict(data.meas.get_counts())
                else:
                    for attr in ["c0", "c1", "c2", "c3"]:
                        if hasattr(data, attr):
                            counts = dict(getattr(data, attr).get_counts())
                            break
            if not counts and hasattr(pub_result, "quasi_dists"):
                quasi = pub_result.quasi_dists[0]
                counts = {k: int(round(v * config.shots)) for k, v in quasi.items()}
        except Exception:
            counts = {}
        val = _expectation_from_counts(counts, cost_op, n)
        history.append({"eval": len(history), "value": float(val), "params": [float(p) for p in params]})
        if callback is not None:
            callback(np.array(params), float(val))
        return float(val)
    t0 = time.time()
    from scipy.optimize import minimize as scipy_minimize
    res = scipy_minimize(objective, init_params, method="COBYLA",
                        options={"maxiter": config.optimizer_max_iter, "tol": config.optimizer_tol,
                                  "rhobeg": 0.05, "disp": False, "catol": 0.002})
    runtime_s = time.time() - t0
    final_params = [float(p) for p in res.x]
    final_expectation = float(res.fun)
    # Final sampling at the optimal parameters
    circ = bind(final_params)
    job = sampler.run([circ], shots=config.shots)
    final_res = job.result()
    # Extract counts
    counts = {}
    try:
        pub_result = final_res[0]
        if hasattr(pub_result, "data"):
            data = pub_result.data
            if hasattr(data, "meas"):
                counts = dict(data.meas.get_counts())
            else:
                for attr in ["c0", "c1", "c2", "c3"]:
                    if hasattr(data, attr):
                        counts = dict(getattr(data, attr).get_counts())
                        break
        if not counts and hasattr(pub_result, "quasi_dists"):
            quasi = pub_result.quasi_dists[0]
            counts = {k: int(round(v * config.shots)) for k, v in quasi.items()}
    except Exception:
        counts = {}
    # Decode bitstrings (Qiskit little-endian: rightmost char is qubit 0)
    best_qubo_energy = float("inf")
    best_ising_energy = float("inf")
    best_bitstring = None
    sampled_records = []
    for bitstr, count in counts.items():
        # Qiskit bitstring rightmost char = qubit 0; our x[k] = bit at qubit k
        bits = bitstr[::-1]  # reverse so position k corresponds to our x[k]
        if len(bits) != n:
            continue
        x = np.array([int(b) for b in bits], dtype=int)
        z = x_to_z(x)
        f_qubo = float(qubo.evaluate(x.astype(float)))
        h_ising = float(ising.evaluate(z.astype(float)))
        sampled_records.append({"bitstring": bitstr, "x": x.tolist(), "z": z.tolist(),
                                "count": int(count), "qubo_energy": f_qubo, "ising_energy": h_ising})
        if f_qubo < best_qubo_energy:
            best_qubo_energy = f_qubo
            best_ising_energy = h_ising
            best_bitstring = bitstr
    sampled_records.sort(key=lambda r: r["qubo_energy"])
    return {
        "config": asdict_safe(config),
        "runtime_s": runtime_s,
        "n_function_evals": len(history),
        "final_params": final_params,
        "final_expectation": final_expectation,
        "best_bitstring": best_bitstring,
        "best_qubo_energy": best_qubo_energy,
        "best_ising_energy": best_ising_energy,
        "sampled_records": sampled_records,
        "sampled_total_count": sum(r["count"] for r in sampled_records),
        "optimization_history": history,
    }


def asdict_safe(obj):
    if hasattr(obj, "__dict__"):
        d = dict(obj.__dict__)
    else:
        d = dict(obj)
    return d


# ---------------------------------------------------------------------------
# Part H: Multi-seed driver
# ---------------------------------------------------------------------------

def run_multi_seed(qubo, ising: IsingModel, instance_name: str, n_qubits: int,
                   p: int, shots: int, seeds: Sequence[int],
                   optimizer: str = "COBYLA", max_iter: int = 200, tol: float = 1e-6,
                   init_strategy: str = "small_random") -> Dict[str, Any]:
    """Run QAOA with multiple seeds and aggregate results."""
    runs = []
    for seed in seeds:
        cfg = QAOAConfig(
            instance_name=instance_name,
            n_qubits=n_qubits,
            p=p,
            shots=shots,
            seed=int(seed),
            optimizer=optimizer,
            optimizer_max_iter=max_iter,
            optimizer_tol=tol,
            init_strategy=init_strategy,
            description=f"seed={seed} p={p} shots={shots}",
        )
        out = run_qaoa(qubo, ising, cfg)
        runs.append(out)
    # Aggregate
    bests = [r["best_qubo_energy"] for r in runs]
    return {
        "instance_name": instance_name,
        "n_qubits": n_qubits,
        "p": p,
        "shots": shots,
        "n_seeds": len(seeds),
        "seeds": list(seeds),
        "optimizer": optimizer,
        "max_iter": max_iter,
        "init_strategy": init_strategy,
        "per_seed": runs,
        "aggregate": {
            "best_qubo_energy_mean": float(np.mean(bests)),
            "best_qubo_energy_std": float(np.std(bests)),
            "best_qubo_energy_median": float(np.median(bests)),
            "best_qubo_energy_best": float(np.min(bests)),
            "best_qubo_energy_worst": float(np.max(bests)),
        },
    }


# ---------------------------------------------------------------------------
# Part I/J: AR, P(opt), P(feasible) from a single QAOA run
# ---------------------------------------------------------------------------

def compute_metrics(qaoa_result: Dict[str, Any], qubo_optimum: float, inst,
                    use_offset: bool = True) -> Dict[str, Any]:
    """Compute approximation ratio, P(opt), P(feasible) for a QAOA run.

    qubo_optimum is the exact QUBO optimum (from Stage 3 enumeration).
    AR = F_QAOA / F_opt. The QUBO energy is computed directly on each sample,
    so the Ising's constant offset is already absorbed and no offset correction
    is needed.
    """
    from stage3.ev_scheduling import decode_feasibility
    sr = qaoa_result["sampled_records"]
    total = qaoa_result["sampled_total_count"]
    if total == 0:
        return {"error": "no_samples"}
    best_qubo = qaoa_result["best_qubo_energy"]
    ar = best_qubo / qubo_optimum if qubo_optimum != 0 else float("nan")
    delta_f = best_qubo - qubo_optimum
    # P(opt): fraction of shots that achieved a qubo_energy within tol of optimum
    tol = 1e-9
    n_opt = sum(1 for r in sr if abs(r["qubo_energy"] - qubo_optimum) < tol)
    p_opt = n_opt / total
    # P(feasible): fraction of shots that produced a feasible schedule
    # Use the refactored decode_feasibility (the four separate metrics).
    keys = list(inst.var_index().keys())
    n_qubo_f = 0; n_energy_f = 0; n_site_f = 0; n_deadline_f = 0; n_all_f = 0
    for r in sr:
        x_list = r["x"]
        n_match = min(len(x_list), len(keys))
        x_dict = {keys[k]: int(x_list[k]) for k in range(n_match)}
        f = decode_feasibility(inst, x_dict)
        n_all_f += int(f["feasible"])
        n_qubo_f += int(f["qubo_feasible"])
        n_energy_f += int(f["energy_feasible"])
        n_site_f += int(f["site_feasible"])
        n_deadline_f += int(f["deadline_feasible"])
    p_feasible = n_all_f / total
    p_qubo_feasible = n_qubo_f / total
    p_energy_feasible = n_energy_f / total
    p_site_feasible = n_site_f / total
    p_deadline_feasible = n_deadline_f / total
    return {
        "best_qubo_energy": best_qubo,
        "qubo_optimum": qubo_optimum,
        "approximation_ratio": float(ar),
        "absolute_gap": float(delta_f),
        "n_shots_total": int(total),
        "n_optimum_samples": int(n_opt),
        "P_opt": float(p_opt),
        "P_feasible": float(p_feasible),
        "P_qubo_feasible": float(p_qubo_feasible),
        "P_energy_feasible": float(p_energy_feasible),
        "P_site_feasible": float(p_site_feasible),
        "P_deadline_feasible": float(p_deadline_feasible),
    }


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

def run_stage4(toy_specs=("toy_A_2x4", "toy_B_3x4"),
               p_values=(1, 2), shot_values=(256, 1024, 4096), seeds=(0, 1, 2, 3, 4),
               rho_d=1.0, rho_p=0.1, rho_cap=0.5) -> Dict[str, Any]:
    """Run the full Stage 4 battery: Ising validation + QAOA multi-seed/depth/shot."""
    from stage3.ev_scheduling import toy_instance, build_qubo, find_optima, enumerate_original_objective
    out = {
        "stage": "Stage 4",
        "rho_d": rho_d, "rho_p": rho_p, "rho_cap": rho_cap,
        "ising_validation": {},
        "qaoa_results": {},
        "depth_results": {},
        "shot_results": {},
        "seed_results": {},
    }
    for name in toy_specs:
        N, T = {"toy_A_2x4": (2, 4), "toy_B_3x4": (3, 4)}[name]
        inst = toy_instance(name, N=N, T=T)
        qubo = build_qubo(inst, rho_d, rho_p, rho_cap)
        ising = qubo_to_ising(qubo.Q, qubo.c, qubo.var_index)
        # Ising validation
        iv = validate_ising_vs_qubo(ising, qubo)
        out["ising_validation"][name] = {
            "n_qubits": ising.n(),
            **iv,
        }
        # Exact optimum
        enum = enumerate_original_objective(inst, rho_d, rho_p, rho_cap)
        opts = find_optima(enum)
        qubo_optimum = opts[0]["objective"]
        out["qaoa_results"][name] = {
            "n_qubits": ising.n(),
            "qubo_optimum": qubo_optimum,
        }
        # Run depth and shot sweeps
        for p in p_values:
            for shots in shot_values:
                ms = run_multi_seed(qubo, ising, name, ising.n(), p, shots, seeds)
                # Compute per-seed metrics
                per_seed_metrics = []
                for r in ms["per_seed"]:
                    m = compute_metrics(r, qubo_optimum, inst)
                    per_seed_metrics.append({"seed": r["config"]["seed"], **m})
                # Aggregate
                ars = [m["approximation_ratio"] for m in per_seed_metrics]
                p_opts = [m["P_opt"] for m in per_seed_metrics]
                p_feas = [m["P_feasible"] for m in per_seed_metrics]
                rec = {
                    "instance": name,
                    "p": p,
                    "shots": shots,
                    "n_seeds": len(seeds),
                    "per_seed": per_seed_metrics,
                    "aggregate": {
                        "P_opt_mean": float(np.mean(p_opts)),
                        "P_opt_std": float(np.std(p_opts)),
                        "P_opt_median": float(np.median(p_opts)),
                        "P_feasible_mean": float(np.mean(p_feas)),
                        "P_feasible_std": float(np.std(p_feas)),
                        "P_feasible_median": float(np.median(p_feas)),
                        "AR_mean": float(np.mean(ars)),
                        "AR_std": float(np.std(ars)),
                        "AR_median": float(np.median(ars)),
                        "AR_best": float(np.min(ars)),
                        "AR_worst": float(np.max(ars)),
                    },
                }
                out["shot_results"].setdefault(name, {}).setdefault(str(p), {})[str(shots)] = rec
                out["depth_results"].setdefault(name, {}).setdefault(str(shots), {})[str(p)] = rec
                out["seed_results"].setdefault(name, {})[f"p{p}_shots{shots}"] = rec
    return out


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=str, default="artifacts/stage4_run.json")
    p.add_argument("--toy", nargs="+", default=["toy_A_2x4", "toy_B_3x4"])
    p.add_argument("--p", nargs="+", type=int, default=[1, 2])
    p.add_argument("--shots", nargs="+", type=int, default=[256, 1024, 4096])
    p.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    p.add_argument("--rho_d", type=float, default=1.0)
    p.add_argument("--rho_p", type=float, default=0.1)
    p.add_argument("--rho_cap", type=float, default=0.5)
    args = p.parse_args()
    result = run_stage4(tuple(args.toy), tuple(args.p), tuple(args.shots), tuple(args.seeds),
                        args.rho_d, args.rho_p, args.rho_cap)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {args.out}")
    # Summary
    for name, iv in result["ising_validation"].items():
        print(f"  {name} Ising validation: passes={iv['passes']} max_dev={iv['max_abs_deviation_from_mean']:.2e}")
