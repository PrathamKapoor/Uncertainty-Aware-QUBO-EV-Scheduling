import pandas as pd
from experiments.public_dataset import prepare_sessions, day_block_interval


def test_dataset_uses_chronological_split_and_excludes_invalid_duration():
    frame = pd.DataFrame({"StartDatetime": ["2022-01-01", "2022-07-01", "2022-08-01"],
                          "EndDatetime": ["2022-01-01 00:20", "2022-07-01 00:10", "2022-07-31 23:00"]})
    samples, counts = prepare_sessions(frame)
    assert counts["invalid_duration"] == 1
    assert [s.calibration for s in samples] == [True, False]
    assert [s.delta_d_minutes for s in samples] == [10, 20]


def test_block_interval_resamples_days_and_preserves_pairs():
    result = day_block_interval([1, 0, 1], [0, 0, 1], ["a", "a", "b"], seed=2, repetitions=100)
    assert result["n_days"] == 2
    assert result["n_sessions"] == 3
    assert result["difference"] == 1 / 3


def test_calibration_excludes_sessions_finishing_after_split():
    frame = pd.DataFrame({"StartDatetime": ["2022-06-30 23:45", "2022-07-01 01:00"],
                          "EndDatetime": ["2022-07-01 00:10", "2022-07-01 01:20"]})
    samples, counts = prepare_sessions(frame)
    assert counts["calibration_crossing_split"] == 1
    assert len(samples) == 1 and not samples[0].calibration
