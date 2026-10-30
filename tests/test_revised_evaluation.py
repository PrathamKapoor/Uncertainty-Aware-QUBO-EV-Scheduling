from types import SimpleNamespace

import pytest

from scheduling.ev_scheduling import EV, Instance
from experiments.real_experiment import evaluate_departures_v2, paired_records_v2


def test_eligible_records_and_unconditional_shortfall():
    inst = Instance("test", [EV("e", 0, 1, 4, 1)], 2, 4, 4, [1, 1])
    sched = {(0, 0): 0, (0, 1): 1}
    samples = [SimpleNamespace(session_id="a", delta_d_minutes=0),
               SimpleNamespace(session_id="missing", delta_d_minutes=None),
               SimpleNamespace(session_id="b", delta_d_minutes=15)]
    result = evaluate_departures_v2(inst, sched, samples, target_ev_id="e")
    assert [r["session_id"] for r in result["records"]] == ["a", "b"]
    assert result["excluded"] == 1
    assert result["mean_unmet_kWh"] == pytest.approx(0.5)
    assert result["mean_unmet_given_shortfall_kWh"] == pytest.approx(1)
    assert result["deadline_violation_rate"] == pytest.approx(0.5)
    assert result["site_violation_rate"] == 0
    assert result["mean_cost"] == pytest.approx(0.5)
    assert result["records"][0]["cost"] == pytest.approx(1)
    assert result["feasibility_rate"] == pytest.approx(0.5)


def test_multi_ev_requires_explicit_target():
    inst = Instance("test", [EV("a", 0, 1, 4, 1), EV("b", 0, 1, 4, 1)], 2, 8, 4, [1, 1])
    with pytest.raises(ValueError):
        evaluate_departures_v2(inst, {}, [], target_ev_id="unknown")


def test_paired_comparison_requires_matching_records_and_adjusts_interval():
    a = [{"session_id": "a", "feasible": True}, {"session_id": "b", "feasible": False}]
    b = [{"session_id": "a", "feasible": False}, {"session_id": "b", "feasible": False}]
    result = paired_records_v2(a, b, n_boot=100, seed=0, comparisons=3)
    assert result["n"] == 2
    assert result["diff_mean"] == pytest.approx(0.5)
    assert result["ci_level"] == pytest.approx(1 - 0.05 / 3)
    with pytest.raises(ValueError):
        paired_records_v2(a, b[::-1], n_boot=100, seed=0, comparisons=3)
