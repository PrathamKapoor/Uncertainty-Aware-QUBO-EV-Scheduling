# Demonstration script: current synthetic pilot

**90 seconds.** EVs compete for limited charging power. We encode charging decisions and unused site capacity as bits, compare exact enumeration with a simulated QAOA circuit, and evaluate measured schedules. This pilot is synthetic and does not claim quantum advantage.

**Three minutes.** Explain that each bit describes a charging decision or slack, construct the squared energy and capacity terms, then show `docs/MATHEMATICAL_WALKTHROUGH.md`. Explain that the Ising substitution turns bits into Z measurements and the mixer changes amplitudes. COBYLA chooses circuit angles using simulated samples.

**Five minutes.** Run `python -m pytest tests -q`, then `python scripts/run_revised_quantum_example.py`. Open `artifacts/revised_v2/experiment_config.json`, the circuit text and `synthetic_quantum_example.json`. Compare exact optimum 1.5, sampled optimum probability and sampled physical feasibility probability. Explain that the latter ignores slack-bit optimality.

For the integrated fixture, run `python -m experiments.revised_experiment --source fixture` and inspect `artifacts/revised_v2/integrated_fixture.json`. Its calibration and evaluation records are fabricated for testing; it is not an ACN result.

**Ten minutes.** Expand the QUBO example, show the test of all 64 Ising energies, compare p=1 and p=2 across the two recorded seeds, and discuss why 256 shots and 20 optimizer evaluations do not justify general performance conclusions. Explain the known defects in the historical ACN study, the unfinished corrected data pipeline, and why a simulator does not prove quantum speedup.
