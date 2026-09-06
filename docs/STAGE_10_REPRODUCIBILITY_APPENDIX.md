# Stage 10 — Appendix C: Reproducibility

**Scope.** This appendix describes the exact environment, configuration, data flow, and commands needed to reproduce every result in the manuscript. The manuscript contains only frozen methodology plus synthetic/placeholder validation; the real-data experiment is blocked on `ACN_API_TOKEN` and is not yet executed.

**Stage 7/8 audit evidence.** The Stage 8 reproducibility test (artifacts/reproducibility_runs.json) shows that three independent fresh-process executions of the entire pipeline produce **bit-identical** QUBO coefficients, scenario centroids, and γ. The Stage 8 Part E revalidation (artifacts/robust_qubo_revalidation.json) confirms algebraic identity at K=4, K=8, K=16. The Stage 8 Part F k-means reproducibility (artifacts/scenario_reproducibility.json) confirms label-deterministic clustering.

---

## C.1 Repository layout

The project root contains:

```
docs/                         # authoritative documents
  STAGE_1_SPEC.md
  STAGE_2_DATA_AUDIT.md
  STAGE_3_DETERMINISTIC.md
  STAGE_4_QAOA.md
  STAGE_5_UNCERTAINTY.md
  STAGE_6_ROBUST_QAOA.md
  STAGE_7_STRESS_TEST.md
  STAGE_8_REPRODUCIBILITY.md
  STAGE_9_REAL_EXPERIMENT.md
  STAGE_10_PAPER.md
  STAGE_10_PAPER_AUDIT.md
  STAGE_10_REPRODUCIBILITY_APPENDIX.md
  STAGE_10_REAL_DATA_PROTOCOL.md
  cleaning_spec.md
  tou_tariff_decision.md
stage3/  ev_scheduling.py
stage4/  qaoa.py
stage5/  uncertainty.py
stage6/  robust_qaoa.py
stage7/  stress_test.py
stage8/  audit.py
stage9/  (empty: blocked)
stage10/ (this stage's docs)
artifacts/                     # all machine-readable artifacts
splits.json                    # temporal split
```

`artifacts/` contains 80+ JSON files, all machine-generated. Each major artifact is referenced by the manuscript's claim-tracking and audit tables.

## C.2 Software environment

- Python 3.13.14
- NumPy 2.5.2
- SciPy 1.17.1
- Qiskit 2.5.1
- qiskit-aer (bundled with Qiskit 2.5)
- PuLP 3.3.2 (CBC + HiGHS solvers)
- psutil 7.0+

Full manifest: `artifacts/environment_manifest.json`.

Hardware used during development: Windows 11 workstation, no GPU required. Statevector simulation scales as 2^n × 16 bytes; the headline 11-qubit instance uses ~32 KB. The 8 EV × 12 slot instance would require ~16 PB and is explicitly out of scope (Stage 1 §9.5).

## C.3 Frozen experimental configuration

Source of truth: `artifacts/final_experiment_config.json` (version `stage7.v1`). Immutability rule recorded in the same file. The Stage 8 SHA-256 fingerprint is in `artifacts/final_config_hash.json`.

| Parameter | Frozen value | Source |
|---|---:|---|
| K | 8 | Stage 1 default; Stage 2 sensitivity |
| α | 1.0 | Stage 5 pre-registration |
| γ | (re-computed on real calibration; frozen before held-out) | Stage 1 §12 |
| ρ_d | 1.0 | Stage 3 lock-in |
| ρ_p | 0.1 | Stage 3 |
| ρ_cap | 0.5 | Stage 3 |
| M_window | 1.0 × 10⁶ | Stage 6 Part D |
| P_target | 6.6 kW | Stage 3 toy instance |
| P_site_max | 9.9 kW | Stage 3 toy instance |
| Δ | 15 min | Stage 1 §1.2 |
| QAOA p | 1 (default), 2 (sensitivity) | Stage 4 |
| QAOA optimizer | COBYLA via scipy.optimize.minimize | Stage 4 |
| QAOA seeds | [0, 1, 2] | Stage 4 / Stage 7 |
| QAOA shots | 1024 | Stage 4 / Stage 7 |
| Cal window UTC | 2018-05-01 .. 2019-07-01 | Stage 1 / Stage 2 |
| Ho window UTC | 2019-07-01 .. 2020-01-01 | Stage 1 / Stage 2 |
| ΔE sign | E_delivered − E_requested (≥ 0 = over; < 0 = unmet) | Stage 1 §4.2 + Stage 6 Part A |
| Δ d sign | d_requested − d_actual (≥ 0 = early) | Stage 1 §4.2 |

## C.4 Random-seed audit

Every stochastic operation is parameterized with an explicit seed:

| Component | Seed source |
|---|---|
| `stage5.uncertainty.placeholder_uncertainty` | `np.random.default_rng(seed=20260829)` |
| `stage5.uncertainty.kmeans_joint` | `np.random.default_rng(seed=20260829+K)` (K=4,8,16) |
| `stage4.qa.run_qaoa` | `qiskit_algorithms.utils.algorithm_globals.random_seed = config.seed` and `AerSampler(seed=config.seed)` |

`Stage 8 Part E` audit (artifacts/seed_audit.json) confirms: no module-level `np.random.seed(...)` or `random.seed(...)` calls exist in any project module.

## C.5 Execution sequence (synthetic / placeholder mode)

The pipeline runs end-to-end with no API token. The sequence is:

1. `python -m stage3.ev_scheduling --help` (smoke)
2. Stage 3 validation:
   - 4 toy instances (toy_A_2x4, toy_B_3x4, toy_C_3x6, toy_D_4x4)
   - QUBO = original objective + C (machine precision)
3. Stage 4 validation:
   - 11-qubit QUBO → Ising conversion (machine precision)
   - 10-seed QAOA study on F0 toy_B_3x4 (AR=1.0)
4. Stage 5 synthetic uncertainty:
   - placeholder_uncertainty() produces 5000 labeled samples
   - kmeans_joint (K=8) on calibration half
5. Stage 6 robust QUBO construction with the corrected Stage 6 scenario transformation.
6. Stage 6 robust QUBO exhaustive algebraic validation on K=4, K=8, K=16 (all 2^11 = 2048 bitstrings for the headline 11-qubit instance).
7. Stage 6 Part C test: Model A (direct window) ≡ Model B (corrected) optimum; Model C (Stage 5 indirect) is wrong.
8. Stage 7 synthetic stress tests (S1 no uncertainty, S2 mild, S3 severe; directionality; distribution shift; ADOPT sensitivity).
9. Stage 8 reproducibility audit (3 fresh-process runs, bit-identical QUBOs).

## C.6 Execution sequence (real-data mode — BLOCKED)

When the token arrives:

1. Set `ACN_API_TOKEN` in the environment.
2. `python -m stage5.uncertainty` with the live loader populated — produces `artifacts/stage5_run.json` from real ACN-Data.
3. `python -m stage6.robust_qaoa` — produces real-data `stage6_run.json`.
4. `python -m stage7.stress_test` — re-runs the synthetic stress tests for the methodology, separately from the real-data run.
5. `python -m stage9.real_experiment` (when implemented) — produces the real-data F0/F1/F2/F3, held-out, statistics.

No methodology decision is made at any of these steps. The frozen configuration is loaded from `artifacts/final_experiment_config.json` and is not modified by the runs.

## C.7 Configuration hash

- `artifacts/final_config_hash.json` contains the Stage 8 SHA-256 of the methodology fingerprint.
- `artifacts/stage9_experiment_start.json` records the raw-file SHA-256 of `artifacts/final_experiment_config.json` at the start of Stage 9.
- The methodology hash must remain unchanged between Stage 8 and any real-data execution. If it changes, the change must be documented as a new versioned configuration (e.g., `stage7.v2`).

## C.8 What is NOT in this reproducibility appendix

- A claimed real-data result: there is none yet. The real-data experiment is blocked on `ACN_API_TOKEN`. Adding fabricated reproducibility for a real-data result would be scientific fraud and is explicitly forbidden.
- A claim of quantum advantage: the project does not claim this. The 11-qubit QAOA result is `AR = 1.0` against the exact optimum, which is a methodology-validation result, not an advantage claim.
- A claim of robust-method superiority on real data: the placeholder F0 dominates F1/F2 on the placeholder's K=8 cluster distribution; this is **placeholder-specific** and is not extrapolated to real data.

## C.9 Repro Run Sequence (synthetic)

```bash
# Stage 3: deterministic QUBO validation
python -c "from stage3.ev_scheduling import toy_instance, build_qubo, validate_qubo_vs_original, enumerate_original_objective; \
inst = toy_instance('toy_B_3x4', 3, 4); \
q = build_qubo(inst, 1.0, 0.1, 0.5); \
print(validate_qubo_vs_original(q, enumerate_original_objective(inst, 1.0, 0.1, 0.5)))"

# Stage 4: QUBO -> Ising + QAOA
python -c "from stage4.qa import qubo_to_ising, run_qaoa, QAOAConfig; \
from stage3.ev_scheduling import toy_instance, build_qubo, _QUBOAdapter_compat; \
inst = toy_instance('toy_B_3x4', 3, 4); \
q = build_qubo(inst, 1.0, 0.1, 0.5); \
isg = qubo_to_ising(q.Q, q.c, inst.var_index()); \
print(isg.n(), 'qubits')"

# Stage 5: synthetic uncertainty
python -c "from stage5.uncertainty import placeholder_uncertainty; \
s, status = placeholder_uncertainty(); \
print(status['source'], 'n=', len(s))"

# Stage 6: corrected robust QUBO
python -c "from stage6.robust_qaoa import build_f0_deterministic, build_f1_robust, build_f2_adopt; \
from stage3.ev_scheduling import toy_instance; \
from stage5.uncertainty import placeholder_uncertainty, kmeans_joint, compute_robust_rho_d; \
import numpy as np; \
inst = toy_instance('toy_B_3x4', 3, 4); \
s, _ = placeholder_uncertainty(); \
cal = [x for x in s if x.calibration and x.delta_d_minutes is not None]; \
dd = np.array([x.delta_d_minutes for x in cal]); \
de = np.array([x.delta_e_kwh for x in cal]); \
scen = kmeans_joint(dd, de, K=8, seed=20260829+8)['clusters']; \
gamma = compute_robust_rho_d(1.0, inst, cal, 1.0)[1]['gamma']; \
print('gamma=', gamma, 'f0=', build_f0_deterministic(inst, 1.0, 0.1, 0.5).classical_optimum)"

# Stage 7: stress tests (already validated end-to-end)
python -c "from stage7.stress_test import run_stage7; print(run_stage7('toy_B_3x4', 8, 1.6414).keys())"
```

## C.10 Single-Command Run

For convenience, the synthetic mode can be re-run end-to-end with:

```bash
python -m stage7.stress_test --out artifacts/stage7_run.json
```

(For real-data, see docs/STAGE_10_REAL_DATA_PROTOCOL.md.)
