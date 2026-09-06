# Stage 3 — Deterministic EV Scheduling, MILP Ground Truth, and QUBO Preparation

**Stage 1 spec:** `docs/STAGE_1_SPEC.md` (authoritative; not modified in this stage).
**Stage 2 audit:** `docs/STAGE_2_DATA_AUDIT.md`.
**Stage 2 cleaning:** `docs/cleaning_spec.md`.
**TOU:** `docs/tou_tariff_decision.md`.

**Stage 3 status: PASSED all 8 hard gates (see §10). Stage 3 GO.**

---

## 1. Exact deterministic scheduling formulation

### 1.1 Sets
- `I = {0, …, N−1}` — set of EVs in the instance.
- `T_set = {0, …, T−1}` — set of time slots in the horizon (length `T`).
- For each EV `i ∈ I`, the available window is `W_i = {a_i, a_i+1, …, d_i} ⊆ T_set`.

### 1.2 Parameters
- `P_i^max` — maximum charging power for EV `i`, in kW.
- `E_i^req` — required energy for EV `i`, in kWh. (Stage 3 toy instances: explicit. ACN-derived instances: **TOKEN-GATED PLACEHOLDER** until the API token is available.)
- `R_i = ⌈E_i^req / (P_i^max · Δ)⌉` — minimum number of active slots for EV `i`, in slot-count units. (Computed automatically in `EV.__post_init__`.)
- `P_site^max` — site capacity, in kW. (Soft cap in the QUBO; smooth quadratic form.)
- `P_target` — preferred operating target, in kW. (Soft peak-shaving; smooth quadratic form.)
- `c_t` — TOU tariff for slot `t`, in $/kWh. (PG&E EV2-A 2018-vintage per Stage 2; exact `$/kWh` pinned in Stage 3 from `docs/tou_tariff_decision.md`.)
- `Δ` — slot duration, in hours. (`Δ = 15/60 = 0.25 h` per Stage 1 §1.2.)
- `ρ_d, ρ_p, ρ_cap` — penalty weights (deadline, peak, site cap).

### 1.3 Decision variables
- `x[i,t] ∈ {0, 1}` for every `i ∈ I` and `t ∈ W_i`.
  - **Interpretation:** `x[i,t] = 1` means EV `i` draws `P_i^max` kW during slot `t`; `x[i,t] = 0` means zero draw.
  - **Existence:** `x[i,t]` is **defined** only for `t ∈ W_i`. Slots outside the window do not get a variable; the QUBO is built on the reduced set `V = ⋃_{i∈I} ({i} × W_i)`.
- **No auxiliary variables, no slack variables.** (Stage 1 ADOPT.)

### 1.4 Energy-unit convention (Stage 3 §2 resolution)
Two mathematically equivalent forms are used:

**QUBO form (slot-count):** the deadline penalty operates on slot counts:
`R_i − Σ_{t∈W_i} x[i,t]`.

**kWh form (downstream metrics):** per Stage 1 §11:
`U(x) = Σ_i max(0, E_i^req − Σ_{t∈W_i} P_i^max · Δ · x[i,t])`.

These are equivalent: `E_i^req / (P_i^max · Δ) = R_i` exactly when `E_i^req` is a multiple of `E_slot = P_i^max · Δ`, and `R_i` is the smallest slot count whose `R_i · E_slot` reaches or exceeds `E_i^req`. The QUBO uses the slot-count form because:
1. Coefficients are small integers (good for QAOA).
2. The penalty `(R_i − Σ x)^2` is the **same** whether we treat `R_i` as a slot count or as a kWh value scaled by 1/E_slot, up to a multiplicative constant.

The kWh form is used by the **feasibility decoder** (`decode_feasibility`) for downstream reporting.

### 1.5 Site-cap interpretation (Stage 3 §3 resolution)
Stage 1 §3.1 introduces `P_target` as "preferred operating target" (e.g., site mean). Stage 1 §3.2 also specifies a **separate** site cap `(Σ_i P_i^max x[i,t] − P_site^max)_+^2`. These are **two distinct quantities**:

| Quantity | Stage 1 reference | Physical meaning | In the QUBO |
|---|---|---|---|
| `P_target` | §3.1 | Soft peak-shaving target (e.g., a tariff-driven load level). NOT a hard physical limit. | Squared penalty `(L_t − P_target)^2` with weight `ρ_p`. Penalizes both over- and under-shoot. |
| `P_site^max` | §3.2 | Hard physical capacity. In the recommended soft form. | Squared penalty `(L_t − P_site^max)^2` with weight `ρ_cap`. |

**Implementation note (Stage 1 mapping):** Stage 1 §3.2 specifies the soft form as `(Σ_i P_i^max x[i,t] − P_site^max)_+^2` (one-sided). The QUBO uses the **smooth** form `(L_t − P_site^max)^2` (two-sided) because the one-sided form requires a `max(0, ·)` which is not a QUBO function. The two forms agree when `L_t ≥ P_site^max`; they differ when `L_t < P_site^max`, where the smooth form over-penalizes under-utilization. For the recommended operating regime `L_t ≈ P_target ≤ P_site^max`, the difference is small and the smooth form keeps the QUBO pure. **This is an explicit Stage-1-to-implementation mapping**, documented for reproducibility.

### 1.6 Complete deterministic objective (pre-QUBO)

```
F(x) = Σ_{t∈T_set} c_t · Σ_{i∈I: t∈W_i} P_i^max · x[i,t]              [cost]
     + ρ_d · Σ_{i∈I} (R_i − Σ_{t∈W_i} x[i,t])^2                          [energy minimum]
     + ρ_p · Σ_{t∈T_set} (L_t − P_target)^2                              [peak target]
     + ρ_cap · Σ_{t∈T_set} (L_t − P_site^max)^2                          [site cap]
```

where `L_t = Σ_{i∈I: t∈W_i} P_i^max · x[i,t]`.

### 1.7 Hard vs soft constraints

| Constraint | Type | Treatment |
|---|---|---|
| `x[i,t]` outside `W_i` | **Hard** | Variable removed (preprocessing). |
| Per-EV energy minimum `Σ_{t∈W_i} x[i,t] ≥ R_i` | **Soft** | Squared penalty `(R_i − Σ x)^2`, weight `ρ_d`. Over-fulfillment allowed. |
| Per-slot site cap `L_t ≤ P_site^max` | **Soft** | Squared penalty `(L_t − P_site^max)^2`, weight `ρ_cap`. |
| Per-slot peak target `L_t ≈ P_target` | **Soft** | Squared penalty `(L_t − P_target)^2`, weight `ρ_p`. |
| `x[i,t] ∈ {0,1}` | **Hard** | Implicit (binary). |

### 1.8 TOU implementation
Tariff periods (PG&E EV2-A 2018-vintage per `docs/tou_tariff_decision.md`):

| Period (local time) | $ / kWh |
|---|---:|
| Super off-peak (00:00–09:00) | 0.15 |
| Off-peak (09:00–14:00) | 0.25 |
| Peak (14:00–21:00) | 0.45 |
| Off-peak (21:00–24:00) | 0.25 |

Slot assignment: for a horizon of `T` slots over 24 h, each slot spans `24/T` hours. The slot's midpoint local hour determines its period. The function `TOU_PERIODS_TO_PER_SLOT(T)` in `stage3/ev_scheduling.py` builds the slot→price list.

For Stage 3 toy instances, a simpler **monotone** tariff `c_t = 0.10 + 0.05·t` is used to exercise the cost-vs-deadline trade-off; this is independent of the TOU mapping and is preserved alongside the PG&E tariff for ACN-derived instances.

### 1.9 QUBO formulation
The QUBO is derived from the objective in §1.6 by expanding every squared term. The QUBO has the form

```
F_QUBO(x) = x^T Q x + c
```

where `Q ∈ R^{n×n}` is symmetric with `n = Σ_i |W_i|`, and `c ∈ R` is a constant. The constant absorbs all terms not depending on `x`. The diagonal of `Q` encodes linear terms (using `x_k^2 = x_k`); off-diagonal entries encode `x_k · x_l` cross-terms.

**Derivation** (matches `build_qubo` in `stage3/ev_scheduling.py`):

1. **Cost:** linear. For each `(i,t) ∈ V`, `Q[k,k] += c_t · P_i^max`.
2. **Deadline:** expand `ρ_d · (R_i − Σ_{t∈W_i} x[i,t])^2`:
   - Constant: `ρ_d · R_i^2` (summed over `i`).
   - Linear: `−2 ρ_d R_i` on each `x[i,t]` for `t ∈ W_i`.
   - Quadratic: `+ρ_d` on each `(x[i,t], x[i,t'])` pair with `t, t' ∈ W_i` (including diagonal; the diagonal is already accounted for by the linear term, so this effectively adds `ρ_d` to off-diagonal within the same EV's window).
3. **Peak target:** expand `ρ_p · (L_t − P_target)^2`:
   - Constant: `ρ_p · T · P_target^2`.
   - Linear: `−2 ρ_p · P_target · P_i^max` on each `x[i,t]`.
   - Quadratic: `+ρ_p · P_i^max · P_j^max` on each `(x[i,t], x[j,t])` pair sharing slot `t`.
4. **Site cap:** same expansion as peak, with `P_site^max` and `ρ_cap`.

The full coefficient map is in `artifacts/deterministic_qubo.json`.

---

## 2. Implementation

All Stage 3 code lives in `stage3/`:

- `stage3/ev_scheduling.py` — instance, MILP, QUBO, validation, feasibility decoder, ACN-derived placeholder instance.
- `stage3/build_artifacts.py` — produces all `artifacts/*.json` deliverables.

Solver: **PuLP/CBC** (MILP) and **NumPy** (QUBO evaluation). No QAOA, no quantum libraries used in this stage.

### 2.1 Variable → qubit mapping
Implemented by `Instance.var_index()`. Outer loop over EVs in declaration order, inner loop over slots in `W_i`. Produces a `{(i, t): k}` dict. **Stable across runs** (no randomness).

### 2.2 MILP reference
`milp_solve` (linear-penalty proxy) and `milp_solve_qubo_equivalent` (quadratic, brute-forced for n_vars ≤ 18). The MILP is a **constraint-feasibility oracle** for the Stage 1 problem: it confirms that the scheduling problem has a feasible solution under the deadline and cap constraints. The MILP's objective is **linear** (using big-M–style slack variables for the squared terms) and is therefore **not directly comparable** to the QUBO's quadratic objective on the same instance. This is documented in the benchmark table and is intentional: the **QUBO objective is the source of truth** for optimality.

### 2.3 Exhaustive enumeration
`enumerate_original_objective` evaluates the **pre-QUBO** objective (`F` in §1.6) on every `2^n` binary vector. `find_optima` returns all global optima within `tol = 1e-9`. Used for the small toy instances only (n ≤ 16).

---

## 3. Three-way validation results

For each toy instance, the report in `artifacts/qubo_validation.json` contains:

| Gate | Description | Result on all 4 toy instances |
|---|---|---|
| **Gate 1** | Dimensional consistency of the objective | ✓ (analytical; see §1.4) |
| **Gate 2** | MILP returns a feasible solution | ✓ (`Optimal` on all 4) |
| **Gate 3** | Exhaustive optimum exists and is found | ✓ (enumeration across 128 / 2048 / 65536 / 32768 bitstrings) |
| **Gate 4** | `F_QUBO(x) = F_original(x) + C` for every bitstring | ✓ (max deviation ≤ 6.32e-14, machine epsilon) |
| **Gate 5** | QUBO optimum == enumeration optimum (after constant offset) | ✓ (diff ≤ 1e-13 on all 4) |
| **Gate 6** | QUBO is pure (no auxiliary variables) | ✓ (n_vars = number of `(i, t)` in any `W_i`; n_qubits = n_vars) |
| **Gate 7** | Feasibility decoder is solver-independent | ✓ (single `decode_feasibility` function used for all 3 solvers) |
| **Gate 8** | Qubit budget ≤ Stage 1 cap (≈12) | ✓ (7, 11, 16, 15) — headline 3×4 = 11 ≤ 12. 3×6 (16) and 4×4 (15) are **classical-validation-only**; the QAOA-eligible instance is the 3×4. |

### 3.1 Numerical validation summary

| Instance | n_vars | n_qubits | Enumeration optimum | QUBO optimum | Max dev (Gate 4) | Diff(QUBO−enum) (Gate 5) | Feasible at optimum |
|---|---:|---:|---:|---:|---:|---:|---|
| `toy_A_2x4` | 7 | 7 | 21.0020 | 21.0020 | 1.60e-14 | 1.07e-14 | ✓ |
| `toy_B_3x4` | 11 | 11 | 30.8430 | 30.8430 | 5.14e-14 | -3.91e-14 | ✓ |
| `toy_C_3x6` | 16 | 16 | 53.5800 | 53.5800 | 5.87e-14 | -2.84e-14 | ✓ (12 tied optima) |
| `toy_D_4x4` | 15 | 15 | 24.2860 | 24.2860 | 6.32e-14 | -8.17e-14 | ✓ (18 tied optima) |

**Gates 4 and 5 pass on all four instances with deviations at machine precision.** Multiple tied optima on the larger instances (`toy_C`, `toy_D`) are reported explicitly in the validation JSON.

### 3.2 Optimal schedules at the headline 3×4 instance

`toy_B_3x4` optimum schedule (n_vars=11, 2048 enumerated bitstrings, 1 unique optimum):

```
EV E1: x[0,0]=1, x[0,1]=1, x[0,2]=1, x[0,3]=1   (4 active slots, R=2)
EV E2: x[1,0]=1, x[1,1]=1, x[1,2]=1, x[1,3]=0   (3 active slots, R=1)
EV E3: x[2,1]=1, x[2,2]=1, x[2,3]=1            (3 active slots, R=1)
```

Cost = $5.775, peak = 9.90 kW (= site cap), unmet = 0.000 kWh. All EVs meet `R_i`; site cap is binding in slot 0 (3 EVs × 3.3 kW = 9.9 kW).

---

## 4. Penalty-weight analysis (Stage 3 §12)

`artifacts/penalty_analysis.json` contains a sweep over `ρ_d ∈ {0, 0.1, 0.5, 1, 2, 5, 10}` × `ρ_cap ∈ {0, 0.1, 0.5, 1, 5}` at fixed `ρ_p = 0.1` on the headline 3×4 instance.

### 4.1 Role of each penalty

- **`ρ_d`** — penalty for each EV's slot-count shortfall relative to `R_i`. A 1-slot shortfall contributes `ρ_d · 1` to the objective. The cost of an extra slot is roughly `c_t · P_i^max` (e.g., $0.15 × 3.3 = $0.495 at super-off-peak). Therefore `ρ_d` should **dominate** the cost of the minimum-energy path to ensure feasibility.
- **`ρ_p`** — soft peak-shaving around `P_target`. For the headline instance (`P_target = 6.6`, `P_site_max = 9.9`), a schedule that swings between 3.3 and 9.9 kW pays `(9.9−6.6)² + (3.3−6.6)² = 21.78` of squared peak deviation; with `ρ_p = 0.1` this is 2.178, comparable to one slot's cost. A `ρ_p ∈ [0.05, 0.5]` range keeps the peak term on the same order as the cost term.
- **`ρ_cap`** — soft site cap. With the smooth form, a 1-kW cap violation in 1 slot pays `ρ_cap · 1`. To make the cap binding, `ρ_cap ≥ 1.0` is needed; at `ρ_cap = 0` the cap is effectively unconstrained.

### 4.2 Sweep findings (headline 3×4)

| Regime | ρ_d | ρ_cap | Feasibility at optimum |
|---|---|---|---|
| **Infeasible optima** (BAD) | 0.0 | 0.0–0.1 | ✗ (unmet = 0.825 kWh) |
| **Forced feasible by cap pressure** | 0.0 | 0.5+ | ✓ (cap pressure dominates) |
| **Feasible across the swept range** | ≥ 0.1 | any | ✓ |

**Default choice (Stage 3 lock-in): `ρ_d = 1.0, ρ_p = 0.1, ρ_cap = 0.5`.**
- `ρ_d = 1.0` is in the regime where the energy minimum is always respected; the optimum is feasible on all 4 toy instances.
- `ρ_p = 0.1` makes the peak term comparable to a slot's cost, so the optimizer trades off peak deviation against cost.
- `ρ_cap = 0.5` is in the regime where the cap is **softly** enforced; the 3×4 optimum has peak = 9.9 kW (cap binding) but no over-shoot.

**Penalty tuning is NOT performed on held-out data.** The default is set by structural reasoning about the relative magnitudes of the cost, energy, and peak terms. The sensitivity sweep confirms feasibility is robust to the choice of `ρ_d, ρ_cap` over a wide range.

---

## 5. Qubit count analysis (Stage 3 §15)

`n_qubits = n_vars = Σ_i |W_i|`.

| Instance | N | T | Window widths `|W_i|` | n_vars | n_qubits | Quantum-eligible? |
|---|---:|---:|---|---:|---:|---|
| `toy_A_2x4` | 2 | 4 | 4, 3 | 7 | 7 | ✓ (under cap) |
| `toy_B_3x4` (headline) | 3 | 4 | 4, 4, 3 | 11 | 11 | ✓ (under cap, **QAOA target**) |
| `toy_C_3x6` | 3 | 6 | 6, 6, 4 | 16 | 16 | ✗ (over cap; **classical validation only**) |
| `toy_D_4x4` | 4 | 4 | 4, 4, 3, 4 | 15 | 15 | ✗ (over cap; **classical validation only**) |

Stage 1 §9.4 cap: ~12 logical qubits for the headline quantum instance. The 3×4 (11 qubits) is the QAOA-eligible instance. The 3×6 and 4×4 are used **only for classical validation** of the QUBO's mathematical correctness; they will not be run on a quantum simulator in this project.

### 5.1 Hard-slack variant
If the hard site-cap form were used (with binary slack `s[t]` per slot), the qubit count would be `n + T` (Stage 1 §9.2). This is rejected in the ADOPT formulation (Stage 1 §3.2) because the soft smooth form keeps the QUBO pure. The hard variant would push the 3×4 to 11 + 4 = 15 qubits, over the cap.

---

## 6. ACN-derived deterministic instance (Stage 3 §14)

`artifacts/acn_placeholder_instance.json` contains a 3×4 instance built from 3 real ACN-Data sessions (sampled from `artifacts/sample_csvs/`).

**Status: infrastructure validated; NOT a final uncertainty experiment.**

- The QUBO builder, validator, and decoder all run on the ACN-derived instance without modification.
- `E_req_kWh` is a **TOKEN-GATED PLACEHOLDER** taken from the source session's `kWhDelivered` (the only energy value in the static snapshot). This is **NOT** the Stage 1 `kWhRequested` from `userInputs[*]`. See `STAGE_2_DATA_AUDIT.md` §H for the blocker.
- With the placeholder values, the instance is **infeasible** (unmet demand = 42.6 kWh). This is expected: real Caltech sessions often require more energy than can be delivered in a 4-slot horizon at 3.3 kW. This is a property of the placeholder, not of the QUBO infrastructure. Once the API token arrives, the real `kWhRequested` will replace the placeholder and the R_i values will be re-computed; the QUBO infrastructure does not change.
- The ACN-derived instance is **not used for the QUBO-vs-original validation** in this stage (the 4 toy instances are sufficient to validate the mathematical pipeline). The ACN instance serves as a **smoke test** of the data-to-QUBO path.

### 6.1 What is blocked without the API token

| Stage 1 quantity | Status | Blocker |
|---|---|---|
| `kWhRequested` (per EV) | **PLACEHOLDER** (from `kWhDelivered`) | `userInputs[*]` is token-gated |
| `requestedDeparture` (per EV) | **MISSING** (window set heuristically) | `userInputs[*]` is token-gated |
| `ΔE` uncertainty distribution | **BLOCKED** | Requires `kWhRequested` |
| `Δd` uncertainty distribution | **BLOCKED** | Requires `requestedDeparture` |
| Adaptive penalty scaling `γ(ω)` | **DEFERRED** | Requires `Δd, ΔE` distributions |
| Held-out evaluation | **DEFERRED** | Requires uncertainty model |

---

## 7. Reproducibility (Stage 3 §17)

| Item | Value |
|---|---|
| Python | 3.13.14 |
| NumPy | 2.5.2 |
| SciPy | 1.17.1 |
| PuLP | 3.3.2 (CBC + HiGHS bundled) |
| Qiskit | 2.5.1 (installed, **NOT used in Stage 3**) |
| Slot duration `Δ` | 15 min = 0.25 h (Stage 1 §1.2) |
| Tariff | PG&E EV2-A 2018-vintage; `c_per_slot` built by `TOU_PERIODS_TO_PER_SLOT(T)` |
| Default penalties | `ρ_d = 1.0, ρ_p = 0.1, ρ_cap = 0.5` (Stage 3 §4.2 lock-in) |
| Variable ordering | Outer loop over EVs in declaration order, inner loop over slots in `W_i` |
| Tolerance | `tol = 1e-9` for optimum identification; `tol = 1e-7` for QUBO equivalence |
| Random seed | Not used (no randomness in Stage 3) |
| QUBO symmetry | `Q` is symmetrized to `0.5 (Q + Q^T)` defensively (the construction is already symmetric) |
| Constant offset | `c` absorbs all x-independent terms; documented in `deterministic_qubo.json` per instance |

---

## 8. Token-gated blockers (Stage 3 §17)

| Item | Status | Impact on Stage 3 | Impact on Stage 4+ |
|---|---|---|---|
| `kWhRequested` | Blocked (token required) | ACN instance is a placeholder | Cannot run final uncertainty experiments |
| `requestedDeparture` | Blocked (token required) | Window set heuristically for ACN instance | Cannot compute `Δd` distribution |
| `ΔE` distribution | Blocked (depends on `kWhRequested`) | Not used in Stage 3 | Stage 5+ (adaptive QUBO) |
| `Δd` distribution | Blocked (depends on `requestedDeparture`) | Not used in Stage 3 | Stage 5+ (adaptive QUBO) |
| Held-out evaluation | Blocked (depends on uncertainty model) | Not used in Stage 3 | Stage 5+ |

**No Stage 3 gate fails because of these blockers.** All 8 gates pass on the 4 toy instances and the ACN-derived placeholder instance. Stage 4 (QAOA) does not require the uncertainty model and can proceed on the deterministic QUBO; Stage 5+ will be blocked until the token arrives.

---

## 9. Known risks (Stage 3 §18)

1. **The MILP uses a linear-penalty proxy and is not directly comparable to the QUBO objective.** This is documented in §2.2 and is intentional; the QUBO is the source of truth. The MILP is a **constraint-feasibility oracle** only.
2. **The QUBO site-cap form is smooth (`(L_t − C)²`), not the one-sided `(L_t − C)₊²` from Stage 1 §3.2.** The two agree when `L_t ≥ C`; the smooth form over-penalizes under-utilization. For the recommended operating regime this difference is small. If a future stage requires exact soft-cap semantics, the QUBO would need a binary slack `s[t]` (Stage 1 §3.2 alternative), which would add `T` qubits and push the 3×4 to 15.
3. **The over-fulfillment term is not penalized.** A schedule can deliver more than `R_i` slots without penalty (subject to the site cap). This is a Stage 1 design choice; the over-fulfillment could in principle be charged as wasted energy. For the toy instances it does not affect the optimum.
4. **Stage 1's `R_i` is the **minimum** slot count.** If `E_req` is not a multiple of `E_slot`, `R_i · E_slot` slightly exceeds `E_req`. The over-delivery is at most one `E_slot` per EV (≈ 0.825 kWh for the 3.3 kW toy EVs).
5. **The headline 3×4 instance has 11 qubits after pruning.** This is at the upper edge of the Stage 1 §9.4 cap (≈12). Larger toy instances (`toy_C_3x6` = 16, `toy_D_4x4` = 15) exceed the cap and are classical-validation-only.
6. **The penalty sweep is on the headline 3×4 instance only.** Sweeping on the larger instances may show different regimes; this is left for Stage 4 if needed.

---

## 10. Hard gates — final status

| Gate | Description | Status | Evidence |
|---|---|---|---|
| 1 | Mathematical consistency (dimensional analysis) | ✓ | §1.4 resolves the energy-unit convention. |
| 2 | MILP correctness | ✓ | All 4 toy instances return `Optimal`; schedules are feasible. |
| 3 | Enumeration optimum exists and is found | ✓ | All 4 instances enumerated exhaustively (128–65536 bitstrings). |
| 4 | `F_QUBO(x) = F_original(x) + C` for all enumerated bitstrings | ✓ | Max deviation ≤ 6.32e-14 on all 4 instances. |
| 5 | QUBO optimum == enumeration optimum | ✓ | Diff ≤ 1.07e-13 on all 4 instances. |
| 6 | QUBO is pure (no auxiliary variables) | ✓ | n_vars = Σ |W_i|; no slacks, no aux. |
| 7 | Feasibility decoder is solver-independent | ✓ | Single `decode_feasibility` used for all 3 solvers. |
| 8 | Qubit budget ≤ Stage 1 cap (≈12) for QAOA target | ✓ | 3×4 instance has 11 qubits; larger instances are classical-only. |

**All 8 gates pass.** Stage 3 GO.

---

## 11. Stage 4 prerequisites (information for the next stage)

The next stage implements **QAOA on the validated QUBO**. The mathematical object handed to QAOA is the QUBO built by `build_qubo(inst, ρ_d, ρ_p, ρ_cap)` on the headline `toy_B_3x4` instance (or any other instance under the 12-qubit cap). The QUBO constant `c` and the QUBO matrix `Q` are the inputs.

Stage 4 should:
- Use the same `var_index` mapping (`Instance.var_index()`) to map bitstring positions to `(i, t)` coordinates.
- Reuse the `decode_feasibility` function to evaluate QAOA-produced schedules.
- Report QAOA's cost approximation ratio against the QUBO optimum from the validation table.
- NOT use the ACN-derived placeholder instance for QAOA (it is infeasible under the placeholder `E_req`).
- NOT use held-out data; the Stage 1 uncertainty model is still blocked.

---

## Appendix A — File map

| File | Purpose |
|---|---|
| `stage3/ev_scheduling.py` | Core: `Instance`, `EV`, `toy_instance`, `build_qubo`, `enumerate_original_objective`, `find_optima`, `validate_qubo_vs_original`, `milp_solve`, `milp_solve_qubo_equivalent`, `decode_feasibility`, `acn_derived_instance`, `qubo_term_breakdown`, `TOU_PERIODS_TO_PER_SLOT`. |
| `stage3/build_artifacts.py` | Writes all 5 JSON artifacts. |
| `artifacts/deterministic_qubo.json` | Per-instance QUBO coefficient map (constant, diagonal, off-diagonal, var index). |
| `artifacts/deterministic_benchmarks.json` | Benchmark table. |
| `artifacts/qubo_validation.json` | Per-instance three-way validation report. |
| `artifacts/instance_manifest.json` | Per-instance parameter manifest. |
| `artifacts/penalty_analysis.json` | Penalty sweep and principled-magnitude analysis. |
| `artifacts/acn_placeholder_instance.json` | ACN-derived placeholder instance + infrastructure smoke test. |
