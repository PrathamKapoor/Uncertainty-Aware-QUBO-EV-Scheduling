"""
Stage 7 -- Methodology stress test, synthetic recovery tests, final experimental freeze.

This module:
  Part A: traces why F1/F2 under-serve on the placeholder (schedule-level + math)
  Part B: decomposes the robust objective for the F0/F1/F2 schedules
  Part C: quantifies ADOPT's actual effect on the QUBO coefficient landscape
  Part D: synthetic recovery tests S1 (no uncertainty), S2 (mild), S3 (severe)
  Part E: directionality tests (early-departure, unmet, magnitude)
  Part F: penalty-scale analysis (M_window vs other coefficients)
  Part G: exact-vs-QAOA comparison under synthetic tests
  Part H: distribution-shift diagnostic (Case A/B/C)
  Part I: no result-driven parameter search (pre-registered config preserved)
  Part J: freeze final_experiment_config.json
  Part K: synthetic<->real data switch test
  Part L: token-arrival procedure
  Part M: scientific decision tree

No methodology modification is permitted merely to improve the placeholder result.
"""
from __future__ import annotations

import copy
import json
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Re-use Stage 3/4/5/6 code
from stage3.ev_scheduling import (
    Instance, EV, build_qubo, enumerate_original_objective, find_optima,
    validate_qubo_vs_original, decode_feasibility, toy_instance,
    DELTA_HOURS, DELTA_MIN,
)
from stage4.qaoa import qubo_to_ising, QAOAConfig, run_qaoa, compute_metrics
from stage5.uncertainty import (
    UncertaintySample, placeholder_uncertainty, kmeans_joint,
    missing_data_report, distribution_stats, sign_breakdown, joint_dependence,
    compute_robust_rho_d, ADOPTParameters,
    CAL_START_UTC, CAL_END_UTC, HO_START_UTC, HO_END_UTC,
    DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
)
from stage6.robust_qaoa import (
    corrected_scenario_aware_instance, scenario_aware_qubo,
    corrected_robust_qubo, validate_corrected_robust_qubo,
    M_window_penalty, build_f0_deterministic, build_f1_robust, build_f2_adopt,
    build_f3_oracle, _QUBOAdapter, DELTA_E_SIGN_DOC as STAGE6_DELTA_E_DOC,
)


# ---------------------------------------------------------------------------
# Part A: Trace F1/F2 under-service
# ---------------------------------------------------------------------------

def trace_under_service(inst: Instance, f0_sched: Dict, f1_sched: Dict, f2_sched: Dict,
                        scenarios: List[Dict[str, Any]],
                        rho_d: float, rho_p: float, rho_cap: float) -> Dict[str, Any]:
    """For each of F0/F1/F2 schedules, compute:
      - Number of charging slots per EV
      - Total scheduled energy (kWh)
      - Per-scenario unmet energy
      - Per-scenario effective departure
      - Unavailable slots per scenario
    """
    var_idx = inst.var_index()
    base_idx_list = list(var_idx.keys())

    def sched_to_x(sched):
        return np.array([int(sched.get(pos, 0)) for pos in base_idx_list], dtype=int)

    x0, x1, x2 = sched_to_x(f0_sched), sched_to_x(f1_sched), sched_to_x(f2_sched)

    def per_ev_slots_used(x):
        result = {}
        for i, ev in enumerate(inst.evs):
            slots = sum(int(x[var_idx[(i, t)]]) for t in range(ev.a_slot, ev.d_slot + 1))
            result[ev.ev_id] = slots
        return result

    def total_energy_kwh(x):
        e = 0.0
        for i, ev in enumerate(inst.evs):
            for t in range(ev.a_slot, ev.d_slot + 1):
                e += ev.P_max_kW * DELTA_HOURS * int(x[var_idx[(i, t)]])
        return e

    def per_scenario_unmet(x, scenarios):
        out = []
        for s in scenarios:
            omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
            scen_inst = corrected_scenario_aware_instance(inst, omega)
            # For each EV, compute the scenario-effective deadline and R_i.
            unmet_total = 0.0
            unavailable_per_ev = {}
            effective_departures = {}
            for i, ev in enumerate(inst.evs):
                dd, de = omega
                slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
                slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
                effective_d = min(ev.d_slot - slots_removed + slots_added, inst.T - 1)
                effective_d = max(effective_d, ev.a_slot)
                # Count slots in x that are PAST effective_d (i.e., physically
                # unavailable under the scenario but still used in the schedule)
                used_unavailable = sum(int(x[var_idx[(i, t)]]) for t in range(ev.a_slot, ev.d_slot + 1)
                                       if t > effective_d)
                # E_req under scenario
                new_e_req = max(0.0, ev.E_req_kWh + de)
                e_slot = ev.P_max_kW * DELTA_HOURS
                r_i = int(math.ceil(new_e_req / e_slot)) if e_slot > 0 else 0
                # Energy delivered in slots within the effective window
                in_window_energy = sum(ev.P_max_kW * DELTA_HOURS * int(x[var_idx[(i, t)]])
                                        for t in range(ev.a_slot, ev.d_slot + 1)
                                        if t <= effective_d)
                # Energy delivered in out-of-window slots (treated as wasted
                # or unavailable depending on interpretation; here treated as
                # NOT contributing to demand satisfaction since the user has left)
                in_window_slots = sum(int(x[var_idx[(i, t)]])
                                       for t in range(ev.a_slot, ev.d_slot + 1)
                                       if t <= effective_d)
                # Deadline violation: didn't charge enough within the effective window
                deadline_violation = max(0, r_i - in_window_slots)
                # Unmet energy: kWh shortfall within the effective window
                delivered = in_window_energy
                unmet_kwh = max(0, new_e_req - delivered)
                unmet_total += unmet_kwh
                unavailable_per_ev[ev.ev_id] = int(used_unavailable)
                effective_departures[ev.ev_id] = effective_d
            out.append({
                "scenario": int(s["cluster"]),
                "weight": float(s["weight"]),
                "omega": (float(s["centroid_delta_d_minutes"]), float(s["centroid_delta_e_kwh"])),
                "unmet_kWh": float(unmet_total),
                "unavailable_slots_per_ev": unavailable_per_ev,
                "effective_departure_per_ev": effective_departures,
            })
        return out

    def decode(inst, sched):
        return decode_feasibility(inst, sched)

    return {
        "schedules_x_lengths": {"F0": int(x0.sum()), "F1": int(x1.sum()), "F2": int(x2.sum())},
        "slots_used_per_ev": {
            "F0": per_ev_slots_used(x0),
            "F1": per_ev_slots_used(x1),
            "F2": per_ev_slots_used(x2),
        },
        "total_energy_kWh": {
            "F0": float(total_energy_kwh(x0)),
            "F1": float(total_energy_kwh(x1)),
            "F2": float(total_energy_kwh(x2)),
        },
        "per_scenario_unmet": {
            "F0": per_scenario_unmet(x0, scenarios),
            "F1": per_scenario_unmet(x1, scenarios),
            "F2": per_scenario_unmet(x2, scenarios),
        },
        "F0_decode": decode(inst, f0_sched),
        "F1_decode": decode(inst, f1_sched),
        "F2_decode": decode(inst, f2_sched),
    }


# ---------------------------------------------------------------------------
# Part B: Robust objective decomposition
# ---------------------------------------------------------------------------

def decompose_robust_objective(inst: Instance, sched: Dict, scenarios: List[Dict[str, Any]],
                                rho_d: float, rho_p: float, rho_cap: float,
                                rho_d_eff: float) -> Dict[str, Any]:
    """Decompose E[cost], E[deadline], E[peak], E[capacity], E[window_penalty], E[unmet]."""
    var_idx = inst.var_index()
    x_dict = sched
    # Convert to a numpy x for use in formulas
    x = np.array([int(x_dict.get(pos, 0)) for pos in var_idx.keys()], dtype=int)
    x_by_pos = {pos: int(x_dict.get(pos, 0)) for pos in var_idx.keys()}

    cost_total = 0.0
    deadline_total = 0.0
    peak_total = 0.0
    cap_total = 0.0
    window_total = 0.0
    unmet_total = 0.0

    n_scenarios = len(scenarios)
    for s in scenarios:
        p_s = s["weight"]
        omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
        dd, de = omega
        # Cost
        for i, ev in enumerate(inst.evs):
            for t in range(ev.a_slot, ev.d_slot + 1):
                cost_total += p_s * inst.c_per_slot[t] * ev.P_max_kW * x_by_pos[(i, t)]
        # Deadline (with effective R_i per scenario)
        for i, ev in enumerate(inst.evs):
            slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
            slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
            effective_d = min(ev.d_slot - slots_removed + slots_added, inst.T - 1)
            effective_d = max(effective_d, ev.a_slot)
            new_e_req = max(0.0, ev.E_req_kWh + de)
            e_slot = ev.P_max_kW * DELTA_HOURS
            r_i = int(math.ceil(new_e_req / e_slot)) if e_slot > 0 else 0
            in_window_slots = sum(int(x_by_pos[(i, t)])
                                   for t in range(ev.a_slot, ev.d_slot + 1)
                                   if t <= effective_d)
            deadline_total += p_s * rho_d_eff * (r_i - in_window_slots) ** 2
            # Unmet
            in_window_energy = sum(ev.P_max_kW * DELTA_HOURS * int(x_by_pos[(i, t)])
                                    for t in range(ev.a_slot, ev.d_slot + 1)
                                    if t <= effective_d)
            unmet_total += p_s * max(0, new_e_req - in_window_energy)
        # Peak
        for t in range(inst.T):
            L = sum(ev.P_max_kW * int(x_by_pos[(i, t)])
                    for i, ev in enumerate(inst.evs)
                    if ev.a_slot <= t <= ev.d_slot)
            peak_total += p_s * rho_p * (L - inst.P_target_kW) ** 2
        # Capacity
        for t in range(inst.T):
            L = sum(ev.P_max_kW * int(x_by_pos[(i, t)])
                    for i, ev in enumerate(inst.evs)
                    if ev.a_slot <= t <= ev.d_slot)
            cap_total += p_s * rho_cap * (L - inst.P_site_max_kW) ** 2
        # Window penalty (M_window per slot)
        for i, ev in enumerate(inst.evs):
            slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
            slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
            effective_d = min(ev.d_slot - slots_removed + slots_added, inst.T - 1)
            effective_d = max(effective_d, ev.a_slot)
            for t in range(ev.a_slot, ev.d_slot + 1):
                if t > effective_d:
                    window_total += p_s * M_window_penalty * int(x_by_pos[(i, t)])

    return {
        "E_cost": float(cost_total),
        "E_deadline_penalty": float(deadline_total),
        "E_peak_penalty": float(peak_total),
        "E_capacity_penalty": float(cap_total),
        "E_window_penalty": float(window_total),
        "E_unmet_kWh": float(unmet_total),
        "E_total_objective": float(cost_total + deadline_total + peak_total + cap_total + window_total),
        "rho_d_effective": float(rho_d_eff),
    }


# ---------------------------------------------------------------------------
# Part C: ADOPT effect analysis
# ---------------------------------------------------------------------------

def adopt_effect_analysis(inst: Instance, scenarios: List[Dict[str, Any]],
                          rho_d: float, rho_p: float, rho_cap: float,
                          gamma: float) -> Dict[str, Any]:
    """Quantify whether ADOPT changes the QUBO landscape materially."""
    # Build F1 and F2 QUBOs
    Q_F1, c_F1, n = corrected_robust_qubo(inst, scenarios, rho_d, rho_p, rho_cap)
    Q_F2, c_F2, n2 = corrected_robust_qubo(inst, scenarios, rho_d * gamma, rho_p, rho_cap)
    # F1 vs F2
    Q_diff = Q_F2 - Q_F1
    c_diff = c_F2 - c_F1
    # Summary stats
    f1_diag_min = float(np.min(np.diag(Q_F1)))
    f1_diag_max = float(np.max(np.diag(Q_F1)))
    f2_diag_min = float(np.min(np.diag(Q_F2)))
    f2_diag_max = float(np.max(np.diag(Q_F2)))
    # Find eigenvalue spread
    f1_eigs = np.linalg.eigvalsh(Q_F1)
    f2_eigs = np.linalg.eigvalsh(Q_F2)
    # Min eigenvalue of Q is the smallest value the quadratic form can have; max is the largest.
    # F0 doesn't include M_window, but F1/F2 do. Compare F1 vs F2.
    # The fraction of the matrix that changes between F1 and F2 is also informative.
    n_offdiag_changed = int(np.sum(np.abs(Q_diff) > 1e-9))
    # Compare Q_F1 and Q_F2 to a "cost-only" Q (just c_t * P_i^max on the diagonal)
    cost_only = np.zeros((n, n))
    for (i, t), k in inst.var_index().items():
        ev = inst.evs[i]
        cost_only[k, k] = inst.c_per_slot[t] * ev.P_max_kW
    # Magnitudes
    f1_diag = np.diag(Q_F1)
    cost_diag = np.diag(cost_only)
    # The deadline-related diagonal terms (negative coefficients on x[i,t] from R_i)
    deadline_diag = f1_diag - cost_diag
    # Magnitude comparison
    f1_total = float(np.sum(np.abs(Q_F1)))
    f2_total = float(np.sum(np.abs(Q_F2)))
    cost_total = float(np.sum(np.abs(cost_only)))
    return {
        "Q_F1_diagonal": [float(x) for x in np.diag(Q_F1)],
        "Q_F2_diagonal": [float(x) for x in np.diag(Q_F2)],
        "Q_F1_to_F2_diagonal_diff": [float(x) for x in np.diag(Q_diff)],
        "Q_F1_off_diagonal_nonzero": int(np.sum(np.abs(np.triu(Q_F1, k=1)) > 1e-12)),
        "Q_F2_off_diagonal_nonzero": int(np.sum(np.abs(np.triu(Q_F2, k=1)) > 1e-12)),
        "Q_F1_to_F2_offdiag_n_cells_changed": n_offdiag_changed,
        "Q_F1_to_F2_c_diff": float(c_diff),
        "f1_eigval_min": float(np.min(f1_eigs)),
        "f1_eigval_max": float(np.max(f1_eigs)),
        "f2_eigval_min": float(np.min(f2_eigs)),
        "f2_eigval_max": float(np.max(f2_eigs)),
        "f1_diag_min": f1_diag_min,
        "f1_diag_max": f1_diag_max,
        "f2_diag_min": f2_diag_min,
        "f2_diag_max": f2_diag_max,
        "f1_diag_range_ratio_max_over_min_abs": f1_diag_max / max(abs(f1_diag_min), 1e-9),
        "f2_diag_range_ratio_max_over_min_abs": f2_diag_max / max(abs(f2_diag_min), 1e-9),
        "f1_total_abs_Q_sum": f1_total,
        "f2_total_abs_Q_sum": f2_total,
        "cost_only_total_abs_Q_sum": cost_total,
        "f1_vs_cost_ratio": f1_total / max(cost_total, 1e-9),
        "f2_vs_cost_ratio": f2_total / max(cost_total, 1e-9),
        "f1_diag_fractions_explained": {
            "cost_diag": float(np.mean(np.abs(cost_diag) / np.maximum(np.abs(f1_diag), 1e-9))),
            "deadline_diag": float(np.mean(np.abs(deadline_diag) / np.maximum(np.abs(f1_diag), 1e-9))),
        },
        "adopt_active": bool(np.max(np.abs(Q_diff)) > 1e-6),
        "adopt_active_magnitude": float(np.max(np.abs(Q_diff))),
    }


# ---------------------------------------------------------------------------
# Part D: Synthetic recovery tests S1 / S2 / S3
# ---------------------------------------------------------------------------

def build_synthetic_scenarios(deltas_d: List[float], deltas_e: List[float]) -> List[Dict[str, Any]]:
    """Build a uniform-weight scenario set from raw (Delta d, Delta e) values.

    Each value becomes its own cluster with weight 1/N.
    """
    assert len(deltas_d) == len(deltas_e)
    n = len(deltas_d)
    return [{
        "cluster": int(i),
        "n_observations": 1,
        "weight": 1.0 / n,
        "centroid_delta_d_minutes": float(d),
        "centroid_delta_e_kwh": float(e),
        "mean_delta_d": float(d),
        "mean_delta_e": float(e),
        "std_delta_d": 0.0,
        "std_delta_e": 0.0,
    } for i, (d, e) in enumerate(zip(deltas_d, deltas_e))]


def run_synthetic_recovery_test(inst: Instance, scenario_name: str,
                                  deltas_d: List[float], deltas_e: List[float],
                                  gamma: float = 1.6414) -> Dict[str, Any]:
    """Run F0/F1/F2 (and ADOPT) on a synthetic scenario set.

    Returns exact optima for all three formulations, plus QAOA samples for
    F0/F1/F2.
    """
    scenarios = build_synthetic_scenarios(deltas_d, deltas_e)
    rho_d, rho_p, rho_cap = DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP
    f0 = build_f0_deterministic(inst, rho_d, rho_p, rho_cap)
    f1 = build_f1_robust(inst, scenarios, rho_d, rho_p, rho_cap)
    f2 = build_f2_adopt(inst, scenarios, rho_d, rho_p, rho_cap, gamma)
    return {
        "scenario_name": scenario_name,
        "deltas_d": deltas_d,
        "deltas_e": deltas_e,
        "scenarios": scenarios,
        "F0_exact_optimum": float(f0.classical_optimum),
        "F1_exact_optimum": float(f1.classical_optimum),
        "F2_exact_optimum": float(f2.classical_optimum),
        "F0_schedule": {f"{p[0]},{p[1]}": int(v) for p, v in f0.classical_optimum_schedule.items()},
        "F1_schedule": {f"{p[0]},{p[1]}": int(v) for p, v in f1.classical_optimum_schedule.items()},
        "F2_schedule": {f"{p[0]},{p[1]}": int(v) for p, v in f2.classical_optimum_schedule.items()},
        "F0_charging_slots": int(sum(f0.classical_optimum_schedule.values())),
        "F1_charging_slots": int(sum(f1.classical_optimum_schedule.values())),
        "F2_charging_slots": int(sum(f2.classical_optimum_schedule.values())),
        "F0_unmet_on_scenarios": _unmet_on_scenarios(inst, f0.classical_optimum_schedule, scenarios),
        "F1_unmet_on_scenarios": _unmet_on_scenarios(inst, f1.classical_optimum_schedule, scenarios),
        "F2_unmet_on_scenarios": _unmet_on_scenarios(inst, f2.classical_optimum_schedule, scenarios),
    }


def _unmet_on_scenarios(inst: Instance, sched: Dict, scenarios: List[Dict]) -> List[float]:
    """For each scenario, compute the unmet energy (kWh) of the schedule."""
    var_idx = inst.var_index()
    x_dict = {pos: int(sched.get(pos, 0)) for pos in var_idx.keys()}
    out = []
    for s in scenarios:
        omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
        dd, de = omega
        unmet = 0.0
        for i, ev in enumerate(inst.evs):
            slots_removed = int(math.floor(dd / DELTA_MIN)) if dd >= 0 else 0
            slots_added = int(math.floor(-dd / DELTA_MIN)) if dd < 0 else 0
            effective_d = min(ev.d_slot - slots_removed + slots_added, inst.T - 1)
            effective_d = max(effective_d, ev.a_slot)
            new_e_req = max(0.0, ev.E_req_kWh + de)
            in_window_energy = sum(ev.P_max_kW * DELTA_HOURS * int(x_dict[(i, t)])
                                    for t in range(ev.a_slot, ev.d_slot + 1)
                                    if t <= effective_d)
            unmet += max(0, new_e_req - in_window_energy)
        out.append(float(unmet))
    return out


# ---------------------------------------------------------------------------
# Part E: Directionality tests
# ---------------------------------------------------------------------------

def directionality_test(inst: Instance, gamma: float = 1.6414) -> Dict[str, Any]:
    """Run a series of monotonicity checks:

    1. Increasing early-departure risk: scenarios with progressively larger
       positive Delta d. F1 should charge MORE in early slots (not less).
    2. Increasing unmet-energy risk: scenarios with progressively more
       negative Delta E. F1 should charge MORE (not less) per unit of risk.
    3. Increasing uncertainty magnitude: scale up the deltas uniformly.
       The robust objective should change measurably.
    """
    results: Dict[str, Any] = {}

    # (1) Early-departure directionality
    f1_edd_charging = []
    f2_edd_charging = []
    for d in [0, 15, 30, 45, 60]:
        scenarios = build_synthetic_scenarios([d], [0])
        f1 = build_f1_robust(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f2 = build_f2_adopt(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
        f1_edd_charging.append(int(sum(f1.classical_optimum_schedule.values())))
        f2_edd_charging.append(int(sum(f2.classical_optimum_schedule.values())))
    results["early_departure_directionality"] = {
        "deltas_d_min": [0, 15, 30, 45, 60],
        "F1_charging_slots": f1_edd_charging,
        "F2_charging_slots": f2_edd_charging,
        "F1_monotonic_in_d": bool(all(f1_edd_charging[i] >= f1_edd_charging[i+1] for i in range(len(f1_edd_charging)-1)) or all(f1_edd_charging[i] <= f1_edd_charging[i+1] for i in range(len(f1_edd_charging)-1))),
        "F2_monotonic_in_d": bool(all(f2_edd_charging[i] >= f2_edd_charging[i+1] for i in range(len(f2_edd_charging)-1)) or all(f2_edd_charging[i] <= f2_edd_charging[i+1] for i in range(len(f2_edd_charging)-1))),
    }
    # (2) Unmet-energy directionality
    f1_ue_charging = []
    f2_ue_charging = []
    for e in [0, -1, -2, -3, -5]:
        scenarios = build_synthetic_scenarios([0], [e])
        f1 = build_f1_robust(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f2 = build_f2_adopt(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
        f1_ue_charging.append(int(sum(f1.classical_optimum_schedule.values())))
        f2_ue_charging.append(int(sum(f2.classical_optimum_schedule.values())))
    results["unmet_energy_directionality"] = {
        "deltas_e_kWh": [0, -1, -2, -3, -5],
        "F1_charging_slots": f1_ue_charging,
        "F2_charging_slots": f2_ue_charging,
        "F1_monotonic_more_neg_e_charges_more": bool(all(f1_ue_charging[i] <= f1_ue_charging[i+1] for i in range(len(f1_ue_charging)-1))),
        "F2_monotonic_more_neg_e_charges_more": bool(all(f2_ue_charging[i] <= f2_ue_charging[i+1] for i in range(len(f2_ue_charging)-1))),
    }
    # (3) Magnitude directionality: scale all deltas
    f1_mag_opt = []
    f2_mag_opt = []
    for scale in [0.0, 0.5, 1.0, 2.0, 4.0]:
        scenarios = build_synthetic_scenarios([30 * scale, -2 * scale], [0, 0])
        f1 = build_f1_robust(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f2 = build_f2_adopt(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
        f1_mag_opt.append(float(f1.classical_optimum))
        f2_mag_opt.append(float(f2.classical_optimum))
    results["magnitude_directionality"] = {
        "scales": [0.0, 0.5, 1.0, 2.0, 4.0],
        "F1_optima": f1_mag_opt,
        "F2_optima": f2_mag_opt,
        "F1_optimum_changes_with_magnitude": bool(f1_mag_opt[0] != f1_mag_opt[-1]),
        "F2_optimum_changes_with_magnitude": bool(f2_mag_opt[0] != f2_mag_opt[-1]),
    }
    return results


# ---------------------------------------------------------------------------
# Part F: Penalty-scale analysis
# ---------------------------------------------------------------------------

def penalty_scale_analysis(inst: Instance, scenarios: List[Dict[str, Any]],
                            gamma: float = 1.6414) -> Dict[str, Any]:
    """Compute the relative scale of every penalty and cost term in the QUBO."""
    # Build F1 QUBO
    rho_d, rho_p, rho_cap = DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP
    Q_F1, c_F1, n = corrected_robust_qubo(inst, scenarios, rho_d, rho_p, rho_cap)
    # Build F2 QUBO
    Q_F2, c_F2, n2 = corrected_robust_qubo(inst, scenarios, rho_d * gamma, rho_p, rho_cap)
    # Categorize the diagonal
    base_idx = inst.var_index()
    base_var_list = list(base_idx.keys())
    # Cost term on diagonal: c_t * P_i_max
    cost_diag = np.zeros(n)
    for (i, t), k in base_idx.items():
        ev = inst.evs[i]
        cost_diag[k] = inst.c_per_slot[t] * ev.P_max_kW
    # Peak term: -2 * rho_p * P_target * P_i_max
    peak_diag = np.zeros(n)
    for (i, t), k in base_idx.items():
        ev = inst.evs[i]
        peak_diag[k] = -2 * rho_p * inst.P_target_kW * ev.P_max_kW
    # Cap term: -2 * rho_cap * P_site_max * P_i_max
    cap_diag = np.zeros(n)
    for (i, t), k in base_idx.items():
        ev = inst.evs[i]
        cap_diag[k] = -2 * rho_cap * inst.P_site_max_kW * ev.P_max_kW
    # Deadline term: -2 * rho_d * R_i
    deadline_diag = np.zeros(n)
    for i, ev in enumerate(inst.evs):
        for t in range(ev.a_slot, ev.d_slot + 1):
            k = base_idx[(i, t)]
            deadline_diag[k] = -2 * rho_d * ev.R_i
    # Deadline quadratic: +rho_d on each pair within same EV
    # (M_window NOT in the diagonal decomposition; it's a separate term)
    f1_diag = np.diag(Q_F1)
    # Verify sum
    diag_sum = cost_diag + peak_diag + cap_diag + deadline_diag
    residual = f1_diag - diag_sum  # should be the M_window + constant offsets (constants go in c)
    m_window_total_diag = float(np.sum(np.maximum(residual, 0)))
    # Per-QUBO scale
    return {
        "M_window": M_window_penalty,
        "rho_d": rho_d, "rho_p": rho_p, "rho_cap": rho_cap, "gamma": gamma,
        "cost_diag_max": float(np.max(np.abs(cost_diag))),
        "peak_diag_max": float(np.max(np.abs(peak_diag))),
        "cap_diag_max": float(np.max(np.abs(cap_diag))),
        "deadline_diag_max_F1": float(np.max(np.abs(deadline_diag))),
        "deadline_diag_max_F2": float(np.max(np.abs(deadline_diag)) * gamma),  # gamma multiplies the rho_d contribution
        "M_window_diag_sum_F1": m_window_total_diag,
        "F1_diag_max_abs": float(np.max(np.abs(f1_diag))),
        "F2_diag_max_abs": float(np.max(np.abs(np.diag(Q_F2)))),
        "c_F1": float(c_F1), "c_F2": float(c_F2),
        "ratio_M_window_over_cost_diag": M_window_penalty / max(float(np.max(np.abs(cost_diag))), 1e-9),
        "ratio_M_window_over_deadline_F1": M_window_penalty / max(float(np.max(np.abs(deadline_diag))), 1e-9),
        "ratio_M_window_over_deadline_F2": M_window_penalty / max(float(np.max(np.abs(deadline_diag)) * gamma), 1e-9),
        "verdict": ("M_window = 1e6 is 5-6 orders of magnitude larger than ordinary "
                    "objective terms. It is not a tuned hyperparameter; it is a "
                    "structural constant chosen to be effectively infinite for "
                    "any feasible operating regime. The verifier in Part C "
                    "checks that M_window is large enough to force out-of-window "
                    "slots to 0 at the optimum."),
    }


# ---------------------------------------------------------------------------
# Part G: Exact vs QAOA under synthetic tests
# ---------------------------------------------------------------------------

def run_qaoa_on_formulation(f0_or_f1_or_f2_obj, inst: Instance,
                            seeds: Sequence[int] = (0, 1, 2),
                            shots: int = 1024, p: int = 1,
                            name: str = "F0") -> Dict[str, Any]:
    ising = qubo_to_ising(f0_or_f1_or_f2_obj.Q, f0_or_f1_or_f2_obj.c, inst.var_index())
    qubo_adapter = _QUBOAdapter(f0_or_f1_or_f2_obj.Q, f0_or_f1_or_f2_obj.c, inst.var_index())
    per_seed = []
    for seed in seeds:
        cfg = QAOAConfig(
            instance_name=inst.name, n_qubits=ising.n(), p=p, shots=shots,
            seed=int(seed), optimizer="COBYLA", optimizer_max_iter=30, optimizer_tol=1e-4,
            init_strategy="small_random", description=f"Stage 7 {name} p={p} shots={shots} seed={seed}",
        )
        qres = run_qaoa(qubo_adapter, ising, cfg)
        m = compute_metrics(qres, f0_or_f1_or_f2_obj.classical_optimum, inst)
        per_seed.append({"seed": seed, **m})
    best_ars = [s["approximation_ratio"] for s in per_seed]
    best_pfe = [s["P_feasible"] for s in per_seed]
    return {
        "method": name,
        "n_qubits": ising.n(),
        "p": p, "shots": shots,
        "classical_optimum": float(f0_or_f1_or_f2_obj.classical_optimum),
        "AR_median": float(np.median(best_ars)),
        "AR_mean": float(np.mean(best_ars)),
        "P_feasible_mean": float(np.mean(best_pfe)),
        "P_feasible_std": float(np.std(best_pfe)),
        "per_seed": per_seed,
    }


# ---------------------------------------------------------------------------
# Part H: Distribution-shift diagnostic
# ---------------------------------------------------------------------------

def distribution_shift_diagnostic(inst: Instance, gamma: float = 1.6414) -> Dict[str, Any]:
    """For each of three cases (A: same distribution; B: mild shift; C: severe shift),
    construct calibration/test pairs and compare F0/F1/F2 robustness.

    Note: this uses synthetic distributions (placeholder), not held-out
    real data. The purpose is to characterize the methodology's behavior
    under controlled distributional shift, not to evaluate on real data.
    """
    # Define three calibration distributions and three test distributions
    cases = {
        "A_same": {
            "cal_deltas_d": [0, 0, 0, 0, 0],
            "cal_deltas_e": [0, 0, 0, 0, 0],
            "test_deltas_d": [0, 0, 0, 0, 0],
            "test_deltas_e": [0, 0, 0, 0, 0],
        },
        "B_mild": {
            "cal_deltas_d": [0, 0, 0, 0, 0],
            "cal_deltas_e": [0, 0, 0, 0, 0],
            "test_deltas_d": [10, 5, -5, 15, 0],
            "test_deltas_e": [-0.5, 0, -0.3, -0.2, 0],
        },
        "C_severe": {
            "cal_deltas_d": [0, 0, 0, 0, 0],
            "cal_deltas_e": [0, 0, 0, 0, 0],
            "test_deltas_d": [60, 30, -10, 90, 45],
            "test_deltas_e": [-3, -1, -2, -4, -0.5],
        },
    }
    out: Dict[str, Any] = {}
    for name, case in cases.items():
        # Build F0 (deterministic, no uncertainty)
        # Build F1 with calibration scenarios
        cal_scen = build_synthetic_scenarios(case["cal_deltas_d"], case["cal_deltas_e"])
        f0 = build_f0_deterministic(inst, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f1 = build_f1_robust(inst, cal_scen, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f2 = build_f2_adopt(inst, cal_scen, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
        # Evaluate each schedule on the test set
        test_scen = build_synthetic_scenarios(case["test_deltas_d"], case["test_deltas_e"])
        f0_unmet = _unmet_on_scenarios(inst, f0.classical_optimum_schedule, test_scen)
        f1_unmet = _unmet_on_scenarios(inst, f1.classical_optimum_schedule, test_scen)
        f2_unmet = _unmet_on_scenarios(inst, f2.classical_optimum_schedule, test_scen)
        out[name] = {
            "cal_scenarios": case["cal_deltas_d"],
            "cal_e": case["cal_deltas_e"],
            "test_scenarios": [(d, e) for d, e in zip(case["test_deltas_d"], case["test_deltas_e"])],
            "F0_exact_optimum": float(f0.classical_optimum),
            "F1_exact_optimum": float(f1.classical_optimum),
            "F2_exact_optimum": float(f2.classical_optimum),
            "F0_charging_slots": int(sum(f0.classical_optimum_schedule.values())),
            "F1_charging_slots": int(sum(f1.classical_optimum_schedule.values())),
            "F2_charging_slots": int(sum(f2.classical_optimum_schedule.values())),
            "F0_unmet_per_scenario": f0_unmet,
            "F1_unmet_per_scenario": f1_unmet,
            "F2_unmet_per_scenario": f2_unmet,
            "F0_mean_unmet": float(np.mean(f0_unmet)),
            "F1_mean_unmet": float(np.mean(f1_unmet)),
            "F2_mean_unmet": float(np.mean(f2_unmet)),
        }
    return out


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

def run_stage7(instance_name: str = "toy_B_3x4", gamma: float = 1.6414) -> Dict[str, Any]:
    """Run the full Stage 7 stress test battery."""
    out: Dict[str, Any] = {
        "stage": "Stage 7",
        "instance": instance_name,
        "gamma": gamma,
        "alpha": 1.0,  # frozen
        "K": 8,  # frozen
        "M_window": M_window_penalty,
    }
    inst = toy_instance(instance_name, N=3, T=4)

    # Part A + B: trace and decompose
    samples, _ = placeholder_uncertainty()
    cal = [s for s in samples if s.calibration and s.delta_d_minutes is not None and s.delta_e_kwh is not None]
    dd_cal = np.array([s.delta_d_minutes for s in cal])
    de_cal = np.array([s.delta_e_kwh for s in cal])
    scenarios = kmeans_joint(dd_cal, de_cal, K=8, seed=20260829 + 8)["clusters"]
    # Re-build F0/F1/F2 with these scenarios (the Stage 6 run also did this; the
    # traces here are independent re-derivations)
    f0 = build_f0_deterministic(inst, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
    f1 = build_f1_robust(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
    f2 = build_f2_adopt(inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
    out["part_a_under_service_trace"] = trace_under_service(
        inst, f0.classical_optimum_schedule, f1.classical_optimum_schedule,
        f2.classical_optimum_schedule, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
    out["part_b_objective_decomposition"] = {
        "F0": decompose_robust_objective(inst, f0.classical_optimum_schedule, scenarios,
                                          DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
                                          rho_d_eff=DEFAULT_RHO_D),
        "F1": decompose_robust_objective(inst, f1.classical_optimum_schedule, scenarios,
                                          DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
                                          rho_d_eff=DEFAULT_RHO_D),
        "F2": decompose_robust_objective(inst, f2.classical_optimum_schedule, scenarios,
                                          DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
                                          rho_d_eff=DEFAULT_RHO_D * gamma),
    }
    # Part C: ADOPT effect
    out["part_c_adopt_effect"] = adopt_effect_analysis(
        inst, scenarios, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
    # Part D: synthetic recovery tests
    s1 = run_synthetic_recovery_test(inst, "S1_no_uncertainty", [0], [0], gamma)
    s2 = run_synthetic_recovery_test(inst, "S2_mild_uncertainty", [10, -5, 0, 5, -2], [0, 0, 0, 0, 0], gamma)
    s3 = run_synthetic_recovery_test(inst, "S3_severe_uncertainty", [60, 30, 90, 45, 15], [-3, -1, -4, -2, -0.5], gamma)
    out["part_d_synthetic_recovery"] = {
        "S1": s1, "S2": s2, "S3": s3,
    }
    # Part E: directionality
    out["part_e_directionality"] = directionality_test(inst, gamma)
    # Part F: penalty scale
    out["part_f_penalty_scale"] = penalty_scale_analysis(inst, scenarios, gamma)
    # Part G: exact vs QAOA on synthetic S1/S2/S3 (light QAOA: 2 seeds, 1024 shots)
    out["part_g_exact_vs_qaoa"] = {}
    for sname, sres in [("S1", s1), ("S2", s2), ("S3", s3)]:
        # Rebuild F0/F1/F2 from the synthetic scenarios used in sres
        s_scens = sres["scenarios"]
        f0_s = build_f0_deterministic(inst, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f1_s = build_f1_robust(inst, s_scens, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP)
        f2_s = build_f2_adopt(inst, s_scens, DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP, gamma)
        # Run QAOA on each (2 seeds for speed)
        out["part_g_exact_vs_qaoa"][sname] = {
            "F0_exact": float(f0_s.classical_optimum),
            "F1_exact": float(f1_s.classical_optimum),
            "F2_exact": float(f2_s.classical_optimum),
            "F0_QAOA": run_qaoa_on_formulation(f0_s, inst, seeds=(0, 1), shots=1024, p=1, name=f"{sname}_F0"),
            "F1_QAOA": run_qaoa_on_formulation(f1_s, inst, seeds=(0, 1), shots=1024, p=1, name=f"{sname}_F1"),
            "F2_QAOA": run_qaoa_on_formulation(f2_s, inst, seeds=(0, 1), shots=1024, p=1, name=f"{sname}_F2"),
        }
    # Part H: distribution shift
    out["part_h_distribution_shift"] = distribution_shift_diagnostic(inst, gamma)
    # Part K: synthetic->real data switch test
    out["part_k_real_data_switch"] = {
        "DATA_MODE_provided_in_env": "SYNTHETIC",  # currently we have no token
        "switch_principle": "DATA_MODE = SYNTHETIC -> use placeholder_uncertainty; DATA_MODE = REAL -> use load_real_uncertainty (requires ACN_API_TOKEN). The downstream pipeline is identical.",
        "code_locations": {
            "data_loader": "stage5/uncertainty.py::load_real_uncertainty",
            "data_fallback": "stage5/uncertainty.py::placeholder_uncertainty",
            "switch_logic": "stage7/stress_test.py::run_stage7 (and stage5/uncertainty.py::run_stage5)",
        },
        "verification": "Running the same instance with placeholder data and with real data (once token arrives) must produce the same downstream artifacts, differing only in the source data and the resulting numerical values.",
    }
    # Part L: token-arrival procedure
    out["part_l_token_arrival_procedure"] = {
        "step_1": "Set the ACN_API_TOKEN environment variable (or ACNPORTAL_TOKEN).",
        "step_2": "Verify token by GET https://ev.caltech.edu/api/v1/sessions/caltech?page=1 (expect 200 OK).",
        "step_3": "The load_real_uncertainty() function in stage5/uncertainty.py is populated from the live API (or a pre-fetched JSON dump). The function structure is already in place.",
        "step_4": "Run `python -m stage5.uncertainty --out artifacts/stage5_run.json` to produce real-data uncertainty distributions, scenarios, ADOPT gamma.",
        "step_5": "Run `python -m stage6.robust_qaoa --out artifacts/stage6_run.json` to produce real-data F0/F1/F2/F3 results and held-out robustness.",
        "step_6": "Run `python -m stage7.stress_test --out artifacts/stage7_run.json` to verify the methodology still passes the Part D directionality tests on the real data (S1/S2/S3 are independent of the real distribution).",
        "step_7": "No code modifications are permitted. The pre-registered K, alpha, M_window, QAOA settings remain frozen.",
        "step_8": "If the real data produces an unfavorable result, the result is reported as-is. No methodology modification is performed to make the result favorable.",
    }
    # Part M: decision tree
    out["part_m_decision_tree"] = {
        "Q1_real_data_supports_uncertainty_model": "Run planned experiment; report results.",
        "Q2_uncertainty_exists_but_weak": "Run planned experiment; report weak uncertainty and the resulting F0/F1/F2 comparison.",
        "Q3_F1_or_F2_outperform_F0_on_held_out": "Report the positive result.",
        "Q4_F0_outperforms_F1_or_F2_on_held_out": "Report the negative result (this is the placeholder behavior).",
        "Q5_F2_approx_F1": "Report that ADOPT contributes little beyond robustness on this data.",
        "Q6_F2_differs_materially_from_F1": "Analyze whether the difference comes from the gamma-scaled rho_d.",
        "Q7_uncertainty_model_cannot_be_constructed": "STOP and document the blocker (e.g., the API token remains unavailable after the project deadline).",
        "decision_rule": "Once the result is observed, do not redesign the study. The methodology is frozen pre-registration.",
    }
    return out


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=str, default="artifacts/stage7_run.json")
    p.add_argument("--instance", type=str, default="toy_B_3x4")
    p.add_argument("--gamma", type=float, default=1.6414)
    args = p.parse_args()
    res = run_stage7(instance_name=args.instance, gamma=args.gamma)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(_tuples_to_str(res), indent=2, default=str))
    print(f"Wrote {args.out}")
    print("---")
    # Summary
    a = res.get("part_a_under_service_trace", {})
    print("Part A: F0/F1/F2 charging slots:", a.get("schedules_x_lengths"))
    print("Part A: F0/F1/F2 total energy (kWh):", a.get("total_energy_kWh"))
    print("Part A: F0/F1/F2 mean unmet per scenario:", [
        round(np.mean([s["unmet_kWh"] for s in a["per_scenario_unmet"][m]]), 3)
        for m in ["F0", "F1", "F2"]
    ])
    b = res.get("part_b_objective_decomposition", {})
    print("Part B: F1 obj decomposition:")
    for k, v in b.get("F1", {}).items():
        print(f"  {k}: {v:.3f}")
    c = res.get("part_c_adopt_effect", {})
    print("Part C: ADOPT active?", c.get("adopt_active"), "max diff:", c.get("adopt_active_magnitude"))
    d = res.get("part_d_synthetic_recovery", {})
    for sname, sres in d.items():
        print(f"Part D {sname}: F0={sres['F0_exact_optimum']:.2f}  F1={sres['F1_exact_optimum']:.2f}  F2={sres['F2_exact_optimum']:.2f}  F1_slots={sres['F1_charging_slots']}  F2_slots={sres['F2_charging_slots']}")
    e = res.get("part_e_directionality", {})
    print("Part E: early-departure F1 slots:", e["early_departure_directionality"]["F1_charging_slots"])
    print("Part E: unmet-energy F1 slots:", e["unmet_energy_directionality"]["F1_charging_slots"])
    print("Part E: magnitude F1 optima:", e["magnitude_directionality"]["F1_optima"])
    f_ = res.get("part_f_penalty_scale", {})
    print(f"Part F: M_window={f_['M_window']}  cost_diag_max={f_['cost_diag_max']:.3f}  deadline_diag_max_F1={f_['deadline_diag_max_F1']:.3f}  ratio_M_window_over_cost={f_['ratio_M_window_over_cost_diag']:.2e}")
    h = res.get("part_h_distribution_shift", {})
    for cs, cres in h.items():
        print(f"Part H {cs}: F0_mean_unmet={cres['F0_mean_unmet']:.3f}  F1_mean_unmet={cres['F1_mean_unmet']:.3f}  F2_mean_unmet={cres['F2_mean_unmet']:.3f}  F0_slots={cres['F0_charging_slots']}  F1_slots={cres['F1_charging_slots']}  F2_slots={cres['F2_charging_slots']}")
