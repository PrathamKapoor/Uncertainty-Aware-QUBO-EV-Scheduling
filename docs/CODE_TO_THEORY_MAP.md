# Code-to-theory map: revised pilot

| Concept | Equation | Implementation | Test | Artifact |
|---|---|---|---|---|
| Delivered energy | `P Δt sum(x)` over complete available slots | `scheduling.ev_scheduling.decode_feasibility` | `tests/test_revised_departure.py` | None yet for ACN |
| Capacity | `L+s=Pmax`, `s≥0` in integer power units | `scheduling.revised_qubo.build_revised_qubo` | `tests/test_revised_qubo.py` | `artifacts/revised_v2/experiment_config.json` |
| QUBO | `xᵀQx+c` | `build_revised_qubo`, `physical_objective` | `test_qubo_matches_objective_and_one_sided_capacity` | Synthetic pilot JSON |
| Ising | `x=(1-Z)/2` | `quantum.qaoa.qubo_to_ising` | `test_ising_energies_and_qiskit_basis_order` | Synthetic pilot JSON |
| QAOA | `exp(-iβ ΣX) exp(-iγH_C)` | `quantum.qaoa._build_qaoa_ansatz`, `run_qaoa` | Basis energies tested; circuit sampling executed | `artifacts/revised_v2/circuit_p1.txt`, `circuit_p2.txt` |
| Paired comparison | resampled mean of paired differences | `experiments.real_experiment.paired_records_v2` | `test_paired_comparison_requires_matching_records_and_adjusts_interval` | No revised ACN result yet |

All relative artifact paths are rooted at the repository. A comprehensive mapping for the historical data path and revised experiments remains unfinished.
