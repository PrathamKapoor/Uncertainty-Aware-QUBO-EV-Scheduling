from experiments.multi_ev_study import build_case, solve_methods, evaluate_schedule
from experiments.multi_ev_study import exact, earliest_multi_ev
from itertools import product
import numpy as np


def test_shared_capacity_binds_and_schedules_are_physically_consistent():
    case = build_case()
    results = solve_methods(case)
    assert not evaluate_schedule(case, (1, 0, 1, 0), (3, 3))["site_feasible"]
    for result in results.values():
        assert evaluate_schedule(case, result["decisions"], (3, 3))["site_feasible"]
    assert results["F0"]["decisions"] != results["F1"]["decisions"]
    assert results["F_early"]["decisions"] == results["F_buffer"]["decisions"]
    nominal = results["F0"]["qubo"]
    opt = exact(nominal)[0]
    assert any(tuple(bits[:4]) == results["F_early"]["decisions"] and abs(nominal.evaluate(np.array(bits)) - opt) < 1e-9
               for bits in product((0, 1), repeat=nominal.n()))
    assert earliest_multi_ev(case) == (1, 0, 0, 1)
