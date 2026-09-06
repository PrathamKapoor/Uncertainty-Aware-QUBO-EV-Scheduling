"""Stage 5 acquisition validation: run ONLY load_real_uncertainty, print
sanitized aggregate counts. No tokens, URLs-with-params, or raw records."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stage5.uncertainty import load_real_uncertainty  # noqa: E402


def main() -> None:
    samples, status = load_real_uncertainty()
    joint_cal = sum(1 for s in samples if s.calibration and s.delta_e_kwh is not None and s.delta_d_minutes is not None)
    joint_ho = sum(1 for s in samples if not s.calibration and s.delta_e_kwh is not None and s.delta_d_minutes is not None)
    out = {
        "source": status.get("source"),
        "http_pages_requested": status.get("n_pages"),
        "records_received": status.get("n_records"),
        "samples_returned": len(samples),
        "records_calibration": sum(1 for s in samples if s.calibration),
        "records_held_out": sum(1 for s in samples if not s.calibration),
        "userInputs_null": status.get("n_user_inputs_null"),
        "userInputs_empty": status.get("n_user_inputs_empty"),
        "userInputs_nonempty": status.get("n_user_inputs_nonempty"),
        "n_skipped_schema": status.get("n_skipped_schema"),
        "n_skipped_window": status.get("n_skipped_window"),
        "n_parseable_conn": status.get("n_parseable_conn"),
        "n_parseable_disc": status.get("n_parseable_disc"),
        "n_with_kwh_delivered": status.get("n_with_kwh_delivered"),
        "n_with_kwh_requested": status.get("n_with_kwh_requested"),
        "n_with_requested_departure": status.get("n_with_requested_departure"),
        "n_valid_dE": status.get("n_valid_dE"),
        "n_valid_dd": status.get("n_valid_dd"),
        "n_valid_joint": status.get("n_valid_joint"),
        "calibration_joint_samples": joint_cal,
        "held_out_joint_samples": joint_ho,
        "http_status_codes": status.get("http_status_codes"),
        "schema_warning_count": status.get("schema_warning_count"),
        "config_sha256": hashlib.sha256(
            Path("artifacts/final_experiment_config.json").read_bytes()
        ).hexdigest(),
    }
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
