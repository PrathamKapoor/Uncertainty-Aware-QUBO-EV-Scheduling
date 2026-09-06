# Uncertainty-Aware QUBO Scheduling for EV Charging — Real Caltech ACN Data Evaluation

**Project root:** `C:/Projects/uncertainity_aware_quantum_opt`
**DATA_MODE:** REAL (live ACN Caltech behavioral data)
**Frozen configuration SHA-256:** `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3` (must remain unchanged)
**Final project status:** COMPLETE — WITH DOCUMENTED LIMITATIONS

## Project Overview

A reproducible real-data evaluation of uncertainty-aware QUBO/QAOA scheduling for electric vehicle charging, using behavioral uncertainty derived from real Caltech ACN session data.

The project implements an end-to-end pipeline: real ACN data retrieval, frozen temporal split, K-means scenario generation on the calibration joint (Δd, ΔE), ADOPT γ inflation, QUBO construction (F0 deterministic, F1 robust K=8, F2 ADOPT, F3 oracle), QAOA p=1 with COBYLA on seeds [0,1,2] at 1024 shots, held-out evaluation on 4,076 valid joint sessions, paired bootstrap 95% CI with Bonferroni correction.

## Main Finding

**Under the frozen experimental configuration, the deterministic baseline achieved higher held-out feasibility than the proposed uncertainty-aware formulations.**

Reported held-out P(feasible) (denominator 4,076 valid joint sessions):

| Formulation | P(feasible) | mean_unmet (kWh) | deadline_viol_rate |
|---|---|---|---|
| **F0 (deterministic baseline)** | **0.9985** | 2.463 | 0.0015 |
| F1 (robust K=8) | 0.8781 | 0.756 | 0.1219 |
| F2 (ADOPT, γ=4.1313) | 0.8781 | 0.756 | 0.1219 |
| F3 (oracle, analysis-only) | 0.9941 | 0.000 | 0.000 |

The 12.19 percentage point gap (F0 − F2) is **statistically significant** (paired bootstrap 95% CI [−0.1095, −0.0926]; CI excludes 0; Bonferroni α = 0.05/3 = 0.01667) but the sign **favors the deterministic baseline**. F1 and F2 produce **identical schedules** on the 11-qubit `toy_B_3x4` instance, so the ADOPT γ-inflation does not change the discrete classical optimum at this scale.

The proposed method achieves a **Pareto trade-off**: lower unmet demand and lower cost, in exchange for 12.19 pp of feasibility and 12.04 pp of additional deadline violations. Whether this trade-off is operationally acceptable depends on deployment-specific priorities.

This is a **negative result**. The framework executes correctly end-to-end on real data; the proposed uncertainty-aware formulations do not outperform the well-tuned deterministic baseline under the frozen configuration.

## Quick Start

The canonical human-facing execution path is the Jupyter notebook:

**`notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`**

To reproduce the published artifacts:

1. From the repository root, start Jupyter: `jupyter notebook` (or use VS Code / JupyterLab).
2. Open `notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`.
3. **Restart Kernel → Run All.**

**Prerequisite**: the notebook assumes the current working directory is the repository root (it uses relative paths like `artifacts/...`). All file references inside the notebook are relative; no absolute paths are hardcoded.

The default mode is **artifact reproduction**: the notebook verifies the frozen configuration, loads the existing Stage 9 results from `artifacts/real_*.json` and `artifacts/stage9_*.json`, regenerates the tables and figures, displays the statistical validation, and renders the final scientific conclusion. **No live data fetching. No QAOA. No overwrite of authoritative results.**

## Reproducibility Modes

The notebook supports two explicit modes, selected by a single user-controlled flag at the top of the notebook.

### Mode A — Artifact Reproduction (DEFAULT)

- `RUN_FULL_EXPERIMENT = False`
- Verifies frozen config hash matches `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`
- Verifies all required Stage 9 artifacts are present
- Verifies artifact internal consistency and DATA_MODE = REAL
- Loads existing real_*.json and stage9_*.json artifacts
- Reproduces tables, figures, statistical summaries
- Displays the final scientific conclusion
- **Requires no credentials, no network, no QAOA**

### Mode B — Full Source Reproduction (EXPLICIT OPT-IN)

- User must manually change `RUN_FULL_EXPERIMENT = False` to `RUN_FULL_EXPERIMENT = True` in the notebook
- **Requires** `ACN_API_TOKEN` or `ACNPORTAL_TOKEN` environment variable
- Fetches live data from `https://ev.caltech.edu/api/v1/sessions/caltech`
- Runs QAOA, scenario generation, bootstrap, all Stage 9 components
- Overwrites `artifacts/real_*.json` and `artifacts/stage9_*.json`
- ~30 minutes wall time
- Will produce a new SHA-256 of the in-memory samples (slightly different from prior runs) but the **frozen config hash remains unchanged**

**Do not enable Mode B unless you intend to regenerate the experiment outputs.**

## Scientific Integrity

The methodology is frozen before evaluation and never modified based on held-out results:

- **Frozen configuration**: `artifacts/final_experiment_config.json` (version `stage7.v1`), SHA-256 verified before, during, and after every scientific run
- **Real data**: `DATA_MODE = REAL`, source `live_api` from the Caltech ACN Data API
- **No post-hoc tuning**: K=8, α=1.0, ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5, M_window=1e6, P_target=6.6 kW, P_site_max=9.9 kW, QAOA p=1, COBYLA optimizer, seeds [0,1,2], shots=1024 — all frozen
- **Unfavorable result retained**: F1 and F2 do not outperform F0. The result is reported as-is. No parameters were tuned, no sessions were dropped, no seeds were changed to improve the outcome.
- **Calibration/held-out isolation**: Calibration window (2018-05-01 → 2019-07-01) and held-out window (2019-07-01 → 2020-01-01) are disjoint by construction; the driver raises an error if any session_id appears in both.

## Repository Layout

```
C:/Projects/uncertainity_aware_quantum_opt/
├── README.md                                <- this file
├── handoff.md                                <- legacy session-continuity pointer
├── RELEASE_CHECKLIST.md                      <- final release-readiness checklist
├── requirements.txt                          <- Python dependencies (see Part 3)
├── notebooks/
│   ├── FINAL_REPRODUCIBLE_EXPERIMENT.ipynb   <- canonical human-facing entry point
│   ├── 00_overview.ipynb ... 12_*.ipynb      <- 13 pre-existing research notebooks
│   └── _build_*.py                            <- notebook build helpers
├── artifacts/
│   ├── final_experiment_config.json         <- FROZEN methodology
│   ├── real_*.json (×17)                    <- Stage 9 results (authoritative)
│   ├── stage9_*.json (×2)                   <- Stage 9 manifests
│   └── stage10/                              <- Stage 10 reporting deliverables
│       ├── FINAL_SCIENTIFIC_REPORT.md
│       ├── STATISTICAL_DENOMINATOR_AUDIT.md
│       ├── FINAL_RESULTS_TABLE.md
│       ├── REPRODUCIBILITY_MANIFEST.json
│       └── figures/ (×5 PNGs)
├── stage3/  stage4/  stage5/  stage6/  stage9/  <- implementation modules
├── docs/                                     <- stage specifications, paper drafts
└── ...
```

## Limitations

- **Single-site dataset**: Results are specific to the Caltech ACN deployment. Other sites, populations, and time periods may exhibit different behavioral distributions.
- **toy_B_3x4 instance scale**: 3 EVs, 4 slots, 11 qubits. The ADOPT γ-inflation of ρ_d does not change the discrete classical optimum schedule on this small instance. F1 and F2 produce identical schedules.
- **Behavioral-data availability asymmetry**: 63.98% of calibration records have null `userInputs` (vs 16.08% in held-out), reflecting the historical rollout of the Caltech user-input feature.
- **Bootstrap denominator convention**: The paired bootstrap operates over a 4,857-length vector with default-zero placeholders for null-userInputs records. The headline P(feasible) uses n=4,076 (valid joint only). The bootstrap diff_mean is scaled by 4076/4857 = 0.8391 relative to the headline P(feasible difference). The statistical conclusion (CI excludes 0) is robust to denominator choice. See `artifacts/stage10/STATISTICAL_DENOMINATOR_AUDIT.md` for the full forensic analysis.
- **QAOA at p=1**: Frozen p=1 is a weak variational form. Higher p is not in the frozen configuration.
- **Real-world generalization**: Not demonstrated. The result is specific to the Caltech ACN deployment, 2018-05-01 to 2020-01-01.
- **No demonstrated quantum advantage**: The QAOA at p=1 with COBYLA achieves AR=1.0 (median) on F0/F1 but AR > 1 on F2 seed 2 (sampling noise, faithfully reported).

## Final Project Status

**COMPLETE — WITH DOCUMENTED LIMITATIONS**

The Stage 9 real-data experiment executed end-to-end on the real Caltech ACN dataset using the frozen methodology. The pipeline is reproducible. The proposed method achieved a Pareto trade-off with the deterministic baseline, not dominance. The result is honestly reported.

## License and Provenance

This project contains material from the Caltech ACN-Data live API. ACN data is publicly accessible; no special licensing applies for use in research. The methodology implementation is original work for this project. The frozen configuration is preserved in `artifacts/final_experiment_config.json`.
