"""Regression test for diagnostic-only RFC-1123 timestamp handling."""
from datetime import timezone
from pathlib import Path
import subprocess
import sys

from artifacts.diag_real_uncertainty_pipeline import _parse_diagnostic_timestamp


def test_rfc1123_timestamp_is_accepted_for_window_classification():
    parsed = _parse_diagnostic_timestamp("Wed, 25 Apr 2018 11:08:04 GMT")
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


def test_diagnostic_runs_by_documented_file_path_without_a_credential():
    script = Path(__file__).with_name("diag_real_uncertainty_pipeline.py")
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
