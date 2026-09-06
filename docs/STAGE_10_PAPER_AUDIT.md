# Stage 10 — Paper Audit

**Purpose.** Cross-check the manuscript (`docs/STAGE_10_PAPER.md`) against the frozen methodology (Stages 1–9) and the supporting artifacts. This audit document is itself an artifact of Stage 10.

**Date.** 2026-08-30

---

## 1. Methodological consistency

Every claim in the manuscript references a frozen parameter. The following checks were performed.

### 1.1 Frozen configuration

| Claim in manuscript | Frozen value | Source artifact | Match |
|---|---|---|:---:|
| K = 8 | 8 | `final_experiment_config.json` (`K: 8`) | ✓ |
| α = 1.0 | 1.0 | `final_experiment_config.json` (`alpha: 1.0`) | ✓ |
| ρ_d = 1.0 | 1.0 | `final_experiment_config.json` (`rho_d: 1.0`) | ✓ |
| ρ_p = 0.1 | 0.1 | `final_experiment_config.json` (`rho_p: 0.1`) | ✓ |
| ρ_cap = 0.5 | 0.5 | `final_experiment_config.json` (`rho_cap: 0.5`) | ✓ |
| M_window = 1e6 | 1.0 × 10⁶ | `final_experiment_config.json` (`M_window: 1000000.0`) | ✓ |
| P_target = 6.6 kW | 6.6 | `final_experiment_config.json` (`P_target_kW: 6.6`) | ✓ |
| P_site_max = 9.9 kW | 9.9 | `final_experiment_config.json` (`P_site_max_kW: 9.9`) | ✓ |
| QAOA p = 1 | 1 | `final_experiment_config.json` (`QAOA_p: 1`) | ✓ |
| QAOA seeds = [0,1,2] | [0,1,2] | `final_experiment_config.json` (`QAOA_seeds: [0, 1, 2]`) | ✓ |
| QAOA shots = 1024 | 1024 | `final_experiment_config.json` (`QAOA_shots: 1024`) | ✓ |
| Cal window = 2018-05-01 .. 2019-07-01 | "2018-05-01T00:00:00+00:00 to 2019-07-01T00:00:00+00:00 (exclusive end)" | `final_experiment_config.json` (`calibration_window_UTC`) | ✓ |
| Ho window = 2019-07-01 .. 2020-01-01 | "2019-07-01T00:00:00+00:00 to 2020-01-01T00:00:00+00:00 (exclusive end)" | `final_experiment_config.json` (`held_out_window_UTC`) | ✓ |

**All 13 frozen parameters match.** No parameter was modified by the manuscript construction.

### 1.2 Sign conventions

| Convention | Manuscript | Artifact | Match |
|---|---|---|:---:|
| `ΔE = E_delivered − E_requested` | yes | `stage6/robust_qaoa.py::DELTA_E_SIGN_DOC` | ✓ |
| `ΔE < 0` = unmet demand | yes (§1.1, §4.3, §13) | `stage6/robust_qaoa.py` docstring | ✓ |
| `ΔE > 0` = over-delivery | yes | same | ✓ |
| `Δ d = d_requested − d_actual` | yes | `stage5/uncertainty.py::UncertaintySample` | ✓ |
| `Δ d > 0` = early | yes | same | ✓ |
| `Δ d < 0` = late | yes | same | ✓ |
| M_window is 1.0 × 10⁶ | yes | `final_experiment_config.json` | ✓ |
| F3 = oracle / analysis only | yes | Stage 6 + Stage 7 + Stage 9 | ✓ |

**All 8 sign / label conventions consistent across the manuscript and the artifacts.**

### 1.3 Algorithm consistency

| Algorithm step | Manuscript | Implementation | Match |
|---|---|---|:---:|
| Stage 3: toy instance generation | §3.1, §4.1 | `stage3/ev_scheduling.py::toy_instance` | ✓ |
| Stage 3: var_index ordering (EV outer, slot inner) | §C.1 | `Instance.var_index()` (same order) | ✓ |
| Stage 3: build_qubo with four terms | §4.2 | `stage3/ev_scheduling.py::build_qubo` | ✓ |
| Stage 5: kmeans_joint with K, seed | §4.4 | `stage5/uncertainty.py::kmeans_joint` (seed=20260829+K) | ✓ |
| Stage 5: scenario weight uniform 1/K | §4.4 | `final_experiment_config.json` (`scenario_weighting: "uniform p_s = 1/K"`) | ✓ |
| Stage 6: corrected scenario transformation | §4.5 | `stage6/robust_qaoa.py::corrected_scenario_aware_instance, scenario_aware_qubo` | ✓ |
| Stage 6: M_window diagonal on out-of-window slots | §4.5 | `stage6/robust_qaoa.py::scenario_aware_qubo` (M_window default = 1e6) | ✓ |
| ADOPT: γ = 1 + α mean(σ_i / R̄_i) | §1.6, §4.6 | `stage5/uncertainty.py::compute_robust_rho_d` | ✓ |
| ADOPT: ρ_d ← γ · ρ_d | §4.6, §4.7 | `stage6/robust_qaoa.py::build_f2_adopt` | ✓ |
| F3 = oracle only, not deployable | §4.7 | `stage6/robust_qaoa.py::build_f3_oracle` (label "ORACLE / ANALYSIS ONLY") | ✓ |
| QAOA: COBYLA, p=1, seeds [0,1,2], shots 1024 | §4.10 | `final_experiment_config.json` + `stage4/qa.py::run_qaoa` | ✓ |

**All 11 algorithm-step consistency checks pass.**

---

## 2. Real-data fabrication check

The manuscript was searched for the following forbidden phrases:

| Phrase | Found? |
|---|:---:|
| "ACN-Data confirms" | no |
| "ADOPT improves reliability" (without "if" qualifier) | no |
| "F2 outperforms F0" (without "if" qualifier) | no |
| "real F0/F1/F2 results" | no |
| "real empirical result" (without "PENDING") | no |
| "real calibration" (without "PENDING") | no |
| "synthetic" presented as "real" | no |
| "placeholder" presented as "real" | no |

**No fabrication detected.** Every real-data value in the manuscript is explicitly marked PENDING or BLOCKED. The placeholder and synthetic findings are clearly labelled as such in §6.

---

## 3. Quantum-advantage check

| Phrase | Found? |
|---|:---:|
| "quantum advantage" | no (manuscript explicitly disclaims) |
| "outperforms classical" | no |
| "superior" | no |
| "computational advantage" | no |
| "state-of-the-art" | no |
| "first" | no |
| "novel" (as standalone) | no (used only in "novelty positioning" sections, with hedging) |

**No quantum-advantage or overclaim phrases present.**

---

## 4. Section 7 PENDING-marker check

Every paragraph in §7 (Real-Data Experiment) is marked PENDING or BLOCKED:

- §7.1: PENDING.
- §7.2: PENDING.
- §7.3: PENDING.
- §7.4: PENDING.
- §7.5: PENDING.
- §7.6: PENDING.
- §7.7: PENDING.
- §7.8: PENDING.
- §7.9: PENDING.

**No PENDING value has been replaced with a real or synthetic number.**

---

## 5. Cross-document consistency

### 5.1 Stage 1 → Stage 10
- Stage 1 §1.2: 15 min slot. Stage 10 §3.2: Δ = 0.25 h. ✓
- Stage 1 §3.1: pure QUBO. Stage 10 §4.9: pure QUBO. ✓
- Stage 1 §3.2: soft (smooth) site cap. Stage 10 §4.2 / §4.5: smooth two-sided. ✓
- Stage 1 §4.2: ΔE and Δ d definitions. Stage 10 §4.3: same. ✓
- Stage 1 §12: ADOPT. Stage 10 §4.6: same. ✓

### 5.2 Stage 5 → Stage 10
- Stage 5 §4.4: α = 1.0. Stage 10 §1.6 / §4.6: α = 1.0. ✓
- Stage 5 §4.5: pre-registration rule. Stage 10 §4.6: same. ✓
- Stage 5 §6 (placeholder γ = 1.6414): NOT used in Stage 10 as a real value. Stage 10 §6.5: explicitly labeled as placeholder. ✓

### 5.3 Stage 6 → Stage 10
- Stage 6 Part A: ΔE sign correction. Stage 10 §4.3 / §13: corrected sign. ✓
- Stage 6 Part B-D: corrected scenario transformation. Stage 10 §4.5: same. ✓
- Stage 6 Part K: capacity form comparison. Stage 10 §4.5: same, with trade-off disclosed. ✓

### 5.4 Stage 7 → Stage 10
- Stage 7 §3: F1/F2 placeholder collapse. Stage 10 §6.6: same, labeled as placeholder. ✓
- Stage 7 §8: ADOPT sensitivity. Stage 10 §6.5: same. ✓
- Stage 7 §5: synthetic recovery. Stage 10 §6.2: same. ✓

### 5.5 Stage 8 → Stage 10
- Stage 8 Part U/V/W: leakage audits. Stage 10 §5.4: same. ✓
- Stage 8 Part D: reproducibility. Stage 10 §6.8: same. ✓
- Stage 8 Part J: configuration hash. Stage 10 Appendix C: same. ✓

### 5.6 Stage 9 → Stage 10
- Stage 9 §10: real experiment blocked. Stage 10 §7 / Conclusion: PENDING ACN-DATA. ✓
- Stage 9 §3: planned procedure. Stage 10 Appendix E: same. ✓

**All cross-document consistency checks pass.** No conflicting equations, parameter values, dates, definitions, or claims.

---

## 6. Hard-gate status (Stage 10 Part 62)

| Gate | Status | Evidence |
|---|:---:|---|
| 1 — Methodology accurately represented | ✓ | §1-5 match Stages 1-9 |
| 2 — No real-data result fabricated | ✓ | §7 PENDING; Section 2 audit |
| 3 — Synthetic/placeholder results explicitly labeled | ✓ | §6 label |
| 4 — Equations match implementation | ✓ | §1.3 algorithm-step audit |
| 5 — ΔE sign correct everywhere | ✓ | §1.2 sign audit |
| 6 — Δ d sign correct everywhere | ✓ | §1.2 sign audit |
| 7 — F0/F1/F2/F3 definitions consistent | ✓ | §1.3, §4.7 |
| 8 — K=8 remains frozen | ✓ | §1.3 parameter audit |
| 9 — α=1.0 remains frozen | ✓ | §1.3 parameter audit |
| 10 — Penalty values remain frozen | ✓ | §1.3 parameter audit |
| 11 — QAOA configuration remains frozen | ✓ | §1.3 parameter audit |
| 12 — Temporal split remains frozen | ✓ | §1.3 parameter audit |
| 13 — Leakage methodology accurately described | ✓ | §5.4 |
| 14 — No quantum-advantage claim | ✓ | §3 quantum-advantage check |
| 15 — Novelty claims conservative | ✓ | §1.6, §2.7 |
| 16 — Every numerical claim has an evidence source | ✓ | §1.1, §1.3, §5.1 |
| 17 — Every unsupported real-data value is marked PENDING | ✓ | §4, §7 |
| 18 — Conclusion does not assume outcome | ✓ | §10 |
| 19 — Token-arrival procedure complete | ✓ | Appendix E |
| 20 — Another researcher could understand remaining work | ✓ | §7, Appendix E |

**All 20 Stage 10 hard gates pass.**

---

## 7. Cross-document conflicts found and resolved

**None.** No conflicting equations, parameter values, dates, definitions, or claims were found between the manuscript and Stages 1-9.

---

## 8. Final audit verdict

**The manuscript `docs/STAGE_10_PAPER.md` is consistent with the frozen methodology of Stages 1-9.** No real-data result is fabricated. Every PENDING value is clearly marked. The placeholder and synthetic results are correctly labeled. The quantum-advantage disclaimer is present. The leakage controls are accurately described. The frozen configuration is verified unchanged. The token-arrival procedure is complete.

The manuscript is ready to receive the real-data result when the `ACN_API_TOKEN` becomes available. Until then, the manuscript reports the methodology as **validated and ready for real-data evaluation**; the final empirical claim remains **PENDING**.
