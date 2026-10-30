import pytest

from scheduling.ev_scheduling import EV, Instance, decode_feasibility, realized_availability_mask


@pytest.mark.parametrize("shift, expected", [(0, 1.0), (15, 0.0), (30, 0.0), (-15, 1.0), (60, 0.0)])
def test_realized_departure_excludes_late_charging(shift, expected):
    instance = Instance("departure", [EV("e", 0, 3, 4, 1)], 4, 4, 4, [1] * 4)
    schedule = {(0, t): int(t == 3) for t in range(4)}
    result = decode_feasibility(instance, schedule, realized_early_minutes={"e": shift})
    assert result["per_ev"][0]["e_delivered_kWh"] == expected
    assert result["feasible"] == bool(expected)


def test_full_slot_ending_at_deadline_is_delivered():
    instance = Instance("boundary", [EV("e", 0, 3, 4, 1)], 4, 4, 4, [1] * 4)
    schedule = {(0, t): int(t == 2) for t in range(4)}
    assert decode_feasibility(instance, schedule, realized_early_minutes={"e": 15})["feasible"]


def test_nonstandard_slot_duration_and_tariff_units():
    instance = Instance("units", [EV("e", 0, 0, 4, 2)], 1, 4, 4, [0.5], Delta_min=30)
    result = decode_feasibility(instance, {(0, 0): 1}, realized_early_minutes={})
    assert result["feasible"]
    assert result["cost"] == pytest.approx(1)


def test_partial_slot_and_per_ev_shifts():
    instance = Instance("independent", [EV("a", 0, 1, 4, 1), EV("b", 0, 1, 4, 1)],
                        2, 8, 8, [1, 1])
    schedule = {(i, t): int(t == 1) for i in range(2) for t in range(2)}
    result = decode_feasibility(instance, schedule, realized_early_minutes={"a": 0.1})
    assert [ev["e_delivered_kWh"] for ev in result["per_ev"]] == [0, 1]


def test_mask_agrees_with_decoder_and_preserves_empty_window():
    ev = EV("e", 1, 3, 4, 1)
    assert realized_availability_mask(ev, 15, 15) == 0b0110
    assert realized_availability_mask(ev, 45, 15) == 0
    assert realized_availability_mask(ev, -30, 15) == 0b1110
