# Literature and novelty review

The current contribution is an **exploratory comparison**, not an original quantum algorithm or a claim that deadline buffers are new. The search below is focused rather than exhaustive; an external novelty claim would require a broader systematic review.

| Verified source | Problem, method and uncertainty | Evidence / relevant distinction |
|---|---|---|
| [Wang, Jochem and Fichtner, 2020, J. Cleaner Production 254, 119886](https://doi.org/10.1016/j.jclepro.2019.119886) | Two-stage stochastic linear programming with scenarios for EV availability and charging demand. | Monte Carlo usage simulation; not a QAOA comparison. Scenario-based EV scheduling is already established. |
| [Dalyac et al., 2021, EPJ Quantum Technology 8, 12](https://doi.org/10.1140/epjqt/s40507-021-00100-3) | Quantum approaches to industrial smart-charging combinatorial optimization. | Demonstrates earlier quantum work on EV charging; it is not evidence that this project has a speedup. |
| [Sone et al., 2024, IEEE Transactions on Intelligent Transportation Systems 25, 21484–21499](https://doi.org/10.1109/TITS.2024.3466514) | Robust scheduling under uncertain demands and deadlines, compared with a MILP baseline. | Deadline uncertainty and robustness are not new; differs from our single-EV, simulated-request stress test. |
| [Farhi, Goldstone and Gutmann, 2014](https://arxiv.org/abs/1411.4028) | Introduces QAOA for combinatorial optimization. | Provides the quantum algorithm used here; no new QAOA algorithm is claimed. |
| [Glover, Kochenberger and Du, QUBO tutorial](https://arxiv.org/abs/1811.11538) | General QUBO modeling, including standard penalty and constraint-encoding techniques. | Slack bits and penalties are established techniques; the project verifies a small encoding rather than inventing one. |
| [Baek, Lee and Kim, 2024, Scientific Data 11, 262](https://doi.org/10.1038/s41597-024-02942-9) | Public South Korean charging transactions, including connection timestamps and delivered energy. | This data paper supplies observed durations, not declared departures or requested energy. Our service targets are simulated. |

The potentially useful question is how quantile-based early completion changes simulated service, cost and QUBO resources under controlled assumptions, relative to nominal and scenario schedules. The present empirical run addresses only a fixed single-EV toy instance and QAOA only for F0. It does not establish superiority for multi-EV fleets, live scheduling, or quantum advantage.
