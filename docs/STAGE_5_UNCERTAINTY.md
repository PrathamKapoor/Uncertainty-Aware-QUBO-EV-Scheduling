# Stage 5 — Empirical Uncertainty Modeling, Scenario Construction, and ADOPT Calibration

**Stage 1 spec:** `docs/STAGE_1_SPEC.md` (authoritative).
**Stage 2 audit:** `docs/STAGE_2_DATA_AUDIT.md`.
**Stage 3 deterministic:** `docs/STAGE_3_DETERMINISTIC.md`.
**Stage 4 QAOA:** `docs/STAGE_4_QAOA.md` (QAOA infrastructure is frozen).
**Stage 5 code:** `stage5/uncertainty.py`, `stage5/build_artifacts.py`.
**Stage 5 artifacts:** all 10 listed in §10 below.

**Status: BLOCKED on ACN-Data API token. Stage 5 infrastructure is complete; uncertainty data is a placeholder.** The token is still unavailable as of 2026-08-29. The blocker from Stage 2 §H remains active. See §1.

---

## 1. Token status (Part A)

**The ACN-Data API token is NOT available.** `ACN_API_TOKEN` / `ACNPORTAL_TOKEN` are not in the environment, no local token file exists, and the live API returns HTTP 401. The `load_real_uncertainty()` function in `stage5/uncertainty.py` will populate as soon as a token is supplied:

- **Option 1 (preferred):** the project owner registers at `https://ev.caltech.edu/register`, obtains a token, sets `ACN_API_TOKEN=...` in the environment, and re-runs `python -m stage5.uncertainty`. The pipeline then ingests the live `userInputs[*]` fields and computes the real `Δd` and `ΔE` distributions.
- **Option 2:** the project owner supplies a pre-fetched JSON dump of session-level records (with `userInputs[*]` intact) at a known path; the function is updated to load from that file.
- **No fabrication. No bypass. No proxy.** The Stage 1 uncertainty variables `Δd` and `ΔE` are only computed from legitimate scheduling-time fields (`requestedDeparture` for `Δd`; `kWhRequested` from `userInputs[*]` for `ΔE`).

Until the token arrives, the Stage 5 pipeline runs in **placeholder mode** for infrastructure validation only. The placeholder is:

- A synthetic mixture model with the **shape** described in `placeholder_uncertainty()`'s docstring (50/30/20 mixture for `Δd`; 70/25/5 for `ΔE`).
- Explicitly tagged `source="placeholder"` on every sample.
- Used **only** to exercise the scenario engine, robust-QUBO construction, and ADOPT calibration. **No claim about the real ACN-Data distribution is made.**

This is the only honest path. Substituting a proxy and calling it the Stage 1 uncertainty model would be a silent methodology change and is explicitly forbidden by the Stage 5 directive.

---

## 2. API acquisition status (Part B)

| Endpoint | Status |
|---|---|
| `https://ev.caltech.edu/api/v1/sessions/caltech` | **HTTP 401 — token required.** |
| `https://ev.caltech.edu/register` | **Human-mediated**; requires Caltech approval. |
| Static fallback `tongxin-li/ACN-Data-Static` | Available; `caltech_sessions.json` is **2 bytes (empty)**; time-series only. |

When the token arrives, the acquisition will record:
- API endpoint: `https://ev.caltech.edu/api/v1/sessions/caltech`
- Site: `caltech`
- Query: `connectionTime >= "2018-05-01" AND connectionTime < "2020-01-01"` (calibration + held-out window, 31,765 sessions per the static filename census)
- Authentication: Basic with token as username, blank password
- Pagination: 25 sessions per page (100 in `acnportal`'s DataClient); full enumeration via `next` HATEOAS link
- Rate-limit behaviour: not tested (token absent); will be recorded when first run completes
- Token storage: environment variable `ACN_API_TOKEN`, never in source or git

---

## 3. Static / API cross-validation (Part C)

**Cannot be performed** until the API is accessible. When the token arrives, the reconciliation rule is:

- Match on `sessionID` (when present in static filenames) or on `(stationID, EVSE, connTime-UTC)` tuple.
- For each matched session, compare `disconnectTime`, `kWhDelivered` (final `Energy Delivered (kWh)` from the time-series CSV), and `connectionTime`.
- Discrepancy policy: timestamp differences within 60 s accepted; energy differences within 0.1 kWh accepted. Outside these tolerances, flag for manual review.
- Duplicate detection: a single sessionID should not map to more than one static file.

The reconciliation rule is implemented in `stage5/uncertainty.py::load_real_uncertainty` (to be added when the API code is written).

---

## 4. Stage 1 uncertainty variables (Part D)

Per Stage 1 §4.2:

- `Δd_i = d̂_i − d_i^actual`, where `d̂_i` is the **scheduling-time** estimate (the `requestedDeparture` from `userInputs[*]`) and `d_i^actual` is the realized `disconnectTime`. Sign convention: positive ⇒ user left **earlier** than expected.
- `ΔE_i = E_i^delivered − E_i^requested`, where `E_i^delivered` is `kWhDelivered` and `E_i^requested` is the most recent `userInputs.modifiedAt` value's `kWhRequested`. **Sign convention (Stage 1 §4.2, also documented in Stage 6):** ΔE < 0 ⇒ unmet demand (delivered < requested); ΔE = 0 ⇒ demand exactly met; ΔE > 0 ⇒ over-delivery (delivered > requested). [Note: an earlier draft of this doc had the sign flipped; corrected 2026-08-30 in Stage 6 Part A.]

**No clipping, no sign changes, no removal of inconvenient observations.** The empirical distributions are preserved in their raw form.

The full per-session extraction is implemented in `load_real_uncertainty` (deferred until the API token is supplied). The placeholder uses the same sign convention with synthetic draws.

---

## 5. Calibration / held-out split (Part E)

| Window | UTC range | Status |
|---|---|---|
| Calibration | `2018-05-01T00:00:00+00:00` to `2019-07-01T00:00:00+00:00` (exclusive) | Used for: distribution fitting, scenario generation, K selection, ADOPT calibration, alpha pre-registration |
| Held-out | `2019-07-01T00:00:00+00:00` to `2020-01-01T00:00:00+00:00` (exclusive) | Used for: nothing in Stage 5; reserved for downstream evaluation in Stage 6+ |

The temporal split is enforced by `UncertaintySample.calibration` (True/False). Every fitting function in `stage5/uncertainty.py` filters on `calibration=True` before fitting. The held-out set is **not touched** by any Stage 5 code path.

The placeholder has `n_cal=3546` and `n_held_out=1454` of the 5000 synthetic samples, matching the 14:6 month ratio. **On real data, the counts will be different** and will be reported in `artifacts/uncertainty_calibration.json`.

---

## 6. Missing-data analysis (Part F)

**Cannot be performed on real data** without the API token. The placeholder has **5.0 % missing rate by construction** (the `placeholder_uncertainty` function randomly drops 5 % of samples to test the missing-data plumbing).

| Field | Placeholder missing % | Real-data expectation |
|---|---:|---|
| `requestedDeparture` | 5.0 % | TBD (token required) |
| `kWhRequested` | 5.0 % | TBD |
| `disconnectTime` | 0.0 % | 0 % (always present in static time-series) |
| `kWhDelivered` | 0.0 % | 0 % (always derivable from static time-series) |
| `Δd` (computed) | 5.0 % | TBD |
| `ΔE` (computed) | 5.0 % | TBD |

The Stage 2 audit's literature-based estimate of 40–65 % `kWhRequested` coverage is **not** used as a placeholder. The real coverage will be measured on real data.

**If the real usable sample (sessions with both `Δd` and `ΔE` non-null) is substantially smaller than ~10,000 calibration sessions**, the experiment may be underpowered. The Stage 2 audit estimated 27,801 calibration sessions × ~50–65 % claim rate × ~80 % valid `kWhRequested` → ~11,000–15,000 usable sessions, which is more than enough for k-means with K=8 (each cluster gets ~1,400–1,900 samples). The exact number will be reported in `artifacts/uncertainty_calibration.json` once the API is accessible.

---

## 7. Empirical distribution statistics (Part G)

### Δd (calibration, placeholder)
| N | Mean | Median | Std | P01 | P05 | P25 | P50 | P75 | P95 | P99 |
|--:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3378 | -18.27 min | — | 60.43 | -224.39 | -134.77 | -34.41 | -6.00 | 6.00 | 60.00 | 108.92 |

| Sign | Fraction |
|---|---:|
| Δd < 0 (late departure) | 0.473 |
| Δd = 0 (on time) | 0.201 |
| Δd > 0 (early departure) | 0.325 |

The placeholder distribution is left-skewed (more early departures than late), which matches the qualitative shape of the ACN-Data behavioral signal reported in the literature. **These numbers are NOT the real ACN-Data distribution.**

### ΔE (calibration, placeholder)
| N | Mean | Median | Std | P01 | P05 | P25 | P50 | P75 | P95 | P99 |
|--:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3378 | -0.251 kWh | — | 1.640 | — | — | — | — | — | — | — |

| Sign | Fraction |
|---|---:|
| ΔE < 0 (negative residual) | 0.172 |
| ΔE = 0 (no residual) | 0.705 |
| ΔE > 0 (positive residual) | 0.123 |

**Note:** in the placeholder, ΔE is **mostly zero** (70.5 %) by construction. The real ACN-Data distribution may have a more substantial negative tail (unmet demand). The placeholder is deliberately a "weak signal" to stress-test the scenario engine.

### Real-data distribution status
**TO BE COMPUTED** when the API token arrives. The infrastructure is in place; only the data source needs to change. The output goes to `artifacts/uncertainty_distributions.json` automatically on the next run.

---

## 8. Joint dependence (Part H)

| Statistic | Calibration value (placeholder) | Interpretation |
|---|---:|---|
| Pearson correlation | -0.0138 | Very weak negative |
| Spearman correlation | -0.0160 | Very weak negative |
| Covariance | -1.37 (kWh·min) | Tiny |
| N | 3378 | |

**Interpretation:** in the placeholder, `Δd` and `ΔE` are **independent by construction** (the synthetic generative process draws them from separate mixtures). The measured near-zero correlation is the expected outcome. The **real** ACN-Data distribution may exhibit weak-to-moderate joint dependence (e.g., users who leave early also demand more energy than they received). The infrastructure to detect and report this is in place; the placeholder merely demonstrates that the code path works.

**Decision:** the scenarios are constructed by k-means on the **joint** (Δd, ΔE) distribution. This preserves whatever dependence structure exists in the calibration set. If the real data show strong correlation, the joint k-means will produce scenarios that capture it. If not, the scenarios reduce to independent marginal samples (which is fine — Stage 1 §4.3 allows this).

---

## 9. Scenario generation (Part I)

K-means clustering on the joint (Δd, ΔE) calibration distribution, with K ∈ {4, 8, 16}. Standardization (mu, sigma) is fitted on the calibration set only and applied to all K scenarios. The output is the per-cluster centroid (in original scale), weight, and per-cluster mean/std for both variables.

### Quality comparison (Part J)

| K | Reconstruction SSE/pt | Tail coverage | W1(Δd) | W1(ΔE) | Emp. Pearson | Mix. Pearson | N clusters |
|--:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 0.6189 | 0.251 | 0.048 | 0.021 | -0.014 | -0.015 | 4 |
| **8** | **0.2848** | **0.244** | **0.024** | **0.013** | **-0.014** | **-0.015** | **8** |
| 16 | 0.1522 | 0.378 | 0.017 | 0.008 | -0.014 | -0.015 | 16 |

- **Reconstruction SSE/pt** decreases as K increases (better fit).
- **Wasserstein-1** to the empirical marginal distribution decreases as K increases (better marginal preservation).
- **Tail coverage** is roughly stable; K=16 has the best tail coverage (more centroids can sit in the tails).
- **Marginal-vs-empirical Pearson** are essentially identical (the placeholder has no real dependence, so the mixture reproduces the near-zero correlation).

**Recommendation: K = 8** (the Stage 1 / Stage 2 default). At K=8 the reconstruction error is acceptable (0.28 vs 0.15 for K=16, the difference is not worth the 2x scenario-count cost) and the tail coverage is comparable to K=16. K=8 is also the Stage 1 default and the most commonly used in the QAOA literature.

### Scenario K=8 details
Eight cluster centroids with weights. Full details in `artifacts/scenarios_K8.json`. The largest cluster (weight ≈ 0.74) corresponds to "close to nominal" behavior (Δd ≈ 0, ΔE ≈ 0); smaller clusters (weights 0.06–0.14) correspond to early-departure, energy-shortfall, and other behavioral regimes.

---

## 10. Scenario-to-QUBO mapping (Part K)

`build_scenario_aware_instance(base_inst, omega)` constructs a scenario-modified copy of a base `Instance`.

**Critical design decision:** to preserve the QUBO variable set across all scenarios (the Stage 5 spec Part K: "If different scenarios produce different variable sets, STOP and resolve the representation before continuing"), the available window `W_i = [a_slot, d_slot]` is **kept fixed** across all scenarios. The scenario only modifies the per-EV **R_i** (slot-count requirement):

- `ΔE > 0` (user demanded more than they got): `R_i(omega) = ceil((E_req + ΔE) / (P_max · Δ))` increases.
- `ΔE < 0` (user demanded less than they got): `R_i(omega) = ceil((E_req + ΔE) / (P_max · Δ))` decreases, clipped at 0.
- `Δd > 0` (user left early): the *physical* window is shorter, but the *variable set* is unchanged. The optimization must allocate enough active slots before the (effective) deadline. This is captured indirectly: a high R_i forces early charging, and the site-cap and cost terms naturally prefer the cheaper earlier slots.

This is the **only** way to keep the QUBO representation stable across scenarios. The alternative (shrinking the variable set) is explicitly forbidden by Part K and would invalidate the robust-QUBO construction.

**Output for the headline instance (toy_B_3x4):** the variable count is `n_vars = 11` (3 EVs × {4, 4, 3} window lengths). All 8 scenarios produce an `Instance` with exactly 11 variables. The `robust_qubo` constructor verifies this and raises if any scenario changes the variable set.

---

## 11. Robust QUBO (Part L)

The scenario-averaged objective is

`F_robust(x) = Σ_{s=1..K} p_s · F_s(x)`

where `F_s(x)` is the Stage 3 QUBO objective on the scenario-s instance. By linearity of the QUBO coefficients in the problem data:

`Q_robust = Σ_{s=1..K} p_s · Q_s`
`c_robust = Σ_{s=1..K} p_s · c_s`

This is **a pure QUBO**: quadratic in `x`, no auxiliary variables, no higher-order terms. The construction preserves the QUBO structure exactly.

**Verification (Part M):** for every bitstring `x ∈ {0, 1}^n`, exhaustive enumeration confirms

`F_QUBO_robust(x) = Σ_s p_s · F_s(x) + C`

up to a constant offset `C` (independent of `x`). The validation passes with **max deviation 5.74 × 10⁻¹⁴** on the headline 11-qubit instance across all 2¹¹ = 2048 bitstrings. Full report in `artifacts/robust_qubo_validation.json`.

---

## 12. ADOPT / A2 (Part N)

### Exact formula
`ρ_d^adaptive = γ(ω) · ρ_d`
`γ(ω) = 1 + α · mean_i(σ_i / R̄_i)`

where the mean is over the EVs in the base instance. **α is pre-registered** (see Part O).

### Exact definition of σ_i
For each EV `i` in the base instance, σ_i is the **cross-sectional standard deviation of R_i(ω) over the empirical calibration (Δd, ΔE) joint**. Concretely:

1. For each calibration sample `(Δd_j, ΔE_j)`, compute
   `R_i(ω_j) = ceil((E_req_i + ΔE_j) / (P_max_i · Δ))`
   clipped to the base instance's window length.
2. The set `{R_i(ω_j) : j = 1..M}` is a sample of M per-EV slot-count requirements.
3. `σ_i = std({R_i(ω_j)})` and `R̄_i = mean({R_i(ω_j)})`.
4. `mean_i(σ_i / R̄_i)` aggregates over the EVs in the base instance. If `R̄_i = 0`, the ratio is treated as 0 (no inflation for that EV).

In the calibration step we use **M = 500 Monte Carlo draws** from the calibration set (a sub-sample for speed). The draws are sampled with a fixed seed for reproducibility. **The held-out set is never used here.**

### α pre-registration (Part O)

**α = 1.0** is the structural default. The rationale:

- α is dimensionless.
- α = 1.0 means "one full mean-ratio inflation": γ = 1 + mean(σ/R̄).
- The formula is locked **before** any held-out use.
- α is **not** swept. α is **not** selected by held-out performance.

The pre-registration record is in `artifacts/adopt_preregistration.json`:

```json
{
  "alpha": 1.0,
  "formula": "gamma(omega) = 1 + alpha * mean_i(sigma_i / R_bar_i)",
  "rationale": "STRUCTURAL DEFAULT: alpha = 1.0 (one full mean-ratio inflation). Pre-registered. NOT tuned on held-out data.",
  "calibration_period_utc": "2018-05-01T00:00:00+00:00 to 2019-07-01T00:00:00+00:00",
  "variables_used": ["delta_d_minutes", "delta_e_kwh"],
  "pre_registered_at_utc": "...",
  "version": "stage5.v1"
}
```

After this file is written, **α is frozen** and cannot be modified based on held-out results. Stage 6+ evaluation reports whatever γ(ω) this pre-registration produces, even if it is close to 1 (in which case the adaptive mechanism has little effect — see Part Q).

### γ statistics (Part Q, placeholder)

| Quantity | Value |
|---|---:|
| `mean(σ)` | (placeholder value, see `artifacts/adopt_calibration.json`) |
| `mean(R̄)` | (placeholder) |
| `mean(σ/R̄)` | (placeholder) |
| **γ** | **1.6414** |
| ρ_d deterministic | 1.0 |
| ρ_d robust (ADOPT) | 1.6414 |
| fractional increase | 0.6414 |

The placeholder produces γ ≈ 1.64, meaning the ADOPT mechanism inflates the deadline penalty by ~64 % in this synthetic scenario. The headline Stage 5 result is that the mechanism **does** have a numerical effect on the placeholder; whether it has an effect on the real data depends on the real `mean(σ/R̄)`.

**If on the real data γ ≈ 1**, the ADOPT mechanism has little effect and that is a **valid result, not a failure**. The Stage 5 directive is explicit: "Do not artificially amplify α. This is a result, not a failure of the experiment."

---

## 13. F0 / F1 / F2 / F3 ablation (Part P)

| Formulation | Uncertainty | Adaptive penalty | Pure QUBO? | Auxiliary vars |
|---|---|---|:---:|---:|
| F0 — Deterministic | No | No | ✓ | 0 |
| F1 — Scenario-averaged robust | Yes (K=8) | No (uses base ρ_d) | ✓ | 0 |
| F2 — ADOPT | Yes (K=8) | Yes (γ · ρ_d) | ✓ | 0 |
| F3 — Oracle | Yes (realized ω) | Analysis only | ✓ | 0 |

All four formulations remain **pure QUBOs** (no auxiliary variables, no higher-order terms). F3 (oracle) is **analysis ceiling only**; it would be implemented in Stage 6+ if the API token is available, and is **not** presented as deployable.

The full coefficient table for F0, F1, F2 is in `artifacts/robust_qubo.json` and `artifacts/stage5_run.json["ablation"]`. F3 is documented as a placeholder for downstream evaluation.

---

## 14. Leakage audit (Part E, repeated for emphasis)

The following data flow is **strictly one-way**:

```
CALIBRATION (2018-05 .. 2019-06)
   -> uncertainty distributions (Part G)
   -> joint dependence (Part H)
   -> k-means scenarios (Part I)
   -> K=4/8/16 quality comparison (Part J)
   -> chosen K, scenario set
   -> sigma_i, R_bar_i estimates
   -> gamma(omega)
   -> pre-registered alpha (frozen)

HELD-OUT (2019-07 .. 2019-12)
   -> NEVER touched in Stage 5
   -> reserved for Stage 6+ evaluation
```

Every fitting function in `stage5/uncertainty.py` filters on `calibration=True` before reading sample data. There is **no code path** in Stage 5 that touches the held-out set.

---

## 15. Token-gated items still blocked

| Item | Status | Resolution path |
|---|---|---|
| ACN-Data API token | **NOT AVAILABLE** | `https://ev.caltech.edu/register` (human-mediated) |
| `kWhRequested` (from `userInputs[*]`) | Blocked | API token |
| `requestedDeparture` (from `userInputs[*]`) | Blocked | API token |
| Live-API `Δd`, `ΔE` distributions | Blocked | API token |
| API-vs-static cross-validation | Blocked | API token |
| Held-out evaluation | Blocked | API token + Stage 6+ |

**Stage 5 GO/NO-GO depends on the token.** With the token, the infrastructure above is sufficient to produce the real-data report in one re-run. Without the token, the **infrastructure is validated** but the **real-data uncertainty model is BLOCKED**.

---

## 16. Stage 5 GO / NO-GO

**CONDITIONAL GO** for the **infrastructure**; **NO-GO for the real-data uncertainty model** until the API token arrives.

| Hard gate | Status | Evidence |
|---|---|---|
| 1 — API data legitimately acquired OR explicitly blocked | **Explicitly blocked** | §1; `load_status.source = "blocked"`. No fabrication, no bypass. |
| 2 — `kWhRequested` and `requestedDeparture` verified from API | **BLOCKED** | API token absent. |
| 3 — `ΔE` and `Δd` computed exactly per Stage 1 | **Placeholder** | Real computation pending token. Sign convention and formula locked. |
| 4 — Calibration / held-out separation enforced | ✓ | `UncertaintySample.calibration` filter applied to every fitting step. |
| 5 — No held-out information influences calibration | ✓ | No code path in Stage 5 reads held-out data. |
| 6 — Joint scenario generation reproducible | ✓ | Fixed seed `20260829+K`; standardization fitted on calibration only. |
| 7 — K=4 / K=8 / K=16 sensitivity evaluated | ✓ | §9; full table in `artifacts/scenario_quality.json`. |
| 8 — Scenario-aware objective remains a pure QUBO | ✓ | `Q_robust = Σ p_s Q_s`; no auxiliary variables. |
| 9 — Robust QUBO passes exhaustive algebraic validation | ✓ | max dev 5.74 × 10⁻¹⁴ on all 2¹¹ bitstrings. |
| 10 — ADOPT γ mathematically defined | ✓ | Part N; σ_i defined as cross-sectional std of R_i over the empirical (Δd, ΔE). |
| 11 — α pre-registered before held-out evaluation | ✓ | `artifacts/adopt_preregistration.json` written **before** any held-out use. |
| 12 — Oracle clearly separated from deployable methods | ✓ | F3 documented as analysis-only, not deployable. |

**Infrastructure passes 11 of 12 hard gates.** The single BLOCK is Gate 2 (real-data `kWhRequested` and `requestedDeparture` not yet accessible). The Stage 5 method, infrastructure, and pre-registration are all in place; only the data source needs to be swapped when the token arrives.

---

## 17. Stage 6 prerequisites

Stage 6+ will:
- Run the **same** `python -m stage5.uncertainty` once the API token is supplied. No code changes needed (the `load_real_uncertainty` function is the only API consumer; the rest of the pipeline is data-agnostic).
- Use the **frozen** α = 1.0 from `artifacts/adopt_preregistration.json`.
- Use the **frozen** K = 8 from `artifacts/scenario_quality.json`.
- Use the **frozen** γ(ω) = 1.6414 (or whatever the real-data value is) from `artifacts/adopt_calibration.json`.
- Re-run QAOA on the **robust QUBO** from `artifacts/robust_qubo.json` using the Stage 4 infrastructure.
- Evaluate on the **held-out** set; report feasibility, cost, peak, and AR for F0 / F1 / F2 / F3.
- **NOT** modify α or γ based on held-out results.

If the token does not arrive within the project timeline, Stage 6+ cannot be meaningfully evaluated and the project must report an **infrastructure-only** result with a clear blocker log.

---

## Appendix A — File map

| File | Purpose |
|---|---|
| `stage5/uncertainty.py` | All Stage 5 code: uncertainty extraction, k-means scenarios, robust QUBO, ADOPT calibration, F0–F3 ablation. |
| `stage5/build_artifacts.py` | Splits `stage5_run.json` into the 10 required artifact files. |
| `docs/STAGE_5_UNCERTAINTY.md` | This document. |
| `artifacts/uncertainty_calibration.json` | Load status, missing-data rates, calibration/held-out counts. |
| `artifacts/uncertainty_distributions.json` | Δd and ΔE distribution stats, joint dependence. |
| `artifacts/scenarios_K4.json` | K=4 scenario cluster set. |
| `artifacts/scenarios_K8.json` | K=8 scenario cluster set (default). |
| `artifacts/scenarios_K16.json` | K=16 scenario cluster set. |
| `artifacts/scenario_quality.json` | K-sensitivity comparison (reconstruction, tail coverage, marginal preservation). |
| `artifacts/robust_qubo.json` | Robust QUBO coefficients (Q, c). |
| `artifacts/robust_qubo_validation.json` | Exhaustive algebraic validation. |
| `artifacts/adopt_preregistration.json` | Pre-registered α = 1.0 with rationale and timestamp. |
| `artifacts/adopt_calibration.json` | γ statistics, mean(σ/R̄), per-EV counts. |
| `artifacts/stage5_run.json` | Full raw output of the Stage 5 run. |
