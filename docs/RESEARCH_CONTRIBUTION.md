# Contribution and scope

This is an exploratory empirical comparison of a simple quantile buffer with nominal and scenario-based QUBO scheduling. It is not a claim to invent buffered deadlines, QUBO, scenario optimization or QAOA. Given a modeled nominal horizon D=30 minutes and observed calibration connection duration T, define `delta = D - T` and `b_tau = quantile_tau(max(0, delta))`. Charging decisions are restricted to complete slots ending by `D-b_tau`. If no slot remains, the request is explicitly unmet.

The calibrated durations are real, but D and the target are synthetic and the duration is not an observed forecast error. The current one-EV study evaluates scheduling behavior, not an installed charging station. QAOA has been run on the nominal and 90% buffer QUBOs with one seed; an F1 QAOA comparison, multi-EV capacity experiments and independent validation remain necessary before making a broader contribution claim.
