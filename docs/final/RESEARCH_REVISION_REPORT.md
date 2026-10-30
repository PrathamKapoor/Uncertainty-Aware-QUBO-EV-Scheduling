# Research revision report

The user identified `docs/final/EV_QUBO_Research_Paper.docx` as the authoritative source. It was edited in place conceptually, leaving the original unchanged, and the resulting revised DOCX was exported to PDF. The cover retains Quantum Computing, Dr. Sreemoyee Sarkar, the supplied author order and roll numbers, and the existing logo. The body author order was corrected to match the cover.

## Earliest feasible charging

The prior single-EV comparison lacked an immediate-charging baseline. `stage9.revised_experiment.earliest_feasible_schedule` now constructs one, with regression tests in `tests/test_earliest_baseline.py`. Running `python -m stage9.public_dataset data/ChargingRecords.csv --output artifacts/revised_v2/earliest_baseline.json.gz` shows the earliest policy and 90% buffer choose the identical first slot, with identical simulated completion (93.56%), mean unmet energy (0.0161 kWh) and cost. The 8.55-point improvement is over the later-slot nominal baseline, not over earliest charging.

## Two-EV capacity example

`python -m stage9.multi_ev_study` produces `artifacts/revised_v2/multi_ev_comparison.json`. This is a synthetic two-EV/two-slot case with a 1 kW binding site limit, 1 kW chargers, 0.25 kWh targets, and two equally weighted modeled availability cases. It is not a historical fleet reconstruction. Exact enumeration finds F0's selected nominal optimum serves the vulnerable EV late, while F1, the buffer and time-first greedy allocation serve it early. Their modeled joint completion is respectively 50% and 100% over these two assumed cases. However, a tested equally optimal nominal solution already matches the early allocation, so the comparison depends on deterministic tie-breaking and does not establish a unique benefit of scenario optimization or buffering. Greedy priority follows declaration order. The nominal cost of fulfilling both requests is the same in these symmetric examples.

For F0 and the buffer the QUBOs use four decision and two slack qubits; F1 uses four decision and four scenario-specific slack qubits. Each was evaluated on Aer with p=1 and p=2, five seeds, 128 shots and up to 12 optimizer evaluations per run. QUBO and Ising energies were checked for every state. The recorded per-run results must be read as small simulated optimization trials, not real-world charging probabilities or evidence of quantum advantage.

## Dependence and duplicates

`python scripts/duplicate_sensitivity.py` generates `artifacts/revised_v2/duplicate_sensitivity.json`. Removing the 13 identical full rows leaves the 90% buffer at 7 minutes and does not change evaluation metrics because those duplicates are outside the evaluation set. A day-block interval remains an exploratory sensitivity analysis. Additional charger-cluster resampling covers 1,661 charger IDs; user-cluster resampling covers 1,254 nonzero IDs and excludes unidentified users. These separate resampling schemes do not jointly eliminate dependence across users, chargers and dates.

## Validation and outstanding work

`python -m pytest -q` reported 35 passed and 14 dependency deprecation warnings. The final DOCX was exported with Microsoft Word to PDF and all 10 pages were rendered and visually reviewed. It contains five numbered figures, five tables and six references; the cover is unnumbered. Equation (1) stays with its introduction and conclusion text stays together. Remaining limitations include tiny modeled multi-EV cases, arbitrary two-scenario probabilities, short QAOA optimizer runs, no calibrated multi-EV real-site reconstruction, no declared departure data in the public dataset, and unverified prior credential rotation. No new Git commit or push has been made.
