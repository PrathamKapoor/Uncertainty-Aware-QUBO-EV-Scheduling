# Statistical Denominator Audit: 4,857 vs 4,076

**Audit date:** 2026-09-05
**Audit type:** READ-ONLY forensic analysis of existing Stage 9 artifacts and source code
**No Stage 9 re-run was performed**

---

## 1. Problem statement

The Stage 9 held-out evaluation reports a `P_feasible` metric with denominator 4,076 (the number of held-out sessions with both ΔE and Δd non-null, i.e., valid joint behavioral observations). However, the paired bootstrap artifact (`real_paired_statistics.json`) reports `n = 4,857`, which is the total number of held-out records (including the 781 null-userInputs records that are otherwise excluded from the headline metric). This discrepancy requires classification.

## 2. Evidence collected

### 2.1 Artifacts inspected

| Artifact | Path |
|---|---|
| Held-out results (headline metrics) | `artifacts/real_heldout_results.json` |
| Paired bootstrap statistics | `artifacts/real_paired_statistics.json` |
| Run manifest | `artifacts/stage9_run.json` |
| Uncertainty statistics | `artifacts/real_uncertainty_statistics.json` |
| Cleaning results | `artifacts/real_cleaning_results.json` |
| Stage 9 driver source | `stage9/real_experiment.py` |

### 2.2 Source code locations inspected

| File:line | Code |
|---|---|
| `stage9/real_experiment.py:288` | `per_session_feasible = np.zeros(len(ho_samples), dtype=int)` |
| `stage9/real_experiment.py:295-297` | `for j, s in enumerate(ho_samples):` <br> `    if s.delta_d_minutes is None or s.delta_e_kwh is None:` <br> `        continue` |
| `stage9/real_experiment.py:303` | `per_session_feasible[j] = int(bool(f["feasible"]))` |
| `stage9/real_experiment.py:314` | `"n_held_out_total": int(n_total),` (where n_total is incremented only for valid-joint records) |
| `stage9/real_experiment.py:316` | `"P_feasible": float(n_feasible / max(1, n_total)),` (denominator = n_total, the valid-joint count = 4,076) |
| `stage9/real_experiment.py:332` | `"_per_session_feasible": per_session_feasible,` (the 4,857-length vector passed to bootstrap) |
| `stage9/real_experiment.py:667-674` | `a = held_out_eval["F2"]["_per_session_feasible"]` (bootstrap receives the 4,857-length vector) |
| `stage9/real_experiment.py:419` | `ho = [s for s in samples if not s.calibration]` (ho list has 4,857 records) |

## 3. Forensic findings

### 3.1 Vector definition

The per-session feasibility vector `_per_session_feasible` is constructed in `evaluate_schedule_on_held_out`:

```python
per_session_feasible = np.zeros(len(ho_samples), dtype=int)  # length 4,857
for j, s in enumerate(ho_samples):
    if s.delta_d_minutes is None or s.delta_e_kwh is None:
        continue  # position remains at default 0
    omega = (s.delta_d_minutes, s.delta_e_kwh)
    scen_inst = corrected_scenario_aware_instance(base_inst, omega)
    f = decode_feasibility(scen_inst, sched)
    per_session_feasible[j] = int(bool(f["feasible"]))
```

The vector has **length 4,857** (the full `ho` list). For null-userInputs records (781 positions), the value remains at the default `np.zeros` initialization = **0**. For valid-joint records (4,076 positions), the value is **0** (infeasible) or **1** (feasible).

### 3.2 Encoding of null-userInputs records

- **Encoding: 0** (default `np.zeros` initialization, never explicitly set to any other value)
- **Ambiguity: yes** — a 0 in the vector could mean either "null-userInputs record" or "valid-joint infeasible session"
- The bootstrap is **not** informed of which 0s are which

### 3.3 Same treatment across F0, F1, F2

The same `ho` list is used for all three formulations (line 631: `held_out_eval[fname] = evaluate_schedule_on_held_out(base_inst, sched, ho)`). The `evaluate_schedule_on_held_out` function is deterministic in its handling of null-userInputs records. Therefore the placeholder treatment is **identical** across F0, F1, F2.

### 3.4 Mathematical consequence: do the paired differences cancel the placeholders?

Let:
- v_F0, v_F1, v_F2 ∈ {0,1}^4857 be the per-session feasibility vectors
- S = set of 781 null-userInputs positions (the same in all three vectors, by §3.3)
- T = set of 4,076 valid-joint positions
- For i ∈ S: v_F0[i] = v_F1[i] = v_F2[i] = 0 (default initialization)
- For i ∈ T: v_F? [i] ∈ {0, 1} (feasibility decision)

For a single resample draw D (a 4,857-element multiset of indices with replacement):

```
mean(v_F2[D]) = (1/4857) * Σ_{i ∈ D} v_F2[i]
              = (1/4857) * [ Σ_{i ∈ S ∩ D} 0 + Σ_{i ∈ T ∩ D} v_F2[i] ]
              = (1/4857) * Σ_{i ∈ T ∩ D} v_F2[i]      (the S positions contribute 0)
```

Similarly:
```
mean(v_F0[D]) = (1/4857) * Σ_{i ∈ T ∩ D} v_F0[i]
```

Therefore the paired difference for draw D is:
```
diff(D) = mean(v_F2[D]) - mean(v_F0[D])
       = (1/4857) * [ Σ_{i ∈ T ∩ D} v_F2[i] - Σ_{i ∈ T ∩ D} v_F0[i] ]
       = (1/4857) * Σ_{i ∈ T ∩ D} (v_F2[i] - v_F0[i])
```

**The S (null-userInputs) positions contribute 0 to the difference and are therefore inert.** They do not affect the mean of the paired difference.

However, the **denominator** matters. The bootstrap's `diff_mean` is:
```
diff_mean = (1/4857) * Σ_{i ∈ T} (v_F2[i] - v_F0[i])
         = (4076/4857) * (1/4076) * Σ_{i ∈ T} (v_F2[i] - v_F0[i])
         = (4076/4857) * (P_feas_F2_headline - P_feas_F0_headline)
```

where `P_feas_F? _headline` is the headline P_feasible metric (denominator 4,076).

So:
- `bootstrap_diff_mean = (4076/4857) * headline_diff`
- `headline_diff = (4857/4076) * bootstrap_diff_mean`

Numerically:
- scale factor (4076/4857) = 0.8391
- reported bootstrap diff_mean (F2 vs F0) = -0.1011
- implied headline diff = -0.1011 × (4857/4076) = **-0.1205**
- actual headline diff = 0.8781 - 0.9985 = **-0.1204** ✓ (matches within rounding)

The bootstrap's diff_mean is therefore a **scaled** version of the headline P_feasible difference. The scaling factor is 4076/4857 = 0.8391, reflecting the fact that 781 of the 4,857 positions in the resample are placeholder zeros.

### 3.5 Is the bootstrap CI numerically equivalent to a valid-joint-only bootstrap?

A valid-joint-only bootstrap would resample 4,076 indices (the T set) and compute:
- diff_D_valid = (1/4076) * Σ_{i ∈ T ∩ D'} (v_F2[i] - v_F0[i])
- diff_mean_valid = (1/4076) * Σ_{i ∈ T} (v_F2[i] - v_F0[i])
- = (4857/4076) × bootstrap_diff_mean
- = 1.192 × (-0.1011)
- = **-0.1205**

CI_valid would be 1.192 × the reported CI:
- CI_lo_valid = 1.192 × (-0.1095) = **-0.1305**
- CI_hi_valid = 1.192 × (-0.0926) = **-0.1104**
- CI_valid = **[-0.1305, -0.1104]**

**Both the 4,857-vector bootstrap and the valid-joint-only bootstrap exclude 0.** The statistical conclusion is the same under both conventions.

The 4,857-vector CI is **narrower** (width 0.0169) than the valid-joint-only CI (width 0.0201) because the variance of the paired difference is reduced when the bootstrap denominator includes constant zeros (the 0s reduce the variance of the mean). However, the relative effect size (diff_mean / width) is essentially identical (5.98 vs 5.99).

## 4. Classification

**Classification: 2 — STATISTICAL REPORTING ISSUE REQUIRING QUALIFICATION**

### 4.1 Justification

**Why not Classification 1 (presentation only)?** The convention is not documented in any artifact. The `mean_a` and `mean_b` in the bootstrap artifact (0.7369, 0.8380) differ from the headline P_feasible (0.8781, 0.9985) by a scaling factor of 0.8391, which a reader could not easily derive without reading the source code. This is more than a presentation issue; it requires explicit documentation.

**Why not Classification 3 (scientific validity)?** The bootstrap is mathematically correct in the 4,857-vector space. The paired difference test statistic is a valid estimator of the difference in mean per-session feasibility, with the convention that null-userInputs records are treated as infeasible. The statistical conclusion (CI excludes 0) is robust to denominator choice. The methodology is reproducible and the math is sound.

### 4.2 What can be verified from existing artifacts

| Question | Answer | Evidence |
|---|---|---|
| What vectors were passed to the bootstrap? | `_per_session_feasible` from each formulation's `held_out_eval` | Source code lines 667-674 |
| What are the vector lengths? | 4,857 (one per record in `ho` list) | Source code line 288 |
| How are null-userInputs records encoded? | 0 (default `np.zeros` initialization, never explicitly set) | Source code lines 288, 295-297 |
| Are F0/F1/F2 treated the same? | Yes (same `ho` list, same function, same encoding) | Source code line 631 |
| Do paired differences cancel placeholders? | Yes (0s contribute 0 to the difference) | Mathematical analysis §3.4 |
| Is the CI numerically equivalent to a valid-joint-only bootstrap? | No (it is scaled by 4076/4857 = 0.8391), but the conclusion (CI excludes 0) is the same | Mathematical analysis §3.5 |

### 4.3 What cannot be verified from existing artifacts

| Question | Status |
|---|---|
| The exact per-resample draws | Not stored; the bootstrap only persists the final `diff_mean`, `ci_lo`, `ci_hi`, `mean_a`, `mean_b` |
| The exact per-session feasibility values | Not stored (the per_session_feasible vector is in-process only); only the aggregate `n_feasible` and `P_feasible` are persisted |

These cannot be recovered without re-running Stage 9, which is explicitly forbidden.

## 5. Recommended action (not implemented; this is a reporting-only stage)

The denominator convention should be explicitly documented in the Stage 9 artifact set or in the Stage 10 paper §7. Specifically:

- `real_paired_statistics.json` should include a `denominator_convention` field explaining that n=4,857 includes 781 null-userInputs placeholder positions.
- `real_heldout_results.json` should already document the denominator (n=4,076); this is correct.
- The `FINAL_SCIENTIFIC_REPORT.md` (this Stage 10 output) explicitly documents the discrepancy and its mathematical consequence.

No change to the bootstrap calculation, no change to the methodology, no re-run of Stage 9.

## 6. Conclusion

The 4,857 vs 4,076 discrepancy is a **statistical reporting issue, not a scientific validity issue**. The bootstrap is mathematically correct in the 4,857-vector space; the paired differences are insensitive to the 781 placeholder zeros; the CI excludes 0 under both the reported convention and the implied valid-joint-only convention. The convention itself is non-standard and warrants explicit documentation in any downstream publication.
