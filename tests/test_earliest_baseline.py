from experiments.revised_experiment import earliest_feasible_schedule


def test_earliest_schedule_uses_first_available_slot():
    assert earliest_feasible_schedule([True, True], 1) == (1, 0)
    assert earliest_feasible_schedule([False, True], 1) == (0, 1)


def test_earliest_schedule_exposes_unmet_energy_when_window_too_short():
    assert earliest_feasible_schedule([False, False], 1) == (0, 0)
    assert earliest_feasible_schedule([True, False], 2) == (1, 0)
