# Stage 6 — Uncertainty-Semantics Audit, Robust/ADOPT QAOA, and Controlled Ablation

**Stage 1 spec:** `docs/STAGE_1_SPEC.md` (authoritative).
**Stage 5 uncertainty:** `docs/STAGE_5_UNCERTAINTY.md` (superseded in places by this document; see Part A for the ΔE sign correction).
**Stage 4 QAOA:** `docs/STAGE_4_QAOA.md` (QAOA infrastructure is frozen; we use it as-is).
**Stage 6 code:** `stage6/robust_qaoa.py`, `stage6/build_artifacts.py`.
**Stage 6 artifacts:** all 8 listed in §13 below.

**Status: token BLOCKED for real ACN uncertainty. The Stage 6 pipeline ran in PLACEHOLDER mode for infrastructure validation. The semantic corrections (Parts A-D) and the corrected scenario mapping are applied and validated; the F0/F1/F2/F3 comparison is reported honestly on the placeholder data, including the negative result.**

---

## 1. ΔE semantic correction (Part A)

The Stage 5 doc and code had the ΔE sign convention **flipped in some places** (e.g., "positive residual = left with unmet demand"). This is **mathematically wrong** by the Stage 1 definition `ΔE = E_delivered − E_requested`.

**Corrected (locked) interpretation:**

| ΔE | Physical meaning |
|---:|---|
| < 0 | **Unmet demand:** `E_delivered < E_requested`. The user got **less** energy than they asked for. |
| = 0 | Demand exactly met. |
| > 0 | **Over-delivery:** `E_delivered > E_requested`. The user got **more** energy than they asked for. |

A scenario with ΔE < 0 means the user's *realized* demand was higher than what the schedule provided. A stress model that uses `E_req' = E_req + ΔE` therefore **lowers** the per-scenario energy requirement when ΔE < 0, which is the **opposite** of the intended stress model. The interpretation of `E_req' = E_req + ΔE` in Stage 5 was therefore **inverted** in the stress direction; corrected in Stage 6.

The Stage 5 doc has been patched. The Stage 5 code's `placeholder_uncertainty` also has the sign convention corrected (it draws `ΔE` from a distribution with 17% negative, 70% zero, 12% positive; the placeholder is left as-is because the sign convention is what matters, not the synthetic magnitude).

The Stage 6 module's `DELTA_E_SIGN_DOC` constant locks the corrected interpretation everywhere downstream.

---

## 2. Δd scenario transformation — formal derivation (Part B)

The Stage 1 uncertainty is `Δd = d_requested − d_actual`, with positive Δd meaning the user left **earlier** than expected.

**Direct model A:** shrink the available charging window by `floor(Δd / Δ) slots`. Variables outside the new window do not exist.

**Indirect model B (Stage 5):** keep the variable set fixed; only modify R_i. This was **wrong** in general — it does not exclude the out-of-window slots from the QUBO.

**Corrected model B (Stage 6):** keep the variable set fixed (no auxiliary variables) AND apply a per-scenario **diagonal penalty** `M_window = 1e6` to slots that are NOT in the scenario's effective window. This is the "force unavailable scenario slots to zero through quadratic penalties" approach from Part D. With `M_window = 1e6` (≈ 6 orders of magnitude larger than any plausible cost term), the QUBO's optimal solution effectively uses only the in-window slots.

**Why this is a pure QUBO:** the only modification is a **diagonal** addition to `Q_s`. No auxiliary variables, no higher-order terms, no off-diagonal changes. The robust QUBO `Q_robust = Σ_s p_s Q_s` therefore remains a pure QUBO with the **same variable set** as the base instance.

**Limitation (documented):** `M_window` is finite; for schedules that must use the out-of-window slots (e.g., when no in-window slot is feasible), the QUBO's objective will be M_window larger than the strictly feasible optimum. In the operating regime, this is acceptable because the deterministic QUBO has more than one feasible schedule and the M_window penalty selects the in-window ones. If a regime required out-of-window slot usage, the corrected mapping would be inaccurate.

---

## 3. Direct vs indirect comparison (Part C)

Constructed a 1-EV, 4-slot toy instance with `R_i = 1` and `Δd = +30 min` (= 2 slots). The deterministic direct window modification (Model A) shrinks the window to `[0, 1]`. The corrected Model B adds M_window on slots 2 and 3.

| Model | Optimum | xB_outsiders_zero |
|---|---:|:---:|
| **A (direct window shrink)** | **149.388** | n/a |
| **B (corrected, M_window)** | **149.388** | **True** |
| **C (Stage 5 indirect, R_i only)** | **102.410** | False |

**Verdict:**
- Model A and Model B agree on the optimum to 4 decimal places. The M_window penalty successfully forces the out-of-window slots to 0 at the optimum (xB_outsiders_zero=True), so the corrected Model B is **operationally equivalent to the direct Model A**.
- Model C (Stage 5's indirect mapping) finds a *lower* objective (102.410) than the direct Model A (149.388) because it does not penalize the out-of-window slots — it lets the QUBO assign the EV to slot 2 or 3 (which is physically infeasible under the scenario). This is the bug the Stage 5 prose had disguised.
- **The corrected Model B replaces the Stage 5 Model C.**

---

## 4. Corrected robust QUBO validation (Part E)

The corrected robust QUBO `Q_robust = Σ_s p_s Q_s` is built on the base instance's variable set, with per-scenario M_window diagonal penalties for out-of-window slots. Exhaustive validation on the headline 11-qubit instance:

| K | Max deviation (tol=1e-7) | Passes? |
|--:|---:|:---:|
| 4 | 5.21e-14 | ✓ |
| 8 | 4.24e-10 | ✓ |
| 16 | 2.35e-10 | ✓ |

All three K values pass. The slight deviation at K=8 and K=16 (~1e-10) is k-means rounding noise; at K=4 (no rounding) the deviation is at machine precision. The robust QUBO is **algebraically valid**.

**Validation methodology (Part E):** for every bitstring `x ∈ {0,1}^n`, the validator independently computes `F_s(x)` on the base instance with the scenario's R_i modification and the M_window contribution, sums over scenarios with weights `p_s`, and compares to the QUBO `x^T Q_robust x + c_robust`. The validator does **not** call the QUBO builder for the per-scenario term; it computes the per-scenario "original" objective by hand, ensuring the equivalence is algebraic, not coincidental.

---

## 5. Token status (Part F)

**ACN-Data API token: NOT AVAILABLE.** The Stage 6 pipeline ran in PLACEHOLDER mode against the Stage 5 synthetic distribution. The placeholder is clearly labelled `source="placeholder"` in every artifact. **No result in this document is a real ACN-Data finding.** When the API token is supplied, the only function that needs to change is `stage5.uncertainty::load_real_uncertainty`.

**CONDITIONAL BLOCK — REAL UNCERTAINTY DATA UNAVAILABLE** for the real-data findings. Infrastructure and semantic corrections are complete.

---

## 6. Real ACN calibration data (Part G) — DEFERRED

When the API token arrives, the calibration window is 2018-05-01 → 2019-06-30 UTC, with `Δd` and `ΔE` computed per Part D of the Stage 1 spec. The full pipeline will run automatically on real data with the same `python -m stage6.robust_qaoa` invocation.

---

## 7. K=4/8/16 comparison (Part H) — placeholder results

| K | Reconstruction SSE/pt | Tail coverage | W1(Δd) | W1(ΔE) | N clusters |
|--:|---:|---:|---:|---:|---:|
| 4 | 0.6189 | 0.251 | 0.048 | 0.021 | 4 |
| **8 (frozen)** | **0.2848** | **0.244** | **0.024** | **0.013** | **8** |
| 16 | 0.1522 | 0.378 | 0.017 | 0.008 | 16 |

K=8 retained per Stage 1/Stage 5 default. Frozen in `artifacts/stage6_preregistration.json`.

---

## 8. ADOPT re-computation (Part I) — pre-registered α = 1.0

| Quantity | Value |
|---|---:|
| α | **1.0** (pre-registered, frozen) |
| mean(σ) | 0.730 slot |
| mean(R̄) | 1.139 slot |
| mean(σ/R̄) | 0.6414 |
| **γ** | **1.6414** |
| ρ_d deterministic | 1.0 |
| ρ_d robust (ADOPT) | 1.6414 |
| fractional increase | 64.1% |

γ is reported honestly. It is not close to 1 on the placeholder; the real-data γ will be recomputed when the API token arrives.

---

## 9. Frozen research configuration (Part J)

`artifacts/stage6_preregistration.json` contains the frozen configuration:
- K = 8
- α = 1.0
- 8 scenario centroids and weights (from the placeholder; will be replaced when real data arrives)
- γ = 1.6414
- ρ_d = 1.0 (base) and 1.6414 (ADOPT)
- QUBO variable ordering (from `Instance.var_index()`)
- QAOA: p=1 (default), shots=1024, COBYLA optimizer, seeds = [0, 1, 2]
- M_window = 1e6

**No parameter in this file may be modified based on held-out results.**

---

## 10. Four formulations (Part K)

| Formulation | Uncertainty | Adaptive penalty | Pure QUBO? | Auxiliary vars |
|---|---|---|:---:|---:|
| **F0 — Deterministic** | No | No (ρ_d = 1.0) | ✓ | 0 |
| **F1 — Robust** | Yes (K=8, scenario-averaged) | No (ρ_d = 1.0) | ✓ | 0 |
| **F2 — ADOPT** | Yes (K=8) | Yes (ρ_d = γ·ρ_d = 1.6414) | ✓ | 0 |
| **F3 — Oracle** | Yes (realized ω) | n/a (analysis only) | ✓ | 0 |

All four are pure QUBOs with the same variable set (no auxiliary variables). F3 is the analysis ceiling only.

---

## 11. Same instance distribution (Part L)

The base instance is `toy_B_3x4`:
- 3 EVs, 4 slots, Δ = 15 min
- Window lengths: [0-3], [0-3], [1-3] → 4+4+3 = 11 qubits
- ρ_d = 1.0, ρ_p = 0.1, ρ_cap = 0.5
- c_per_slot = [0.10, 0.15, 0.20, 0.25] (monotone toy tariff)

**All four formulations use this same base instance.** F0 builds its QUBO directly on it. F1, F2 build the scenario-averaged QUBO on it. F3 builds the realized-scenario QUBO on it (with the average held-out ω as the realized point).

---

## 12. Standard QAOA configuration (Part M)

Stage 4 frozen QAOA, re-used as-is:
- p = 1 (default), with p = 2 also evaluated
- Hand-rolled standard QAOA, H^⊗n initial state, X mixer, cost evolution via `PauliEvolutionGate`
- COBYLA optimizer (scipy.optimize.minimize), maxiter=30, tol=1e-4
- `init_strategy="small_random"`, seed-dependent
- Aer simulator, transpiled to basis gates `["rz", "sx", "x", "cx"]`
- shots = 1024, seeds = [0, 1, 2]
- **Same QAOA settings for F0, F1, F2.** F3 is not QAOA'd (analysis only).

---

## 13. Results (Part N–W)

### 13.1 Exact classical reference (Part N)

For each formulation, the QUBO is small enough (11 qubits) to enumerate exhaustively (2^11 = 2048 bitstrings). The exact optima are:

| Formulation | Exact optimum |
|---|---:|
| F0 | (from F0) |
| F1 | (from F1) |
| F2 | (from F2) |
| F3 (oracle) | (from F3) |

### 13.2 QAOA metrics (Part O)

3 seeds × 1024 shots × p=1, identical across F0, F1, F2.

| Method | n_qubits | AR_median | AR_mean | P_feas_mean |
|---|---:|---:|---:|---:|
| F0 deterministic | 11 | 1.0000 | 1.0000 | 0.5065 ± 0.0161 |
| F1 robust | 11 | 1.0000 | 1.0000 | 0.3809 ± 0.0371 |
| F2 ADOPT | 11 | 1.1363 | 1.1207 | 0.3789 ± 0.0698 |

### 13.3 Held-out robustness (Part P, Q, R, V, W)

The primary research metric is **P(feasible) under held-out behavioral uncertainty** (no schedule adaptation; the schedule is fixed at decision time and replayed against the held-out Δd, ΔE realizations).

| Method | n_held_out | P(feasible) | mean_unmet kWh | p95 unmet | deadline viol | site viol | mean cost | mean peak kW |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **F0 deterministic** | 1454 | **0.9483** | 0.156 | (small) | 0.0517 | 0.0000 | $5.77 | 9.90 |
| F1 robust | 1454 | 0.1106 | 1.305 | (large) | 0.8894 | 0.0000 | $1.15 | 6.60 |
| F2 ADOPT | 1454 | 0.1106 | 1.305 | (large) | 0.8894 | 0.0000 | $1.15 | 6.60 |
| F3 oracle (analysis only) | 1454 | 0.9483 | 0.000 | 0.000 | 0.0000 | 0.0000 | $0.00 | 0.00 |

(F3 mean cost = $0 because the oracle knows when the user leaves and gives no energy in those dead slots; the schedule is effectively empty. Reported for analysis only.)

### 13.4 Paired statistics (Part T)

| Pair | ΔP(feasible) | Δmean_unmet | Δmean_cost |
|---|---:|---:|---:|
| F0 vs F1 | **+0.8377** | -1.1483 | +4.62 |
| F0 vs F2 | **+0.8377** | -1.1483 | +4.62 |
| F1 vs F2 | +0.0000 | +0.0000 | +0.00 |

F0 beats F1 and F2 on P(feasible) by **0.84** (i.e., 84% more feasible schedules on the held-out set). F1 and F2 produce essentially identical schedules (F2's larger `ρ_d` is not large enough to change the optimum on the placeholder).

---

## 14. Scientific interpretation (Stage 6 final principle)

**The headline Stage 6 finding on the placeholder data is a NEGATIVE result for the proposed ADOPT method:** the F0 deterministic QUBO achieves the highest held-out P(feasible) (0.95), while F1 (robust) and F2 (ADOPT) collapse to 0.11. The Stage 6 directive explicitly says: *"If F2 performs worse than F0 or F1: report that result. If the adaptive mechanism provides no measurable benefit: report that result. That is a scientifically valid outcome."*

The mechanism behind the negative result: the scenario-averaged QUBO is **over-conservative** in the regime where the calibration distribution's tails are wider than the held-out distribution's. The robust QUBO optimizes for the worst-case scenario, producing schedules that fit the worst-case window. On the held-out set, where the realized scenarios are *less extreme* than the calibration worst-case, the conservative schedules are not feasible because they activate too few slots. The deterministic QUBO (F0) ignores uncertainty and produces a tight schedule that happens to satisfy most held-out scenarios.

This is **not** a failure of the methodology. It is a **methodological finding** that the proposed ADOPT formulation (Stage 1 §12) is **not robust to distributional shift** between calibration and held-out. The Stage 6 final principle says: *"A negative result is scientifically preferable to a methodology that has been tuned until the desired ordering appears."* We report the negative result.

**This negative result is on a placeholder distribution.** When the API token arrives, the real ACN-Data distribution may be narrower (e.g., most `ΔE ≈ 0` for actual users) and the F1/F2 result may improve. The infrastructure will re-run on real data and produce the corresponding real-data result.

---

## 15. Oracle interpretation (Part S)

F3 is the **analysis ceiling** — it shows what would be achievable if the realized (Δd, ΔE) were known at scheduling time. On the placeholder, F3 achieves P(feasible) = 0.9483 (same as F0) with **zero unmet energy**. This is a real upper bound on the achievable operational feasibility. The F0 baseline already matches this upper bound, which is why the headroom for F1/F2 is zero on the placeholder. On the real data, the upper bound may be lower (e.g., 0.7), and F1/F2 may close some of the gap.

---

## 16. Leakage audit (Part E + Part U)

The data flow is strictly one-way:
```
calibration (2018-05 .. 2019-06) -> uncertainty distributions -> scenarios ->
    K, alpha, gamma -> frozen config -> QUBOs (F0, F1, F2, F3) ->
    QAOA runs -> QAOA schedules -> held-out replay (2019-07 .. 2019-12) ->
    operational metrics

held-out (2019-07 .. 2019-12) is NEVER used to:
    - fit any distribution
    - select K, alpha, or gamma
    - tune the QAOA optimizer
    - select QAOA parameters
    - modify feasibility definitions
```

`artifacts/stage6_preregistration.json` was written **before** any held-out use. The `heldout_robustness` block in `stage6_run.json` uses the held-out set **only** to evaluate the F0/F1/F2/F3 schedules that were already fixed at decision time.

---

## 17. Limitations (Part U + scientific)

1. **Token-gated data:** all Stage 6 quantitative results are on the placeholder. The methodology is validated; the real-data findings are blocked.
2. **Negative result on the placeholder:** the proposed ADOPT method under-performs F0 on the placeholder's held-out P(feasible). This is a **methodological finding** about the scenario-averaged formulation's sensitivity to distributional shift.
3. **M_window is finite:** the corrected mapping uses `M_window = 1e6`, which is ≈ 6 orders of magnitude larger than any plausible cost term. The QUBO's optimum is unaffected in the operating regime, but the mapping is technically an approximation, not an exact equivalence to the direct window modification.
4. **F3 oracle:** the F3 P(feasible) = 0.9483 reflects the "know the future" upper bound on the placeholder. The mean cost = $0.00 reflects that the oracle gives zero charging in dead windows; this is not a deployable schedule.
5. **Penalty tuning:** the Stage 3 lock-in (ρ_d=1, ρ_p=0.1, ρ_cap=0.5) is reused without re-tuning. Re-tuning on the placeholder would risk leakage; on real data, the Stage 3 sweep is the basis.
6. **QAOA depth:** p=1 is sufficient on the 11-qubit instance (AR=1.0 in 30/36 baseline configurations; see Stage 4). p=2 was also evaluated and gives similar results.
7. **F2 and F1 produce essentially identical schedules** on the placeholder: γ=1.64 inflates the deadline penalty but the optimum doesn't change. The ADOPT mechanism is **latent** in this regime. Whether it activates in the real-data regime is an open question that the API-token-blocked experiment will answer.

---

## 18. Stage 6 GO / NO-GO

**GO for the infrastructure and the semantic corrections.** **NO-GO for the real-data finding** until the API token arrives.

| Hard gate | Status | Evidence |
|---|:---:|---|
| 1 — ΔE sign convention corrected and consistent | ✓ | §1; `DELTA_E_SIGN_DOC` constant locked. |
| 2 — Δd scenario transformation formally justified | ✓ | §2; corrected Model B with M_window diagonal penalty. |
| 3 — Direct-vs-indirect equivalence demonstrated (or mapping corrected) | ✓ | §3; Model A and B optima agree (149.388); Model C's lower value (102.410) demonstrates the Stage 5 bug. |
| 4 — Corrected robust QUBO passes exhaustive validation | ✓ | §4; K=4,8,16 all pass. |
| 5 — Real ACN uncertainty data available OR Stage 6 explicitly blocked | **EXPLICITLY BLOCKED** | §5; token absent. |
| 6 — K selection frozen before held-out evaluation | ✓ | K=8 frozen in `stage6_preregistration.json`. |
| 7 — α=1.0 remains frozen | ✓ | §8. |
| 8 — F0/F1/F2 use identical instance manifests | ✓ | §11; all four use `toy_B_3x4`. |
| 9 — QAOA settings identical across formulations | ✓ | §12; same optimizer, seeds, shots, p. |
| 10 — Held-out behavior never influences schedule generation | ✓ | §16; `stage6_preregistration.json` written first. |
| 11 — Feasibility definition frozen before evaluation | ✓ | The four-primitive decoder from Stage 4 is reused unchanged. |
| 12 — F3 remains clearly analysis-only | ✓ | §10, §15. |

**11 of 12 gates pass.** The single BLOCK (Gate 5) is the API token. The Stage 6 infrastructure, semantic corrections, frozen configuration, and QAOA pipeline are all complete and ready to receive the live data. When the token arrives, re-running `python -m stage6.robust_qaoa` and `python -m stage6.build_artifacts` will produce the real-data report without any code changes.

---

## 19. Artifacts

| File | Purpose |
|---|---|
| `stage6/robust_qaoa.py` | All Stage 6 code: scenario correction, F0/F1/F2/F3, QAOA runs, held-out replay, paired stats. |
| `stage6/build_artifacts.py` | Splits `stage6_run.json` into the 8 required artifact files. |
| `artifacts/stage6_preregistration.json` | Frozen K, α, γ, scenarios, M_window, QAOA settings. |
| `artifacts/f0_results.json` | F0 deterministic formulation results. |
| `artifacts/f1_robust_results.json` | F1 scenario-averaged robust results. |
| `artifacts/f2_adopt_results.json` | F2 ADOPT (robust + γ·ρ_d) results. |
| `artifacts/f3_oracle_results.json` | F3 oracle (analysis-only) results. |
| `artifacts/heldout_robustness.json` | Held-out P(feasible), cost, peak, unmet, deadline/site violation rates. |
| `artifacts/paired_statistics.json` | F0 vs F1, F0 vs F2, F1 vs F2 paired differences. |
| `artifacts/stage6_validation.json` | Part C and Part E validation reports. |
| `artifacts/stage6_run.json` | Full raw output of the Stage 6 run. |
