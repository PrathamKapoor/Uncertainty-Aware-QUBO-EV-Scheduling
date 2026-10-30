# EV scheduling: a code walkthrough with actual examples

This guide follows the revised implementation. It traces real functions and shows the values they produce, so you can open the files alongside the explanation. It is also a presentation script: the **Show** cues tell you what to open for a faculty member. The two-EV example is synthetic; its schedules are not reconstructed historical charging decisions.

## 1. What are we trying to decide?

Imagine a site with two vehicles, A and B. Both need 0.25 kWh. There are two 15-minute slots. Each vehicle charges at 1 kW, but the site permits only 1 kW total. So both vehicles cannot charge at the same time.

Since 15 minutes is 0.25 hours, one vehicle receives `1 kW × 0.25 h = 0.25 kWh` in one complete slot. Both requests can be met if one vehicle charges in each slot.

**Show:** [`build_case()`](../experiments/multi_ev_study.py), then the `EV` and `Instance` classes in [`ev_scheduling.py`](../scheduling/ev_scheduling.py).

```python
EV("a", 0, 1, 1, .25)
EV("b", 0, 1, 1, .25)
Instance("two_ev", [...], 2, 1, 1, [1.0, .5], Delta_min=15)
```

The EV arguments mean identifier, first slot, last slot, power in kW and requested energy in kWh. `T=2`, the site limit is 1 kW, and the assumed tariffs are 1.0 and 0.5 currency units per kWh. Charging in the second slot is cheaper. These are model assumptions, not observed customer requests or real tariffs.

The four charging-decision bits are ordered by EV, then slot:

```text
           A slot 0   A slot 1   B slot 0   B slot 1
x =            0          1          1          0
```

This schedule charges B first and A second. It does not charge both at once. A bitstring can contain additional **slack bits** after these four decisions; those bits represent unused site capacity, not extra charging.

## 2. How do we find exact schedules?

**Show:** [`make_model()` and `solve_methods()`](../experiments/multi_ev_study.py).

The code builds three QUBOs: F0 with nominal availability, F1 with two equally weighted availability scenarios, and a buffered model where A's second slot is unavailable. `exact()` enumerates all QUBO bitstrings and selects the one with minimum energy. The separate `earliest_multi_ev()` heuristic fills slots in time order and breaks ties using the order in which EVs appear in the instance.

Running the code in this checkout gave:

| Method | A slots | B slots | Meaning |
|---|---|---|---|
| F0 | `01` | `10` | B first, A second |
| F1 | `10` | `01` | A first, B second |
| Buffer | `10` | `01` | A first, B second |
| Earliest | `10` | `01` | A first, B second |

**Important:** F0 has another equally optimal nominal solution that also charges A first. The `exact()` function breaks ties using Python tuple ordering. Therefore, the different displayed schedules do not show that F1 or the buffer uniquely improves on every F0 optimum. [`test_multi_ev_comparison.py`](../tests/test_multi_ev_comparison.py) checks that the early allocation is also an F0 optimum.

## 3. Where does the QUBO matrix come from?

**Show:** [`build_revised_qubo()`](../scheduling/revised_qubo.py), especially the nested `square()` function.

The direct objective has three parts: charging cost, a penalty when the number of available charging slots differs from the request, and a capacity penalty. To model the one-sided site limit, the code introduces a nonnegative binary slack value `s[t]`:

```text
load[t] + slack[t] = site capacity
```

If the load is 0 kW, slack can be 1 kW. If the load is 1 kW, slack can be 0. If the load is 2 kW, no nonnegative slack can make the sum equal 1. The implementation squares the difference and multiplies it by `capacity_penalty`.

For this example, there is one slack bit per slot, so the full nominal QUBO order is:

```text
[A0, A1, B0, B1, slack0, slack1]
```

The inner helper expands a squared expression into the symmetric matrix `Q` and a constant `c`:

```python
Q[:] += coefficient * np.outer(v, v)
Q[np.diag_indices(n)] -= 2 * coefficient * target * v
c += coefficient * target ** 2
```

This is the expansion of `coefficient × (v·x − target)²`. A binary bit satisfies `x²=x`, which lets the linear terms go on the diagonal. The result is `xᵀQx+c`. For the F0 solution `(0,1,1,0,0,0)`, exact enumeration returns **0.375**: B's first-slot energy costs `0.25 × 1.0 = 0.25` and A's second-slot energy costs `0.25 × 0.5 = 0.125`. Both energy and capacity penalties are zero.

**Important:** These are soft penalties, not automatically hard constraints. A penalty that is too small can make an infeasible schedule cheaper. [`test_revised_qubo.py`](../tests/test_revised_qubo.py) includes such a counterexample. The QUBO code currently requires integer power units; it is not a general continuous-power model.

## 4. What changes when departure is uncertain?

In the second modeled scenario, A leaves one slot early. A's available mask changes from `3` (`11` in binary: slots 0 and 1 available) to `1` (`01`: only slot 0 available). B stays available for both slots.

**Show:** [`realized_availability_mask()`](../scheduling/ev_scheduling.py) and [`evaluate_schedule()`](../experiments/multi_ev_study.py).

For A's nominal last slot `d_slot=1`, an early shift of 15 minutes and 15-minute slots produces:

```text
last complete slot = 1 − ceil(15 / 15) = 0
```

The revised decoder counts a slot only when the whole slot ends before the realized deadline. If A was scheduled in slot 1, that planned charge is not counted as delivered. If A leaves before any complete slot, the mask can be empty: the code does not invent a feasible slot.

**Show:** [`decode_feasibility()`](../scheduling/ev_scheduling.py). For the F0 schedule `A=01, B=10`:

| Realized availability | A delivered | B delivered | Total unmet | Feasible? |
|---|---:|---:|---:|---|
| Both remain for both slots | 0.25 kWh | 0.25 kWh | 0 | Yes |
| A leaves one slot early | 0 | 0.25 kWh | 0.25 kWh | No |

With `A=10, B=01`, both requests are met in both of these modeled scenarios. The example uses two assumed scenarios; it does not demonstrate that real drivers follow a 50/50 departure distribution.

## 5. How do the scenario and buffer methods differ?

**Show:** [`scenario_qubo_with_recourse()`](../scheduling/revised_qubo.py) and [`solve_methods()`](../experiments/multi_ev_study.py).

F1 uses the same charging decisions across scenarios but has separate capacity-slack bits for each scenario. Conceptually it minimizes

```text
0.5 × objective(schedule, scenario 1, slack 1)
+ 0.5 × objective(schedule, scenario 2, slack 2)
```

The separate slack registers matter because unused capacity can differ by scenario. In this two-slot example, F0 has four decision bits plus two slack bits; F1 has four decision bits plus four scenario-specific slack bits.

The buffer approach instead restricts the allowed window before solving. In the public-duration study, [`reliability_buffer_minutes()`](../experiments/revised_experiment.py) calculates a quantile of `max(0, 30 − connection_duration)`. A seven-minute buffer moves the modeled deadline from 30 minutes to 23 minutes. Because only a complete 15-minute slot counts, only the first slot remains available.

In that single-EV study, [`earliest_feasible_schedule()`](../experiments/revised_experiment.py) chooses exactly the same first-slot schedule as the 90th-percentile buffer. Both produce **93.56% simulated completion**, compared with **85.01%** for the later-slot F0 schedule. This is not a measured improvement for the original drivers: the 30-minute deadline, 0.25 kWh target, power and tariffs are simulated. At the 95th-percentile buffer, neither complete slot remains, so the model cannot deliver its target.

## 6. How does the matrix become a quantum problem?

**Show:** [`qubo_to_ising()`](../quantum/qaoa.py) and [`test_ising_energies_and_qiskit_basis_order()`](../tests/test_revised_qubo.py).

Each QUBO bit maps to one qubit in this implementation. The conversion uses `xᵢ = (1 − Zᵢ)/2`: a computational-basis measurement of 0 corresponds to `xᵢ=0`, and a measurement of 1 corresponds to `xᵢ=1`.

The resulting cost Hamiltonian contains single-qubit Z terms, two-qubit ZZ terms and a constant offset. The offset is omitted from the circuit operator because it adds the same global phase to every state; it must be restored when comparing numerical energies. The tests enumerate small bitstrings and compare the QUBO and Ising energies, including that offset. For the two-EV F0 model there are six qubits: four charging decisions and two slack bits. The two-scenario F1 model has eight, because it uses four slack bits.

## 7. What does QAOA actually execute?

**Show:** [`_build_qaoa_ansatz()`](../quantum/qaoa.py) and [`run_qaoa()`](../quantum/qaoa.py).

1. Apply a Hadamard gate to every qubit to prepare a superposition.
2. Apply the cost evolution, which adds energy-dependent phases.
3. Apply X rotations as the mixer, which can move amplitude among bitstrings.
4. Repeat the cost and mixer layers `p` times.
5. Measure the qubits. The classical optimizer COBYLA adjusts the circuit angles using sampled circuit energies.

COBYLA optimizes **circuit parameters**; it is not the exact enumerator. Repeated measurements produce a distribution of bitstrings. `run_qaoa()` reverses Qiskit's displayed string because the rightmost displayed bit is qubit 0. It then evaluates the decoded binary vector against the QUBO and Ising model.

For example, a displayed six-bit string `000110` reverses to `011000` in variable order. The first four bits represent A=`01`, B=`10`; the last two are slack `00`. That is the nominal F0 schedule above. This is an interpretation example, not a claim that a particular run measured that string.

The multi-EV artifact records five seeds each at p=1 and p=2, with 128 final shots per run. For F0 at p=1, mean optimal-state sampling was **9.38%** across seeds; mean nominal physical-feasibility sampling was **22.81%**. Those are different questions: a physically feasible schedule can have nonoptimal cost or slack bits. Neither number is a probability that a real driver will receive a charge. Aer is a classical simulator, not quantum hardware, and these results do not establish quantum advantage.

## 8. Where do the public records enter?

**Show:** [`prepare_sessions()`](../experiments/public_dataset.py) and [`run_experiment()`](../experiments/revised_experiment.py).

The public dataset contains connection and disconnection timestamps and delivered energy. It does not provide the observed declared-departure and requested-energy fields needed to validate that particular forecasting problem. The code calculates connection duration from timestamps, excludes invalid or nonpositive durations and excludes calibration sessions ending across the evaluation split. It fits calibration scenarios and buffers before evaluating the later records.

The final experiment used 50,185 calibration and 22,083 evaluation records. Each observed connection duration is applied to the same synthetic scheduling instance; these are **counterfactual model evaluations**, not reconstructed fleet schedules. [`day_block_interval()`](../experiments/public_dataset.py) resamples calendar days for a paired comparison. Its interval does not by itself remove dependence from repeat users or chargers on different days.

## 9. Run and inspect the example

From the repository root:

```powershell
python -m pytest tests/test_revised_qubo.py tests/test_multi_ev_comparison.py -q
python -m experiments.multi_ev_study
```

The first command checks small-instance equivalence and the binding-capacity example. The second runs the multi-seed simulator experiment and writes [`multi_ev_comparison.json`](../artifacts/revised_v2/multi_ev_comparison.json). It can take longer than the tests. To inspect the earlier public-data comparison, see [`earliest_baseline.json.gz`](../artifacts/revised_v2/earliest_baseline.json.gz) and [`DATASET_VALIDATION.md`](DATASET_VALIDATION.md). Re-running the public-data experiment requires the documented source CSV in `data/ChargingRecords.csv`.

## 10. A concise viva explanation

“We represent each possible EV-slot charge as a binary decision and add slack bits to represent unused site capacity. The code converts charging cost and penalty terms into a QUBO, maps it to an Ising Hamiltonian, and evaluates small instances both by exact enumeration and by a QAOA circuit on Qiskit Aer. We then decode schedules and test whether energy arrived before the modeled departure while respecting capacity. Our real-data study uses observed connection durations but simulated requests and tariffs. An earlier buffer improved the result relative to the cost-oriented baseline, but the simplest earliest-slot policy matched it; in the two-EV illustration, an equally optimal nominal tie also matches the early allocation. These results show why baseline choice and tie-breaking matter, not that QAOA has a quantum advantage.”
