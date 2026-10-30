# Traceability for the exploratory study

| Claim | Source function | Inputs and output | Reproduce |
|---|---|---|---|
| Eligibility and temporal split | `experiments.public_dataset.prepare_sessions` | Public CSV; `public_duration_stress.json.gz` dataset/counts | `python -m experiments.public_dataset data/ChargingRecords.csv` |
| Calibrated margins and exact schedules | `experiments.revised_experiment.reliability_buffer_minutes`, `buffered_schedule`, `run_experiment` | Same CSV and artifact, fields `buffers_minutes` and `methods` | Same command |
| Paired day interval | `experiments.public_dataset.day_block_interval` | Same CSV and artifact, `buffer90_vs_F0_day_block` | Same command |
| QAOA metrics | `quantum.qaoa.run_qaoa`, `experiments.revised_experiment.run_experiment` | Same artifact, `quantum` | Same command |
| Figure | `scripts/plot_public_stress.py` | Compressed results to `public_duration_stress.png` | `python scripts/plot_public_stress.py` |
| QUBO and Ising equivalence | `scheduling.revised_qubo`, `quantum.qaoa.qubo_to_ising` | Six-qubit synthetic test instance | `python -m pytest tests/test_revised_qubo.py -q` |
