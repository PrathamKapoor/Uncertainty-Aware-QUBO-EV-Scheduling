# Uncertainty-Aware QUBO/QAOA Scheduling for EV Charging

A real-data evaluation of an uncertainty-aware quantum-optimization framework for electric-vehicle charging, executed end-to-end on the **Caltech ACN** live dataset.

> **Headline result (honest, unfavorable):** the deterministic baseline (**F0**) achieved **99.85%** held-out feasibility. The proposed uncertainty-aware formulations (**F1**, **F2**) achieved **87.81%**. The 12.19 percentage-point gap is statistically significant (paired bootstrap 95% CI [−0.1095, −0.0926], Bonferroni α = 0.05/3) and favors the deterministic baseline. The proposed methods achieve a Pareto trade-off (lower unmet demand and cost) but **do not dominate** F0 on this instance. This is a documented negative result, not a fabricated success.

| Formulation | Held-out P(feasible) | mean_unmet (kWh) | deadline_viol_rate |
|---|---|---|---|
| **F0 (deterministic baseline)** | **0.9985** | 2.463 | 0.0015 |
| F1 (robust K=8) | 0.8781 | 0.756 | 0.1219 |
| F2 (ADOPT, γ=4.1313) | 0.8781 | 0.756 | 0.1219 |
| F3 (oracle, analysis-only) | 0.9941 | 0.000 | 0.000 |

- **DATA_MODE:** REAL — live API at `https://ev.caltech.edu/api/v1/sessions/caltech` (25,656 records, 1,029 pages)
- **Frozen configuration SHA-256:** `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3` (must remain unchanged)
- **Held-out denominator:** 4,076 valid joint behavioral sessions
- **Status:** COMPLETE — WITH DOCUMENTED LIMITATIONS

---

## Start Here

The canonical entry point is one Jupyter notebook:

**`notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`**

Everything a reviewer needs to verify the published result is in that notebook. Choose the path that matches your goal:

### Option A — I want to inspect / reproduce the published results *(default, no credentials, no network)*

**Time:** ~1 minute. **Credentials needed:** none. **Network:** none. **QAOA rerun:** no.

```bash
# 1. Clone
git clone https://github.com/PrathamKapoor/Uncertainty-Aware-QUBO-EV-Scheduling.git
cd Uncertainty-Aware-QUBO-EV-Scheduling

# 2. (Optional but recommended) create a virtual environment
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Linux / macOS:          source .venv/bin/activate

# 3. Install minimum dependencies
pip install -r requirements.txt

# 4. Launch Jupyter
jupyter notebook
```

Then in the Jupyter browser:

1. Open `notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`
2. **Kernel → Restart & Run All**

What happens during Run All:

- Frozen configuration hash is verified against the expected value. Mismatch → notebook stops with `SystemExit(1)`.
- All 21 authoritative Stage 9 artifacts are validated for presence and internal consistency.
- `stage9_run.json` is checked for `DATA_MODE = REAL` and `source = live_api`.
- Source files are SHA-256-checked against the reproducibility manifest.
- Existing `real_*.json` and `stage9_*.json` artifacts are **loaded**, not regenerated.
- Tables, figures, and statistical summaries are reproduced.
- The final scientific conclusion is rendered inline.
- **Authoritative artifacts are not overwritten.**

> Seeing F0 outperform F1/F2 in the reproduced tables is the **expected** result — it is the published finding, faithfully reproduced. It is not a failure.

### Option B — I want to rerun the full experiment from source *(explicit opt-in)*

**Time:** ~30 minutes. **Credentials needed:** `ACN_API_TOKEN` or `ACNPORTAL_TOKEN` (Caltech ACN API). **Network:** yes. **QAOA rerun:** yes.

In `notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`, cell 9, change:

```python
RUN_FULL_EXPERIMENT = False   # → True
```

Then set the credential in your shell (the token value is never logged, hashed, or written):

```bash
# Linux / macOS
export ACN_API_TOKEN="<your token>"
# Windows (PowerShell)
$env:ACN_API_TOKEN = "<your token>"
```

Re-run all cells. The notebook will:

- Fetch live Caltech ACN session data over HATEOAS-paginated HTTP Basic auth.
- Apply R9–R11 cleaning rules on the live records.
- Compute empirical (Δd, ΔE) distributions on the calibration window (2018-05-01 → 2019-07-01 UTC).
- Run K-means scenario generation (K=8, seed = 20260837).
- Freeze ADOPT γ on calibration only.
- Build F0 / F1 / F2 / F3 QUBOs with the frozen penalties.
- Run QAOA at p=1 (COBYLA, seeds [0,1,2], shots=1024) on the local Aer simulator.
- Evaluate classical optima on the held-out window (2019-07-01 → 2020-01-01 UTC).
- Compute paired bootstrap 95% CIs with Bonferroni correction.
- **Overwrite** `artifacts/real_*.json` and `artifacts/stage9_*.json` with new values.

The frozen methodology file is checked before, during, and after the run; it must remain unchanged.

> Do **not** enable Option B unless you intend to regenerate the experiment outputs. A fresh run produces a new SHA-256 of the in-memory sample list (slightly different from the published values) but the **frozen config hash remains identical**.

---

## What Is Stage 9?

Stage 9 is the real-data experiment that ties every other stage together. Conceptually:

```
Real Caltech ACN sessions (25,656 records, 1,029 paginated HTTP requests)
        |
        v
Behavioral uncertainty extraction
        (Delta_E = E_delivered - E_requested, Delta_d = d_requested - d_actual)
        |
        v
Frozen calendar split (Stage 2)
        calibration: 2018-05-01 -> 2019-07-01 UTC  (20,799 records)
        held-out:    2019-07-01 -> 2020-01-01 UTC  (4,857 records)
        |
        v
Per-uncertainty cleaning (R9, R10, R11)
        -> 7,492 valid joint calibration, 4,076 valid joint held-out
        |
        v
K-means scenario generation on the calibration joint (Delta_d, Delta_E)
        -> K=8 scenarios, weights p_s = 1/K, seed = 20260837
        |
        v
ADOPT gamma inflation on calibration only
        -> gamma = 1 + alpha * mean(sigma_i / R_bar_i) = 4.1313
        -> rho_d_robust = gamma * rho_d = 4.1313
        |
        v
Four QUBO formulations on toy_B_3x4 (3 EVs, 4 slots, 11 qubits)
        F0  deterministic baseline
        F1  scenario-averaged over K=8
        F2  scenario-averaged with rho_d scaled by gamma (ADOPT)
        F3  oracle: built from held-out realized (Delta_d, Delta_E) [analysis-only]
        |
        v
Classical optimum + QAOA p=1 (COBYLA, seeds [0,1,2], shots=1024)
        |
        v
Held-out evaluation
        Apply each classical optimum schedule to each held-out session's
        realized (Delta_d, Delta_E). Decode feasibility (energy + site +
        deadline + qubo). Report P(feasible), unmet energy, deadline-viol.
        |
        v
Paired bootstrap 95% CI on P(feasible) difference (F2-F0 primary;
        F1-F0, F2-F1 secondary; Bonferroni alpha = 0.05/3)
```

### The four formulations, briefly

- **F0 — deterministic baseline.** Standard QUBO with no uncertainty. Penalty weights (ρ_d, ρ_p, ρ_cap) = (1.0, 0.1, 0.5). This is the well-tuned baseline.
- **F1 — robust, K=8 scenarios.** Same penalty weights as F0, but QUBO coefficients are scenario-averaged over K=8 empirical scenarios drawn from calibration.
- **F2 — ADOPT, γ=4.1313.** Same as F1, but with ρ_d multiplied by γ to compensate for the σ_i / R̄_i noise-to-signal ratio observed in calibration.
- **F3 — oracle, analysis-only.** Uses the held-out *realized* (Δd, ΔE) to build the QUBO. **Not deployable** — leaks held-out information. Included as an upper-bound reference. Produces the lowest unmet energy (0.000 kWh) and zero deadline violations.

On the evaluated 11-qubit `toy_B_3x4` instance, F1 and F2 produce **identical schedules** because the γ-inflation on ρ_d does not change the discrete classical optimum at this scale. The ADOPT framework's distinct contribution cannot be evaluated at this instance size.

---

## Expected Output

A successful default (Option A) Run All of the canonical notebook produces, in order:

1. **Environment verification.** Python version, dependency import check, expected-path existence check.
2. **Frozen configuration verification.** SHA-256 of `artifacts/final_experiment_config.json` is recomputed and asserted to equal `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`.
3. **Source-file integrity check.** Each implementation module is SHA-256-checked against `artifacts/stage10/REPRODUCIBILITY_MANIFEST.json`.
4. **Stage 9 artifact validation.** All 21 `real_*.json` / `stage9_*.json` files are confirmed present; `stage9_run.json` is checked for `DATA_MODE = REAL` and `source = live_api`.
5. **Scenario diagnostics.** K=8 cluster centroids (Δd in minutes, ΔE in kWh) and weights are printed.
6. **ADOPT calibration parameters.** γ = 4.1313, ρ_d_robust = 4.1313, α = 1.0, M_window = 1e6.
7. **QUBO formulations.** F0/F1/F2/F3 classical optima, variable counts (n_vars = 11), Q matrix structure, algebraic 2^11-bitstring validation.
8. **QAOA results.** Per-seed AR and P(feasible) for F0/F1/F2 (p=1, shots=1024).
9. **Held-out results table.**

   ```
   Method                        P_feasible   n_feasible   mean_unmet   deadline_viol   site_viol
   ----------------------------------------------------------------------------------------------
   F0 (deterministic)               0.9985       4069       2.4631       0.0015          0.0000
   F1 (robust K=8)                  0.8781       3579       0.7556       0.1219          0.0000
   F2 (ADOPT)                       0.8781       3579       0.7556       0.1219          0.0000
   F3 (oracle, analysis-only)       0.9941       4052       0.0000       0.0000          0.0000
   ```

10. **Paired bootstrap 95% CIs.** Primary endpoint F2 vs F0: diff_mean = −0.1011, CI = [−0.1095, −0.0926], n_bootstrap = 10,000, Bonferroni α = 0.01667. CI excludes 0 → statistically significant in the direction favoring F0.
11. **Five figures** (displayed inline): held-out performance, Pareto trade-off, K=8 scenario centroids, distribution shift, primary CI.
12. **Final scientific interpretation.** Honest framing: this is a Pareto trade-off, not a dominance claim.

If the reproduced numbers match the table above, the run is successful. If F0 does **not** outperform F1/F2 in the reproduced table, that is the signal that something is wrong (e.g., a corrupt artifact, a corrupted frozen-config file, or a wrong working directory).

---

## Scientific Integrity

- **Frozen configuration:** `artifacts/final_experiment_config.json` (version `stage7.v1`), SHA-256 verified before, during, and after every scientific run.
- **Real data:** `DATA_MODE = REAL`, source `live_api` from `https://ev.caltech.edu/api/v1/sessions/caltech`. 25,656 records retrieved, 1,029 HTTP 200 responses.
- **No post-hoc tuning.** K=8, α=1.0, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5, M_window=1e6, P_target=6.6 kW, P_site_max=9.9 kW, QAOA p=1, COBYLA optimizer, seeds [0,1,2], shots=1024 — all frozen before held-out evaluation.
- **Unfavorable result retained.** F1 and F2 do not outperform F0. The result is reported as-is. No parameters were tuned, no sessions were dropped, no seeds were changed to improve the outcome.
- **Calibration / held-out isolation.** Calibration window (2018-05-01 → 2019-07-01) and held-out window (2019-07-01 → 2020-01-01) are disjoint by construction; the driver raises an error if any session_id appears in both.

---

## Repository Map

```
.
├── README.md                                <- this file
├── PROJECT_SUMMARY.md                       <- one-page project summary
├── RELEASE_CHECKLIST.md                     <- final release-readiness checklist
├── requirements.txt                         <- minimum-version Python dependencies
├── .gitignore                               <- Python caches, env files, credentials
│
├── notebooks/
│   └── FINAL_REPRODUCIBLE_EXPERIMENT.ipynb  <- CANONICAL entry point
│   ├── 00_overview.ipynb                    <- research question and reading guide
│   ├── 01_data_audit_and_cleaning.ipynb
│   ├── 02_temporal_split.ipynb
│   ├── 03_uncertainty_characterization.ipynb
│   ├── 04_deterministic_qubo_and_validation.ipynb
│   ├── 05_qaoa_implementation_and_metrics.ipynb
│   ├── 06_scenario_generation_and_adopt.ipynb
│   ├── 07_robust_qubo_construction.ipynb
│   ├── 08_synthetic_recovery_stress_tests.ipynb
│   ├── 09_exact_vs_qaoa_comparison.ipynb
│   ├── 10_real_acn_data_experiment.ipynb
│   ├── 11_heldout_evaluation_and_statistics.ipynb
│   └── 12_results_and_paper_integration.ipynb
│
├── stage3/                                  <- EV instance, QUBO construction,
│   └── ev_scheduling.py                        MILP/QUBO equivalence, feasibility decoder
├── stage4/                                  <- QUBO → Ising mapping, QAOA ansatz,
│   └── qaoa.py                                 COBYLA optimization, multi-seed driver
├── stage5/                                  <- Live ACN API fetcher,
│   └── uncertainty.py                          K-means scenarios, ADOPT γ computation
├── stage6/                                  <- F0/F1/F2/F3 QUBO builders,
│   └── robust_qaoa.py                          scenario-averaged robust QUBO
├── stage7/                                  <- synthetic stress tests
├── stage8/                                  <- reproducibility audit + readiness checks
├── stage9/                                  <- E.2–E.15 protocol driver
│   └── real_experiment.py                      (full real-data experiment entry point)
│
├── artifacts/
│   ├── final_experiment_config.json         <- FROZEN methodology (SHA-256 above)
│   ├── real_*.json                          <- 21 authoritative Stage 9 results
│   ├── stage9_run.json, stage9_audit.json   <- Stage 9 run manifest + audit
│   ├── stage10/
│   │   ├── FINAL_SCIENTIFIC_REPORT.md       <- 20-section publication report
│   │   ├── FINAL_RESULTS_TABLE.md
│   │   ├── STATISTICAL_DENOMINATOR_AUDIT.md <- forensic audit of bootstrap denominator
│   │   ├── REPRODUCIBILITY_MANIFEST.json
│   │   └── figures/                         <- 5 publication PNGs
│   └── sample_csvs/                         <- 200 publicly downloadable ACN sample CSVs
│
└── docs/                                    <- stage specifications, paper drafts,
                                                token-incident handoff
```

`stage3/`–`stage9/` are importable Python modules. Stages 1–2 and 7–8 have supporting notebooks but their primary artifacts are committed under `artifacts/`. Build helpers under `notebooks/_*.py` are internal tooling used during the research phase; the canonical notebook does not depend on them.

---

## Limitations

- **Single-site dataset.** Results are specific to the Caltech ACN deployment. Other sites, populations, and time periods may exhibit different behavioral distributions.
- **`toy_B_3x4` instance scale.** 3 EVs, 4 slots, 11 qubits. The ADOPT γ-inflation of ρ_d does not change the discrete classical optimum at this scale; F1 and F2 produce identical schedules.
- **Behavioral-data availability asymmetry.** 63.98% of calibration records have null `userInputs` versus 16.08% in held-out, reflecting the historical rollout of the Caltech user-input feature.
- **Bootstrap denominator convention.** The paired bootstrap operates over a 4,857-length vector with default-zero placeholders for null-`userInputs` records. The headline P(feasible) uses n = 4,076 (valid joint only). The bootstrap diff_mean is scaled by 4076/4857 = 0.8391 relative to the headline P(feasible) difference. The statistical conclusion (CI excludes 0) is robust to denominator choice. See `artifacts/stage10/STATISTICAL_DENOMINATOR_AUDIT.md` for the full forensic analysis.
- **QAOA at p=1.** Frozen p=1 is a weak variational form. Higher p is not in the frozen configuration.
- **Distribution shift.** Classified as A_mild, but the held-out ΔE range (max +3.4 kWh) is a strict subset of the calibration range (max +69.5 kWh); worst-case performance may be understated.
- **No demonstrated quantum advantage.** QAOA at p=1 with COBYLA achieves AR=1.0 (median) on F0/F1 but AR > 1 on F2 seed 2 (sampling noise, faithfully reported).
- **External API dependency for full reproduction.** The Option B (full rerun) path requires a Caltech ACN API token; the published artifacts can be inspected without one (Option A).

---

## Final Project Status

**COMPLETE — WITH DOCUMENTED LIMITATIONS.**

The Stage 9 real-data experiment executed end-to-end on the real Caltech ACN dataset using the frozen methodology. The pipeline is reproducible. The proposed method achieved a Pareto trade-off with the deterministic baseline, not dominance. The result is honestly reported.

---

## License and Provenance

This project contains material from the Caltech ACN-Data live API. ACN data is publicly accessible; no special licensing applies for use in research. The methodology implementation is original work for this project. The frozen configuration is preserved in `artifacts/final_experiment_config.json`.
