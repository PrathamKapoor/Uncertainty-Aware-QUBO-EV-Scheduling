# Evaluating Buffered QUBO Scheduling With Observed EV Connection Durations

**Draft — exploratory, not submission-ready.** The empirical comparison uses one synthetic EV scheduling instance; the scenario QUBO has not yet been evaluated with QAOA. Formatting and independent validation remain outstanding.

## Abstract

Electric-vehicle charging schedules must supply energy while respecting limited time and electrical capacity. Connection times are uncertain, so a schedule that delays charging can fail when a vehicle disconnects early. We compare a nominal schedule, a scenario-averaged schedule and schedules with calibration-derived deadline buffers in a small quadratic unconstrained binary optimization (QUBO) model. We use 72,268 public charging-connection records, with 22,083 records in a later evaluation period. Since the dataset does not provide declared departure times or requested energy, the nominal deadline and service target are simulated, and observed connection durations are used as counterfactual availability. Simulated service completion is 85.01% for the nominal schedule and 93.56% for a 90th-percentile buffer; a larger buffer leaves no complete slot and completes no requests. A four-qubit QAOA simulation of the nominal formulation samples an optimal state in 23.83% of 256 shots. These results illustrate a reliability-cost trade-off and a discretization failure, not a quantum advantage or demonstrated real-world deployment benefit.

**Keywords:** electric vehicles; charging scheduling; QUBO; QAOA; uncertainty; reliability.

## 1. Introduction

Charging can be delayed to use cheaper electricity, but vehicles can disconnect before a planned slot. We ask how a calibration-based early-completion buffer affects simulated service and cost compared with nominal and scenario-based schedules, and how a small QUBO can be evaluated on a quantum simulator. The study evaluates an established type of reliability margin; it does not claim a novel quantum algorithm.

## 2. Related work

Wang et al. [1] use scenario-based stochastic programming for uncertain vehicle availability and demand. Dalyac et al. [2] study quantum approaches for industrial EV smart charging. Sone et al. [3] examine robust scheduling with uncertain demands and deadlines. Farhi et al. [4] introduce QAOA. These studies establish that neither uncertainty-aware scheduling nor quantum treatment of charging is new. Our contribution is a narrowly scoped, reproducible comparison using observed connection durations and explicit simulated requests; it does not establish a new theoretical method.

## 3. Model and implementation

A binary decision `x_t` indicates charging at 1 kW for a 15-minute slot. The assumed service target is 0.25 kWh, or one slot; site capacity is 1 kW. Prices are 1.0 and 0.5 arbitrary currency units per kWh. F0 uses a nominal 30-minute window. F1 averages eight calibration-only scenarios. For a calibration duration `T` in minutes, define `delta=30-T`, then `b_tau=Q_tau(max(0,delta))`. A buffer schedule uses only complete slots ending by `30-b_tau`. The buffer is a hard restriction in exact enumeration; a zero-slot window remains infeasible.

For binary charging variables and nonnegative binary-encoded capacity slack, the toy model penalizes squared service-slot deviation and squared `(load + slack - capacity)` with coefficient 5. Scenario-specific slack is independent for each scenario. These penalties are soft and may fail for other coefficients or instances; a counterexample is tested. The symmetric QUBO `xᵀQx+c` maps to Ising by `x_i=(1-Z_i)/2`. Exhaustive basis-energy tests check the mapping, including its constant. The full two-EV numerical example is in `MATHEMATICAL_WALKTHROUGH.md`; it is a separate educational example, not the data experiment.

## 4. Quantum methodology

The nominal and 90%-buffer four-variable QUBOs are solved by enumeration and QAOA using Qiskit Aer. Hadamards prepare superposition; a diagonal cost evolution imprints phases; X rotations mix states; COBYLA adjusts the variational angles using sampled energies; measurements provide candidate bitstrings. Qubit zero is the rightmost displayed bit. Two qubits are charging decisions and two encode slack. The circuit is simulated, not executed on hardware. QAOA was not run on the scenario formulation in this experiment.

## 5. Data and design

The public dataset [5] provides connection and disconnection timestamps and delivered energy. Its 72,856 downloaded rows contain 13 columns; 547 records with invalid or nonpositive durations and 41 calibration records ending at or after the cutoff are excluded. Of 72,268 remaining records, 50,185 calibrate the methods before July 1, 2022; 22,083 later records evaluate them. Thirteen duplicate full rows are retained. Timestamps are treated as local naive values because their timezone has not been independently established. The nominal duration, target, charging power, capacity and tariffs are assumed; observed connection duration is used to simulate availability under each schedule. These are not reconstructed historical schedules and the declared departure and actual driver demand are unknown.

## 6. Results

| Method | Calibrated buffer | Simulated completion | Mean simulated unmet kWh |
|---|---:|---:|---:|
| F0 nominal | — | 85.01% | 0.0375 |
| F1 scenario | — | 85.01% | 0.0375 |
| Buffer, 80th percentile | 0 min | 85.01% | 0.0375 |
| Buffer, 90th percentile | 7 min | 93.56% | 0.0161 |
| Buffer, 95th percentile | 18 min | 0% | 0.2500 |

The 90th-percentile margin moves charging into the first slot; the 95th-percentile margin eliminates both full slots. The 90% versus F0 paired difference is 8.55 percentage points, with a 95% day-block percentile bootstrap interval of 8.20–8.91 points across 92 days. This interval does not account for a user or charger recurring on different days. Mean simulated realized charging cost rises from 0.1063 to 0.2339 arbitrary currency units. All values are generated from `public_duration_stress.json.gz`.

The nominal QUBO optimum is 0.125. At p=1 and 256 shots, QAOA sampled the optimal state with probability 0.2383 and a physically feasible schedule with probability 0.8672; uniform random sampling gives 0.0625 and 0.75 for these respective measures. The best sampled energy matched the optimum; mean sampled energy was 3.1113. The circuit used four logical qubits and, after transpilation, depth 16 and six CX gates. These are outcomes of one short simulated run.

For the 90% buffer QUBO, the exact optimum is 0.25 and the best sampled energy also matches it. Optimal states occur in 36.72% of 256 shots; 92.97% obey the conservative window and 56.64% both obey it and satisfy the modeled service target. The comparison uses one seed and does not establish a general advantage for either formulation.

## 7. Discussion and limitations

An earlier slot can improve simulated completion because fewer observed connections end before it, at the cost of a higher assumed tariff. Rounding to whole slots can instead make an aggressive buffer unusable. The result does not establish a 90% service guarantee. The data do not contain the modeled request or actual declared deadline, and the study cannot infer what would have happened if real users had received a different schedule. One synthetic EV cannot test competition for shared capacity. The short QAOA runs do not compare the proposed buffer against F1, and are not evidence of quantum advantage. Chronological splitting is useful but the study remains exploratory and day clustering does not eliminate all dependence.

## 8. Conclusion

In a small counterfactual model calibrated with public connection durations, a moderate buffer improved simulated service while an aggressive one made the modeled window infeasible. Stronger evidence requires decision-time requested departures and energy, realistic multi-EV sites, additional exact and quantum comparisons, and independent validation.

## References

1. Z. Wang, P. Jochem and W. Fichtner, “A scenario-based stochastic optimization model for charging scheduling of electric vehicles under uncertainties of vehicle availability and charging demand,” *Journal of Cleaner Production*, vol. 254, 119886, 2020. https://doi.org/10.1016/j.jclepro.2019.119886
2. C. Dalyac et al., “Qualifying quantum approaches for hard industrial optimization problems. A case study in the field of smart-charging of electric vehicles,” *EPJ Quantum Technology*, vol. 8, 12, 2021. https://doi.org/10.1140/epjqt/s40507-021-00100-3
3. S. P. Sone et al., “Robust EV Scheduling in Charging Stations Under Uncertain Demands and Deadlines,” *IEEE Transactions on Intelligent Transportation Systems*, vol. 25, pp. 21484–21499, 2024. https://doi.org/10.1109/TITS.2024.3466514
4. E. Farhi, J. Goldstone and S. Gutmann, “A Quantum Approximate Optimization Algorithm,” arXiv:1411.4028, 2014. https://arxiv.org/abs/1411.4028
5. K. Baek, E. Lee and J. Kim, “A dataset for multi-faceted analysis of electric vehicle charging transactions,” *Scientific Data*, vol. 11, 262, 2024. https://doi.org/10.1038/s41597-024-02942-9
