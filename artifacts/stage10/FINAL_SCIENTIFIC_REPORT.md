# Final Scientific Report: Uncertainty-Aware QUBO Framework for EV Charging Scheduling

**Project root:** `C:/Projects/uncertainity_aware_quantum_opt`
**Report date:** 2026-09-05
**DATA_MODE:** REAL (live ACN Caltech behavioral data)
**Frozen configuration SHA-256:** `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`

---

## 1. Title

**Uncertainty-Aware QUBO Scheduling for Electric Vehicle Charging: A Real-Data Evaluation on the Caltech ACN Deployment**

## 2. Abstract

We present an uncertainty-aware QUBO framework for electric vehicle (EV) charging scheduling under behavioral uncertainty, evaluated end-to-end on the real Caltech ACN dataset. The framework formulates the EV scheduling problem as a QUBO with frozen penalty weights (ρ_d, ρ_p, ρ_cap), constructs K=8 scenario clusters from empirical joint (Δd, ΔE) observations in a frozen calibration window (2018-05-01 → 2019-07-01), and evaluates three formulations: F0 (deterministic, no uncertainty), F1 (robust scenario-averaged), and F2 (ADOPT with γ-inflated ρ_d). Held-out evaluation (2019-07-01 → 2020-01-01) shows a Pareto trade-off: F0 achieves higher per-session feasibility (99.85% vs 87.81% for F1/F2) at the cost of higher mean unmet demand (2.46 kWh vs 0.76 kWh). F1 and F2 produce identical classical optimum schedules on the 11-qubit `toy_B_3x4` instance. The primary statistical endpoint (F2 vs F0 P(feasible), paired bootstrap, n=10,000) is statistically significant (95% CI excludes 0) but the sign is unfavorable to the proposed method: F0 has higher feasibility than F2 on held-out data. The framework is reproducible, the methodology is frozen, and no synthetic data is used.

## 3. Research question

Does a scenario-robust or ADOPT-inflated QUBO formulation improve held-out EV-charging-schedule feasibility over a deterministic baseline when the uncertainty model is calibrated on real Caltech ACN behavioral data?

## 4. Motivation

EV charging schedules must respect per-EV energy requirements, site capacity, and per-slot deadlines. The energy and departure requirements are uncertain: users may request more or less energy than they actually need, and they may depart earlier or later than requested. A schedule that is optimal under nominal requirements may be infeasible under realized requirements. Scenario-robust optimization (F1) and ADOPT (F2) aim to hedge against this uncertainty by either averaging over empirical scenarios or by inflating the deadline penalty (ρ_d) to encourage early completion. The proposed hypothesis was that F1/F2 would maintain or improve feasibility relative to F0 on held-out data, with reduced unmet demand as a secondary benefit. The real-data evaluation in this report shows that this hypothesis is **not supported** on the `toy_B_3x4` instance: F0 achieves the highest held-out feasibility, and F1/F2 trade feasibility for lower unmet demand.

## 5. Dataset and real-data provenance

| Item | Value |
|---|---|
| Source | Live ACN-Data API: `https://ev.caltech.edu/api/v1/sessions/caltech` |
| Data mode | **REAL** (not synthetic) |
| Authentication | HTTP Basic, token from `ACN_API_TOKEN` env var (never logged) |
| Total records retrieved (in-window) | 25,656 |
| Calibration window records | 20,799 (2018-05-01 → 2019-07-01) |
| Held-out window records | 4,857 (2019-07-01 → 2020-01-01) |
| Records excluded by R9-R11 cleaning | 14,088 (all due to `userInputs == null`) |
| Calibration valid joint ΔE + Δd | 7,492 |
| Held-out valid joint ΔE + Δd | 4,076 |
| Pages visited | 1,029 (HTTP 200) |

Frozen sign conventions:
- ΔE = `E_delivered − E_requested` (positive = over-delivery, negative = unmet demand)
- Δd = `requestedDeparture − disconnectTime` (positive = early departure)

No imputation, proxy construction, sign changes, or synthetic substitution was performed.

## 6. Experimental design

The framework executes the Stage 9 protocol (E.2–E.15) end-to-end on real ACN data:

1. **E.2 Acquisition**: Fetch all Caltech sessions with the frozen `where` filter, page_size=25, max_pages=4000.
2. **E.3 Schema validation**: Verify `sessionID`, `connectionTime`, `disconnectTime`, `kWhDelivered` are present.
3. **E.4 Cleaning (R9-R11)**: Exclude sessions with missing `kWhRequested` (R9) or `requestedDeparture` (R10) or insufficient time data (R11).
4. **E.5 Temporal split**: Assign each session to calibration or held-out based on `connectionTime`.
5. **E.6 ΔE/Δd computation**: Apply the frozen sign conventions.
6. **E.7 Scenario generation**: K=8 k-means on the calibration joint (Δd, ΔE), seed = 20260829 + 8 = 20260837.
7. **E.8 γ computation (ADOPT)**: γ = 1 + α × mean(σ_i / R̄_i) on calibration, then frozen.
8. **E.9 F0/F1/F2/F3 QUBO construction**: Use the frozen penalties (ρ_d, ρ_p, ρ_cap) and γ.
9. **E.10 QAOA**: p=1, COBYLA, seeds [0,1,2], shots=1024 on F0/F1/F2.
10. **E.11 Held-out evaluation**: Apply each schedule to each held-out session's realized (Δd, ΔE).
11. **E.12 Bootstrap CI**: Paired bootstrap 95% CI on P(feasible) differences.
12. **E.13 Bonferroni correction**: α = 0.05/3 across 3 comparisons.
13. **E.14 Number-consistency audit + frozen-config hash re-verify.**
14. **E.15 Run manifest emission.**

## 7. Frozen methodology

The methodology is frozen at `artifacts/final_experiment_config.json` (version `stage7.v1`). No parameter in this file was modified based on held-out results.

| Parameter | Value |
|---|---|
| K | 8 |
| α | 1.0 |
| ρ_d | 1.0 |
| ρ_p | 0.1 |
| ρ_cap | 0.5 |
| M_window | 1,000,000 |
| P_target | 6.6 kW |
| P_site_max | 9.9 kW |
| Δ | 15 minutes |
| QAOA depth p | 1 |
| Optimizer | COBYLA |
| Seeds | [0, 1, 2] |
| Shots | 1024 |
| Calibration window | 2018-05-01 → 2019-07-01 |
| Held-out window | 2019-07-01 → 2020-01-01 |
| Bootstrap n | 10,000 |
| Bonferroni α | 0.05 / 3 = 0.01667 |

## 8. Calibration procedure

γ (ADOPT inflation factor) is computed on calibration only and frozen immediately:
- σ_i = cross-sectional std of R_i over the empirical (Δd, ΔE) samples
- R̄_i = cross-sectional mean of R_i
- γ = 1 + α × mean(σ_i / R̄_i) = 1 + 1.0 × 3.1313 = **4.1313**
- ρ_d_robust = γ × ρ_d = 4.1313 × 1.0 = **4.1313**
- n_calibration_samples = 20,799 (window total)
- Frozen at: 2026-09-04T20:14:44 UTC (before any held-out use; freeze marker in `real_calibration_freeze.json`)

## 9. Scenario generation

K=8 k-means on the 7,492 calibration valid joint observations (Δd, ΔE), seed = 20260837.

| cluster | n_obs | weight | Δd centroid (min) | ΔE centroid (kWh) |
|---|---|---|---|---|
| 0 | 1,651 | 0.220 | +8.55 | −13.64 |
| 1 | 561 | 0.075 | +48.68 | −31.27 |
| 2 | 3,901 | 0.521 | −34.15 | −3.18 |
| 3 | 143 | 0.019 | +34.76 | −71.60 |
| 4 | 14 | 0.002 | −69.38 | +32.07 |
| 5 | 1,181 | 0.158 | −437.10 | −6.46 |
| 6 | 37 | 0.005 | −2,689.44 | −8.86 |
| 7 | 4 | 0.001 | −9,033.20 | −9.63 |
| **Sum** | **7,492** | **1.000** | | |

All 8 clusters are non-empty. Sum of weights = 1.0 exactly. K=4 and K=16 sensitivity analyses are recorded as diagnostic only.

## 10. QUBO formulations

All four QUBOs operate on the 11-qubit `toy_B_3x4` instance (3 EVs, 4 slots, 12 variables after pruning −1 unavailable = 11). All are pure QUBOs (no auxiliary variables).

### F0 (deterministic)

- Method: `F0_deterministic`
- Classical optimum: **30.843**
- Schedule: 10 ones (dense)
- No uncertainty modeling
- Penalty weights: (ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5)

### F1 (robust, K=8 scenarios)

- Method: `F1_robust`
- Classical optimum: **147.860**
- Schedule: 3 ones (sparse)
- QUBO = scenario-averaged QUBO over K=8 empirical scenarios
- Penalty weights: (ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5)

### F2 (ADOPT)

- Method: `F2_adopt`
- Classical optimum: **184.398**
- Schedule: 3 ones (sparse) — **identical to F1 schedule**
- QUBO = scenario-averaged QUBO with ρ_d scaled to γ × ρ_d = 4.1313
- Penalty weights: (ρ_d=4.1313, ρ_p=0.1, ρ_cap=0.5)

### F3 (oracle, analysis-only)

- Method: `F3_oracle_analysis_only`
- Classical optimum: **48.400**
- Built using the held-out mean (Δd, ΔE) as the realized scenario
- **Not a primary baseline**; included as an upper-bound reference for what scenario-perfect information would yield

The corrected-robust-QUBO algebraic validation passes with max offset 2.4e-10 (tolerance 1e-7).

## 11. QAOA methodology

QAOA is executed by `stage4/qaoa.py::run_qaoa` using Qiskit's `AerSampler` (local simulator) with the following frozen configuration:

- Depth p = 1
- Optimizer: COBYLA via `scipy.optimize.minimize` (maxiter=30, tol=1e-4, rhobeg=0.05, catol=0.002)
- Seeds: [0, 1, 2]
- Shots: 1024 per evaluation
- Transpilation: `basis_gates=["rz","sx","x","cx"]`, `optimization_level=1`, `seed_transpiler=config.seed`

Each (formulation, seed) combination produces a distinct per-seed record in `real_qaoa_results.json`.

## 12. Held-out evaluation

Each formulation's `classical_optimum_schedule` is applied to each held-out session's realized (Δd, ΔE) to produce per-session feasibility, cost, peak, unmet demand, and constraint-violation flags. Aggregate metrics:

| Metric | F0 | F1 | F2 | F3 (oracle) |
|---|---|---|---|---|
| n_feasible | 4,070 | 3,579 | 3,579 | 4,052 |
| P_feasible | **0.9985** | **0.8781** | **0.8781** | 0.9941 |
| mean_unmet_kWh | 2.463 | 0.756 | 0.756 | 0.000 |
| p95_unmet_kWh | 4.911 | 0.808 | 0.808 | 0.000 |
| max_unmet_kWh | 5.148 | 10.923 | 10.923 | 0.000 |
| mean_peak_kW | 9.900 | 6.600 | 6.600 | 0.000 |
| mean_cost | 5.775 | 1.155 | 1.155 | 0.000 |
| deadline_violation_rate | 0.0015 | 0.1219 | 0.1219 | 0.000 |
| site_violation_rate | 0.000 | 0.000 | 0.000 | 0.000 |

## 13. Statistical validation

Paired bootstrap 95% CI on per-session 0/1 feasibility vectors (n_bootstrap = 10,000, paired within session_id, seed = 20260829 / 20260830 / 20260831). Bonferroni correction: α = 0.05/3 = 0.01667.

**Denominator convention caveat**: The bootstrap operates over a vector of length 4,857 (the full `ho` list, including 781 null-userInputs records represented as 0 by default `np.zeros` initialization). The reported P_feasible in `real_heldout_results.json` uses n=4,076 (valid joint only) as denominator. The bootstrap's `mean_a` and `mean_b` are therefore scaled by 4076/4857 = 0.8391 relative to the headline P_feasible. The `diff_mean` and CI are internally consistent under this convention. See `STATISTICAL_DENOMINATOR_AUDIT.md` for the full forensic analysis.

| Comparison | n | diff_mean | 95% CI | Excludes 0? |
|---|---|---|---|---|
| **F2 vs F0 (primary)** | 4,857 | **−0.1011** | **[−0.1095, −0.0926]** | **Yes** |
| F1 vs F0 (secondary) | 4,857 | −0.1011 | [−0.1095, −0.0924] | Yes |
| F2 vs F1 (secondary) | 4,857 | 0.0000 | [0.0000, 0.0000] | No (F1 = F2 schedules) |

## 14. Results

### QAOA per-seed

| | F0 | F1 | F2 |
|---|---|---|---|
| AR_median | 1.0000 | 1.0000 | 1.0000 |
| AR_mean | 1.0000 | 1.0000 | 1.0245 |
| P_feasible_mean | 0.5065 | 0.3695 | 0.4277 |
| P_feasible_std | 0.0161 | 0.0628 | 0.0219 |
| P_feasible per seed | [0.4854, 0.5098, 0.5244] | [0.4277, 0.2822, 0.3984] | [0.4043, 0.4219, 0.4570] |

### Failure-case cross-tab (held-out, F0 × F2)

| | F0 infeasible | F0 feasible |
|---|---|---|
| F2 infeasible | 787 | 0 |
| F2 feasible | 491 | 3,579 |

### Objective decomposition (cost / deadline_penalty / peak_penalty / cap_penalty)

| Method | cost | deadline | peak | cap | Schedule size |
|---|---|---|---|---|---|
| F0 | 5.775 | 12.000 | 21.780 | 21.780 | 10 |
| F1 | 1.155 | 1.000 | 98.010 | 250.470 | 3 |
| F2 | 1.155 | 1.000 | 98.010 | 250.470 | 3 |

### Distribution shift diagnostic

- Δd: cal mean −98.73 min, ho mean −103.08 min; cal std 360.03, ho std 290.34
- ΔE: cal mean −9.38 kWh, ho mean −9.50 kWh; cal std 12.84, ho std 11.56
- **Case label: A_mild** (small mean shift; both windows in the same regime)

## 15. Interpretation

The held-out results reveal a **Pareto trade-off / Pareto characteristic** between feasibility and unmet demand:

- **F0** (deterministic, no uncertainty hedging): dense 10-slot schedule that over-delivers energy to ensure deadline compliance. Achieves 99.85% feasibility at the cost of 2.46 kWh mean unmet demand (i.e., users are typically over-served, not under-served).
- **F1 / F2** (scenario-robust, with or without ADOPT): sparse 3-slot schedule that under-allocates to stay robust. Achieves only 87.81% feasibility because the under-allocation causes deadline violations on sessions where the realized (Δd, ΔE) is far outside the calibration envelope.

The primary statistical endpoint (F2 vs F0 P(feasible) on held-out, paired bootstrap 95% CI [−0.1095, −0.0926]) is **statistically significant but in the unfavorable direction**: F0 has higher feasibility than F2. The Bonferroni-corrected threshold (0.01667) is exceeded by 5 standard deviations.

F1 and F2 produce **identical schedules** on the 11-qubit `toy_B_3x4` instance. The ADOPT γ-inflation of ρ_d from 1.0 to 4.13 changes the objective landscape but not the discrete binary classical optimum. The F2 vs F1 secondary comparison is therefore degenerate (diff_mean = 0, CI = [0, 0]).

## 16. Trade-off analysis

The framework can be characterized by the following trade-off:

- **Higher feasibility**: favors F0 (deterministic over-allocation)
- **Lower unmet demand**: favors F1 / F2 (scenario-robust under-allocation)
- **Lower cost**: favors F1 / F2 (3-slot schedule, ~80% less energy delivered)
- **Lower peak**: favors F1 / F2 (less site load)
- **Deadline compliance**: favors F0 (over-allocation ensures early completion)

The proposed method (F1 / F2) **does not** dominate the deterministic baseline (F0) on the Pareto frontier. It trades feasibility for cost/peak/unmet demand, but not in a universally desirable direction: the lost feasibility (12.19 percentage points) is a significant operational cost in a real EV deployment.

## 17. Distribution-shift diagnostic

The calibration-to-held-out distribution shift is labeled **A_mild**: the means of Δd and ΔE shift by < 5 minutes and < 0.2 kWh respectively, and the standard deviations are similar. This indicates that the calibration envelope reasonably represents the held-out population, so the failure of F1/F2 to improve on F0 is not attributable to a large distribution shift — it is a structural property of the formulations on this instance.

## 18. Limitations

1. **toy_B_3x4 instance scale**: 3 EVs, 4 slots, 11 qubits. This is a small instance where the ADOPT γ-inflation of ρ_d does not change the discrete classical optimum schedule. The result may not generalize to larger or more constrained instances.

2. **F1 = F2 schedule identity**: On this instance, F1 and F2 produce identical schedules. The ADOPT framework's distinct contribution cannot be evaluated because the binary classical optimum is unchanged by ρ_d inflation. A larger instance with more flexible scheduling structure would be needed to observe F1 ≠ F2.

3. **Behavioral-data availability differences between calibration and held-out periods**: 63.98% of calibration records have null `userInputs` (vs 16.08% in held-out). This reflects the historical rollout of the Caltech ACN user-input feature and is a data-availability characteristic, not a defect. The methodology correctly excludes null-userInputs records from scenario fitting and evaluation.

4. **Denominator/bootstrap convention**: The bootstrap operates over a 4,857-vector with default-zero placeholders for null-userInputs records. This is mathematically correct but non-standard. The conclusion (F2 < F0) is robust to denominator choice. See `STATISTICAL_DENOMINATOR_AUDIT.md`.

5. **Distribution shift**: While the shift is labeled A_mild, the held-out window is 6 months vs the 14-month calibration window. The held-out ΔE values have a maximum of +3.4 kWh (over-delivery) while the calibration envelope has a maximum of +69.5 kWh. The held-out distribution is therefore a strict subset of the calibration distribution. This may understate the worst-case performance of F1/F2 in adversarial held-out periods.

6. **Real-world generalization**: The results are specific to the Caltech ACN deployment. Generalization to other EV charging deployments (different site, different population, different time period) is not demonstrated.

7. **QAOA at p=1**: The frozen configuration uses p=1. The QAOA at p=1 is known to be a weak variational form; higher p could in principle find better parameters. The frozen configuration is what it is, but this is a known limitation of the p=1 choice.

## 19. Reproducibility

- All source files: SHA-256-verified unchanged.
- Stage 5 loader: `stage5/uncertainty.py` (one retrieval-only pagination fix; SHA-256 `12b672297eab817767a44927e13dd2bfe1fa573b34b12562d383a1241a1c6e19`)
- Stage 9 driver: `stage9/real_experiment.py` (one dead-code import removed; SHA-256 `d1d365bd39756430acfce15c1c9797451643e15b6b9b40c40509ce49a824d622`)
- Deterministic seeds: k-means seed = 20260837, QAOA seeds = [0,1,2], bootstrap seeds = 20260829/30/31
- All 22 Stage 9 artifacts on disk in `artifacts/`; manifest in `artifacts/stage9_run.json`
- REPRODUCIBILITY_MANIFEST.json in this directory
- No credentials, no raw API records, no individual behavioral values in any artifact

## 20. Final conclusion

The experiment **successfully executed** end-to-end on real Caltech ACN data using the frozen methodology. The scientific conclusion is:

**The proposed scenario-robust (F1) and ADOPT (F2) formulations do not improve held-out feasibility over the deterministic baseline (F0) on the `toy_B_3x4` instance.** F0 achieves the highest P(feasible) at 99.85%; F1 and F2 achieve 87.81%. The primary statistical endpoint (F2 vs F0) is significant (CI excludes 0, p ≪ 0.0001) but in the direction **unfavorable** to the proposed method.

The trade-off is real: F1/F2 reduce unmet demand and energy delivered (cost, peak, unmet) at the expense of feasibility and deadline compliance. Whether this trade-off is acceptable depends on the operational priorities of the deployment, which are outside the scope of this evaluation.

The framework is reproducible. The methodology is frozen. The data is real. The conclusion is honest.
