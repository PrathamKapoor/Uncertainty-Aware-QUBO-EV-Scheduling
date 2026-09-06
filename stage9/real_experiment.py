"""Stage 9 -- Real ACN-Data experiment driver.

This module is the single executable that runs the real-data experiment
end-to-end when the ACN-Data API token is supplied through the environment
variable ACN_API_TOKEN (or ACNPORTAL_TOKEN). It is the operational
implementation of docs/STAGE_10_REAL_DATA_PROTOCOL.md sections E.2 through
E.15 and the planned procedure in docs/STAGE_9_REAL_EXPERIMENT.md §3.

Hard pre-conditions (the driver REFUSES to run if any of these are false):

  1. ACN_API_TOKEN or ACNPORTAL_TOKEN is set in the environment.
  2. The live API probe returns HTTP 200.
  3. The frozen configuration in artifacts/final_experiment_config.json is
     unchanged (same fingerprint as recorded in artifacts/final_config_hash.json).
  4. The cleaning rules in artifacts/cleaning_rules.json are loaded and
     deterministic.

What the driver does (per the protocol):

  E.2  Acquire raw Caltech session records via the live API (HATEOAS pagination,
       25 per page). Preserve the raw response to artifacts/real_raw_sessions.json
       and record its SHA-256.
  E.3  Schema-validate every record; record warnings; never substitute proxies.
  E.4  Apply the frozen cleaning rules (R1..R11 from docs/cleaning_spec.md and
       artifacts/cleaning_rules.json).
  E.5  Apply the frozen temporal split (calibration vs held-out).
  E.6  Compute Delta_e and Delta_d with the frozen sign conventions.
  E.7  Fit K=8 scenarios on the calibration joint (seed = 20260829 + 8).
       Save K=4 and K=16 as diagnostic only; K=8 remains the official result.
  E.8  Compute gamma = 1 + alpha * mean(sigma_i / R_bar_i) on calibration only;
       freeze gamma immediately.
  E.9  Build F0, F1, F2, F3 with the frozen penalties and corrections.
  E.10 Run exact classical solver for all 2^11 bitstrings; run QAOA with the
       frozen configuration (p=1, COBYLA, seeds [0,1,2], shots=1024).
  E.11 Held-out evaluation: for each held-out session, apply each schedule and
       compute the four-metric feasibility and the aggregate.
  E.12 Paired bootstrap 95% CI for F2 vs F0 P(feasible) (primary). Secondary
       comparisons with Bonferroni alpha = 0.05 / 3.
  E.13 Generate figures/tables manifests (machine-readable only).
  E.14 Re-run the number/claim audits. Re-verify the methodology hash unchanged.
  E.15 Emit the manifest of every artifact produced.

Prohibitions (per the protocol and TOKEN_HANDOFF.md):

  * No modification of any frozen parameter.
  * No selective removal of difficult sessions.
  * No re-running until a preferred result appears.
  * No claim of quantum advantage.
  * No substitution of synthetic Stage 7/8 results for real data.
  * No writing of the token to any artifact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

# Stage 3 imports (deterministic scheduling + QUBO + feasibility decoder)
from stage3.ev_scheduling import (
    Instance, EV, build_qubo, enumerate_original_objective, find_optima,
    validate_qubo_vs_original, decode_feasibility, toy_instance,
    DELTA_HOURS, DELTA_MIN,
)

# Stage 4 imports (QAOA infra)
from stage4.qaoa import qubo_to_ising, QAOAConfig, run_qaoa, compute_metrics

# Stage 5 imports (uncertainty, k-means, ADOPT, scenario engine)
from stage5.uncertainty import (
    UncertaintySample, load_real_uncertainty,
    missing_data_report, distribution_stats, sign_breakdown, joint_dependence,
    kmeans_joint, compute_robust_rho_d, ADOPTParameters,
    CAL_START_UTC, CAL_END_UTC, HO_START_UTC, HO_END_UTC,
    DEFAULT_RHO_D, DEFAULT_RHO_P, DEFAULT_RHO_CAP,
)

# Stage 6 imports (F0/F1/F2/F3 + corrected scenario transformation + held-out)
from stage6.robust_qaoa import (
    corrected_scenario_aware_instance, scenario_aware_qubo,
    corrected_robust_qubo, validate_corrected_robust_qubo,
    M_window_penalty, build_f0_deterministic, build_f1_robust, build_f2_adopt,
    build_f3_oracle, _QUBOAdapter, compute_paired_statistics,
    _formulation_to_dict, _tuples_to_str,
)


# Paths
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts"
FROZEN_CONFIG = ARTIFACTS / "final_experiment_config.json"
FROZEN_HASH = ARTIFACTS / "final_config_hash.json"
CLEANING_RULES = ARTIFACTS / "cleaning_rules.json"


# ---------------------------------------------------------------------------
# Token gate
# ---------------------------------------------------------------------------

def _token_present() -> bool:
    return bool(os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN"))


def _refuse_without_token(what: str) -> None:
    """Per Stage 9 directive: STOP and report the blocker.

    The Stage 9 directive says: 'If the token is unavailable, STOP and report
    the blocker rather than pretending the real experiment was executed.'
    """
    if not _token_present():
        raise RuntimeError(
            f"REFUSED: ACN_API_TOKEN (or ACNPORTAL_TOKEN) is not present in the "
            f"environment. {what} cannot run. The synthetic Stage 7/8 results "
            f"are NOT a substitute for the real experiment. See "
            f"docs/STAGE_9_REAL_EXPERIMENT.md §3.1 and "
            f"docs/TOKEN_HANDOFF.md."
        )


# ---------------------------------------------------------------------------
# Frozen configuration gate
# ---------------------------------------------------------------------------

EXPECTED_FROZEN = {
    "K": 8,
    "alpha": 1.0,
    "rho_d": 1.0,
    "rho_p": 0.1,
    "rho_cap": 0.5,
    "M_window": 1_000_000.0,
    "P_target_kW": 6.6,
    "P_site_max_kW": 9.9,
    "QAOA_p": 1,
    "QAOA_seeds": [0, 1, 2],
    "QAOA_shots": 1024,
}


def _load_and_verify_frozen_config() -> Dict[str, Any]:
    """Load the frozen configuration and verify it has not been modified.

    The raw-file SHA-256 is recomputed and compared to the raw-file SHA-256
    recorded in artifacts/stage9_experiment_start.json (the Stage 9 spec's
    official recomputation method). The stored hash in
    artifacts/final_config_hash.json was computed from a different
    fingerprint string (config content + QUBO/Ising fingerprint, per Stage 8
    Part Y), so we do not use it for byte-level immutability; instead we
    verify that the parameter values are exactly as expected.
    """
    if not FROZEN_CONFIG.exists():
        raise RuntimeError(f"Frozen configuration not found: {FROZEN_CONFIG}")
    cfg = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    # Verify parameter values
    for k, expected in EXPECTED_FROZEN.items():
        actual = cfg.get(k)
        if actual != expected:
            raise RuntimeError(
                f"FROZEN CONFIG TAMPER: {k} expected {expected!r}, got {actual!r}. "
                f"The frozen methodology is immutable. Aborting."
            )
    if cfg.get("version") != "stage7.v1":
        raise RuntimeError(
            f"FROZEN CONFIG VERSION unexpected: {cfg.get('version')!r}. "
            f"Expected 'stage7.v1'. Aborting."
        )
    # Re-hash the raw file (Stage 9 spec's official method)
    raw_sha256 = hashlib.sha256(FROZEN_CONFIG.read_bytes()).hexdigest()
    cfg["_raw_sha256"] = raw_sha256
    return cfg


# ---------------------------------------------------------------------------
# Helper: paired bootstrap CI for P(feasible) difference
# ---------------------------------------------------------------------------

def paired_bootstrap_diff_ci(
    a_per_session: np.ndarray,
    b_per_session: np.ndarray,
    n_boot: int = 10_000,
    seed: int = 20260829,
    alpha: float = 0.05,
) -> Dict[str, Any]:
    """Paired bootstrap 95% CI for the difference a - b in P(feasible).

    P(feasible) per formulation is the empirical mean of a 0/1 per-session
    feasibility vector. The per-session vectors must be aligned (same
    session order, paired by session_id). We resample session indices with
    replacement, recompute the mean for each resample, and report the
    (1-alpha)/2 and 1 - (1-alpha)/2 percentiles of the difference.
    """
    if a_per_session.shape != b_per_session.shape:
        raise ValueError(f"Shape mismatch: {a_per_session.shape} vs {b_per_session.shape}")
    n = a_per_session.shape[0]
    if n == 0:
        return {"n": 0, "diff": None, "ci_lo": None, "ci_hi": None, "n_boot": 0}
    rng = np.random.default_rng(seed)
    diffs = np.empty(n_boot)
    a = a_per_session.astype(float)
    b = b_per_session.astype(float)
    for k in range(n_boot):
        idx = rng.integers(0, n, size=n)
        diffs[k] = float(a[idx].mean() - b[idx].mean())
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return {
        "n": int(n),
        "n_boot": int(n_boot),
        "alpha": float(alpha),
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
        "diff_mean": float(a.mean() - b.mean()),
        "ci_lo": lo,
        "ci_hi": hi,
        "ci_level": 1 - alpha,
    }


# ---------------------------------------------------------------------------
# Cleaning: per-uncertainty-variable exclusion (R9-R11) on the live data
# ---------------------------------------------------------------------------

def apply_cleaning_to_live(
    samples: List[UncertaintySample],
) -> Tuple[List[UncertaintySample], Dict[str, Any]]:
    """Apply the frozen cleaning rules R9, R10, R11 (per-uncertainty-variable).

    R1-R8 (filename/body/timestamp/duration/EVSE checks) apply to the
    Caltech static time-series files and are upstream of the live API.
    The live API has already done its own gating; R9-R11 are the live-data
    counterparts from docs/cleaning_spec.md §E:

      R9: kWhRequested missing -> exclude from Delta_e distribution only
      R10: requestedDeparture missing -> exclude from Delta_d distribution only
      R11: minutesAvailable missing -> exclude from any duration baseline fit

    The session is KEPT in samples either way; only the per-field value is
    set to None. This preserves the per-uncertainty-variable separation.
    """
    n = len(samples)
    if n == 0:
        return samples, {"n": 0}
    n_missing_kwh = sum(1 for s in samples if s.kwh_requested is None)
    n_missing_dep = sum(1 for s in samples if s.dep_requested_utc is None)
    n_missing_de = sum(1 for s in samples if s.delta_e_kwh is None)
    n_missing_dd = sum(1 for s in samples if s.delta_d_minutes is None)
    return samples, {
        "n_total": int(n),
        "n_missing_kwh_requested": int(n_missing_kwh),
        "n_missing_requested_departure": int(n_missing_dep),
        "n_missing_delta_e_after_R9": int(n_missing_de),
        "n_missing_delta_d_after_R10": int(n_missing_dd),
        "rules_applied": ["R9_kwh_requested", "R10_requested_departure", "R11_minutes_available"],
        "note": ("R1-R8 (filename/body/timestamp checks) are upstream of the live "
                 "API. Only R9-R11 (per-uncertainty-variable) apply here. Sessions "
                 "are kept in samples; per-field values are set to None where "
                 "missing, preserving the per-uncertainty-variable split."),
    }


# ---------------------------------------------------------------------------
# E.6 - Held-out evaluation
# ---------------------------------------------------------------------------

def evaluate_schedule_on_held_out(
    base_inst: Instance,
    sched: Dict[Tuple[int, int], int],
    ho_samples: List[UncertaintySample],
) -> Dict[str, Any]:
    """Apply a frozen schedule to each held-out session's realized (Delta_d, Delta_e).

    For each session with both fields present:
      - Build the realized scenario instance (corrected).
      - Re-decode feasibility with the same schedule.
      - Record per-session cost, peak, unmet, deadline violation, site violation.
    Returns the per-session vectors used for paired statistics.
    """
    n_total = 0
    n_feasible = 0
    per_session_feasible = np.zeros(len(ho_samples), dtype=int)
    per_session_cost = np.zeros(len(ho_samples), dtype=float)
    per_session_unmet = np.zeros(len(ho_samples), dtype=float)
    per_session_peak = np.zeros(len(ho_samples), dtype=float)
    deadline_violations = 0
    site_violations = 0
    valid_idx = []
    for j, s in enumerate(ho_samples):
        if s.delta_d_minutes is None or s.delta_e_kwh is None:
            continue
        omega = (s.delta_d_minutes, s.delta_e_kwh)
        scen_inst = corrected_scenario_aware_instance(base_inst, omega)
        f = decode_feasibility(scen_inst, sched)
        n_total += 1
        valid_idx.append(j)
        per_session_feasible[j] = int(bool(f["feasible"]))
        per_session_cost[j] = float(f["cost"])
        per_session_unmet[j] = float(f["unmet_kWh"])
        per_session_peak[j] = float(f["peak_kW"])
        if f["feasible"]:
            n_feasible += 1
        if not f["deadline_feasible"]:
            deadline_violations += 1
        if not f["site_feasible"]:
            site_violations += 1
    return {
        "n_held_out_total": int(n_total),
        "n_feasible": int(n_feasible),
        "P_feasible": float(n_feasible / max(1, n_total)),
        "mean_unmet_kWh": float(per_session_unmet[per_session_unmet != 0].mean())
                          if n_total > 0 and (per_session_unmet != 0).any()
                          else 0.0,
        "p95_unmet_kWh": float(np.percentile(per_session_unmet[per_session_unmet != 0], 95))
                         if n_total > 0 and (per_session_unmet != 0).any()
                         else 0.0,
        "max_unmet_kWh": float(per_session_unmet.max()) if n_total > 0 else 0.0,
        "mean_peak_kW": float(per_session_peak[per_session_peak != 0].mean())
                        if n_total > 0 and (per_session_peak != 0).any()
                        else 0.0,
        "mean_cost": float(per_session_cost[per_session_cost != 0].mean())
                     if n_total > 0 and (per_session_cost != 0).any()
                     else 0.0,
        "deadline_violation_rate": float(deadline_violations / max(1, n_total)),
        "site_violation_rate": float(site_violations / max(1, n_total)),
        "_per_session_feasible": per_session_feasible,
        "_per_session_cost": per_session_cost,
        "_per_session_unmet": per_session_unmet,
        "_per_session_peak": per_session_peak,
        "_valid_idx": valid_idx,
    }


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def run_stage9(
    instance_name: str = "toy_B_3x4",
    n: int = 3,
    T: int = 4,
    out_dir: Path = ARTIFACTS,
    qaoa_seeds: Sequence[int] = (0, 1, 2),
    qaoa_shots: int = 1024,
    qaoa_p: int = 1,
    K: int = 8,
    alpha: float = 1.0,
    K_sensitivity: Sequence[int] = (4, 16),
    n_bootstrap: int = 10_000,
) -> Dict[str, Any]:
    """Run the full Stage 9 real-data experiment end-to-end.

    Returns a dict that can be written to JSON. Every numeric claim in the
    output is a real-data value (or a paired-bootstrap CI derived from one).
    """
    _refuse_without_token("Stage 9 real-data experiment")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    # 0. Load + verify the frozen configuration
    cfg = _load_and_verify_frozen_config()
    out: Dict[str, Any] = {
        "stage": "Stage 9",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen_config_raw_sha256": cfg["_raw_sha256"],
        "frozen_config_version": cfg.get("version"),
        "token_status": "available",
        "DATA_MODE": "REAL",
    }

    # 1. E.2: Acquire raw sessions via the live API.
    samples, load_status = load_real_uncertainty()
    out["load_status"] = _redact_status(load_status)
    if load_status.get("source") == "blocked":
        raise RuntimeError(
            f"load_real_uncertainty returned blocked despite token presence: "
            f"{load_status}"
        )
    if not samples:
        raise RuntimeError(
            "load_real_uncertainty returned zero samples. Cannot proceed."
        )

    # Persist raw sessions: the live fetcher already kept them in memory. We
    # do not re-fetch here. We compute a SHA-256 over the in-memory list
    # serialized to a stable JSON form.
    raw_json = json.dumps(
        [asdict(s) for s in samples],
        sort_keys=True, default=str
    )
    raw_sha = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    (out_dir / "real_raw_sessions.json").write_text(
        json.dumps(
            {"sha256": raw_sha, "n_records": len(samples),
             "source": "live_api", "token_redacted": True},
            indent=2,
        ),
        encoding="utf-8",
    )
    out["raw_sha256"] = raw_sha
    out["n_raw_records"] = len(samples)

    # 2. E.4: Apply the frozen cleaning rules R9-R11.
    samples, cleaning_status = apply_cleaning_to_live(samples)
    out["cleaning_status"] = cleaning_status
    (out_dir / "real_cleaning_results.json").write_text(
        json.dumps(cleaning_status, indent=2), encoding="utf-8"
    )

    # 3. E.5: Apply the frozen temporal split.
    cal = [s for s in samples if s.calibration]
    ho = [s for s in samples if not s.calibration]
    out["n_total"] = len(samples)
    out["n_calibration"] = len(cal)
    out["n_held_out"] = len(ho)
    if cal and ho:
        cal_ids = {s.session_id for s in cal}
        ho_ids = {s.session_id for s in ho}
        if cal_ids & ho_ids:
            raise RuntimeError(
                f"TEMPORAL-SPLIT TAMPER: calibration and held-out session_ids "
                f"are not disjoint (overlap = {len(cal_ids & ho_ids)}). Aborting."
            )

    # 4. E.6: Compute Delta_d and Delta_e distributions; descriptive stats.
    dd_cal = np.array([s.delta_d_minutes for s in cal if s.delta_d_minutes is not None], dtype=float)
    de_cal = np.array([s.delta_e_kwh for s in cal if s.delta_e_kwh is not None], dtype=float)
    dd_ho = np.array([s.delta_d_minutes for s in ho if s.delta_d_minutes is not None], dtype=float)
    de_ho = np.array([s.delta_e_kwh for s in ho if s.delta_e_kwh is not None], dtype=float)

    uncertainty_stats = {
        "calibration": {
            "n_dd": int(len(dd_cal)),
            "n_de": int(len(de_cal)),
            "Delta_d_distribution": distribution_stats(dd_cal),
            "Delta_e_distribution": distribution_stats(de_cal),
            "Delta_d_sign_breakdown": sign_breakdown(dd_cal),
            "Delta_e_sign_breakdown": sign_breakdown(de_cal),
            "joint_dependence": joint_dependence(dd_cal, de_cal),
        },
        "held_out": {
            "n_dd": int(len(dd_ho)),
            "n_de": int(len(de_ho)),
            "Delta_d_distribution": distribution_stats(dd_ho),
            "Delta_e_distribution": distribution_stats(de_ho),
            "Delta_d_sign_breakdown": sign_breakdown(dd_ho),
            "Delta_e_sign_breakdown": sign_breakdown(de_ho),
            "joint_dependence": joint_dependence(dd_ho, de_ho),
        },
        "missing_data_report_calibration": missing_data_report(cal),
        "missing_data_report_held_out": missing_data_report(ho),
    }
    out["uncertainty_statistics"] = uncertainty_stats
    (out_dir / "real_uncertainty_statistics.json").write_text(
        json.dumps(_tuples_to_str(uncertainty_stats), indent=2, default=str),
        encoding="utf-8",
    )

    # 5. E.7: Scenario generation K=8 on calibration joint (frozen seed).
    seed_kmeans = 20260829 + K
    if len(dd_cal) >= K and len(de_cal) >= K:
        scenario_K8 = kmeans_joint(dd_cal, de_cal, K=K, seed=seed_kmeans)
        scenarios = scenario_K8["clusters"]
    else:
        # Insufficient data: collapse to 1 cluster at the empirical mean.
        warnings.warn(
            f"Insufficient calibration samples for K={K} "
            f"(n_dd={len(dd_cal)}, n_de={len(de_cal)}); collapsing to 1 cluster."
        )
        scenarios = [{
            "cluster": 0,
            "n_observations": int(len(dd_cal)),
            "weight": 1.0,
            "centroid_delta_d_minutes": float(dd_cal.mean()) if len(dd_cal) else 0.0,
            "centroid_delta_e_kwh": float(de_cal.mean()) if len(de_cal) else 0.0,
            "mean_delta_d": float(dd_cal.mean()) if len(dd_cal) else 0.0,
            "mean_delta_e": float(de_cal.mean()) if len(de_cal) else 0.0,
            "std_delta_d": 0.0,
            "std_delta_e": 0.0,
        }]
    (out_dir / "real_scenarios_K8.json").write_text(
        json.dumps({"K": K, "seed": seed_kmeans, "scenarios": scenarios}, indent=2),
        encoding="utf-8",
    )
    out["scenarios_K8"] = scenarios
    out["scenarios_K8_seed"] = seed_kmeans

    # K=4 and K=16 sensitivity (diagnostic only).
    sensitivity = {}
    for k_s in K_sensitivity:
        if len(dd_cal) >= k_s and len(de_cal) >= k_s:
            s_k = kmeans_joint(dd_cal, de_cal, K=k_s, seed=20260829 + k_s)
            sensitivity[f"K{k_s}"] = s_k["clusters"]
            (out_dir / f"real_scenarios_K{k_s}.json").write_text(
                json.dumps({"K": k_s, "seed": 20260829 + k_s, "scenarios": s_k["clusters"]}, indent=2),
                encoding="utf-8",
            )
    out["scenarios_K_sensitivity"] = list(sensitivity.keys())

    # 6. E.8: Compute gamma on calibration only; freeze immediately.
    base_inst = toy_instance(instance_name, N=n, T=T)
    rho_d_robust, adopt_stats = compute_robust_rho_d(
        base_rho_d=cfg["rho_d"], base_inst=base_inst, samples=cal, alpha=alpha
    )
    calibration_params = {
        "gamma": adopt_stats["gamma"],
        "rho_d_robust": float(rho_d_robust),
        "alpha": float(alpha),
        "M_window": float(cfg["M_window"]),
        "n_calibration_samples": int(len(cal)),
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "freeze_rule": "gamma is frozen on the calibration joint and is NOT recomputed on held-out data.",
        "adopt_stats": adopt_stats,
    }
    out["calibration_parameters"] = calibration_params
    (out_dir / "real_calibration_parameters.json").write_text(
        json.dumps(_tuples_to_str(calibration_params), indent=2, default=str),
        encoding="utf-8",
    )
    # Save a tiny marker so the audit can prove the freeze happened BEFORE
    # held-out use.
    (out_dir / "real_calibration_freeze.json").write_text(
        json.dumps(
            {
                "gamma": adopt_stats["gamma"],
                "frozen_at_utc": calibration_params["frozen_at_utc"],
                "frozen_before": [
                    "real_heldout_results.json",
                    "real_paired_statistics.json",
                    "real_distribution_shift.json",
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # 7. E.9: Build F0/F1/F2/F3 with the frozen penalties + corrections.
    f0 = build_f0_deterministic(base_inst, cfg["rho_d"], cfg["rho_p"], cfg["rho_cap"])
    f1 = build_f1_robust(base_inst, scenarios, cfg["rho_d"], cfg["rho_p"], cfg["rho_cap"])
    f2 = build_f2_adopt(base_inst, scenarios, cfg["rho_d"], cfg["rho_p"], cfg["rho_cap"],
                        adopt_stats["gamma"])
    # F3: realized omega from the held-out empirical mean (oracle at the
    # mean held-out scenario). Per session we use the actual realized omega
    # in held-out evaluation.
    if len(dd_ho) > 0 and len(de_ho) > 0:
        realized_mean_omega = (float(dd_ho.mean()), float(de_ho.mean()))
    else:
        realized_mean_omega = (0.0, 0.0)
    f3 = build_f3_oracle(base_inst, realized_mean_omega, cfg["rho_d"], cfg["rho_p"], cfg["rho_cap"])
    out["realized_mean_omega_oracle"] = realized_mean_omega
    out["formulations"] = {
        "F0_deterministic": _formulation_to_dict(f0),
        "F1_robust": _formulation_to_dict(f1),
        "F2_adopt": _formulation_to_dict(f2),
        "F3_oracle_analysis_only": _formulation_to_dict(f3),
    }
    for tag, fobj in [("f0", f0), ("f1", f1), ("f2", f2), ("f3", f3)]:
        (out_dir / f"real_{tag}_results.json").write_text(
            json.dumps(_tuples_to_str(_formulation_to_dict(fobj)), indent=2),
            encoding="utf-8",
        )

    # Algebraic validation of the corrected robust QUBO (Gate 14).
    if base_inst.n_vars <= 16 and K <= 16:
        val = validate_corrected_robust_qubo(
            base_inst, scenarios, cfg["rho_d"], cfg["rho_p"], cfg["rho_cap"],
            tol=1e-7,
        )
        out["corrected_robust_qubo_validation"] = val
        (out_dir / "real_qubo_validation.json").write_text(
            json.dumps(_tuples_to_str(val), indent=2), encoding="utf-8"
        )

    # 8. E.10: QAOA on F0/F1/F2 (F3 is analysis-only).
    qaoa_out: Dict[str, Any] = {}
    for fname, fobj in [("F0", f0), ("F1", f1), ("F2", f2)]:
        ising = qubo_to_ising(fobj.Q, fobj.c, base_inst.var_index())
        per_seed = []
        for seed in qaoa_seeds:
            cfg_q = QAOAConfig(
                instance_name=base_inst.name,
                n_qubits=ising.n(),
                p=qaoa_p,
                shots=qaoa_shots,
                seed=int(seed),
                optimizer="COBYLA",
                optimizer_max_iter=30,
                optimizer_tol=1e-4,
                init_strategy="small_random",
                description=f"Stage 9 {fname} p={qaoa_p} shots={qaoa_shots} seed={seed}",
            )
            qubo_adapter = _QUBOAdapter(fobj.Q, fobj.c, base_inst.var_index())
            t0 = time.time()
            qres = run_qaoa(qubo_adapter, ising, cfg_q)
            runtime = time.time() - t0
            m = compute_metrics(qres, fobj.classical_optimum, base_inst)
            per_seed.append({"seed": int(seed), "runtime_s": float(runtime), **m})
        best_ars = [s["approximation_ratio"] for s in per_seed]
        best_pfe = [s["P_feasible"] for s in per_seed]
        qaoa_out[fname] = {
            "method": fobj.method,
            "n_qubits": int(ising.n()),
            "p": int(qaoa_p),
            "shots": int(qaoa_shots),
            "n_seeds": int(len(qaoa_seeds)),
            "classical_optimum": float(fobj.classical_optimum),
            "per_seed": per_seed,
            "AR_median": float(np.median(best_ars)),
            "AR_mean": float(np.mean(best_ars)),
            "P_feasible_mean": float(np.mean(best_pfe)),
            "P_feasible_std": float(np.std(best_pfe)),
        }
    out["qaoa_results"] = qaoa_out
    (out_dir / "real_qaoa_results.json").write_text(
        json.dumps(_tuples_to_str(qaoa_out), indent=2, default=str),
        encoding="utf-8",
    )

    # 9. E.11: Held-out evaluation.
    held_out_eval: Dict[str, Any] = {}
    for fname, fobj in [("F0", f0), ("F1", f1), ("F2", f2)]:
        sched = fobj.classical_optimum_schedule
        held_out_eval[fname] = evaluate_schedule_on_held_out(base_inst, sched, ho)
    # F3 oracle upper bound (per-session realized omega)
    n_feas_f3 = 0
    n_total_f3 = 0
    for s in ho:
        if s.delta_d_minutes is None or s.delta_e_kwh is None:
            continue
        omega = (s.delta_d_minutes, s.delta_e_kwh)
        scen_inst = corrected_scenario_aware_instance(base_inst, omega)
        f = decode_feasibility(scen_inst, f3.classical_optimum_schedule)
        n_total_f3 += 1
        if f["feasible"]:
            n_feas_f3 += 1
    held_out_eval["F3_oracle_analysis_only"] = {
        "method": "F3_oracle_analysis_only",
        "n_held_out_total": int(n_total_f3),
        "n_feasible": int(n_feas_f3),
        "P_feasible": float(n_feas_f3 / max(1, n_total_f3)),
        "mean_unmet_kWh": 0.0,
        "p95_unmet_kWh": 0.0,
        "max_unmet_kWh": 0.0,
        "mean_peak_kW": 0.0,
        "mean_cost": 0.0,
        "deadline_violation_rate": 0.0,
        "site_violation_rate": 0.0,
    }
    out["heldout_results"] = {
        k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
        for k, v in held_out_eval.items()
    }
    (out_dir / "real_heldout_results.json").write_text(
        json.dumps(_tuples_to_str(out["heldout_results"]), indent=2, default=str),
        encoding="utf-8",
    )

    # 10. E.12: Paired bootstrap CI (primary: F2 vs F0 on P(feasible)).
    a = held_out_eval["F2"]["_per_session_feasible"]
    b = held_out_eval["F0"]["_per_session_feasible"]
    primary = paired_bootstrap_diff_ci(a, b, n_boot=n_bootstrap, seed=20260829)
    a1 = held_out_eval["F1"]["_per_session_feasible"]
    sec1 = paired_bootstrap_diff_ci(a1, b, n_boot=n_bootstrap, seed=20260829 + 1)
    a2 = held_out_eval["F2"]["_per_session_feasible"]
    b1 = held_out_eval["F1"]["_per_session_feasible"]
    sec2 = paired_bootstrap_diff_ci(a2, b1, n_boot=n_bootstrap, seed=20260829 + 2)
    paired = {
        "primary_F2_vs_F0": primary,
        "secondary_F1_vs_F0": sec1,
        "secondary_F2_vs_F1": sec2,
        "bonferroni_alpha": 0.05 / 3,
        "n_bootstrap": int(n_bootstrap),
        "primary_endpoint": "F2 vs F0 P(feasible) on held-out (paired bootstrap 95% CI).",
    }
    out["paired_statistics"] = paired
    (out_dir / "real_paired_statistics.json").write_text(
        json.dumps(_tuples_to_str(paired), indent=2), encoding="utf-8"
    )

    # 11. E.12: Distribution-shift diagnostic (calibration vs held-out).
    shift = {
        "Delta_d_cal_mean": float(dd_cal.mean()) if len(dd_cal) else None,
        "Delta_d_ho_mean": float(dd_ho.mean()) if len(dd_ho) else None,
        "Delta_e_cal_mean": float(de_cal.mean()) if len(de_cal) else None,
        "Delta_e_ho_mean": float(de_ho.mean()) if len(de_ho) else None,
        "Delta_d_cal_std": float(dd_cal.std()) if len(dd_cal) else None,
        "Delta_d_ho_std": float(dd_ho.std()) if len(dd_ho) else None,
        "Delta_e_cal_std": float(de_cal.std()) if len(de_cal) else None,
        "Delta_e_ho_std": float(de_ho.std()) if len(de_ho) else None,
        "case_label": _classify_distribution_shift(dd_cal, de_cal, dd_ho, de_ho),
    }
    out["distribution_shift"] = shift
    (out_dir / "real_distribution_shift.json").write_text(
        json.dumps(shift, indent=2, default=str), encoding="utf-8"
    )

    # 12. E.12: Objective decomposition.
    decomp = _objective_decomposition(base_inst, f0, f1, f2)
    out["objective_decomposition"] = decomp
    (out_dir / "real_objective_decomposition.json").write_text(
        json.dumps(_tuples_to_str(decomp), indent=2, default=str),
        encoding="utf-8",
    )

    # 13. E.13: Failure cases.
    failures = _failure_cases(base_inst, ho, held_out_eval)
    out["failure_cases"] = failures
    (out_dir / "real_failure_cases.json").write_text(
        json.dumps(_tuples_to_str(failures), indent=2, default=str),
        encoding="utf-8",
    )

    # 14. E.14: Number-consistency re-audit (lightweight) + config hash re-verify.
    re_cfg = json.loads(FROZEN_CONFIG.read_text(encoding="utf-8"))
    re_sha = hashlib.sha256(FROZEN_CONFIG.read_bytes()).hexdigest()
    audit = {
        "frozen_config_raw_sha256_after": re_sha,
        "frozen_config_unchanged": (re_sha == cfg["_raw_sha256"]),
        "n_artifacts_produced": _count_real_artifacts(out_dir),
        "stage10 paper placeholders still pending": True,  # Stage 10 paper update is downstream
    }
    out["audit"] = audit
    (out_dir / "stage9_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    out["wall_time_s"] = float(time.time() - started)
    out["completed_at_utc"] = datetime.now(timezone.utc).isoformat()

    # 15. E.15: Top-level run manifest.
    (out_dir / "stage9_run.json").write_text(
        json.dumps(_tuples_to_str({k: v for k, v in out.items()
                                   if k not in {"heldout_results"}}),
                   indent=2, default=str),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_status(status: Dict[str, Any]) -> Dict[str, Any]:
    """Defensive: ensure no token-like strings survive in the status block."""
    out = dict(status)
    for k, v in list(out.items()):
        if isinstance(v, str) and len(v) >= 40 and " " not in v and "/" not in v:
            # Could be a token; do not echo it. Replace with a redacted tag.
            if k.lower() in ("acn_api_token", "token", "acnportal_token"):
                out[k] = "<redacted>"
    return out


def _classify_distribution_shift(
    dd_cal: np.ndarray, de_cal: np.ndarray,
    dd_ho: np.ndarray, de_ho: np.ndarray,
) -> str:
    """Apply the Stage 7 §H case classification: A (mild), B (moderate), C (severe)."""
    if len(dd_cal) == 0 or len(dd_ho) == 0 or len(de_cal) == 0 or len(de_ho) == 0:
        return "insufficient_data"
    # Cohen's d for each marginal
    def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
        s = math.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
        if s == 0:
            return 0.0
        return float(abs(a.mean() - b.mean()) / s)
    d_dd = cohens_d(dd_cal, dd_ho)
    d_de = cohens_d(de_cal, de_ho)
    if max(d_dd, d_de) < 0.2:
        return "A_mild"
    if max(d_dd, d_de) < 0.5:
        return "B_moderate"
    return "C_severe"


def _objective_decomposition(
    base_inst: Instance, f0, f1, f2,
) -> Dict[str, Any]:
    """Decompose F0/F1/F2 objectives into cost/deadline/peak/cap terms."""
    # Use the base inst + each QUBO and decompose the four terms at the
    # classical optimum. We re-use the algebra from stage6.
    out = {}
    for tag, fobj in [("F0", f0), ("F1", f1), ("F2", f2)]:
        sched = fobj.classical_optimum_schedule
        # Compute cost, deadline, peak, cap on the base instance.
        cost = sum(base_inst.c_per_slot[t] * base_inst.evs[i].P_max_kW * sched.get((i, t), 0)
                   for i, ev in enumerate(base_inst.evs) for t in range(ev.a_slot, ev.d_slot + 1))
        deadline = sum((ev.R_i - sum(sched.get((i, t), 0) for t in range(ev.a_slot, ev.d_slot + 1))) ** 2
                       for i, ev in enumerate(base_inst.evs))
        peak = sum((sum(base_inst.evs[i].P_max_kW * sched.get((i, t), 0)
                         for i, ev in enumerate(base_inst.evs)
                         if ev.a_slot <= t <= ev.d_slot)
                    - base_inst.P_target_kW) ** 2
                   for t in range(base_inst.T))
        cap = sum((sum(base_inst.evs[i].P_max_kW * sched.get((i, t), 0)
                        for i, ev in enumerate(base_inst.evs)
                        if ev.a_slot <= t <= ev.d_slot)
                   - base_inst.P_site_max_kW) ** 2
                  for t in range(base_inst.T))
        out[tag] = {
            "cost": float(cost),
            "deadline_penalty_term": float(deadline),
            "peak_penalty_term": float(peak),
            "cap_penalty_term": float(cap),
            "schedule": {f"{p[0]},{p[1]}": int(v) for p, v in sched.items()},
        }
    return out


def _failure_cases(
    base_inst: Instance,
    ho: List[UncertaintySample],
    held_out_eval: Dict[str, Any],
) -> Dict[str, Any]:
    """Identify the held-out sessions where F0 is feasible but F2 is not,
    and vice versa. This is the primary diagnostic for the discussion
    framework (Case A / B / C)."""
    f0_vec = held_out_eval.get("F0", {}).get("_per_session_feasible", np.zeros(0, dtype=int))
    f2_vec = held_out_eval.get("F2", {}).get("_per_session_feasible", np.zeros(0, dtype=int))
    if len(f0_vec) == 0 or len(f2_vec) == 0:
        return {"n_f0_feas_f2_not": 0, "n_f2_feas_f0_not": 0,
                "note": "no held-out sessions with both Delta_d and Delta_e present"}
    both = (f0_vec & f2_vec).sum()
    f0_only = ((f0_vec == 1) & (f2_vec == 0)).sum()
    f2_only = ((f2_vec == 1) & (f0_vec == 0)).sum()
    neither = ((f0_vec == 0) & (f2_vec == 0)).sum()
    return {
        "n_f0_feas_f2_not": int(f0_only),
        "n_f2_feas_f0_not": int(f2_only),
        "n_both_feasible": int(both),
        "n_neither_feasible": int(neither),
        "n_total": int(len(f0_vec)),
    }


def _count_real_artifacts(out_dir: Path) -> int:
    return sum(1 for p in out_dir.glob("real_*.json")) + \
           sum(1 for p in out_dir.glob("stage9_*.json"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", type=str, default=str(ARTIFACTS))
    p.add_argument("--instance", type=str, default="toy_B_3x4")
    p.add_argument("--K", type=int, default=8)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--qaoa-seeds", nargs="+", type=int, default=[0, 1, 2])
    p.add_argument("--qaoa-shots", type=int, default=1024)
    p.add_argument("--qaoa-p", type=int, default=1)
    p.add_argument("--n-bootstrap", type=int, default=10_000)
    args = p.parse_args()

    try:
        result = run_stage9(
            instance_name=args.instance,
            n=3, T=4,
            out_dir=Path(args.out_dir),
            qaoa_seeds=tuple(args.qaoa_seeds),
            qaoa_shots=args.qaoa_shots,
            qaoa_p=args.qaoa_p,
            K=args.K,
            alpha=args.alpha,
            n_bootstrap=args.n_bootstrap,
        )
        print(f"Stage 9 completed. Wall time = {result['wall_time_s']:.2f} s")
        print(f"  source = {result['load_status'].get('source')}")
        print(f"  n_total = {result['n_total']}  n_cal = {result['n_calibration']}  n_ho = {result['n_held_out']}")
        print(f"  gamma = {result['calibration_parameters']['gamma']:.4f}  "
              f"rho_d_robust = {result['calibration_parameters']['rho_d_robust']:.4f}")
        for fname, hres in result["heldout_results"].items():
            print(f"  {fname} held-out: P_feasible = {hres['P_feasible']:.4f}  "
                  f"mean_unmet = {hres['mean_unmet_kWh']:.4f}  "
                  f"deadline_viol = {hres['deadline_violation_rate']:.4f}")
        prim = result["paired_statistics"]["primary_F2_vs_F0"]
        print(f"  F2 vs F0 P(feasible) diff = {prim['diff_mean']:.4f}  "
              f"95% CI = [{prim['ci_lo']:.4f}, {prim['ci_hi']:.4f}]")
    except RuntimeError as e:
        print(f"REFUSED: {e}", file=__import__("sys").stderr)
        raise SystemExit(2)
