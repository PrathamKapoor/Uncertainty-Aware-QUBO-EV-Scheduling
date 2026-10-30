from types import SimpleNamespace

from experiments.revised_experiment import run_experiment


def sample(session_id, calibration, shift):
    return SimpleNamespace(session_id=session_id, calibration=calibration,
                           delta_d_minutes=shift)


def test_pipeline_uses_calibration_only_and_aligned_valid_records():
    samples = [sample("c1", True, 15), sample("c2", True, 15),
               sample("a", False, 0), sample("b", False, 15),
               sample("missing", False, None)]
    result = run_experiment(samples, scenario_count=2, shots=32, maxiter=4)
    assert result["counts"]["evaluation_eligible"] == 2
    assert result["scenarios"]["centers_minutes"] == [15.0, 15.0]
    assert result["methods"]["F0"]["schedule"] != result["methods"]["F1"]["schedule"]
    for method in ("F0", "F1"):
        records = result["methods"][method]["evaluation"]["records"]
        assert [r["session_id"] for r in records] == ["a", "b"]
        assert result["methods"][method]["evaluation"]["mean_unmet_kWh"] == sum(r["unmet_kWh"] for r in records) / 2
    assert result["paired_F1_minus_F0"]["n"] == 2
    assert result["quantum"]["shots_observed"] == 32
    assert result["quantum_buffer_90"]["shots_observed"] == 32
    assert result["quantum_buffer_90"]["best_sampled_gap"] >= 0
