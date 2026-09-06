"""Safety and aggregation tests for the final credential-safe probe."""
import json
from pathlib import Path
import subprocess
import sys

from artifacts.final_data_availability_probe import summarize_items


def test_no_credential_run_emits_one_sanitized_json_object():
    script = Path(__file__).with_name("final_data_availability_probe.py")
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["authentication"]["credential_available"] is False
    assert "token" not in result.stdout.lower()


def test_summary_counts_latest_and_any_user_input_fields_without_values():
    items = [{
        "sessionID": "synthetic-session",
        "connectionTime": "Wed, 01 May 2019 00:00:00 GMT",
        "disconnectTime": "Wed, 01 May 2019 01:00:00 GMT",
        "kWhDelivered": 1.0,
        "userInputs": [
            {"kWhRequested": 2.0, "requestedDeparture": "Wed, 01 May 2019 02:00:00 GMT", "modifiedAt": "Wed, 01 May 2019 00:00:00 GMT"}
        ],
    }]
    summary = summarize_items(items)
    assert summary["n_userInputs_nonnull"] == 1
    assert summary["n_userInputs_nonempty"] == 1
    assert summary["n_kWhRequested_any"] == 1
    assert summary["n_requestedDeparture_latest"] == 1
    assert summary["n_modifiedAt_any"] == 1
    assert summary["n_modifiedAt_latest"] == 1
    assert summary["n_createdAt_latest"] == 0
    assert summary["n_valid_joint_behavioral_records"] == 1
    assert summary["n_calibration_joint_samples"] == 1
