# Research notebooks

This directory contains the human-readable research narrative for the
project. The Python modules in `stage3/`–`stage9/` are the implementation
source; these notebooks are a research-facing layer that exposes the
scientific workflow.

## Reading order

| # | Notebook | What it shows |
|---|---|---|
| 00 | overview | The research question, the hypothesis, the reading guide, the frozen-config statement |
| 01 | data audit and cleaning | The ACN-Data source, R1-R11 cleaning rules, the static-snapshot audit |
| 02 | temporal split | The calendar split, disjointness proof, the leakage-safe-by-construction property |
| 03 | uncertainty characterization | ΔE and Δd empirical distributions, with placeholder fallback clearly labeled |
| 04 | deterministic QUBO | The toy instance, MILP/QUBO equivalence, algebraic validation |
| 05 | QAOA implementation | p=1, COBYLA, AR / P(opt) / P(feas) |
| 06 | scenarios and ADOPT | k-means K=8, γ pre-registration on calibration only |
| 07 | robust QUBO | Corrected scenario transformation, M_window diagonal penalty |
| 08 | synthetic stress tests | S1 / S2 / S3, directionality, freeze |
| 09 | exact vs QAOA | AR and the small-instance regime |
| 10 | real ACN-Data experiment | The 20-step protocol; the PENDING section in the paper |
| 11 | held-out evaluation and statistics | P(feas), unmet, cost, peak, paired bootstrap CI |
| 12 | results and paper integration | Populating Stage 10 PENDING placeholders |

## Contract for every notebook

Each notebook follows the same structure:

- **Question** — what the notebook is asking.
- **Why this test exists** — the scientific motivation.
- **Method** — the approach, including the mathematical formulation where
  relevant.
- **Implementation** — the code cells, with the implementation source in
  `stage3/`–`stage9/`.
- **Result** — the output, with a table or figure.
- **Interpretation** — what the result means scientifically.
- **Limitations** — what the result does NOT show.
- **Reproducibility** — the exact env, data, and commands needed to
  reproduce the result.

## Credential-safety

The real-data notebook (10) is hardened:

- It checks `ACN_API_TOKEN` or `ACNPORTAL_TOKEN` as a **boolean only**.
- It never displays, logs, stores, hashes, or otherwise exposes the
  token's value, length, prefix, suffix, base64 encoding, or any header
  that contains it.
- Outputs are sanitized; the loader's `_redact_status` defensive filter
  strips token-shaped strings from the status block before write.
- Notebooks are committed with cleared outputs; if any token-shaped
  string appears in a saved output, that is a bug and must be reported.

## No quantum-advantage claim

The frozen QAOA configuration is reported as a methodology-validation
result, not as a quantum-advantage claim. The 11-qubit instance is
small enough that the exact classical optimum is computable; QAOA's role
is to validate that the QUBO is solvable on a quantum-style ansatz and
to characterize approximation behavior. The notebooks and the paper
both explicitly disavow quantum-advantage language.

## What the notebooks do NOT do

- They do not modify the frozen methodology.
- They do not re-tune γ, K, α, M_window, ρ_d, ρ_p, ρ_cap, or any QAOA
  setting based on held-out data.
- They do not claim quantum advantage.
- They do not synthesize or substitute data for the real data.
- They do not display the token or any credential.

## Frozen configuration (re-stated)

The methodology is frozen at `artifacts/final_experiment_config.json`
(version `stage7.v1`):

- K=8
- α=1.0
- M_window=1e6
- ρ_d=1.0, ρ_p=0.1, ρ_cap=0.5
- P_target=6.6 kW, P_site_max=9.9 kW
- Δ=15 min
- calibration window 2018-05-01..2019-07-01 (UTC, exclusive end)
- held-out window 2019-07-01..2020-01-01 (UTC, exclusive end)
- QAOA: p=1, COBYLA, seeds [0,1,2], shots 1024
- sign conventions: ΔE = E_delivered − E_requested; Δd = d_requested − d_actual

Raw-file SHA-256: `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`.
