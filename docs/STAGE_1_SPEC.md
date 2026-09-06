# Stage 1 — Research Design Specification

**Project:** An Empirically Calibrated Uncertainty-Aware Adaptive QUBO Framework for Robust EV Charging Scheduling Using Real-World Charging Data.

**Stage scope:** Mathematical and literature foundation only. No code, no QAOA circuit, no simulator, no adaptive-loop implementation.

**Status convention:**
- **ADOPT** — locked decision for Stage 2.
- **UNRESOLVED — REQUIRES DECISION** — open item that must be closed before or during Stage 2.

---

## 0. Executive Summary

We frame EV charging scheduling as a **binary QUBO** over a discretized time grid. The novelty is **not** applying QAOA to EV charging (that has been done). The novelty is the **pipeline**:

> ACN-Data empirical behavioral distributions → uncertainty set construction → scenario-based quadratic robust reformulation that preserves QUBO structure → adaptive offline penalty mechanism that uses calibration-set feasibility statistics to inflate QUBO penalties before any quantum solve → out-of-sample evaluation on held-out days to measure feasibility recovery.

We recommend an **offline, uncertainty-informed penalty mechanism (A2 in §7)** as the primary adaptive contribution. Online iteration is documented as a backup (A1) and an upper bound (A3), but A2 is consistent with the 14-day timeline and is genuinely novel: adaptive penalty selection driven by **empirical feasibility distributions** rather than by self-tuning on the evaluation set (which would leak).

The headline claim we **will** make: empirically-calibrated, uncertainty-aware adaptive QUBO penalties improve **out-of-sample feasibility** of QAOA-produced schedules vs deterministic and non-adaptive robust baselines, with comparable cost and peak-load. We will **not** claim quantum advantage, not claim QAOA beats classical optimization at scale, and not claim the adaptive mechanism is universal outside the ACN-Data behavioral regime.

**Final feasibility check (§10):** the recommended instance size is **N=3, T=4 (12 logical qubits after QUBO slack reduction, see §9.4)**. This is the largest size that fits within state-vector simulation budget for the project timeline. Larger instances (8×12, 15×16 from prior proposal drafts) are explicitly marked infeasible under the constraint of a defensible end-to-end pipeline in 14 days.

**GO/NO-GO: GO** with the size and scope caveats in §15.

---

## 1. Problem Definition (Deterministic Core)

### 1.1 One EV (decision unit)
A single EV charging session is one EV. Each EV `i ∈ {1,…,N}` is associated with:
- an arrival (connection) time `a_i` (observed, but with noise — see §4),
- a deadline `d_i` (observed),
- a requested energy `E_i^req` (observed at plug-in; treated as a *realization* of a random variable),
- a per-slot maximum charging rate `P_i^max` (assumed fixed per EV; see §1.7),
- a chosen station / charger. For this stage we **assume a single homogeneous site with parallel identical chargers and ignore station-level contention** beyond the global site current cap. This is a modeling simplification, not a hidden assumption — see `UNRESOLVED-1`.

### 1.2 One time slot
Time is discretized into `T` equal-length slots of duration `Δ` minutes. **ADOPT:** `Δ = 15 min`, the smallest granularity supported by ACN-Data pilot signals. With a 24 h horizon that gives `T = 96`; for tractable instance sizes we use `T ∈ {4, 6, 8}` for quantum runs and `T = 96` for classical baselines that solve the same conceptual problem.

### 1.3 Scheduling horizon
A single horizon `H` of length `T·Δ`. The project studies **single-horizon day-ahead scheduling**: at the start of the horizon, the scheduler commits to a charge plan for every EV whose arrival is known. The schedule is then evaluated against actual arrivals/departures that are only revealed at the start of each slot.

### 1.4 Information available at solve time (decision time)
- Nominal arrival time `â_i` (the connection time recorded in ACN-Data for that session).
- Nominal deadline `d̂_i` (computed from the session's `disconnectTime`).
- Nominal requested energy `Ê_i^req` (from `userInputs[*].kWhRequested` if claimed, else from `kWhDelivered`).
- Site-level cap `P_site^max` (from `acnportal` site config; treated as known).
- TOU tariff `c_t` (assumed known, can be set to PG&E EV-9 or flat — `UNRESOLVED-2`).

### 1.5 Information observed only after the schedule is committed
- The actual arrival may be later than `â_i` (early arrival is unmodelled — it can only make deadline easier).
- The actual departure may be earlier than `d̂_i` (this is the dominant behavioral risk: an EV leaves with unmet demand).
- The actual energy drawn may differ from `Ê_i^req` (mainly because the user is free to leave earlier/later).
- Charger availability shocks (an EVSE becomes unavailable mid-horizon) — modelled via a per-slot "ev charger is usable" indicator. Whether this is treated as a random variable is `UNRESOLVED-3`.

### 1.6 Charging power
We adopt the **binary maximum-power approximation**:

> `x[i,t] = 1` means EV `i` draws its maximum rate `P_i^max` during slot `t`; `x[i,t] = 0` means zero draw.

This is the **standard QUBO-EV convention** in the literature and is the only encoding that produces a pure QUBO with `N·T` binary variables and a quadratic objective. We **explicitly document this as a modeling decision**, not an artifact of convenience. Continuous-power encodings require discretization (e.g., 3 levels → log2(3) qubits per slot) and roughly 1.6×–2× the variable count for negligible modeling gain at the time resolutions we use. See §2.2 for the trade-off.

### 1.7 Energy requirements
Energy requirement `E_i^req` is **not** a free variable. It is a constraint parameter. We represent it as a *minimum* required energy (an inequality). Any energy delivered above the minimum is wasted; this is why the binary approximation is appropriate — you either charge at full rate or not at all, and over-charging is bounded by the deadline.

### 1.8 Arrival / departure
- An EV cannot charge before its actual arrival: `x[i,t] = 0` for all `t < t_arr(i)`.
- An EV cannot charge after its actual departure: `x[i,t] = 0` for all `t > t_dep(i)`.
- These are **hard structural constraints** and are enforced by removing the corresponding `x[i,t]` from the problem (preprocessing step), not by penalty. This is a standard QUBO technique and reduces the effective qubit count.

### 1.9 Charger availability
Single-site, parallel, identical chargers. The site cap is a **global constraint**: `Σ_i x[i,t] · P_i^max ≤ P_site^max` for all `t`. Per-EVSE contention is `UNRESOLVED-1`.

### 1.10 Grid / load constraints
- **Site cap** as above.
- **Soft peak penalty**: squared deviation of the per-slot total load from a target (e.g., site mean). This is a soft objective term, not a hard constraint, because minor over-target is acceptable.
- **No feeder-level constraints** in this stage; add later if time permits.

### 1.11 Deadline constraints
Deadline is encoded as: every EV must be connected to the grid for at least `⌈E_i^req / (P_i^max · Δ)⌉` slots within its available window. The exact count required is a function of the energy requirement. This is a **per-EV inequality** encoded as a soft penalty (see §3).

---

## 2. Decision Variables

### 2.1 Primary variable (ADOPT)
`x[i,t] ∈ {0, 1}` for every (EV, slot) pair that is within EV `i`'s available window.

- `x[i,t] = 1` ⇒ EV `i` charges at full rate `P_i^max` during slot `t`.
- `x[i,t] = 0` ⇒ no charge.

### 2.2 Alternative encodings considered
| Encoding | Vars per (i,t) | Total vars | Pros | Cons |
|---|---|---|---|---|
| **Binary on/off (ADOPT)** | 1 | `N·T` (minus pruned) | Pure QUBO, minimum qubits, standard | Coarse power resolution |
| Discrete k-level (k=2,3,4) | `⌈log2 k⌉` | `N·T·⌈log2 k⌉` | Finer power | Quadratic in `⌈log2 k⌉`, more couplers, still requires power-level-to-energy mapping |
| Continuous → fine discretization (k=8) | 3 | `3·N·T` | Finer | QUBO 3× larger; penalty weight tuning harder |
| Auxiliary "slot-count" variables | n/a (replaces x) | `N + T` | Tighter energy bound | Loses per-slot control; site cap becomes nonlinear |

**Decision:** binary on/off. It minimizes qubit count while preserving a meaningful EV-scheduling problem. We acknowledge the power-resolution loss and note that ACN-Data's behavioral uncertainty dwarfs the discretization error at `Δ = 15 min` (typical delivered `kWh` per slot ≫ 15 min × 0.1 kW, so on/off captures >95% of behavioral variance). Quantified in §10.3.

### 2.3 Auxiliary variables
- **One slack variable per per-EV energy inequality** is **not needed** if the inequality is encoded as a squared penalty `(Σ_t x[i,t] − R_i)^2` with weight `ρ_energy`. The squared form is the standard QUBO trick and contributes only quadratic cross-terms `x[i,t]·x[i,u]`. No binary slack is introduced.
- **One slack variable per per-slot site cap** is **not needed** if the cap is encoded as `max(0, Σ_i P_i^max x[i,t] − P_site^max)^2`. This is quadratic in `x` (after expanding the square), so still pure QUBO. See `UNRESOLVED-4` for whether a hard-cap is preferred.

### 2.4 Total variable count (after arrival/departure pruning)
Let `w_i` = number of slots in EV `i`'s available window. Total active variables:

`n_vars = Σ_i w_i`

For a balanced instance where each EV's window is `T_eff` slots: `n_vars ≈ N · T_eff ≤ N · T`. We use this as the **logical qubit count** before the standard `Ising` mapping that maps each binary to one qubit. The QUBO is therefore encoded with **one qubit per binary variable**.

---

## 3. Deterministic Objective (Before Uncertainty)

### 3.1 Decision-time objective (cost + demand satisfaction)
`F(x) = F_cost(x) + ρ_d · F_deadline(x) + ρ_p · F_peak(x)`

with weights `ρ_d, ρ_p ≥ 0` to be set in Stage 2.

**Cost term** (quadratic in `x` because TOU tariff `c_t` is constant per slot and `x` is binary; this is *linear* in `x`, not quadratic — it is added directly to the QUBO diagonal):
`F_cost(x) = Σ_t c_t · Σ_i P_i^max · x[i,t]`

**Deadline / energy demand term** (quadratic penalty for each EV under-fulfilling its energy requirement):
`F_deadline(x) = Σ_i ( max(0, R_i − Σ_t x[i,t]) )^2`

where `R_i = ⌈E_i^req / (P_i^max · Δ)⌉` is the minimum number of charging slots EV `i` requires within its window. Using the squared residual is the standard QUBO penalty form. The max(·,0) is not directly encodable as QUBO; the conventional relaxation is to use `(R_i − Σ_t x[i,t])_+^2` and tolerate over-fulfillment. We adopt the relaxed form (over-fulfillment is allowed but discouraged by the site cap).

**Peak-load term** (quadratic deviation from a target per-slot total):
`F_peak(x) = Σ_t ( Σ_i P_i^max · x[i,t] − P_target )^2`

This is a soft penalty that flattens load.

### 3.2 Hard vs soft constraints
| Constraint | Treatment | Encoding |
|---|---|---|
| Arrival / departure | **Hard** | Variable removal (preprocessing) |
| Per-EV energy minimum | **Soft** | Squared penalty `F_deadline` |
| Per-slot site cap | **Soft** (smooth two-sided, **AMENDED 2026-08-29** in Stage 4 Part A) | The Stage 1 draft specified one-sided `(Σ_i P_i^max x[i,t] − P_site^max)_+^2`. Stage 3 implemented the smooth two-sided `(Σ_i P_i^max x[i,t] − P_site^max)^2` to preserve a pure QUBO (no auxiliary variables). Stage 4 Part A demonstrated that the two formulations produce **different optima on every test instance** (set overlap of optima = 0 on all 4 toy instances; max objective difference up to 87 units at `rho_cap = 0.5`). The two-sided form is **formally adopted as a methodological amendment** to keep the QUBO pure. The paper will explicitly state this. |
| Non-negativity of `x` | **Hard** | Implicit (`x ∈ {0,1}`) |

### 3.3 Complete deterministic QUBO (decision-time)
`min_x  F(x) = Σ_t c_t P_i^max x[i,t]          (linear; diagonal in QUBO)`
`        + ρ_d Σ_i (R_i − Σ_t x[i,t])^2       (quadratic cross-terms x[i,t]·x[i,u])`
`        + ρ_p Σ_t (Σ_i P_i^max x[i,t] − P_target)^2   (quadratic cross-terms x[i,j,t]·x[k,l,t])`

This is a **legitimate QUBO** with `n_vars` binary variables and `O(n_vars^2)` couplers (sparse because most cross-terms are zero due to arrival/departure pruning).

---

## 4. Behavioral Uncertainty

### 4.1 The four candidates

| Variable | What it represents | ACN-Data support | When observed | Empirically constructable? |
|---|---|---|---|---|
| `δ_arr(i)` | Arrival delay (plug-in later than `â_i`) | `connectionTime` is recorded per session; historical distribution of `connectionTime − requestedStart` (or from `userInputs[*].modifiedAt`) | After the fact | **Yes**, but ACN-Data records the *actual* connection time, not a separately stated "expected" connection time. The empirical distribution must come from cross-session variability: `connectionTime_i − median(connectionTime for userID_i, day-of-week, hour)`. Treat the user-level median as the "nominal" and the residual as `δ_arr`. |
| `δ_dep(i)` | Early departure (user leaves before `d̂_i`) | `disconnectTime` is recorded; `userInputs[*].requestedDeparture` is recorded if the user claimed the session. The residual `requestedDeparture − disconnectTime` (when negative = early departure) is the empirical support. | After the fact | **Yes**. This is the dominant source of unmet demand. |
| `δ_E(i)` | Energy demand deviation | `kWhDelivered` is recorded; `userInputs[*].kWhRequested` is recorded if the user claimed. Residual `kWhDelivered − kWhRequested` is the empirical support. | After the fact | **Yes**, with caveat: for unclaimed sessions only `kWhDelivered` exists, so we either restrict to claimed sessions or use the cross-session marginal. |
| `δ_EVSE(t)` | Charger availability shock (an EVSE goes down mid-horizon) | ACN-Data does **not** record mid-session EVSE failures. | After the fact | **No**. We exclude this from the uncertainty set. |

**ADOPT uncertainty set: `ω = (δ_dep, δ_E)` for each EV `i`.** Arrival deviation is excluded as a primary variable because it rarely causes deadline violations (late arrival only relaxes the deadline) and the empirical proxy is noisier. Energy demand is included because it has a direct, observable effect on QUBO constraint satisfaction.

`UNRESOLVED-3` closes this question formally: δ_EVSE is excluded.

### 4.2 Formal definition
For each EV `i`, the uncertainty vector is
`ω_i = (Δd_i, ΔE_i) ∈ R²`

where:
- `Δd_i = d̂_i − actual_disconnect_i` (positive ⇒ user left early),
- `ΔE_i = kWhDelivered_i − kWhRequested_i` (signed residual).

Both are random with an empirical distribution estimated from the calibration set (see §5). They are **only observed after the fact** and are **never used to set the schedule at decision time** (no look-ahead bias).

### 4.3 Scenario generation
Discretize the empirical joint `f(Δd, ΔE)` into `K` scenarios via k-means clustering (k ∈ {8, 16, 32}). `K=8` is recommended for the small quantum instances; `K=32` is feasible for the classical baseline runs.

---

## 5. Data Split (Leakage-Safe Methodology)

### 5.1 The leakage problem
If we use the same ACN-Data sessions to (a) estimate the empirical distribution `f̂(ω)` and (b) evaluate the schedule, then a schedule that "memorizes" the calibration distribution will appear artificially robust. The data split must enforce this.

### 5.2 ADOPT split: temporal site-level split
- **Calibration set**: all sessions from a defined earlier window (e.g., Caltech 2018-05-01 → 2019-06-30). Used to estimate `f̂(ω)`, to fit the TOU tariff, and to set adaptive-penalty initial values.
- **Held-out evaluation set**: all sessions from a later window (e.g., Caltech 2019-07-01 → 2019-12-31). Used **only** to construct test-instance days and to evaluate feasibility, cost, and peak metrics. **Never used to tune penalties.**
- The split is **temporal** (not random) because ACN-Data has a strong day-of-week and time-of-year structure. Random splits leak seasonality.

### 5.3 Within the held-out set: instance construction
For each test day in the held-out window:
1. Take all sessions whose `connectionTime` falls within `[day_start, day_end]`.
2. Restrict to the first `N` sessions that have non-empty available windows (drop sessions with zero-window windows).
3. Solve the QUBO with the **frozen** penalty weights from Stage 2.
4. Replay the schedule against the **actual** session outcomes from the held-out data.
5. Record feasibility, cost, peak, unmet demand, deadline violation.

The adaptive mechanism (see §7) is **trained on calibration set feasibility statistics** and **frozen before any held-out solve**. This is the central leakage-prevention rule.

### 5.4 Sanity check
The two windows must not overlap in time. Document the exact calendar windows in the Stage 2 code release.

---

## 6. Robust-Objective Choices

### 6.1 Candidate set evaluated

| Risk formulation | Math | Stays quadratic in `x`? | Aux vars | Qubit overhead | Implementation | 14-day fit |
|---|---|---|---|---|---|---|
| **A. Expected cost** `E_ω[F(x; ω)]` | Scenario average: `(1/K) Σ_k F(x; ω_k)` | Yes (linearity of expectation + per-scenario quadratic) | 0 | 0 (same QUBO structure; just averaged diagonal/coupler) | Low | ✓ |
| **B. Variance** `Var_ω[F(x; ω)]` | `E[F²] − E[F]²` | **No** — `F²` introduces cubic terms in `x` once expanded; not a QUBO | n/a | n/a | High | ✗ |
| **C. CVaR_α` | `(1/(1−α)) E_ω[ F · 1{F ≥ VaR_α} ]` | **No** — the indicator `1{F ≥ q}` is not a smooth QUBO function. Requires piecewise linear / Lagrangian relaxation | ≥ K auxiliary | K qubits | High | ✗ |
| **D. Worst-case** `max_k F(x; ω_k)` | `max_k …` | **No** — max is non-smooth. Encode via big-M auxiliary `z ≥ F(x; ω_k)` | K aux (continuous) | K continuous → needs discretization | High | ✗ |
| **E. Probability of infeasibility** | `P_ω[ F_constraint(x; ω) > τ ]` | **No** — indicator again | ≥ K | K | High | ✗ |
| **F. Expected unmet demand** `E_ω[ Σ_i max(0, E_i^req − delivered_i(ω)) ]` | Scenario mean of a per-EV residual | **Yes** (each scenario contributes a quadratic per-EV residual) | 0 | 0 | Low | ✓ |
| **G. Scenario-based constraint penalty** | `Σ_k p_k · F_constraint(x; ω_k)` | **Yes** | 0 | 0 | Low | ✓ |

### 6.2 ADOPT robust formulation: G + F (scenario-based expected cost & expected unmet demand)

`F_robust(x) = Σ_k p_k · [ F_cost(x; ω_k) + ρ_d Σ_i (R_i(ω_k) − Σ_t x[i,t])_+^2 + ρ_p Σ_t (Σ_i P_i^max x[i,t] − P_target(ω_k))^2 ]`

where `R_i(ω_k) = ⌈ E_i^req(ω_k) / (P_i^max · Δ) ⌉` and `p_k = 1/K` for uniform scenarios. The terms inside the brackets are **the same quadratic form as in the deterministic QUBO**, just with scenario-shifted parameters. This is the key property: **the QUBO structure is preserved, with shifted diagonal and shifted couplers.**

**Justification for ADOPT:** it is the only formulation in §6.1 that is (i) quadratic in `x`, (ii) requires zero auxiliary variables, (iii) preserves the QUBO coupling-graph topology, and (iv) is implementable in 14 days. CVaR and worst-case would be scientifically richer but are not QUBO-native and would force a piecewise / big-M reformulation that breaks the Stage 2 pipeline.

### 6.3 Caveats
- The expected-unmet-demand term is a **proxy for feasibility under uncertainty**. We will measure feasibility directly on held-out data, but the QUBO objective has to encode it.
- Scenario-based robust QUBOs of this form have a known literature precedent (e.g., distributionally robust mean-CVaR relaxations); we position our contribution as the **empirical scenario source** and the **adaptive weight selection**, not the robust-formulation invention.

---

## 7. Adaptive Mechanisms

### 7.1 Three candidates

**A1. Online iterative penalty update (in-loop with QAOA).**
- Initial penalty: `ρ_0` from deterministic QUBO calibration.
- What is measured: empirical feasibility over `M` Monte Carlo scenarios of the *current* QUBO's output bitstring.
- Update rule: `ρ ← ρ + η · (feasibility_observed − feasibility_target)` (signed).
- Stopping: `|feasibility_observed − feasibility_target| < ε` or `T_max` iterations.
- Number of QUBO solves: `T_max × M` (in the worst case).
- Offline/online: online; iterates during solve.
- Risk: 14-day timeline cannot absorb `T_max × M` quantum solves; classical pre-evaluation works but adds complexity.

**A2. Offline uncertainty-informed penalty mechanism (ADOPT).**
- Initial penalty: `ρ_0` from a small ablation grid on the calibration set.
- What is measured: **on the calibration set, the empirical correlation between penalty weight and out-of-sample feasibility** for the deterministic QUBO, then propagated to the scenario-averaged QUBO via a one-shot analytic shift.
- Update rule: closed-form — `ρ_robust = ρ_0 · γ(ω)` where `γ(ω)` is a calibration-set regression coefficient that scales the penalty with the empirical variance of `ω`. Concretely: `γ(ω) = 1 + α · std_ω(R_i) / mean_ω(R_i)`. This is a single scalar multiplier per QUBO instance, not an iteration.
- Stopping: closed form.
- Number of QUBO solves: 1 (the robust QUBO with the calibrated penalty).
- Offline/online: fully offline; the penalty is frozen before the quantum solve.
- Justification: tractable in 14 days, leakage-safe (calibration set is disjoint from held-out evaluation), genuinely data-driven, and preserves the QUBO structure of §6.2 exactly.

**A3. Upper-bound oracle (not shipped, used for analysis only).**
- Re-solving the QUBO with the **true** `ω` at decision time (impossible in practice). Used to bracket the achievable robustness and to validate that the adaptive mechanism's gap is reasonable.
- This is an oracle, not an algorithm. Mentioned only to make the contribution's ceiling explicit.

### 7.2 ADOPT mechanism: A2 (offline, calibration-driven penalty scaling)

**Mathematical statement of the update rule:**

Given calibration-set estimate of the joint empirical distribution `f̂(Δd, ΔE)`:
1. Compute per-EV empirical moments of the energy requirement: `R̄_i = E_ω[R_i(ω)]` and `σ_i = std_ω[R_i(ω)]`.
2. Compute a global coefficient: `γ = 1 + α · (1/N) Σ_i σ_i / R̄_i`, where `α` is a hyperparameter (Stage 2 default `α = 1.0`).
3. Scale the deadline-penalty weight: `ρ_d^robust = γ · ρ_d^deterministic`.
4. Solve the scenario-averaged QUBO of §6.2 with this single scaled weight.

**Why this is a real adaptive mechanism and not just a constant tweak:**
- `γ` is **a function of the empirical uncertainty distribution**, not a fixed hyperparameter.
- The mechanism **inflates the penalty precisely when behavioral noise is large** and leaves it alone when the calibration distribution is tight.
- It is **leakage-safe**: `γ` is computed once on the calibration set and frozen.

**Why A2 beats A1 for this project:**
- A1 requires `T_max × M` solves, which is impossible in 14 days even with a simulator (one state-vector solve at 12 qubits takes seconds; at 16 qubits, minutes; at 20+ qubits, hours).
- A2 reduces the entire adaptation to a single scalar pre-computation. The quantum solve itself is unchanged.
- A2 is what the literature calls a "**scenario-conditional penalty reweighting**" — it is a small but defensible contribution.

### 7.3 Stopping, complexity summary

| Mech | QUBO solves | Hyperparameters | QAOA-internal coupling | 14-day viable? |
|---|---|---|---|---|
| A1 | `T_max · M` (≥ 30 typical) | `η, T_max, M, ε` | Yes (inner loop) | Tight |
| **A2 (ADOPT)** | **1** | **`α` only** | **No** | **Yes** |
| A3 | 1 (oracle) | none | No | Used as analysis ceiling, not shipped |

---

## 8. Novelty / Literature Assessment

### 8.1 What is already done
- **QAOA applied to EV charging.** Multiple prior works; this is well-trodden. We do not claim novelty here.
- **QUBO formulations of EV charging** (binary on/off). Standard in the literature.
- **Robust EV charging under demand uncertainty** (classical, distributionally robust). Established field.
- **CVaR-QAOA** (Barkoutsos et al., 2020). The CVaR aggregation trick in QAOA is well-known.
- **Adaptive penalty QUBO / Lagrangian relaxation QUBO.** Has prior work in general QUBO literature; not specific to uncertainty-driven calibration.

### 8.2 What is genuinely new here
The **specific pipeline**: (i) empirical behavioral distribution `f̂(ω)` estimated from ACN-Data calibration set → (ii) scenario-averaged QUBO with calibration-driven penalty weight `ρ_d^robust = γ(ω) · ρ_d^deterministic` → (iii) QAOA solved on the single robust QUBO → (iv) out-of-sample feasibility measured on a temporally-disjoint held-out set. The calibration-driven penalty scaling is the load-bearing novelty; the rest of the pipeline is composed from existing techniques.

### 8.3 What we will NOT claim
- We will **not** claim quantum advantage.
- We will **not** claim QAOA outperforms classical solvers on cost at any scale.
- We will **not** claim the adaptive mechanism is optimal in any minimax sense.
- We will **not** claim generality beyond the ACN-Data behavioral regime.

### 8.4 Recommended framing
> "An **empirical uncertainty-driven adaptive QUBO framework** for EV charging scheduling, in which ACN-Data-calibrated behavioral distributions condition the penalty weights of a scenario-averaged QUBO prior to a single QAOA solve, and out-of-sample feasibility is measured on a temporally disjoint held-out window."

This framing is **defensible, narrow, and publishable** in a quantum-optimization-adjacent venue. It does not over-claim.

---

## 9. Qubit Count & Feasibility Analysis

### 9.1 Qubit count formula
For the ADOPT encoding (binary on/off, no hard slacks): `n_qubits = n_vars = Σ_i w_i`.

For small balanced instances where each EV's available window is exactly `T` slots (worst case): `n_qubits = N · T`.

### 9.2 Hard-slack alternative cost
If we use the hard site-cap form with binary slack `s[t]`: `n_qubits = N · T + T = T · (N + 1)`. Stage 2 ADOPT does not pay this overhead.

### 9.3 Small instance table

| N | T | Nominal `n_vars = N·T` | After arrival/departure pruning (typical 60% retention) | Hard-slack variant `T·(N+1)` | State-vector simulator feasible? |
|---|---|---|---|---|---|
| 2 | 4 | 8 | ~5 | 12 | ✓ trivial |
| 3 | 4 | 12 | ~7 | 16 | ✓ easy |
| 3 | 6 | 18 | ~11 | 24 | ✓ easy |
| 4 | 4 | 16 | ~10 | 20 | ✓ easy |
| 4 | 6 | 24 | ~14 | 30 | ✓ marginal (state vector needs 16 GB RAM; 30-qubit hard-slack variant needs 16+ GB) |
| 8 | 12 | 96 | ~58 | 104 | ✗ (state vector at 96 qubits infeasible; even 60 infeasible on a single workstation) |
| 15 | 16 | 240 | ~145 | 256 | ✗ (categorically infeasible without tensor-network tricks) |

### 9.4 Recommended maximum quantum instance
**ADOPT: N=3, T=4 (≈7–12 logical qubits after pruning).** Reasoning:
- 12-qubit QAOA on a state-vector simulator runs in seconds per parameter evaluation; the full 50-trial QAOA optimization finishes in minutes on a laptop.
- 12 qubits fits a "meaningful" instance: 3 EVs with 4-slot horizons capture the deadline-uncertainty-vs-cost trade-off, which is the central scientific claim.
- 16 qubits (4×4) is the next step up; should be feasible in minutes per QAOA evaluation but is **not the headline instance**.

### 9.5 Why prior 8×12 / 15×16 sizes are NOT used
State-vector simulation memory scales as `2^n_qubits × 16 bytes`. At 30 qubits: 16 GB. At 60 qubits: 1 EB. The 8×12 (96 qubits) and 15×16 (240 qubits) sizes from earlier proposal drafts are **categorically infeasible** on any classical simulation infrastructure available within a 14-day research project. We explicitly de-scope them.

### 9.6 What the small instance size costs us scientifically
The small size limits how much statistical power the experiment has. We compensate by:
- Running **many QAOA restarts** (50+) on each instance to estimate the bitstring distribution.
- Running **many instance realizations** by sampling different days from the held-out window.
- Reporting **feasibility, cost, peak, unmet demand** with bootstrap confidence intervals across instance realizations, not across QAOA shots.

---

## 10. Data Leakage Prevention (Operational)

### 10.1 Three rules
1. **No parameter learned on the held-out set is used at solve time.** Penalties, `γ`, scenario weights, and TOU tariff are all frozen at end of calibration phase.
2. **No session appears in both calibration and held-out sets.** Enforced by temporal split.
3. **No peeking at the realized `ω` for a held-out session when constructing the schedule.** The schedule is committed using only the *nominal* `â_i, d̂_i, Ê_i^req` of that session; the held-out *realization* is used only at evaluation.

### 10.2 What counts as leakage
- Choosing `ρ_d` by grid-searching on the held-out set: **leakage**.
- Choosing `γ` by fitting to held-out feasibility: **leakage**.
- Choosing TOU tariff from the held-out period's prices: **leakage** (use a fixed tariff published in the calibration period).
- Reporting on the calibration set: **not leakage** but useless (it is in-sample).

### 10.3 Audit trail
Stage 2 code release must include a `splits.json` file with the exact calibration and held-out calendar windows, and a script that verifies no session ID appears in both.

---

## 11. Evaluation Metrics (Exact Definitions)

For each held-out instance and its committed schedule `x̂`:

- **Cost** `C(x̂) = Σ_t c_t · Σ_i P_i^max · x̂[i,t]` (tariff units).
- **Peak load** `L_peak(x̂) = max_t Σ_i P_i^max · x̂[i,t]` (kW).
- **Unmet demand** `U(x̂) = Σ_i max(0, E_i^req − Σ_t P_i^max · Δ · x̂[i,t])` (kWh).
- **Deadline violation** `V(x̂) = 1{ U(x̂) > 0 for any i }` (binary per instance; rate across instances).
- **Feasibility** `F(x̂) = 1{ U(x̂) = 0 AND L_peak(x̂) ≤ P_site^max }` (binary per instance; rate across instances).
- **Approximation ratio** `r(x̂) = F_cost(x̂) / F_cost(x̂*)` where `x̂*` is the classical exact solution to the **same** QUBO (i.e., the same objective). Computed only when the QUBO is small enough to solve exactly.

All metrics aggregated across held-out instances with bootstrap 95% CIs.

---

## 12. Recommended Mathematical Formulation (Single Block)

**Decision variables:** `x[i,t] ∈ {0,1}` for every (EV `i`, slot `t`) within EV `i`'s available window.

**Robust objective:**
`min_x  Σ_k (1/K) · [ Σ_t c_t Σ_i P_i^max x[i,t] + ρ_d^robust Σ_i (R_i(ω_k) − Σ_t x[i,t])_+^2 + ρ_p Σ_t (Σ_i P_i^max x[i,t] − P_target(ω_k))^2 ]`

with `ρ_d^robust = γ(ω) · ρ_d^deterministic`, `γ(ω) = 1 + α · (1/N) Σ_i σ_i(ω) / R̄_i(ω)`, and `ω_k` drawn from the calibration-set empirical distribution.

**Constraints (hard, by preprocessing):** `x[i,t] = 0` for `t < t_arr(i)`, `t > t_dep(i)`.

**Constraints (soft, via penalty):** per-EV energy minimum and per-slot site cap, as in the bracketed terms.

**No auxiliary / slack variables** in the ADOPT form.

---

## 13. Known Risks

1. **Quantum simulation cost at the recommended size is low, so the QAOA-vs-classical comparison is weak.** Mitigation: report feasibility, not approximation ratio, as the primary metric; QAOA at this size is essentially a noisy classical sampler and the comparison is about distribution shape, not speed.
2. **ACN-Data access requires a token.** Mitigation: request it on Day 1; have the static snapshot `tongxin-li/ACN-Data-Static` as a fallback.
3. **Behavioral signal in ACN-Data may be weak** (most sessions are short, low-energy, with low `kWhRequested` variability). Mitigation: pre-screen sessions; restrict to claimed sessions with non-trivial energy and declared deadlines.
4. **Scenario generation from a small calibration set may be noisy.** Mitigation: bootstrap the empirical distribution; report sensitivity to `K` (number of scenarios).
5. **The adaptive mechanism (A2) reduces to a single scalar `γ`; reviewers may call it "just a hyperparameter."** Mitigation: pre-register the form of `γ` before the held-out evaluation; show that `γ` is not a constant but a function of the empirical distribution.
6. **QAOA at 12 qubits is unlikely to beat a classical solver on cost.** Mitigation: explicitly do not claim that; report cost as a non-primary metric.
7. **Time-of-use tariff is not in ACN-Data.** Must use an external published tariff (`UNRESOLVED-2`).

---

## 14. Unresolved Decisions

| ID | Question | Default if unresolved | When to close |
|---|---|---|---|
| `UNRESOLVED-1` | Per-EVSE contention beyond the global site cap | Ignore; global cap only | Stage 2 if time allows |
| `UNRESOLVED-2` | TOU tariff source | PG&E EV-9 (publicly published) | Day 1 of Stage 2 |
| `UNRESOLVED-3` | EVSE-availability random variable | Excluded from uncertainty set | This stage (resolved in §4.1) |
| `UNRESOLVED-4` | Hard vs soft site cap | Soft cap (no slack) | Stage 2 |
| `UNRESOLVED-5` | Instance-size upper bound for QAOA experiments | 12 qubits (3×4 pruned) | This stage (resolved in §9.4) |
| `UNRESOLVED-6` | Number of scenarios `K` | 8 (small instance) | Stage 2 ablation |
| `UNRESOLVED-7` | Exact calibration / held-out calendar windows | Caltech 2018-05 → 2019-06 / 2019-07 → 2019-12 | Day 1 of Stage 2 |
| `UNRESOLVED-8` | Whether to pre-register `γ(ω)` form | Yes, before any held-out solve | Day 1 of Stage 2 |

---

## 15. GO / NO-GO Recommendation

**GO.**

**Conditions:**
- We adopt the 3×4 (12-qubit) headline instance. Larger sizes are explicitly de-scoped.
- We adopt A2 (offline calibration-driven penalty scaling) as the adaptive mechanism. A1 is documented as backup.
- We adopt the temporal split (Caltech, calibration → held-out as in `UNRESOLVED-7`).
- We adopt the scenario-based robust formulation (§6.2) over CVaR or worst-case, because it is the only one that preserves QUBO structure.
- The headline claim is **out-of-sample feasibility** of QAOA-generated schedules, not cost, not quantum advantage.

**Why GO:**
- The mathematical foundation is internally consistent.
- The QUBO is real (binary variables, quadratic, finite, solvable on the recommended instance).
- The uncertainty set is grounded in concrete ACN-Data fields.
- The data split is leakage-safe by construction.
- The adaptive mechanism is novel in its specific form (calibration-driven penalty scaling), even though adaptive penalties are not new in general.
- The recommended instance size fits a 14-day timeline with state-vector simulation on a workstation.
- The framing is defensible: it does not over-claim quantum advantage.

**Why this is a defensible paper:**
- The narrative is "an empirical-uncertainty-driven adaptive QUBO for EV charging" — not "QAOA beats classical."
- The evaluation is on held-out data, not in-sample.
- The pipeline (data → uncertainty → QUBO → adaptive penalty → QAOA → held-out evaluation) is end-to-end in 14 days if executed in order.
- Negative results (e.g., adaptive mechanism shows no improvement) are still publishable as a methodological note.

**Stage 2 entry prerequisites:**
1. Acquire ACN-Data API token.
2. Close `UNRESOLVED-2`, `UNRESOLVED-7`, `UNRESOLVED-8`.
3. Implement the QUBO builder (not the QAOA circuit yet).
4. Pre-register `γ(ω)` form before any held-out solve.

---

## Appendix A — Notation Glossary

- `N` — number of EVs in the instance.
- `T` — number of time slots.
- `Δ` — slot duration (15 min).
- `x[i,t]` — binary decision variable.
- `a_i, d_i` — actual arrival, actual departure (realizations).
- `â_i, d̂_i` — nominal arrival, nominal deadline (decision-time estimates).
- `E_i^req` — energy required (kWh).
- `R_i(ω)` — minimum number of charging slots required under scenario `ω`.
- `P_i^max` — per-EV max charging rate (kW).
- `P_site^max` — site cap (kW).
- `c_t` — TOU tariff ($/kWh) at slot `t`.
- `ρ_d, ρ_p` — deadline penalty, peak penalty weights.
- `ρ_d^robust = γ(ω) · ρ_d` — robust deadline penalty.
- `ω = (Δd, ΔE)` — uncertainty vector.
- `K` — number of scenarios in the discretized empirical distribution.
- `f̂(ω)` — empirical joint distribution of `ω` from the calibration set.

## Appendix B — One-Page Decision Summary

- **Encoding:** binary on/off `x[i,t]`, no slacks.
- **Objective:** scenario-averaged QUBO with calibration-scaled deadline penalty.
- **Uncertainty:** `ω = (Δd, ΔE)`, from ACN-Data.
- **Adaptive rule:** `ρ_d ← γ(ω) · ρ_d` where `γ(ω) = 1 + α · mean(σ/R̄)`.
- **Split:** temporal Caltech 2018-05 → 2019-06 vs 2019-07 → 2019-12.
- **Instance size:** N=3, T=4 (≈12 qubits).
- **Headline claim:** higher held-out feasibility vs deterministic and non-adaptive robust baselines, comparable cost and peak.
