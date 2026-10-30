from itertools import product

import numpy as np
import pytest

from scheduling.revised_qubo import build_revised_qubo, physical_objective, average_scenario_qubos, scenario_qubo_with_recourse
from quantum.qaoa import qubo_to_ising


def test_qubo_matches_objective_and_one_sided_capacity():
    model = build_revised_qubo([1, 1], [1, 1], [3, 3], 1, [0.5, 1], 1, 5, 5)
    for bits in product((0, 1), repeat=model.n):
        x = np.array(bits)
        assert x @ model.Q @ x + model.c == pytest.approx(physical_objective(model, x))
    # One EV charging under the limit requires no capacity penalty.
    assert physical_objective(model, np.array([1, 0, 0, 1, 0, 0])) == pytest.approx(1.5)


def test_ising_energies_and_qiskit_basis_order():
    model = build_revised_qubo([1, 1], [1, 1], [3, 3], 1, [0.5, 1], 1, 5, 5)
    ising = qubo_to_ising(model.Q, model.c, {(0, i): i for i in range(model.n)})
    diagonal = np.real(np.diag(ising.to_qiskit_op().to_matrix())) + ising.offset
    for bits in product((0, 1), repeat=model.n):
        x = np.array(bits)
        energy = x @ model.Q @ x + model.c
        assert ising.evaluate(1 - 2 * x) == pytest.approx(energy)
        index = sum(bit << i for i, bit in enumerate(bits))
        assert diagonal[index] == pytest.approx(energy)


def test_slack_minimization_is_one_sided_for_binding_capacity():
    model = build_revised_qubo([1, 1], [0, 0], [1, 1], 1, [0], 1, 0, 5)
    for decisions in product((0, 1), repeat=2):
        energies = [physical_objective(model, np.array((*decisions, slack))) for slack in (0, 1)]
        assert min(energies) == pytest.approx(5 * max(0, sum(decisions) - 1) ** 2)


def test_scenario_late_charging_does_not_satisfy_energy():
    model = build_revised_qubo([1], [1], [1], 1, [0, 0], 1, 5, 5)
    # Charge only in slot 1, after the actual departure; slack in slot 0.
    bits = np.array([0, 1, 1, 1])
    assert physical_objective(model, bits) == pytest.approx(10)
    assert bits @ model.Q @ bits + model.c == pytest.approx(10)


def test_scenario_weight_modes_and_validation():
    a = build_revised_qubo([1], [1], [3], 1, [0, 0], 1, 5, 5)
    b = build_revised_qubo([1], [1], [1], 1, [0, 0], 1, 5, 5)
    uniform = average_scenario_qubos([a, b], [9, 1], "uniform")
    empirical = average_scenario_qubos([a, b], [9, 1], "empirical")
    assert np.allclose(uniform.Q, (a.Q + b.Q) / 2)
    assert np.allclose(empirical.Q, 0.9 * a.Q + 0.1 * b.Q)
    with pytest.raises(ValueError):
        average_scenario_qubos([a, b], [0, 0], "empirical")


def test_scenario_specific_slack_matches_independent_recourse():
    a = build_revised_qubo([1], [1], [3], 1, [0, 0], 1, 5, 5)
    b = build_revised_qubo([1], [1], [1], 1, [0, 0], 1, 5, 5)
    q = scenario_qubo_with_recourse([a, b], [1, 1], "uniform")
    for decisions in product((0, 1), repeat=2):
        direct = sum(min(physical_objective(m, np.array((*decisions, *s)))
                         for s in product((0, 1), repeat=2)) / 2 for m in (a, b))
        encoded = min(q.evaluate(np.array((*decisions, *s))) for s in product((0, 1), repeat=4))
        assert encoded == pytest.approx(direct)


def test_insufficient_penalty_can_produce_infeasible_optimum():
    model = build_revised_qubo([1], [1], [1], 1, [10], 1, 0.1, 1)
    best = min(product((0, 1), repeat=model.n), key=lambda bits: physical_objective(model, bits))
    assert best[0] == 0


def test_uncertain_departure_does_not_penalize_planned_command_itself():
    model = build_revised_qubo([1], [1], [0], 1, [0], 1, 5, 5,
                               penalize_unavailable=False)
    # Both schedules leave the request unmet after the vehicle has departed.
    assert physical_objective(model, np.array([0, 1])) == pytest.approx(5)
    assert physical_objective(model, np.array([1, 1])) == pytest.approx(5)
