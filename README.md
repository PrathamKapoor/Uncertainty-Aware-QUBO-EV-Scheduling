# Uncertainty-Aware EV Charging Optimization

This project studies small electric-vehicle charging schedules using binary optimization, exact enumeration and simulated QAOA circuits. It compares nominal, scenario-based, earliest-feasible and deadline-buffer schedules. The real charging-session data in the revised study supplies connection durations; the charging requests, tariffs and scheduling decisions are modeled.

## Start here

- [Code walkthrough with examples](docs/CODE_WALKTHROUGH_WITH_EXAMPLES.md) traces a two-EV example through the implementation.
- [Teacher explanation](docs/TEACHER_EXPLANATION.md) and [mathematical walkthrough](docs/MATHEMATICAL_WALKTHROUGH.md) explain the main ideas.
- [Research paper](docs/final/EV_QUBO_Research_Paper_Polished.pdf) presents the exploratory experiments and limitations.

## Project layout

| Directory | Responsibility |
|---|---|
| `scheduling/` | EV instances, physical feasibility and QUBO construction |
| `quantum/` | QUBO-to-Ising conversion and QAOA simulation |
| `uncertainty/` | Charging-data acquisition and scenario modeling |
| `experiments/` | Revised data pipeline, evaluation and reproducible studies |
| `robust/`, `stress/`, `audit/` | Preserved historical formulations and checks |
| `tests/` | Mathematical, physical, data and integration tests |
| `artifacts/` | Preserved historical results and revised experiment outputs |
| `docs/` | Research, teaching and manuscript documentation |

Historical filenames and artifacts retain their original stage labels as provenance; they are not the current package layout. The [historical README](docs/HISTORICAL_README.md) is retained as a record and its old headline claims should not be treated as validated revised results.

## Run locally

Install the dependencies in `requirements.txt`, then from the repository root:

```powershell
python -m pytest -q
python -m experiments.revised_experiment --source fixture
python -m experiments.multi_ev_study
```

The fixture and two-EV study are synthetic. The latter runs QAOA simulations for multiple seeds and may take longer. To reproduce the public-data stress test, obtain the CSV as described in [dataset validation](docs/DATASET_VALIDATION.md), then run:

```powershell
python -m experiments.public_dataset data/ChargingRecords.csv
```

The live ACN API route requires a token supplied through a local environment variable. Never put a token in the repository or chat. Previously disclosed credentials should be considered compromised until revoked or rotated.

## What the experiments show

In the public-duration single-EV counterfactual, the 90% buffer and earliest-feasible baseline choose the same schedule. Both outperform the cost-oriented nominal schedule on modeled completion, while a more aggressive buffer leaves no complete charging slot. In a synthetic two-EV case with binding site capacity, the comparison also depends on how a nominal optimum tie is resolved. These are exploratory modeled results, not measured deployment benefits. QAOA uses a classical simulator; the project does not demonstrate quantum advantage.
