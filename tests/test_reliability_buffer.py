import pytest
from experiments.revised_experiment import reliability_buffer_minutes, buffered_schedule


def test_buffer_uses_calibration_quantile_and_ignores_late_departures():
    assert reliability_buffer_minutes([-15, 0, 15, 30], 0.75) == pytest.approx(18.75)


def test_buffer_schedule_and_impossible_window():
    assert buffered_schedule(15) == (1, 0)
    assert buffered_schedule(30) == (0, 0)


def test_reliability_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        reliability_buffer_minutes([], 0.9)
    with pytest.raises(ValueError):
        reliability_buffer_minutes([1], 1.1)
