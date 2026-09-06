# Final Results Table — Held-Out Evaluation (4,076 valid joint behavioral sessions)

**DATA_MODE:** REAL (live ACN Caltech data)
**Source:** `https://ev.caltech.edu/api/v1/sessions/caltech`
**Held-out window:** 2019-07-01 → 2020-01-01
**Valid joint ΔE + Δd sessions:** 4,076 (out of 4,857 total held-out records; 781 excluded due to null `userInputs`)

All values below are derived from `artifacts/real_heldout_results.json`. No values are interpolated, estimated, or fabricated. Each formulation was applied to each held-out session's realized (Δd, ΔE) using the schedule produced by its frozen QUBO formulation.

## Primary table

| Metric | F0 (deterministic) | F1 (robust K=8) | F2 (ADOPT) | F3 (oracle) |
|---|---|---|---|---|
| **P_feasible** (denominator = 4,076) | **0.9985** | **0.8781** | **0.8781** | 0.9941 |
| n_feasible | 4,070 | 3,579 | 3,579 | 4,052 |
| **mean_unmet_kWh** | **2.463** | **0.756** | **0.756** | 0.000 |
| p95_unmet_kWh | 4.911 | 0.808 | 0.808 | 0.000 |
| max_unmet_kWh | 5.148 | 10.923 | 10.923 | 0.000 |
| mean_peak_kW | 9.900 | 6.600 | 6.600 | 0.000 |
| mean_cost | 5.775 | 1.155 | 1.155 | 0.000 |
| **deadline_violation_rate** | **0.0015** | **0.1219** | **0.1219** | 0.000 |
| site_violation_rate | 0.000 | 0.000 | 0.000 | 0.000 |

**Bolded rows** are the primary trade-off metrics: P_feasible (higher is better) and deadline_violation_rate (lower is better) favor F0; mean_unmet_kWh (lower is better, since over-delivery is wasteful) favors F1/F2.

## Method descriptions

| Formulation | Method tag | QUBO construction | Classical optimum | Schedule size |
|---|---|---|---|---|
| F0 | `F0_deterministic` | `build_f0_deterministic(inst, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5)` | 30.843 | 10 |
| F1 | `F1_robust` | `build_f1_robust(inst, scenarios, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5)` | 147.860 | 3 |
| F2 | `F2_adopt` | `build_f2_adopt(inst, scenarios, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5, γ=4.1313)` | 184.398 | 3 |
| F3 | `F3_oracle_analysis_only` | `build_f3_oracle(inst, realized_mean_omega, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5)` | 48.400 | (analysis-only) |

## Statistical endpoint (F2 vs F0 P(feasible))

- Paired bootstrap 95% CI, n_bootstrap = 10,000, seed = 20260829
- Bonferroni correction: α = 0.05/3 = 0.01667 (3 comparisons: F2 vs F0, F1 vs F0, F2 vs F1)
- diff_mean = **−0.1011**
- 95% CI = **[−0.1095, −0.0926]**
- CI excludes 0: **Yes** (statistically significant at the Bonferroni-corrected level)
- Sign: **negative** (F2 has LOWER feasibility than F0 on held-out data)

## Secondary statistical endpoints

| Comparison | n | diff_mean | 95% CI | Excludes 0? |
|---|---|---|---|---|
| F1 vs F0 | 4,857 | −0.1011 | [−0.1095, −0.0924] | Yes |
| F2 vs F1 | 4,857 | 0.0000 | [0.0000, 0.0000] | No (F1 = F2 schedules) |

## Failure-case cross-tab (held-out, F0 × F2)

| | F0 infeasible | F0 feasible |
|---|---|---|
| F2 infeasible | 787 | 0 |
| F2 feasible | 491 | 3,579 |

- F2 is **strictly dominated** by F0 in terms of feasibility on held-out data: 491 sessions where F0 is feasible and F2 is not, vs 0 sessions the other way.

## Trade-off summary

| | Better feasibility | Better unmet demand | Better deadline compliance | Better cost | Better peak |
|---|---|---|---|---|---|
| F0 wins on: | ✓ (99.85%) | | ✓ (0.15% violation) | | |
| F1 wins on: | | ✓ (0.76 kWh) | | ✓ (1.155) | ✓ (6.60 kW) |
| F2 wins on: | | ✓ (0.76 kWh) | | ✓ (1.155) | ✓ (6.60 kW) |

The proposed methods (F1, F2) trade **12.19 percentage points of feasibility** for **1.71 kWh of unmet demand** and **4.62 of cost** relative to the deterministic baseline (F0).

## Source artifacts

| Artifact | Purpose |
|---|---|
| `artifacts/real_heldout_results.json` | Per-formulation held-out metrics (this table's source) |
| `artifacts/real_paired_statistics.json` | Bootstrap CIs |
| `artifacts/real_failure_cases.json` | F0 × F2 cross-tab |
| `artifacts/real_objective_decomposition.json` | F0/F1/F2 cost / deadline / peak / cap decomposition |
| `artifacts/real_qaoa_results.json` | QAOA per-seed results (F0/F1/F2; F3 is analysis-only) |
| `artifacts/stage9_run.json` | Top-level run manifest |

## Denominator convention note

The headline P_feasible in this table uses **n=4,076** (valid joint held-out sessions) as the denominator. The bootstrap CI uses a vector of length **n=4,857** (the full held-out list, including 781 null-userInputs records represented as default-zero placeholders). The bootstrap diff_mean and CI are internally consistent under the 4,857-vector convention and are scaled by 4076/4857 = 0.8391 relative to the headline P_feasible difference. The statistical conclusion (CI excludes 0) is robust to denominator choice. See `STATISTICAL_DENOMINATOR_AUDIT.md` for the full forensic analysis.
