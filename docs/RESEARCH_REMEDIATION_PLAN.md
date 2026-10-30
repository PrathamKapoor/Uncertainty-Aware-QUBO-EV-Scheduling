# Research remediation plan (initial audit)

Status: incomplete. Historical results remain unchanged and must not be treated as validated revised results. This document records an initial source inspection, not a complete audit.

## Observed architecture

The historical pipeline constructs scheduling instances and QUBOs in `scheduling/ev_scheduling.py`; `robust/robust_qaoa.py` constructs scenario formulations; `experiments/real_experiment.py` evaluates fixed schedules and performs paired bootstrap comparisons. Stage 4 implements the quantum workflow, and stages 5, 7 and 8 supply uncertainty, stress tests and audits. The precise full data and circuit dependency map remains to be verified.

## Verified findings

* `corrected_scenario_aware_instance` preserves nominal `d_slot`, while `scenario_aware_qubo` computes a separate window mask. `evaluate_schedule_on_held_out` passes the nominal-window instance to `decode_feasibility`, which counts all nominal-window charging. Realized deadlines therefore are not enforced in that evaluation. The QUBO mask also clamps the effective deadline to arrival, masking impossible windows.
* The same scenario transformation adds the measured delivery residual to every EV's requirement and clamps it at zero. This does not establish a change in true driver demand and can eliminate demand.
* The stage 9 F3 evaluation uses one previously constructed schedule for all held-out records and hard-codes several metrics, including cost and unmet energy, to zero. It is not a valid per-record oracle comparison.
* Stage 9 initializes vectors for all held-out records, skips missing records without removing their entries, and passes the full feasibility vectors to the bootstrap. Its reported mean unmet energy excludes zero values, making it conditional on nonzero shortfall. The reported bootstrap intervals are described as 95% despite a separate Bonferroni alpha field.
* `corrected_robust_qubo` uses each scenario's `weight`; the frozen configuration specifies uniform weights. The actual scenario-generation path still needs tracing to determine the numerical effect.
* `build_qubo` uses a squared deviation from site capacity, penalizing load below the limit as well as above it. The decoder separately checks a one-sided limit. `decode_feasibility` computes cost as price times power without a slot-duration factor; whether its price units justify this requires tracing the input tariff definition.

## Investigation and repair sequence

1. Trace dataset provenance, units, temporal split and full experiment imports; quantify missing records and preserve all historical artifacts. Verify calibration-only fitting and inspect per-EV dependence.
2. Create a versioned physical model with explicit nominal and realized deadlines, a documented slot-boundary convention, unchanged requested energy, and a one-sided capacity constraint with a validated binary slack encoding. Exhaustively compare direct objective, QUBO and physical feasibility on small cases, including impossible windows and binding capacity. Establish penalty bounds rather than assuming a large value is safe.
3. Verify QUBO-to-Ising coefficients and offsets exhaustively, then test actual QAOA circuit ordering, measurement endianness, optimizer and sampling against enumeration. Record circuit resources and seed variation; do not claim quantum advantage.
4. Implement paired eligible-record statistics, unconditional and conditional shortfall summaries, correctly adjusted intervals and an appropriate dependence sensitivity analysis. Either compute a per-instance oracle using identical metrics or omit it. Tests must exercise missing data and zero-valued observations.
5. Define separate uniform and empirical weights, calibration-only feature normalization, and prespecified K sensitivity. Preserve the original frozen configuration and put all corrected outputs under a new version. Revised results are exploratory because historical held-out outcomes have already been inspected.
6. Execute available experiments and document data, assumptions, limitations and reproducibility. Build teacher guides and manuscript only from verified code and generated artifacts. Inspect credentials and Git history before any release.

All of these changes may alter previously reported results. No corrected numerical results or test outcomes have yet been established. The quantum correctness, full dataset semantics, dependency versions, historical denominator counts and literature claims remain unverified.
