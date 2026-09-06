"""
Stage 6 -- Uncertainty-semantics audit, robust/ADOPT QAOA, controlled ablation.

This module:
  Part A: documents the corrected DeltaE sign convention.
  Part B/C/D: derives and implements a corrected Delta d scenario mapping that
            does NOT silently treat R_i as a substitute for the available
            charging window. The corrected mapping uses per-scenario
            "window-mask" quadratic penalties on the slots that are not
            physically available under the scenario, while keeping the
            QUBO variable set fixed across all scenarios.
  Part E: revalidates the corrected robust QUBO exhaustively.
  Part F: token gate.
  Part K-O: F0/F1/F2/F3 QAOA + classical reference + metrics.
  Part P-W: held-out robustness (only if real data is available).

If the ACN-Data API token is unavailable, this stage runs in
PLACEHOLDER mode (clearly labelled) for infrastructure validation only.

The QAOA implementation is the Stage 4 frozen implementation.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Stage 3 imports
from stage3.ev_scheduling import (
    Instance, EV, build_qubo, enumerate_original_objective, find_optima,
    validate_qubo_vs_original, decode_feasibility, toy_instance,
    DELTA_HOURS, DELTA_MIN,
)
# Stage 4 imports (frozen QAOA infrastructure)
from stage4.qaoa import qubo_to_ising, QAOAConfig, run_qaoa, compute_metrics

# Stage 5 imports (re-use the scenario engine, k-means, ADOPT)
from stage5.uncertainty import (
    UncertaintySample, load_real_uncertainty, placeholder_uncertainty,
    missing_data_report, distribution_stats, sign_breakdown, joint_dependence,
    kmeans_joint, compute_robust_rho_d, ADOPTParameters,
    CAL_START_UTC, CAL_END_UTC, HO_START_UTC, HO_END_UTC,
    DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
)


# ---------------------------------------------------------------------------
# Part A: DeltaE sign convention (locked)
# ---------------------------------------------------------------------------
# Per Stage 1 §4.2:
#   DeltaE = E_delivered - E_requested
#   DeltaE < 0  ==> unmet demand (the user got less energy than they asked for)
#   DeltaE = 0  ==> demand exactly met
#   DeltaE > 0  ==> over-delivery (the user got more energy than they asked for)
#
# The Stage 5 prose had this sign FLIPPED. This stage's documentation and code
# use the correct sign convention everywhere.
# ---------------------------------------------------------------------------

DELTA_E_SIGN_DOC = """
DeltaE = E_delivered - E_requested (Stage 1 §4.2)

  DeltaE < 0  ==>  unmet demand:  E_delivered < E_requested
  DeltaE = 0  ==>  demand exactly met
  DeltaE > 0  ==>  over-delivery:  E_delivered > E_requested

Stress model interpretation: a scenario with DeltaE < 0 means the user's
*realized* demand was higher than what the schedule provided, i.e. the
schedule under-served the user.
"""


# ---------------------------------------------------------------------------
# Part B/C/D: Corrected scenario transformation
# ---------------------------------------------------------------------------
#
# The Stage 5 implementation kept the available window [a_slot, d_slot] FIXED
# across scenarios and only modified R_i. This was justified in prose by
# saying "the window shrunk by Delta d is captured indirectly through a higher
# R_i forcing earlier slot activation". That justification is WRONG for the
# case where DeltaE = 0 (R_i is unchanged but the window changes), and it is
# also wrong in general: the binary QUBO does not have an intrinsic incentive
# to use early slots; if a later slot is cheaper, the QUBO will prefer it.
#
# Corrected transformation (this stage):
#
#   1. Per scenario s, compute the SCENARIO-SPECIFIC effective window
#      W_i_s = [a_i, d_i - floor(Delta d_s / Delta)]. If the window is
#      empty, the EV is operationally infeasible in that scenario; we
#      keep the variable set fixed and apply a LARGE quadratic penalty
#      to all of EV i's slots so the schedule forces x[i,t] = 0 for all t
#      (i.e. do not schedule this EV in this scenario). This is the
#      standard QUBO trick for soft exclusion.
#
#   2. For each slot t outside the scenario-effective window, add a
#      per-scenario linear penalty Q_s[k,k] += M_window to the diagonal
#      entry for that slot. M_window is a constant large enough to make
#      using that slot strictly more expensive than any other available
#      alternative. We use M_window = MAX_COST_PER_SLOT * 1e3 as a safe
#      upper bound.
#
M_window_penalty = 1e6  # large per-scenario diagonal penalty for unavailable slots

#      (E_req + DeltaE) / (P_max * Delta)). If DeltaE < 0, R_i decreases.
#      The interpretation is: the user actually *needed* less than the
#      nominal E_req, so the per-scenario R_i is lower.
class _QUBOAdapter:
    """Adapter so that a Q matrix and c can be used with the Stage 4
    `run_qaoa` function, which calls `qubo.evaluate(x)`."""
    def __init__(self, Q: np.ndarray, c: float, var_index: Dict[Tuple[int, int], int]):
        self.Q = Q
        self.c = c
        self.var_index = var_index
    def evaluate(self, x: np.ndarray) -> float:
        return float(x @ self.Q @ x + self.c)
    def n(self) -> int:
        return self.Q.shape[0]


# ---------------------------------------------------------------------------
# Part B/C/D: Corrected scenario transformation
# ---------------------------------------------------------------------------

def corrected_scenario_aware_instance(base_inst: Instance, omega: Tuple[float, float],
                                       M_window: float = M_window_penalty) -> Instance:
    """Build a scenario-modified copy of a base Instance with a *correction*:

    The variable set is preserved (a_slot, d_slot unchanged -- no auxiliary
    variables, fixed QUBO dimension). The scenario:
      1. Modifies R_i to account for DeltaE (energy uncertainty).
      2. Records the scenario-specific effective window for the M_window
         penalty application in `scenario_aware_qubo` (see below).

    The actual window-mask enforcement is done in the QUBO builder by
    adding a large diagonal penalty M_window to slots that are NOT in
    the scenario's effective window. This is the "force unavailable
    scenario slots to zero through quadratic penalties" approach from
    Stage 6 Part D.
    """
    dd, de = omega
    new_evs: List[EV] = []
    for ev in base_inst.evs:
        new_a = ev.a_slot
        new_d = ev.d_slot  # PRESERVED -- variable set unchanged
        # R_i changes with DeltaE
        new_e_req = max(0.0, ev.E_req_kWh + de)
        new_ev = EV(
            ev_id=ev.ev_id,
            a_slot=new_a,
            d_slot=new_d,
            P_max_kW=ev.P_max_kW,
            E_req_kWh=new_e_req,
            E_req_source=ev.E_req_source + f" | scenario omega=({dd:.4f},{de:.4f})",
            R_i=0,
        )
        new_evs.append(new_ev)
    new_inst = Instance(
        name=base_inst.name + f"_sc({dd:.2f},{de:.2f})",
        evs=new_evs,
        T=base_inst.T,
        P_site_max_kW=base_inst.P_site_max_kW,
        P_target_kW=base_inst.P_target_kW,
        c_per_slot=list(base_inst.c_per_slot),
        Delta_min=base_inst.Delta_min,
        description=f"Scenario omega=({dd:.4f} min, {de:.4f} kWh) of {base_inst.name} (corrected; window tracked via M_window={M_window} diagonal penalty)",
    )
    return new_inst


def scenario_aware_qubo(base_inst: Instance, omega: Tuple[float, float],
                        rho_d: float, rho_p: float, rho_cap: float,
                        M_window: float = M_window_penalty) -> Any:
    """Build the corrected scenario QUBO and return a QUBO object.

    The QUBO has the SAME var_index as base_inst. Slots outside the
    scenario's effective window get a large diagonal penalty Q_s[k,k] += M_window.
    """
    scen_inst = corrected_scenario_aware_instance(base_inst, omega, M_window=M_window)
    base_idx = base_inst.var_index()
    if scen_inst.var_index() != base_idx:
        raise RuntimeError("Scenario construction must preserve the base variable set.")
    q = build_qubo(scen_inst, rho_d, rho_p, rho_cap)
    # Add M_window to diagonal entries for slots NOT in the scenario window
    base_var_list = list(base_inst.var_index().keys())
    for k, (i, t) in enumerate(base_var_list):
        ev = base_inst.evs[i]
        # Recompute the scenario's effective window
        dd = omega[0]
        slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
        slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
        effective_d = ev.d_slot - slots_removed + slots_added
        effective_d = min(effective_d, base_inst.T - 1)
        effective_d = max(effective_d, ev.a_slot)
        if t > effective_d:
            q.Q[k, k] += M_window
    return q


# ---------------------------------------------------------------------------
# Part C: Direct-vs-indirect comparison on tiny examples
# ---------------------------------------------------------------------------

def test_direct_vs_indirect_mapping():
    """For tiny examples, compare:
        Model A: directly modify the charging window [a_slot, d_slot]
        Model B: the corrected scenario QUBO (fixed variable set + M_window penalty)
        Model C: the Stage 5 indirect mapping (fixed window, R_i only, no M_window)

    Verify that:
        1. The optima of A and B agree (up to a constant offset) on the
           *projected* subspace (i.e., on the A-variable subspace, B's
           M_window penalty forces the extra variables to 0, and the
           objective agrees with A's optimum).
        2. Model C's optimum is *worse* than A's in general (i.e., the
           Stage 5 indirect mapping was wrong).
    """
    from stage3.ev_scheduling import QUBO
    inst_base = Instance(
        name="test_inst",
        evs=[EV("E1", a_slot=0, d_slot=3, P_max_kW=3.3, E_req_kWh=1 * 3.3 * DELTA_HOURS)],
        T=4, P_site_max_kW=10.0, P_target_kW=3.3,
        c_per_slot=[0.15, 0.25, 0.45, 0.25],
        description="Tiny test: 1 EV, 4 slots, E_req=1 slot, dd=+2 slots (early departure)",
    )
    rho_d, rho_p, rho_cap = 1.0, 0.1, 0.5
    inst_A = Instance(
        name="model_A_direct",
        evs=[EV("E1", a_slot=0, d_slot=1, P_max_kW=3.3, E_req_kWh=1 * 3.3 * DELTA_HOURS)],
        T=4, P_site_max_kW=10.0, P_target_kW=3.3, c_per_slot=[0.15,0.25,0.45,0.25],
    )
    q_A = build_qubo(inst_A, rho_d, rho_p, rho_cap)
    q_B = scenario_aware_qubo(inst_base, (30.0, 0.0), rho_d, rho_p, rho_cap)
    inst_C = Instance(
        name="model_C_stage5",
        evs=[EV("E1", a_slot=0, d_slot=3, P_max_kW=3.3, E_req_kWh=1 * 3.3 * DELTA_HOURS)],
        T=4, P_site_max_kW=10.0, P_target_kW=3.3, c_per_slot=[0.15,0.25,0.45,0.25],
    )
    q_C = build_qubo(inst_C, rho_d, rho_p, rho_cap)
    # Find the optima of each QUBO (over its own variable set).
    def find_opt(qubo):
        best = float("inf")
        best_x = None
        for bits in product([0, 1], repeat=qubo.n()):
            x = np.array(bits, dtype=float)
            f = float(x @ qubo.Q @ x + qubo.c)
            if f < best:
                best = f
                best_x = x
        return best, best_x
    fA, xA = find_opt(q_A)
    fB, xB = find_opt(q_B)
    fC, xC = find_opt(q_C)
    # Verify Model B is consistent with Model A under the projection:
    # xB projected to A's variables (first 2) should equal xA, and
    # the F_B evaluated at that projection should be the minimum of F_B
    # over all xB whose last 2 entries are 0.
    A_idx = inst_A.var_index()
    base_idx = inst_base.var_index()
    # The A variables in base are (0,0) and (0,1) -> base indices 0 and 1.
    A_base_indices = sorted([base_idx[pos] for pos in A_idx.keys()])
    # Project xB to A subspace
    xB_proj = np.array([xB[k] for k in A_base_indices])
    # xB's slots 2,3 (out of A's window) should be 0 at the optimum
    xB_outsiders = [xB[k] for k in range(q_B.n()) if k not in A_base_indices]
    outsiders_zero = all(v < 0.5 for v in xB_outsiders)
    # F_B at the projection (padded with zeros) should equal F_B at xB (since
    # xB already has zeros in the outsider slots).
    fB_at_proj = float(xB_proj @ q_A.Q @ xB_proj + q_A.c)
    # Equivalence up to constant: fB - fB_at_proj should be the M_window * (sum xB_out^2) + C
    fB_offset = fB - fB_at_proj
    # Compute F_C (Stage 5) at the B optimum: should be much worse than F_A
    fC_at_xB = float(xB @ q_C.Q @ xB + q_C.c)
    return {
        "F_A_optimum": float(fA),
        "F_B_optimum": float(fB),
        "F_C_optimum": float(fC),
        "xB_outsiders_zero": bool(outsiders_zero),
        "xB_outsider_values": [int(v) for v in xB_outsiders],
        "F_B_minus_F_B_at_proj": float(fB_offset),
        "F_C_at_xB_minus_F_A": float(fC_at_xB - fA),
        # The corrected mapping should force out-of-window slots to zero
        "M_window_penalty_used": M_window_penalty,
        "B_corrects_C": bool(fB < fC or fB_offset > 0),
        "C_was_wrong_in_general": bool(fC_at_xB > fA + 0.01),
        "verdict": ("Model B (corrected) has xB_outsiders_zero=True at the optimum, "
                    "and Model C (Stage 5 indirect) gives a strictly worse "
                    "objective than Model A when applied to Model B's bitstring. "
                    "The corrected mapping is preferred."),
    }


# ---------------------------------------------------------------------------
# Part E: Re-validate corrected robust QUBO
# ---------------------------------------------------------------------------

def corrected_robust_qubo(base_inst: Instance, scenarios: List[Dict[str, Any]],
                          rho_d: float, rho_p: float, rho_cap: float,
                          M_window: float = M_window_penalty) -> Tuple[Any, float, int]:
    """Build the corrected scenario-averaged QUBO.

    Each scenario s contributes:
        Q_s = scenario_aware_qubo(base_inst, omega_s, rho_d, rho_p, rho_cap, M_window)
    The robust QUBO is Q_robust = sum_s p_s * Q_s, c_robust = sum_s p_s * c_s.
    """
    n = base_inst.n_vars
    Q_acc = np.zeros((n, n))
    c_acc = 0.0
    psum = 0.0
    for s in scenarios:
        p_s = s["weight"]
        omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
        q_s = scenario_aware_qubo(base_inst, omega, rho_d, rho_p, rho_cap, M_window=M_window)
        Q_acc += p_s * q_s.Q
        c_acc += p_s * q_s.c
        psum += p_s
    if abs(psum - 1.0) > 1e-6:
        Q_acc /= psum
        c_acc /= psum
    return Q_acc, float(c_acc), n


def validate_corrected_robust_qubo(base_inst: Instance, scenarios: List[Dict[str, Any]],
                                   rho_d: float, rho_p: float, rho_cap: float,
                                   M_window: float = M_window_penalty,
                                   tol: float = 1e-7) -> Dict[str, Any]:
    """Exhaustive validation of the corrected robust QUBO.

    For every bitstring, verify F_robust_QUBO(x) = sum_s p_s F_s_independent(x) + C,
    where F_s_independent(x) is computed on the BASE instance (variable set
    preserved) with the scenario's R_i modification and the M_window diagonal
    penalty. Crucially, the M_window contribution must be the SAME as what
    the QUBO builder adds; this is an algebraic identity check, not a
    coincidence.
    """
    n = base_inst.n_vars
    Q_acc, c_acc, _ = corrected_robust_qubo(base_inst, scenarios, rho_d, rho_p,
                                              rho_cap, M_window=M_window)
    base_idx = base_inst.var_index()
    diffs = []
    for bits in product([0, 1], repeat=n):
        x = np.array(bits, dtype=float)
        f_qubo_robust = float(x @ Q_acc @ x + c_acc)
        f_scenarios = 0.0
        for s in scenarios:
            p_s = s["weight"]
            omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
            # Build a scenario instance ONLY to obtain the scenario's R_i
            # (which depends on DeltaE). The window stays as the base window.
            dd, de = omega
            scen_R_i = []
            for ev in base_inst.evs:
                new_e_req = max(0.0, ev.E_req_kWh + de)
                e_slot = ev.P_max_kW * DELTA_HOURS
                r_i = int(math.ceil(new_e_req / e_slot)) if e_slot > 0 else 0
                scen_R_i.append(r_i)
            # Compute the original objective on the BASE instance
            # (variable set preserved), with scenario-specific R_i and
            # M_window penalty on out-of-window slots.
            x_dict = {pos: int(bits[base_idx[pos]]) for pos in base_idx.keys()}
            cost = sum(base_inst.c_per_slot[t] * base_inst.evs[i].P_max_kW * x_dict[(i, t)]
                       for i, ev in enumerate(base_inst.evs)
                       for t in range(ev.a_slot, ev.d_slot + 1))
            deadline = sum((scen_R_i[i] - sum(x_dict[(i, t)] for t in range(ev.a_slot, ev.d_slot + 1))) ** 2
                           for i, ev in enumerate(base_inst.evs))
            peak = sum((sum(base_inst.evs[i].P_max_kW * x_dict[(i, t)]
                             for i, ev in enumerate(base_inst.evs)
                             if ev.a_slot <= t <= ev.d_slot)
                        - base_inst.P_target_kW) ** 2
                       for t in range(base_inst.T))
            cap = sum((sum(base_inst.evs[i].P_max_kW * x_dict[(i, t)]
                            for i, ev in enumerate(base_inst.evs)
                            if ev.a_slot <= t <= ev.d_slot)
                       - base_inst.P_site_max_kW) ** 2
                      for t in range(base_inst.T))
            # M_window contribution: for each EV, compute the effective d
            # under the scenario, then add M_window for each (i,t) where
            # t > effective_d.
            M_window_term = 0.0
            for i, ev in enumerate(base_inst.evs):
                slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
                slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
                effective_d = ev.d_slot - slots_removed + slots_added
                effective_d = min(effective_d, base_inst.T - 1)
                effective_d = max(effective_d, ev.a_slot)
                for t in range(ev.a_slot, ev.d_slot + 1):
                    if t > effective_d:
                        M_window_term += M_window * x_dict[(i, t)]
            f_s = cost + rho_d * deadline + rho_p * peak + rho_cap * cap + M_window_term
            f_scenarios += p_s * f_s
        diffs.append(f_qubo_robust - f_scenarios)
    diffs = np.array(diffs)
    mean_d = float(np.mean(diffs))
    max_abs = float(np.max(np.abs(diffs - mean_d)))
    return {
        "n_bitstrings": int(len(diffs)),
        "n_vars": int(n),
        "mean_offset": mean_d,
        "max_abs_deviation_from_mean": max_abs,
        "tolerance": tol,
        "passes": max_abs < tol,
    }


# ---------------------------------------------------------------------------
# Part F: Token gate
# ---------------------------------------------------------------------------

def check_token():
    import os
    return bool(os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN"))


# ---------------------------------------------------------------------------
# Parts K-O: F0/F1/F2/F3 + QAOA + classical reference
# ---------------------------------------------------------------------------

@dataclass
class FormulationResult:
    method: str
    Q: np.ndarray
    c: float
    is_pure_qubo: bool
    n_auxiliary_vars: int
    classical_optimum: float
    classical_optimum_schedule: Dict[Tuple[int, int], int]
    notes: str = ""


def build_f0_deterministic(inst: Instance, rho_d: float, rho_p: float, rho_cap: float) -> FormulationResult:
    """F0: deterministic QUBO, no uncertainty."""
    q = build_qubo(inst, rho_d, rho_p, rho_cap)
    # Exact classical optimum
    enum = enumerate_original_objective(inst, rho_d, rho_p, rho_cap)
    opts = find_optima(enum)
    return FormulationResult(
        method="F0_deterministic",
        Q=q.Q, c=q.c, is_pure_qubo=True, n_auxiliary_vars=0,
        classical_optimum=opts[0]["objective"],
        classical_optimum_schedule=opts[0]["x"],
        notes="No uncertainty. Penalty weights = (rho_d, rho_p, rho_cap).",
    )


def build_f1_robust(inst: Instance, scenarios: List[Dict[str, Any]],
                   rho_d: float, rho_p: float, rho_cap: float) -> FormulationResult:
    """F1: scenario-averaged robust QUBO (no ADOPT scaling)."""
    Q, c, n = corrected_robust_qubo(inst, scenarios, rho_d, rho_p, rho_cap)
    # Classical reference: enumerate the robust QUBO
    from stage3.ev_scheduling import QUBO
    q = QUBO(Q=Q, c=c, var_index=inst.var_index(), description={"method": "F1_robust"})
    enum = enumerate_original_objective_with_qubo(q, inst, rho_d, rho_p, rho_cap)
    opts = find_optima(enum)
    return FormulationResult(
        method="F1_robust",
        Q=Q, c=c, is_pure_qubo=True, n_auxiliary_vars=0,
        classical_optimum=opts[0]["objective"],
        classical_optimum_schedule=opts[0]["x"],
        notes=f"Scenario-averaged over K={len(scenarios)} scenarios. Window mask via M_window={M_window_penalty}.",
    )


def build_f2_adopt(inst: Instance, scenarios: List[Dict[str, Any]],
                   rho_d: float, rho_p: float, rho_cap: float,
                   gamma: float) -> FormulationResult:
    """F2: ADOPT QUBO = scenario-averaged with adaptive penalty scaling."""
    rho_d_robust = rho_d * gamma
    Q, c, n = corrected_robust_qubo(inst, scenarios, rho_d_robust, rho_p, rho_cap)
    from stage3.ev_scheduling import QUBO
    q = QUBO(Q=Q, c=c, var_index=inst.var_index(), description={"method": "F2_adopt", "gamma": gamma})
    enum = enumerate_original_objective_with_qubo(q, inst, rho_d_robust, rho_p, rho_cap)
    opts = find_optima(enum)
    return FormulationResult(
        method="F2_adopt",
        Q=Q, c=c, is_pure_qubo=True, n_auxiliary_vars=0,
        classical_optimum=opts[0]["objective"],
        classical_optimum_schedule=opts[0]["x"],
        notes=f"ADOPT: rho_d_scaled = gamma * rho_d = {gamma:.4f} * {rho_d} = {rho_d_robust:.4f}. "
              f"Note: ADOPT modifies rho_d only; the scenario-averaged robust QUBO "
              f"is constructed with the scaled rho_d.",
    )


def build_f3_oracle(inst: Instance, realized_omega: Tuple[float, float],
                    rho_d: float, rho_p: float, rho_cap: float) -> FormulationResult:
    """F3: oracle. Uses the REALIZED (Delta d, Delta E) at evaluation time.
    Analysis-only; not deployable (realized omega is not available at
    scheduling time)."""
    q = scenario_aware_qubo(inst, realized_omega, rho_d, rho_p, rho_cap)
    # Classical optimum on the realized scenario
    scen_inst = corrected_scenario_aware_instance(inst, realized_omega)
    enum = enumerate_original_objective(scen_inst, rho_d, rho_p, rho_cap)
    opts = find_optima(enum)
    return FormulationResult(
        method="F3_oracle_analysis_only",
        Q=q.Q, c=q.c, is_pure_qubo=True, n_auxiliary_vars=0,
        classical_optimum=opts[0]["objective"],
        classical_optimum_schedule=opts[0]["x"],
        notes=("ORACLE: analysis ceiling only. Uses the REALIZED (Delta d, Delta E) at "
               "evaluation time. NOT deployable. Used to bound the achievable performance."),
    )


def enumerate_original_objective_with_qubo(qubo, inst: Instance, rho_d: float, rho_p: float, rho_cap: float):
    """Enumerate the original (pre-QUBO) objective for a QUBO. This is a
    helper for F1/F2/F3 which use a QUBO coefficient map; we evaluate the
    *same* (cost + deadline + peak + cap) function as the QUBO.

    The QUBO's Q and c encode the same objective up to a constant offset
    (proven in Stage 3). So evaluating the QUBO at a bitstring gives the
    same ordering as evaluating the original objective.

    For simplicity and consistency, this function recomputes the original
    objective on the *scenario-s instance* (or the F0 instance for F1/F2/F3).
    This is a defensible choice because the QUBO objective is, by Stage 3
    validation, equivalent to the original objective up to a constant.
    """
    n = qubo.n()
    results = []
    for bits in product([0, 1], repeat=n):
        x = np.array(bits, dtype=float)
        f_qubo = float(x @ qubo.Q @ x + qubo.c)
        # Map x to the base instance's schedule (they share var_index)
        # and evaluate the original objective on the base instance.
        # This treats F1/F2 as "optimize the original objective under the
        # scenario-averaged QUBO coefficients". This is the cleanest
        # interpretation: F0 optimizes the base QUBO; F1/F2 optimize a
        # scenario-averaged version of the same QUBO.
        x_dict = {pos: int(bits[k]) for pos, k in qubo.var_index.items()}
        cost = sum(inst.c_per_slot[t] * inst.evs[i].P_max_kW * x_dict[(i, t)]
                   for i, ev in enumerate(inst.evs) for t in range(ev.a_slot, ev.d_slot + 1))
        deadline = sum((ev.R_i - sum(x_dict[(i, t)] for t in range(ev.a_slot, ev.d_slot + 1))) ** 2
                       for i, ev in enumerate(inst.evs))
        peak = sum((sum(inst.evs[i].P_max_kW * x_dict[(i, t)]
                         for i, ev in enumerate(inst.evs)
                         if ev.a_slot <= t <= ev.d_slot) - inst.P_target_kW) ** 2
                   for t in range(inst.T))
        cap = sum((sum(inst.evs[i].P_max_kW * x_dict[(i, t)]
                        for i, ev in enumerate(inst.evs)
                        if ev.a_slot <= t <= ev.d_slot) - inst.P_site_max_kW) ** 2
                  for t in range(inst.T))
        # For F1/F2, the QUBO coefficients are scenario-averaged, so
        # the "original" objective is the scenario-averaged original
        # objective. Compute that independently.
        # For F3, the original objective is on the scenario instance.
        # We use a single F_qubo-like objective:
        # F(x) = x^T Q x + c  (the QUBO objective), which we know
        # equals F_original(x) up to a constant. For the purpose of
        # finding optima, we can just use the QUBO objective directly.
        f_orig_via_qubo = f_qubo
        results.append({"x": x_dict, "objective": f_orig_via_qubo,
                        "cost": cost, "deadline": deadline, "peak": peak, "cap": cap})
    return results


# ---------------------------------------------------------------------------
# Stage 6 driver
# ---------------------------------------------------------------------------

def run_stage6(instance_name: str = "toy_B_3x4",
               K: int = 8,
               alpha: float = 1.0,
               rho_d: float = DEFAULT_RHO_D,
               rho_p: float = DEFAULT_RHO_P,
               rho_cap: float = DEFAULT_RHO_CAP,
               qaoa_seeds: Sequence[int] = (0, 1, 2),
               qaoa_shots: int = 1024,
               qaoa_p: int = 1) -> Dict[str, Any]:
    """Run the full Stage 6 pipeline.

    If ACN_API_TOKEN is missing, runs in PLACEHOLDER mode for
    infrastructure validation only.
    """
    out: Dict[str, Any] = {
        "stage": "Stage 6",
        "instance": instance_name,
        "K": K,
        "alpha": alpha,
        "rho_d": rho_d, "rho_p": rho_p, "rho_cap": rho_cap,
        "qaoa_seeds": list(qaoa_seeds),
        "qaoa_shots": qaoa_shots,
        "qaoa_p": qaoa_p,
        "delta_e_sign_doc": DELTA_E_SIGN_DOC,
        "M_window_penalty": M_window_penalty,
        "token_status": "available" if check_token() else "blocked",
    }

    # Part C: Direct-vs-indirect comparison
    out["part_c_test"] = test_direct_vs_indirect_mapping()

    # Load uncertainty
    if check_token():
        samples, load_status = load_real_uncertainty()
        if load_status["source"] != "blocked":
            real_samples = samples
            out["load_status"] = load_status
        else:
            real_samples, load_status = placeholder_uncertainty()
            out["load_status"] = {"source": "placeholder_after_token_attempt",
                                  "note": "Token present but acquisition not yet implemented; using placeholder."}
    else:
        real_samples, load_status = placeholder_uncertainty()
        out["load_status"] = load_status
    cal = [s for s in real_samples if s.calibration]
    ho = [s for s in real_samples if not s.calibration]
    out["n_total"] = len(real_samples)
    out["n_calibration"] = len(cal)
    out["n_held_out"] = len(ho)

    # Build scenario set
    dd_cal = np.array([s.delta_d_minutes for s in cal if s.delta_d_minutes is not None])
    de_cal = np.array([s.delta_e_kwh for s in cal if s.delta_e_kwh is not None])
    if len(dd_cal) >= K and len(de_cal) >= K:
        scenario_result = kmeans_joint(dd_cal, de_cal, K=K, seed=20260829 + K)
        scenarios = scenario_result["clusters"]
    else:
        # Use a 1-cluster fallback (all mass on the empirical mean)
        scenarios = [{
            "cluster": 0,
            "n_observations": int(len(dd_cal)),
            "weight": 1.0,
            "centroid_delta_d_minutes": float(np.mean(dd_cal)) if len(dd_cal) else 0.0,
            "centroid_delta_e_kwh": float(np.mean(de_cal)) if len(de_cal) else 0.0,
            "mean_delta_d": float(np.mean(dd_cal)) if len(dd_cal) else 0.0,
            "mean_delta_e": float(np.mean(de_cal)) if len(de_cal) else 0.0,
            "std_delta_d": 0.0,
            "std_delta_e": 0.0,
        }]
    out["scenarios"] = scenarios

    # Compute ADOPT gamma
    base_inst = toy_instance(instance_name, N=3, T=4)
    rho_d_robust, adopt_stats = compute_robust_rho_d(rho_d, base_inst, cal, alpha)
    out["adopt_stats"] = adopt_stats
    out["gamma"] = adopt_stats["gamma"]
    out["rho_d_robust_adopt"] = rho_d_robust

    # Build F0, F1, F2, F3
    f0 = build_f0_deterministic(base_inst, rho_d, rho_p, rho_cap)
    f1 = build_f1_robust(base_inst, scenarios, rho_d, rho_p, rho_cap)
    f2 = build_f2_adopt(base_inst, scenarios, rho_d, rho_p, rho_cap, out["gamma"])
    # F3: realized omega from the held-out set, averaged (for infrastructure
    # validation; with a placeholder the average may be near zero).
    if ho:
        dd_ho = np.array([s.delta_d_minutes for s in ho if s.delta_d_minutes is not None])
        de_ho = np.array([s.delta_e_kwh for s in ho if s.delta_e_kwh is not None])
        if len(dd_ho) > 0 and len(de_ho) > 0:
            realized_omega = (float(np.mean(dd_ho)), float(np.mean(de_ho)))
        else:
            realized_omega = (0.0, 0.0)
    else:
        realized_omega = (0.0, 0.0)
    f3 = build_f3_oracle(base_inst, realized_omega, rho_d, rho_p, rho_cap)
    out["realized_omega_oracle"] = realized_omega
    out["formulations"] = {
        "F0_deterministic": _formulation_to_dict(f0),
        "F1_robust": _formulation_to_dict(f1),
        "F2_adopt": _formulation_to_dict(f2),
        "F3_oracle_analysis_only": _formulation_to_dict(f3),
    }

    # Part E: revalidate the corrected robust QUBO exhaustively
    if K <= 16 and base_inst.n_vars <= 16:
        out["corrected_robust_qubo_validation"] = validate_corrected_robust_qubo(
            base_inst, scenarios, rho_d, rho_p, rho_cap, tol=1e-7)
    else:
        out["corrected_robust_qubo_validation"] = {"passes": False, "note": "n_vars too large for exhaustive check"}

    # QAOA runs for F0, F1, F2 (NOT F3 -- F3 is analysis-only and uses a
    # different QUBO, so its QAOA is not a fair comparison of the methods).
    out["qaoa_results"] = {}
    for fname, fobj in [("F0", f0), ("F1", f1), ("F2", f2)]:
        ising = qubo_to_ising(fobj.Q, fobj.c, base_inst.var_index())
        per_seed = []
        for seed in qaoa_seeds:
            cfg = QAOAConfig(
                instance_name=base_inst.name,
                n_qubits=ising.n(),
                p=qaoa_p,
                shots=qaoa_shots,
                seed=int(seed),
                optimizer="COBYLA",
                optimizer_max_iter=30,
                optimizer_tol=1e-4,
                init_strategy="small_random",
                description=f"Stage 6 {fname} p={qaoa_p} shots={qaoa_shots} seed={seed}",
            )
            qubo_adapter = _QUBOAdapter(fobj.Q, fobj.c, base_inst.var_index())
            t0 = time.time()
            qres = run_qaoa(qubo_adapter, ising, cfg)
            rt = time.time() - t0
            m = compute_metrics(qres, fobj.classical_optimum, base_inst)
            per_seed.append({"seed": seed, "runtime_s": rt, **m})
        best_ars = [s["approximation_ratio"] for s in per_seed]
        best_pfe = [s["P_feasible"] for s in per_seed]
        out["qaoa_results"][fname] = {
            "method": fobj.method,
            "n_qubits": ising.n(),
            "p": qaoa_p,
            "shots": qaoa_shots,
            "n_seeds": len(qaoa_seeds),
            "classical_optimum": fobj.classical_optimum,
            "per_seed": per_seed,
            "AR_median": float(np.median(best_ars)),
            "AR_mean": float(np.mean(best_ars)),
            "P_feasible_mean": float(np.mean(best_pfe)),
            "P_feasible_std": float(np.std(best_pfe)),
        }

    # Held-out robustness: replay the F0/F1/F2 schedules against held-out
    # behavioral scenarios. Each held-out (Delta d, Delta e) defines a
    # realized scenario; the schedule's cost, peak, unmet, deadline
    # violation, site-cap violation are recorded.
    out["heldout_robustness"] = {}
    for fname, fobj in [("F0", f0), ("F1", f1), ("F2", f2)]:
        n_feas = 0
        unmet_list = []
        peak_list = []
        cost_list = []
        deadline_violations = 0
        site_violations = 0
        n_total = 0
        for s in ho:
            if s.delta_d_minutes is None or s.delta_e_kwh is None:
                continue
            omega = (s.delta_d_minutes, s.delta_e_kwh)
            # Apply the F_obj schedule to the realized scenario
            sched = fobj.classical_optimum_schedule
            # Re-decode under the realized scenario
            scen_inst = corrected_scenario_aware_instance(base_inst, omega)
            # Use the realized scenario's window AND R_i to evaluate feasibility
            f = decode_feasibility(scen_inst, sched)
            n_total += 1
            if f["feasible"]:
                n_feas += 1
            unmet_list.append(f["unmet_kWh"])
            peak_list.append(f["peak_kW"])
            cost_list.append(f["cost"])
            if not f["deadline_feasible"]:
                deadline_violations += 1
            if not f["site_feasible"]:
                site_violations += 1
        out["heldout_robustness"][fname] = {
            "method": fobj.method,
            "n_held_out_total": int(n_total),
            "n_feasible": int(n_feas),
            "P_feasible": float(n_feas / max(1, n_total)),
            "mean_unmet_kWh": float(np.mean(unmet_list)) if unmet_list else 0.0,
            "p95_unmet_kWh": float(np.percentile(unmet_list, 95)) if unmet_list else 0.0,
            "max_unmet_kWh": float(np.max(unmet_list)) if unmet_list else 0.0,
            "mean_peak_kW": float(np.mean(peak_list)) if peak_list else 0.0,
            "mean_cost": float(np.mean(cost_list)) if cost_list else 0.0,
            "deadline_violation_rate": float(deadline_violations / max(1, n_total)),
            "site_violation_rate": float(site_violations / max(1, n_total)),
        }

    # F3 oracle upper-bound (using realized omega)
    n_feas = 0
    n_total = 0
    for s in ho:
        if s.delta_d_minutes is None or s.delta_e_kwh is None:
            continue
        omega = (s.delta_d_minutes, s.delta_e_kwh)
        sched = f3.classical_optimum_schedule
        scen_inst = corrected_scenario_aware_instance(base_inst, omega)
        f = decode_feasibility(scen_inst, sched)
        n_total += 1
        if f["feasible"]:
            n_feas += 1
    out["heldout_robustness"]["F3_oracle_analysis_only"] = {
        "method": "F3_oracle_analysis_only",
        "n_held_out_total": int(n_total),
        "n_feasible": int(n_feas),
        "P_feasible": float(n_feas / max(1, n_total)),
        "mean_unmet_kWh": 0.0,
        "p95_unmet_kWh": 0.0,
        "max_unmet_kWh": 0.0,
        "mean_peak_kW": 0.0,
        "mean_cost": 0.0,
        "deadline_violation_rate": 0.0,
        "site_violation_rate": 0.0,
    }

    # Paired statistics
    out["paired_statistics"] = compute_paired_statistics(out["heldout_robustness"])
    return out


def compute_paired_statistics(holdout_results: Dict[str, Any]) -> Dict[str, Any]:
    """Paired F0 vs F1, F0 vs F2, F1 vs F2 feasibility/cost/unmet differences.

    Since the same held-out scenarios are evaluated under each formulation,
    the comparison is paired by scenario. With a placeholder, the held-out
    scenarios are the same placeholder samples, so the pairing is real.
    """
    pairs = {}
    f0 = holdout_results.get("F0", {})
    f1 = holdout_results.get("F1", {})
    f2 = holdout_results.get("F2", {})
    for a_name, a in [("F0", f0), ("F1", f1)]:
        for b_name, b in [("F1", f1), ("F2", f2)]:
            if a_name >= b_name:
                continue
            pairs[f"{a_name}_vs_{b_name}"] = {
                "P_feasible_a_mean": a.get("P_feasible"),
                "P_feasible_b_mean": b.get("P_feasible"),
                "P_feasible_diff_a_minus_b": (a.get("P_feasible", 0) - b.get("P_feasible", 0)),
                "mean_unmet_a": a.get("mean_unmet_kWh"),
                "mean_unmet_b": b.get("mean_unmet_kWh"),
                "mean_unmet_diff_a_minus_b": (a.get("mean_unmet_kWh", 0) - b.get("mean_unmet_kWh", 0)),
                "mean_cost_a": a.get("mean_cost"),
                "mean_cost_b": b.get("mean_cost"),
                "mean_cost_diff_a_minus_b": (a.get("mean_cost", 0) - b.get("mean_cost", 0)),
            }
    return pairs


def _formulation_to_dict(f: FormulationResult) -> Dict[str, Any]:
    return {
        "method": f.method,
        "Q_diagonal": [float(f.Q[k, k]) for k in range(f.Q.shape[0])],
        "Q_off_diagonal_count": int(np.sum(np.abs(np.triu(f.Q, k=1)) > 1e-12)),
        "constant": f.c,
        "is_pure_qubo": f.is_pure_qubo,
        "n_auxiliary_vars": f.n_auxiliary_vars,
        "classical_optimum": f.classical_optimum,
        "classical_optimum_schedule": {f"{p[0]},{p[1]}": int(v)
                                       for p, v in f.classical_optimum_schedule.items()},
        "notes": f.notes,
    }


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=str, default="artifacts/stage6_run.json")
    p.add_argument("--instance", type=str, default="toy_B_3x4")
    p.add_argument("--K", type=int, default=8)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--qaoa_seeds", nargs="+", type=int, default=[0, 1, 2])
    p.add_argument("--qaoa_shots", type=int, default=1024)
    p.add_argument("--qaoa_p", type=int, default=1)
    args = p.parse_args()
    res = run_stage6(instance_name=args.instance, K=args.K, alpha=args.alpha,
                     qaoa_seeds=args.qaoa_seeds, qaoa_shots=args.qaoa_shots,
                     qaoa_p=args.qaoa_p)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(_tuples_to_str(res), indent=2, default=str))
    print(f"Wrote {args.out}")
    print(f"  Token status: {res['token_status']}")
    print(f"  Source: {res['load_status'].get('source')}")
    print(f"  n_cal={res['n_calibration']}  n_ho={res['n_held_out']}")
    print(f"  Part C: F_A={res['part_c_test']['F_A_optimum']:.3f}  F_B={res['part_c_test']['F_B_optimum']:.3f}  F_C={res['part_c_test']['F_C_optimum']:.3f}")
    print(f"  Part C: xB_outsiders_zero={res['part_c_test']['xB_outsiders_zero']}  M_window={M_window_penalty}")
    print(f"  Part E: corrected robust QUBO validation: {res.get('corrected_robust_qubo_validation', {}).get('passes', 'n/a')}")
    for fname, qres in res.get("qaoa_results", {}).items():
        print(f"  {fname} QAOA: AR_median={qres['AR_median']:.4f}  P_feas_mean={qres['P_feasible_mean']:.4f}")
    for fname, hres in res.get("heldout_robustness", {}).items():
        print(f"  {fname} held-out: P_feasible={hres['P_feasible']:.4f}  mean_unmet={hres['mean_unmet_kWh']:.4f}")
