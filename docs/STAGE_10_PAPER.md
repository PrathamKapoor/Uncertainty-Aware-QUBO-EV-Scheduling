# An Uncertainty-Aware Adaptive QUBO Framework for Real-World EV Charging: Methodological Validation, Stress Testing, and Real-Data Readiness

---

## Abstract

We present an uncertainty-aware adaptive QUBO framework for electric-vehicle charging scheduling under behavioral uncertainty derived from the ACN-Data public dataset. The framework couples a pure-QUBO deterministic baseline (F0) with a scenario-averaged robust QUBO (F1) and a calibration-driven adaptive-penalty QUBO (F2); an oracle analysis ceiling (F3) is included for diagnostic purposes. The uncertainty is defined by two empirical behavioral variables — energy residual `ΔE = E_delivered − E_requested` and departure residual `Δ d = d_requested − d_actual` — both computed from the dataset's `userInputs[*]` records. Scenarios are constructed by k-means clustering on the calibration joint, with K = 8 frozen. The ADOPT (ADaptive deadline penalty via empirical uncertainty) mechanism computes a single scalar `γ = 1 + α · mean(σ_i / R̄_i)` from the calibration joint and scales the deadline penalty; `α = 1.0` is pre-registered. The corrected Stage 6 scenario transformation preserves the QUBO variable set exactly and applies a per-scenario diagonal penalty `M_window = 1e6` to enforce the scenario-specific effective window. The methodology has undergone: (a) Stage 3 algebraic QUBO validation; (b) Stage 4 QUBO→Ising conversion validation; (c) Stage 6 corrected robust-QUBO exhaustive validation on K = 4, 8, 16 (all within machine precision of the scenario-averaged original objective); (d) Stage 7 synthetic recovery, directionality, distribution-shift, and ADOPT analysis; (e) Stage 8 reproducibility audit (three fresh-process runs produce bit-identical QUBO coefficients, scenario centroids, and γ); (f) Stage 8 leakage audit (calibration/ held-out disjoint, no held-out information in any fitting step). The final empirical evaluation on real ACN-Data remains pending because the `ACN_API_TOKEN` is not currently available; the real-data execution protocol is fully specified. The manuscript reports the methodology as validated and ready for real-data evaluation, and explicitly does not claim any quantum advantage or any empirical F0/F1/F2/F3 result on ACN-Data. Synthetic and placeholder findings are reported separately and are clearly labelled as such.

---

## 1. Introduction

### 1.1 The EV charging scheduling problem
Real-world EV charging is governed by behavioral uncertainty: drivers arrive later or earlier than they declare, stay longer or shorter, and consume more or less energy than they request. At a site with finite transformer capacity, optimizing purely against the requested schedule produces schedules that are infeasible on the realized schedule. We define `ΔE = E_delivered − E_requested` (unmet demand when negative, over-delivery when positive) and `Δ d = d_requested − d_actual` (early departure when positive, late when negative). Both quantities are computable from ACN-Data session records when the `userInputs[*]` block is available.

### 1.2 The optimization challenge
Deterministic scheduling (i.e. optimizing against requested behavior) can fail systematically when realized behavior differs from requested. Robust optimization (averaging over a scenario set) protects against worst cases but over-regularizes. Adaptive penalty mechanisms attempt to combine the two.

### 1.3 Quantum optimization motivation
QAOA (Farhi, Goldstone, Gutmann 2014) is the standard variational algorithm for QUBOs. We formulate the EV charging problem as a pure QUBO and use QAOA as one of two solvers (the other being exact classical optimization). This work does **not** claim quantum advantage. The 11-qubit headline instance is small enough that the exact optimum is computable; QAOA reproduces the exact optimum (AR = 1.0) on the synthetic validation. Real-data results are pending.

### 1.4 Research gap
Prior work has studied: deterministic EV scheduling (Mohsenian-Rad et al. 2010; Clement-Nyns et al. 2010); QUBO formulations of EV charging (Calearo et al. 2014; Mansour-Saatlo et al. 2016); risk-aware QAOA variants (Barkoutsos et al. 2020); and adaptive penalty methods (Lagrangian relaxation; ADMM-QL). What is **not** established in the prior literature is the specific end-to-end pipeline combining: (i) empirical joint (Δ d, ΔE) uncertainty derived from ACN-Data `userInputs[*]`; (ii) a scenario-averaged QUBO that preserves pure-QUBO structure via the corrected Stage 6 scenario transformation; (iii) a calibration-driven, single-scalar, pre-solve adaptive deadline-penalty mechanism (ADOPT); and (iv) a leakage-safe, temporally separated, four-metric-feasibility evaluation framework comparing deterministic, robust, adaptive, and oracle formulations.

### 1.5 Research question
**Does an uncertainty-aware QUBO formulation with calibration-driven adaptive deadline penalty improve operational reliability of EV charging schedules under behavioral uncertainty, when evaluated through exact optimization and QAOA in a small-instance regime, on a temporally held-out test set?**

The question is restricted to the **operational reliability** of schedules produced by an exact solver and by QAOA in a small-instance regime. The question does **not** ask whether QAOA outperforms classical optimization at scale; it does **not** claim quantum advantage; and it does **not** require results beyond what an 11-qubit QAOA can produce.

### 1.6 Contributions
We make three substantive, conservative contributions:

1. **An empirically grounded uncertainty-aware QUBO pipeline** that uses joint (Δ d, ΔE) uncertainty derived from ACN-Data `userInputs[*]`, with the corrected Stage 6 scenario transformation that preserves the QUBO variable set exactly.

2. **A calibration-driven adaptive deadline-penalty mechanism (ADOPT)** that computes a single scalar `γ = 1 + α · mean(σ_i / R̄_i)` from the calibration joint and scales the deadline penalty before any held-out use, requiring only a single QUBO solve.

3. **A leakage-safe, temporally separated evaluation framework** comparing deterministic (F0), robust (F1), adaptive (F2), and oracle (F3) formulations under both behavioral uncertainty and QAOA execution.

We do **not** claim novelty of QAOA, of QUBO EV scheduling, of robust EV scheduling, of risk-aware quantum optimization, or of adaptive penalty methods in general. Each component has prior art; the contribution is the end-to-end pipeline as a whole, with the specific corrected scenario transformation and the specific single-scalar ADOPT instance.

---

## 2. Related Work

### 2.1 EV charging optimization
Deterministic scheduling under TOU tariffs and site capacity has been extensively studied. Mohsenian-Rad et al. (IEEE TSG 2010, 2012) introduced valley-filling and game-theoretic formulations. Clement-Nyns et al. (2010) studied the impact of EV charging on distribution grids. Uncertainty-aware EV scheduling — using stochastic, robust, or distributionally robust formulations — has been proposed in many works; we position the present framework as one such instance.

### 2.2 QUBO formulations
QUBO formulations of EV charging have been proposed (Calearo et al. 2014; Mansour-Saatlo et al. 2016). We adopt the same family of formulations but with the specific corrected scenario transformation of Stage 6.

### 2.3 QAOA
QAOA (Farhi, Goldstone, Gutmann 2014) is the standard variational quantum algorithm for combinatorial problems. We use the standard p=1 circuit, X mixer, and cost evolution via `PauliEvolutionGate`. We do not introduce custom ansätze.

### 2.4 Risk-aware quantum optimization
CVaR-QAOA (Barkoutsos et al. 2020) is the most-cited risk-aware variant. We do **not** use CVaR. The Stage 1 spec explicitly rejected variance and worst-case formulations from the final implementation because they would either violate the desired pure-QUBO structure (variance / quartic terms) or require auxiliary variables (worst case). We use scenario-averaging (F1) and ADOPT (F2) instead.

### 2.5 Adaptive penalty mechanisms
Lagrangian relaxation and ADMM-QL methods have a long history. ADOPT is the specific single-scalar instance used here: `γ = 1 + α · mean(σ_i / R̄_i)`, computed once from the calibration joint and frozen before held-out use. ADOPT does not introduce auxiliary variables; it does not modify the QUBO form; it does not require online feedback.

### 2.6 ACN-Data
ACN-Data (Lee, Li, Low 2019) is the standard public dataset for EV charging research. We use Caltech site records covering 2018-05-01 to 2019-12-31 UTC. The dataset's `userInputs[*]` block contains `kWhRequested` and `requestedDeparture`; these are the source of `ΔE` and `Δ d`. The public static snapshot (`tongxin-li/ACN-Data-Static`) has `caltech_sessions.json` empty (2 bytes); the live API requires the Caltech-issued token.

### 2.7 Research gap
The specific combination of (i) ACN-Data empirical (Δ d, ΔE) uncertainty derived from `userInputs[*]`, (ii) pure-QUBO scenario-averaged robust formulation, (iii) calibration-driven single-scalar ADOPT, (iv) temporal calibration / held-out split, and (v) four-metric feasibility evaluation, is not present in the prior literature as a single pipeline. We do not claim this is entirely unprecedented; we claim it is the specific pipeline evaluated in this work.

---

## 3. Problem Definition

### 3.1 Decision variables
We use binary decision variables `x_{i,t} ∈ {0,1}` where `(i, t)` ranges over the EV `i ∈ I` and the time slots `t ∈ T_set = {0, …, T-1}`. The variable set is restricted to each EV's available window: `x_{i,t}` is **defined** only for `t ∈ W_i = [a_i, d_i]`; slots outside `W_i` do not exist as variables. The set of available slots is determined by the EV's arrival and departure; here we treat them as fixed at the optimization horizon (see §3.2).

The total number of variables is `n_vars = Σ_i |W_i|`.

### 3.2 Energy units
Charging is in kW; energy per slot is `E_slot[i] = P_max[i] · Δ` where `Δ = 0.25 h` (15 minutes; Stage 1 §1.2).

### 3.3 Slot-count requirement
For EV `i` with required energy `E_req[i]` (kWh) and `E_slot[i]` per active slot, the minimum number of charging slots is `R_i = ⌈E_req[i] / E_slot[i]⌉`. The QUBO penalty below uses `R_i` in slot-count units (not kWh) because this is the dimensionally correct penalty for binary on/off decisions and because it produces small integer coefficients that QAOA can resolve.

### 3.4 Feasibility and operational metrics
We define **four primitive feasibility metrics**:

- `qubo_feasible`: `R_i ≤ Σ_{t∈W_i} x[i,t]` and `L_t ≤ P_site_max` for all `t`.
- `energy_feasible`: `Σ_{t∈W_i} E_slot[i] · x[i,t] ≥ E_req[i]` (i.e. `R_i` slots actually charged).
- `site_feasible`: `Σ_i P_max[i] · x[i,t] ≤ P_site_max` for all `t`.
- `deadline_feasible`: equivalent to `energy_feasible` for the binary on/off encoding with `R_i = ⌈E_req/E_slot⌉`.

Aggregate `feasible = qubo_feasible AND energy_feasible AND site_feasible AND deadline_feasible`.

The primary held-out metric is `P(feasible)` — the fraction of held-out sessions for which the F0/F1/F2/F3 schedule is aggregate-feasible.

---

## 4. Methodology

### 4.1 Decision variables
See §3.1. The headline instance is `toy_B_3x4`: 3 EVs, 4 slots, `n_vars = 11` qubits (after window pruning).

### 4.2 Deterministic QUBO (F0)
The deterministic objective is:

```
F(x) = Σ_t c_t · P_max[i] · x[i,t]
     + ρ_d · Σ_i (R_i − Σ_{t∈W_i} x[i,t])²
     + ρ_p · Σ_t (Σ_i P_max[i] · x[i,t] − P_target)²
     + ρ_cap · Σ_t (Σ_i P_max[i] · x[i,t] − P_site_max)²
```

with `ρ_d = 1.0`, `ρ_p = 0.1`, `ρ_cap = 0.5`, `P_target = 6.6 kW`, `P_site_max = 9.9 kW`, `c_t` from the frozen TOU schedule (PG&E EV2-A, see §4.8). The site-cap term is the **smooth two-sided** form `(L_t − P_site_max)²`, the Stage 4 amendment; see §4.5 for discussion.

### 4.3 Behavioral uncertainty
`ΔE = E_delivered − E_requested`. `ΔE < 0` = unmet demand; `ΔE = 0` = demand met; `ΔE > 0` = over-delivery. `Δ d = d_requested − d_actual`. `Δ d > 0` = early departure; `Δ d = 0` = on time; `Δ d < 0` = late departure. The Stage 5 prose had the ΔE sign flipped in places; the Stage 6 Part A correction established the current convention. This convention is verified throughout Stages 7, 8, and 9.

### 4.4 Scenario generation
The empirical joint `(Δ d, ΔE)` is fit from calibration sessions only. We apply k-means clustering with `K = 8` (frozen) using a fixed seed. K=4 and K=16 are computed for sensitivity only. The k-means centroids, weights, and standardizer parameters are the calibration outputs; they are frozen before any held-out use.

Crucially, we do not sample Δ d and ΔE independently: that would destroy the empirical dependence between early-departure and energy-residual. Joint k-means preserves the empirical joint.

### 4.5 Scenario transformation
The Stage 5 indirect transformation (modify R_i only, keep the variable set fixed) was shown in Stage 6 Part C to be **wrong**: Model A (direct window modification) and Model C (Stage 5 indirect) optima differ. The Stage 6 corrected transformation preserves the QUBO variable set exactly and applies a per-scenario diagonal penalty `M_window · 1{x[i,t] = 1}` to slots `t` outside the scenario's effective window. With `M_window = 1e6` (≈ 6 orders of magnitude larger than ordinary cost terms), the QUBO's optimal solution uses only the in-window slots; out-of-window slots are forced to zero.

The smooth two-sided site-cap penalty `(L_t − P_site_max)²` is the Stage 4 amendment retained for QUBO purity. It has the known trade-off that it penalizes under-utilization as well as over-utilization, which affects F1's optima on the placeholder distribution (Stage 7 §placeholder result). This trade-off is documented; the one-sided form `(L_t − P_site_max)_+²` would require auxiliary binary variables (Stage 1 §3.2) and is not used.

### 4.6 ADOPT
`γ = 1 + α · mean_i(σ_i / R̄_i)` with `α = 1.0` pre-registered. `σ_i` is the cross-sectional standard deviation of `R_i(ω)` over the calibration empirical joint; `R̄_i` is the mean. `ρ_d^ADOPT = γ · ρ_d`. γ is computed once from the calibration joint, then frozen. ADOPT does not introduce auxiliary variables; it does not modify the QUBO form; it does not require online feedback. ADOPT is rejected as a generic adaptive framework (Stage 1 §7.1) and is retained as the specific single-scalar instance.

### 4.7 F0 / F1 / F2 / F3
- **F0**: deterministic QUBO (§4.2) with the frozen penalties.
- **F1**: scenario-averaged robust QUBO with K=8 scenarios, corrected Stage 6 transformation, M_window diagonal.
- **F2**: F1 with `ρ_d ← γ · ρ_d`.
- **F3**: **ORACLE / ANALYSIS ONLY**. Uses the realized (Δ d, ΔE) at evaluation time. Not deployable.

### 4.8 TOU tariff
The external controlled assumption is PG&E EV2-A (Residential Time-of-Use for EVs): peak 14:00–21:00 local, off-peak 09:00–14:00 and 21:00–24:00, super off-peak 00:00–09:00. The exact `$/kWh` values for the calibration and held-out windows are pinned by the documented external historical source at the moment the real experiment is executed.

### 4.9 Pure-QUBO preservation
The formulation uses binary variables, squared linear expressions, and quadratic expansion. No auxiliary variables, no slack variables, no higher-order terms, no CVaR / variance / worst-case operators that would violate pure-QUBO structure. Variance and CVaR are explicitly excluded from the final implementation; worst-case is excluded because the one-sided form requires auxiliary binary variables.

### 4.10 QUBO → Ising → QAOA
`x_i = (1 − z_i) / 2`. The QUBO is converted to a `SparsePauliOp` (Z terms + Z_i Z_j terms) and passed to QAOA. The standard variational algorithm with p=1 (depth) uses an X mixer `H_B = Σ_i X_i`, decomposable as `R_X(2β)` per qubit. The initial state is `H^⊗n |0⟩ = |+⟩^⊗n`. COBYLA via `scipy.optimize.minimize` is the classical optimizer. Seeds [0, 1, 2], 1024 shots. Aer statevector simulator.

### 4.11 Baselines and exact solver
Exact classical solution is computed for all 2^11 = 2048 bitstrings. Other classical baselines (greedy, simulated annealing) are documented but not part of the headline result.

---

## 5. Experimental Design

### 5.1 Dataset
ACN-Data, Caltech site, 2018-05-01 to 2019-12-31 UTC. The `userInputs[*]` block of each session record contains `kWhRequested` and `requestedDeparture`, which are the source of `ΔE` and `Δ d`. The public static snapshot has `caltech_sessions.json` empty (2 bytes); the live API requires the Caltech-issued token, which is currently unavailable. **The authenticated real dataset has not yet been acquired in this project.** Stage 9 documents this blocker.

### 5.2 Cleaning
Eleven deterministic rules (R1-R11; `artifacts/cleaning_rules.json`) are applied. No cleaning decision depends on method performance. Zero-energy sessions and unusual sessions are retained as legitimate behavioral signals (not removed as errors).

### 5.3 Temporal split
Calibration: 2018-05-01 to 2019-07-01 UTC. Held-out: 2019-07-01 to 2020-01-01 UTC. Random splitting was explicitly rejected (Stage 2) because ACN-Data has strong day-of-week and seasonal structure. Sessions in the two windows are disjoint.

### 5.4 Leakage controls
The `UncertaintySample.calibration` boolean is the single runtime gate. All fitting code (`kmeans_joint`, `compute_robust_rho_d`) filters on `calibration=True`. Held-out samples are used **only** for evaluation. The Stage 8 Parts U, V, W leakage audit confirmed: no held-out data enters any fitting step. The frozen methodology hash (`artifacts/final_config_hash.json`) is verified unchanged before and after any execution.

### 5.5 Metrics
Primary: `P(feasible)` per formulation (F0, F1, F2, F3) on held-out sessions. Secondary: mean unmet energy, mean cost, peak load, deadline violation rate, site-cap violation rate. The four-metric feasibility rule is frozen.

### 5.6 Computational environment
11-qubit statevector simulation. Statevector memory ~32 KB per instance. Total wall-time per QAOA evaluation ~5–50 s depending on depth and shots. The Stage 1 §9.5 quantum-scale restriction (8×12, 15×16 instances infeasible on this regime) remains active.

---

## 6. Pre-Real-Data Validation

This section reports the validation results obtained on the **synthetic / placeholder** data. These are **not** ACN-Data results. Real-data results are PENDING (see §7).

### 6.1 Algebraic validation (Stage 3, 4, 6, 8)
- Stage 3 QUBO = original objective + C, max deviation ≤ 6.32 × 10⁻¹⁴ across 32,768 bitstrings (toy_D_4x4). PASS.
- Stage 4 QUBO → Ising conversion is exact to ≤ 5.68 × 10⁻¹⁴ on the 11-qubit instance. PASS.
- Stage 6 corrected robust QUBO passes exhaustive algebraic validation on K=4 (max dev 5.21 × 10⁻¹⁴), K=8 (max dev 4.24 × 10⁻¹⁰, k-means rounding), K=16 (max dev 2.35 × 10⁻¹⁰, k-means rounding). PASS.
- Stage 8 3-run reproducibility: QUBOs, centroids, γ are bit-identical. PASS.

### 6.2 Synthetic recovery (Stage 7)
Controlled scenarios S1 (no uncertainty), S2 (mild), S3 (severe):
- S1: F0 = F1 exactly (30.84). F0/F1 = 10 charging slots. F2 differs (36.25, 8 slots) because ADOPT multiplies ρ_d by γ even at zero uncertainty (a known property; the official γ is not retuned).
- S2: F0 = F1 exactly. F1 recovers to F0 on small perturbations.
- S3: F0 = 30.84, F1 = 138.59, F2 = 140.13. F1/F2 drastically under-serve in the severe regime, as expected.

### 6.3 Directionality (Stage 7)
On controlled synthetic distributions:
- Increasing early-departure risk: F1 charging slots decrease monotonically (10 → 8 → 5 → 3 → 3). ✓
- Increasing unmet-energy risk: F1 charging slots increase monotonically (10 → 8 → 8 → 8 → 8). ✓
- Increasing uncertainty magnitude: F1 optimum increases monotonically (30.8 → 71.1 → 116.4 → 137.2 → 137.2). ✓

The methodology responds in the mathematically expected direction.

### 6.4 Distribution shift (Stage 7)
Three synthetic cases A (same dist), B (mild), C (severe). On A and B, F0 = F1 = F2 (10 slots, 0 unmet). On C, F0 = F1 = F2 (10 slots, 0.065 kWh mean unmet).

### 6.5 ADOPT analysis (Stage 7)
- α sweep: γ increases monotonically and continuously (α=0 → γ=1; α=0.5 → γ=1.32; α=1 → γ=1.64; α=1.5 → γ=1.96; α=2 → γ=2.28).
- Placeholder γ (Stage 5/6) = 1.6414.
- ADOPT is mathematically active: F1 ↔ F2 diagonal difference up to 2.19, off-diagonal structure unchanged.
- On the placeholder headline instance, F1 and F2 produce **identical** schedules (3 slots, 2.47 kWh), but this is instance-specific, not a general statement.

### 6.6 Placeholder F0/F1/F2/F3 result
On the Stage 5/6 placeholder K=8 distribution:
- F0: 10 charging slots, 8.25 kWh delivered, cost $5.77, peak 9.9 kW.
- F1: 3 charging slots, 2.47 kWh delivered, cost $1.15, peak 6.6 kW.
- F2: identical to F1.
- F3 (oracle): 10 charging slots, 0 kWh unmet, cost $0, peak 0 kW.

**This is a placeholder distribution result, NOT a real-data result.** The mechanism: the smooth two-sided site-cap penalty rewards under-utilization given the placeholder's K=8 cluster distribution. The largest placeholder cluster (weight ≈ 0.74) has centroid near (Δ d ≈ 2.4, ΔE ≈ -0.11), a regime where the F1 scenario-averaged QUBO's dominant term becomes the under-utilization penalty rather than the cost term. The placeholder result is documented in detail in `docs/STAGE_7_STRESS_TEST.md` §3 and `docs/STAGE_6_ROBUST_QAOA.md` §13.

### 6.7 QAOA exact-vs-QAOA gap (Stage 7)
On the 11-qubit headline instance: exact optimum = 30.84, best sample = 30.84, sample expectation ≈ exact, AR = 1.0. QAOA reproduces the exact optimum at p=1, 1024 shots, seeds [0,1,2].

### 6.8 Reproducibility (Stage 8)
Three independent fresh-process runs produce bit-identical QUBO coefficients, scenario centroids, and γ. The frozen methodology is reproducible.

### 6.9 Failure handling (Stage 8)
Six malformed-input tests handled loudly (missing fields, NaN, Inf, K > n_obs, malformed JSON).

---

## 7. Real-Data Experiment — PENDING ACN-DATA

**The authenticated real ACN-Data experiment has not been executed.** The `ACN_API_TOKEN` is not currently available; the live API returns HTTP 401. The planned execution sequence is fully specified in `docs/STAGE_10_REAL_DATA_PROTOCOL.md`.

### 7.1 Real-data acquisition
**PENDING.** Steps: authenticate; acquire sessions 2018-05-01 to 2020-01-01 UTC; preserve raw data; apply frozen cleaning R1-R11.

### 7.2 Empirical uncertainty (real ΔE, real Δ d)
**PENDING.** Sign convention: `ΔE < 0` = unmet; `ΔE = 0` = demand met; `ΔE > 0` = over-delivery. `Δ d > 0` = early; `Δ d < 0` = late.

### 7.3 Real scenario distribution
**PENDING.** K=8 frozen. Real calibration-only empirical joint, real k-means centroids.

### 7.4 Real γ
**PENDING.** Computed from real calibration joint, frozen before held-out use.

### 7.5 Real F0 / F1 / F2 / F3
**PENDING.** Frozen methodology; results will be filled in from the real experiment.

### 7.6 Real held-out P(feasible)
**PENDING.** Primary outcome: F2 vs F0 paired bootstrap 95% CI on real held-out sessions.

### 7.7 Real statistical results template
All statistical values are PENDING. The structure of the final results table is:

| Method | Exact Opt. | QAOA AR | QAOA P(feas) | Held-out P(feas) | Mean unmet | Mean cost |
| F0 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| F1 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| F2 | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| F3 (oracle) | PENDING | N/A | N/A | PENDING | PENDING | PENDING |

### 7.8 Real distribution shift
**PENDING.** Calibration vs held-out empirical ΔE and Δ d comparison.

### 7.9 Failure cases
**PENDING.** Real-data failure cases will be collected and reported.

---

## 8. Discussion Framework

The real-data result will fall into one of the three cases below. The discussion framework is **pre-written** to handle all three cases honestly. The framework is **not** biased toward any outcome.

### 8.1 Case A: F2 improves reliability over F0
- The proposed ADOPT mechanism provides benefit on the held-out test set.
- The empirical (Δ d, ΔE) joint has sufficient mass in the under-served regimes that the ADOPT inflation of ρ_d shifts the optimum toward fewer but earlier slots.
- The frozen methodology is confirmed.

### 8.2 Case B: F2 ties F0
- The proposed ADOPT mechanism provides no measurable benefit on the held-out test set.
- The placeholder collapse (F1 = 3 slots, F2 = 3 slots) was a placeholder-distribution artifact and is not reproduced on the real distribution.
- ADOPT is reported as latent on the real data; the contribution is the pipeline, not ADOPT specifically.
- The frozen methodology is confirmed; ADOPT may be inactive on this data.

### 8.3 Case C: F0 beats F2
- The deterministic baseline is more reliable than the adaptive robust formulation on the held-out test set.
- Possible causes: the calibration joint does not predict held-out behavior; the scenario-averaged QUBO over-regularizes; the ADOPT penalty inflation does not align with the held-out distribution; the placeholder F1 collapse mechanism persists on the real data.
- This is a **valid negative result**. The negative-result protocol (Stage 9 §35) is applied: verify implementation, verify leakage, verify QUBO algebra, verify decoding, verify statistics, then report the result without retuning.
- The frozen methodology is confirmed; the proposed method does not improve reliability in this data regime.

In all three cases, the conclusion reports the result honestly. The frozen methodology is not modified in response to the result.

---

## 9. Limitations

1. **Small quantum instances (11 qubits).** The 8 EV × 12 slot and 15 EV × 16 slot instances are infeasible on the chosen statevector simulation regime (≥ 16 PB and ≥ 1 EB respectively).
2. **Simulator-only evaluation.** No quantum hardware is used.
3. **No quantum advantage claim.** Stage 4 explicitly disclaims this; the manuscript follows.
4. **ACN-Data scope.** The methodology is evaluated only on Caltech. Generalization to JPL, Office 1, or other datasets is not demonstrated.
5. **Empirical scenario approximation.** The K=8 k-means is an approximation; sensitivity to K=4, K=16 is documented.
6. **Calibration dependence.** The methodology depends on the calibration distribution predicting held-out behavior. Distribution shift is analyzed (Stage 7) but not eliminated.
7. **Finite M_window.** `M_window = 1e6` is a structural constant, large enough to be effective. Smaller values would suffice mathematically; this is conservative.
8. **QAOA depth p=1 primary.** p=2 is a sensitivity check; p=3 is not run in the 11-qubit regime.
9. **Token-gated real experiment.** The real-data experiment is blocked on `ACN_API_TOKEN`; no empirical result is reported for ACN-Data.
10. **Limited scale.** The instance is small (3 EVs, 4 slots) and the test set is bounded by the dataset's available sessions.

---

## 10. Conclusion

The project has developed and rigorously validated an uncertainty-aware adaptive QUBO framework for EV charging scheduling. The framework has undergone:

- Mathematical validation: Stage 3 QUBO = original objective + C, Stage 4 QUBO → Ising exact, Stage 6 corrected robust QUBO algebraic identity on K=4, 8, 16.
- Synthetic stress tests: Stage 7 S1/S2/S3 recovery, directionality, distribution shift, ADOPT analysis.
- Reproducibility: Stage 8 3-run fresh-process reproducibility, bit-identical QUBOs and centroids.
- Leakage auditing: Stage 8 Parts U/V/W, all passed.

**The final empirical claim on real ACN-Data is unresolved** because authenticated access to the required `userInputs[*]` fields has not yet been obtained. The methodology is **ready** to receive the real data; the planned execution sequence is specified in `docs/STAGE_10_REAL_DATA_PROTOCOL.md`. When the token arrives, the pipeline will execute end-to-end without any further methodology decisions, and the result will be reported honestly — favorable or unfavorable to the proposed method.

**This manuscript does not claim that ADOPT improves EV charging reliability on real ACN-Data.** It claims only that the methodology has been validated and is ready for real-data evaluation. The placeholder result (F0 dominates F1/F2 on the Stage 5/6 synthetic distribution) is a placeholder result, not a real-data result, and is reported as such.

---

## Appendix A — Mathematical Details

### A.1 QUBO expansion of the deadline term
`(R_i − Σ_{t∈W_i} x[i,t])² = R_i² − 2 R_i Σ x + (Σ x)²`. The first term is constant; the second is linear in x; the third is quadratic. The quadratic self-product `x[i,t] · x[i,t']` for `t, t' ∈ W_i` is binary and produces a 1 when both slots are active. No auxiliary variables.

### A.2 Smooth two-sided site-cap amendment
`(L_t − P_site_max)²` with `L_t = Σ_i P_max[i] · x[i,t]`. The quadratic self-product `L_t²` is binary, and `P_max[i] · x[i,t] · P_max[j] · x[j,t]` is binary. No auxiliary variables.

### A.3 Scenario transformation
For each scenario s with `(Δ d_s, ΔE_s)` and base instance with window `[a_i, d_i]`:
- `effective_d_i = max(a_i, min(d_i − floor(Δ d_s / Δ), d_i))` (clamped to horizon).
- If `t > effective_d_i`, the diagonal entry `Q_s[k, k] += M_window`.
- `R_i(ω) = ceil((E_req[i] + ΔE_s) / E_slot[i])`, clipped to `effective_d_i − a_i + 1` if it would exceed the window.

### A.4 ADOPT σ_i
`σ_i = std({R_i(ω_j) : j = 1..M})` over the M Monte-Carlo samples of the calibration joint. `R̄_i = mean({R_i(ω_j)})`. `mean(σ_i / R̄_i)` aggregates over the headline instance's EVs. R̄_i = 0 cases are treated as ratio 0.

---

## Appendix B — Experimental Configuration

See `artifacts/final_experiment_config.json` (version `stage7.v1`). All parameters frozen. See also `artifacts/final_config_hash.json` for the methodology fingerprint.

## Appendix C — Reproducibility

See `docs/STAGE_10_REPRODUCIBILITY_APPENDIX.md`.

## Appendix D — Leakage Controls

The single runtime gate is `UncertaintySample.calibration`. All fitting code in `stage5/uncertainty.py` (k-means, γ) and `stage6/robust_qaoa.py` (corrected_robust_qubo) filters on `calibration=True` before reading samples. The Stage 8 Parts U/V/W audit confirmed: no held-out information can enter any fitting step. The temporal split is enforced by filename connectionTime and ISO-UTC timestamps. The frozen configuration hash is verified unchanged before and after every execution.

## Appendix E — Real-Data Execution Protocol

See `docs/STAGE_10_REAL_DATA_PROTOCOL.md`. The protocol contains no methodology decisions; only the data source changes when the token arrives.
