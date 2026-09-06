# Final Release Checklist

**Date:** 2026-09-05
**Project root:** `C:/Projects/uncertainity_aware_quantum_opt`
**Frozen config SHA-256:** `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3` (MUST remain unchanged)
**Final project status:** COMPLETE — WITH DOCUMENTED LIMITATIONS

This checklist records the verified state of the repository at the time of final release. Items marked `[x]` have been verified by direct inspection, file read, or simulation. Items marked `[ ]` have NOT been verified.

## Scientific

- [x] **Frozen configuration verified**
  - File: `artifacts/final_experiment_config.json`
  - SHA-256: `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`
  - Match: VERIFIED (verified pre-release, mid-run, and post-run)
- [x] **Real-data status accurately labeled**
  - `DATA_MODE = REAL` (in `stage9_run.json`)
  - `source = live_api` (from `https://ev.caltech.edu/api/v1/sessions/caltech`)
  - 25,656 records retrieved (1,029 pages × HTTP 200)
- [x] **Negative result accurately reported**
  - F0 P(feasible) = 0.9985 (4,076 valid joint sessions)
  - F1 P(feasible) = 0.8781
  - F2 P(feasible) = 0.8781
  - F1 and F2 produce identical schedules on the 11-qubit `toy_B_3x4` instance
  - 12.19 pp gap favors F0; statistically significant (CI excludes 0)
- [x] **No superiority claim unsupported by evidence**
  - 0 instances of "proposed method dominates" or "F1/F2 wins" in headline context
  - All 4 Stage 9 baseline formulations executed and reported
  - The "F1 wins on" cells in `FINAL_RESULTS_TABLE.md` are per-metric Pareto cells (unmet demand, cost, peak), not a claim of overall superiority

## Reproducibility

- [x] **Canonical notebook identified**
  - Path: `notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`
  - Prominently named in `README.md` Quick Start
  - 37 cells (18 markdown, 19 code)
- [x] **Clean-kernel Run All verified (simulated)**
  - 19 code cells executed in sequence with persistent state
  - 0 errors
  - Frozen config hash verified mid-run
  - No Stage 9 artifacts modified
- [x] **Artifact mode requires no credentials**
  - `RUN_FULL_EXPERIMENT = False` (default)
  - Only `os.environ.get('ACN_API_TOKEN')` is checked (presence only, never value)
  - 0 tokens, 0 Authorization headers, 0 Bearer tokens in any artifact
- [x] **Dependency specification available**
  - File: `requirements.txt`
  - Contents: numpy>=1.24, scipy>=1.10, qiskit>=1.0, qiskit-aer>=0.13, matplotlib>=3.5, jupyter>=1.0, notebook>=6.5, ipykernel>=6.0, ipython>=8.0
  - Tested versions noted in comments
- [x] **Required artifacts present**
  - 21 Stage 9 fresh artifacts on disk (from run 2026-09-05)
  - 5 Stage 10 deliverables (4 documents + 5 figures)
  - 1 canonical reproducibility manifest (`REPRODUCIBILITY_MANIFEST.json`)
  - 1 README.md (this release)
  - 1 RELEASE_CHECKLIST.md (this file)
  - 1 requirements.txt (created during this audit)
- [x] **No hidden dependencies in notebook**
  - All file references are relative (e.g., `artifacts/real_*.json`)
  - 0 hardcoded absolute paths (Windows, Linux, macOS)
  - Only env var read: `ACN_API_TOKEN` / `ACNPORTAL_TOKEN` (presence only)

## Security

- [x] **Credential scan completed**
  - 187 text files scanned
  - 0 credential patterns (no tokens, no Authorization: Basic, no Bearer, no API keys, no private keys)
- [x] **No credentials committed**
  - 0 tokens in any file in the repository
  - 0 Authorization headers in any file
  - `real_raw_sessions.json` contains only `{sha256, n_records, source, token_redacted: true}`
- [x] **No Authorization headers persisted**
  - 0 instances in any artifact
  - Token value is never echoed, hashed, or written
- [x] **No raw ACN session records committed to main artifacts**
  - `real_raw_sessions.json`: contains SHA-256 of in-memory sample list, NOT raw records
  - `real_cleaning_results.json`: contains aggregate counts only
  - `artifacts/sample_csvs/`: contains 200 gzipped CSVs from the **public** Caltech ACN data portal (no credentials involved; these are publicly downloadable timeseries data)

## Documentation

- [x] **README explains main finding**
  - "Main Finding" section in `README.md` states F0/F1/F2 P(feasible) values
  - States the 12.19 pp gap favors F0
  - Calls the result a "negative result" explicitly
- [x] **README explains artifact reproduction**
  - "Quick Start" section: `notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb`
  - Step-by-step: from repo root, `jupyter notebook`, open the file, Restart Kernel → Run All
  - Explicit cwd prerequisite
- [x] **README explains full reproduction requirements**
  - "Mode B — Full Source Reproduction" section
  - Lists: `ACN_API_TOKEN` or `ACNPORTAL_TOKEN` env var, network access, ~30 min wall time, will overwrite `real_*.json` / `stage9_*.json`
  - Documents env var names only; never values
- [x] **Limitations documented**
  - 8 limitations in `README.md` (toy_B_3x4 scale, F1=F2 schedule, behavioral-data availability asymmetry, bootstrap denominator, distribution shift, p=1 QAOA, single-site, no quantum advantage)
  - Full forensic audit in `artifacts/stage10/STATISTICAL_DENOMINATOR_AUDIT.md`

## Files Created or Modified in This Release Pass

| Path | Change | Classification |
|---|---|---|
| `README.md` | NEW (was absent) | documentation |
| `requirements.txt` | NEW (was absent) | reproducibility infrastructure |
| `RELEASE_CHECKLIST.md` | NEW (this file) | release engineering |

**ZERO scientific methodology changes.** No modifications to `artifacts/final_experiment_config.json`, no modifications to any `stage3-9/*.py` source file, no modifications to any Stage 9 or Stage 10 scientific artifact.

## Source File Integrity (verified SHA-256)

| File | SHA-256 |
|---|---|
| `artifacts/final_experiment_config.json` | `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3` (FROZEN, UNCHANGED) |
| `stage3/ev_scheduling.py` | `066322e8d78feeeacfd2a4cf35068d7be4e2e52efab3d08f1d14f0528b773428` |
| `stage4/qaoa.py` | `5fadf933843e52ba49c513b0d14239868e12a2aad4f2c4eed1ab6d910ccc45fd` |
| `stage5/uncertainty.py` | `12b672297eab817767a44927e13dd2bfe1fa573b34b12562d383a1241a1c6e19` (retrieval-only fix from prior turn, pre-authorized) |
| `stage6/robust_qaoa.py` | `da1994cb7dd116b5ad5c3b2218d8e3a6e62a33048c95c2539964b3b3524e8142` |
| `stage9/real_experiment.py` | `d1d365bd39756430acfce15c1c9797451643e15b6b9b40c40509ce49a824d622` (dead-code import removed from prior turn, pre-authorized) |

## How a Reviewer Can Independently Verify

1. **Verify the frozen config hash** (any time):
   ```
   python -c "import hashlib; print(hashlib.sha256(open('artifacts/final_experiment_config.json','rb').read()).hexdigest())"
   ```
   Expected: `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`

2. **Reproduce the published artifacts** (default mode):
   ```
   jupyter notebook
   # Open notebooks/FINAL_REPRODUCIBLE_EXPERIMENT.ipynb
   # Restart Kernel → Run All
   ```

3. **Cross-check the headline numbers** (any time):
   ```
   python -c "import json; h=json.load(open('artifacts/real_heldout_results.json')); print(f'F0={h[\"F0\"][\"P_feasible\"]:.4f} F1={h[\"F1\"][\"P_feasible\"]:.4f} F2={h[\"F2\"][\"P_feasible\"]:.4f}')"
   ```

4. **Verify the statistical conclusion** (any time):
   ```
   python -c "import json; p=json.load(open('artifacts/real_paired_statistics.json'))['primary_F2_vs_F0']; print(f'diff={p[\"diff_mean\"]:.4f} CI=[{p[\"ci_lo\"]:.4f},{p[\"ci_hi\"]:.4f}]')"
   ```
