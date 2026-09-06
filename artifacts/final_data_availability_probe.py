"""One bounded, credential-safe ACN behavioral-data availability probe.

This is diagnostic/reproducibility infrastructure only. It does not modify the
scientific pipeline, write raw data, or emit record-level values.
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

ROOT = "https://ev.caltech.edu/api/v1/sessions"
PAGE_SIZE = 10
PAGES = (1, 2)
CAL_START = datetime(2018, 5, 1, tzinfo=timezone.utc)
CAL_END = datetime(2019, 7, 1, tzinfo=timezone.utc)
HO_START = datetime(2019, 7, 1, tzinfo=timezone.utc)
HO_END = datetime(2020, 1, 1, tzinfo=timezone.utc)
RFC1123 = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} "
    r"\d{2}:\d{2}:\d{2} (GMT|UT|UTC|EST|EDT|CST|CDT|MST|MDT|PST|PDT|Z)$"
)

# Six bounded strata across the already-frozen windows. Values stay local to
# request construction and are never included in output.
STRATA = (
    ("early_calibration", "Tue, 01 May 2018 00:00:00 GMT", "Sun, 15 Jul 2018 00:00:00 GMT"),
    ("middle_calibration", "Thu, 01 Nov 2018 00:00:00 GMT", "Tue, 15 Jan 2019 00:00:00 GMT"),
    ("late_calibration", "Wed, 01 May 2019 00:00:00 GMT", "Mon, 01 Jul 2019 00:00:00 GMT"),
    ("early_held_out", "Mon, 01 Jul 2019 00:00:00 GMT", "Sun, 01 Sep 2019 00:00:00 GMT"),
    ("middle_held_out", "Sun, 15 Sep 2019 00:00:00 GMT", "Fri, 01 Nov 2019 00:00:00 GMT"),
    ("late_held_out", "Fri, 15 Nov 2019 00:00:00 GMT", "Wed, 01 Jan 2020 00:00:00 GMT"),
)


def parse_timestamp(value: Any) -> datetime:
    """Strictly parse supported ACN timestamp forms without value logging."""
    if not isinstance(value, str) or not value:
        raise ValueError("invalid timestamp")
    if RFC1123.match(value):
        result = parsedate_to_datetime(value)
        if result.tzinfo is None:
            raise ValueError("timestamp has no timezone")
        return result.astimezone(timezone.utc)
    if value.endswith("Z"):
        return datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("_items", "items", "sessions", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return candidate
    return []


def _latest_input(user_inputs: Any) -> Any:
    if isinstance(user_inputs, dict):
        return user_inputs
    if not isinstance(user_inputs, list) or not user_inputs:
        return None
    entries = [entry for entry in user_inputs if isinstance(entry, dict)]
    if not entries:
        return None
    return sorted(entries, key=lambda entry: str(entry.get("modifiedAt") or entry.get("createdAt") or ""))[-1]


def _is_numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def summarize_items(items: list[Any]) -> dict[str, int]:
    """Return aggregate-only behavioral and temporal availability counts."""
    counts = {
        "n_records": 0, "n_userInputs_null": 0, "n_userInputs_nonnull": 0, "n_userInputs_empty": 0,
        "n_userInputs_nonempty": 0, "n_kWhRequested_any": 0,
        "n_requestedDeparture_any": 0, "n_kWhRequested_latest": 0,
        "n_requestedDeparture_latest": 0, "n_modifiedAt_any": 0,
        "n_createdAt_any": 0, "n_modifiedAt_latest": 0,
        "n_createdAt_latest": 0, "n_both_any": 0, "n_both_latest": 0,
        "n_valid_DeltaE": 0, "n_valid_Deltad": 0,
        "n_valid_joint_behavioral_records": 0,
        "n_calibration_joint_samples": 0, "n_held_out_joint_samples": 0,
        "n_connectionTime_parseable": 0, "n_in_calibration_window": 0,
        "n_in_held_out_window": 0, "n_passing_frozen_temporal_window": 0,
    }
    for record in items:
        counts["n_records"] += 1
        if not isinstance(record, dict):
            continue
        ui = record.get("userInputs")
        if ui is None:
            counts["n_userInputs_null"] += 1
        else:
            counts["n_userInputs_nonnull"] += 1
        if isinstance(ui, list) and not ui:
            counts["n_userInputs_empty"] += 1
        elif isinstance(ui, (list, dict)):
            counts["n_userInputs_nonempty"] += 1
        entries = [ui] if isinstance(ui, dict) else (ui if isinstance(ui, list) else [])
        dict_entries = [entry for entry in entries if isinstance(entry, dict)]
        any_kwh = any("kWhRequested" in entry for entry in dict_entries)
        any_dep = any("requestedDeparture" in entry for entry in dict_entries)
        if any_kwh: counts["n_kWhRequested_any"] += 1
        if any_dep: counts["n_requestedDeparture_any"] += 1
        if any("modifiedAt" in entry for entry in dict_entries): counts["n_modifiedAt_any"] += 1
        if any("createdAt" in entry for entry in dict_entries): counts["n_createdAt_any"] += 1
        if any_kwh and any_dep: counts["n_both_any"] += 1
        latest = _latest_input(ui)
        latest_kwh = isinstance(latest, dict) and "kWhRequested" in latest
        latest_dep = isinstance(latest, dict) and "requestedDeparture" in latest
        if latest_kwh: counts["n_kWhRequested_latest"] += 1
        if latest_dep: counts["n_requestedDeparture_latest"] += 1
        if isinstance(latest, dict) and "modifiedAt" in latest: counts["n_modifiedAt_latest"] += 1
        if isinstance(latest, dict) and "createdAt" in latest: counts["n_createdAt_latest"] += 1
        if latest_kwh and latest_dep: counts["n_both_latest"] += 1
        in_calibration = False
        in_held_out = False
        try:
            connection = parse_timestamp(record.get("connectionTime"))
            counts["n_connectionTime_parseable"] += 1
            if CAL_START <= connection < CAL_END:
                in_calibration = True
                counts["n_in_calibration_window"] += 1
                counts["n_passing_frozen_temporal_window"] += 1
            elif HO_START <= connection < HO_END:
                in_held_out = True
                counts["n_in_held_out_window"] += 1
                counts["n_passing_frozen_temporal_window"] += 1
        except Exception:
            pass
        valid_de = latest_kwh and _is_numeric(record.get("kWhDelivered")) and _is_numeric(latest.get("kWhRequested"))
        valid_dd = False
        if latest_dep:
            try:
                parse_timestamp(latest.get("requestedDeparture"))
                parse_timestamp(record.get("disconnectTime"))
                valid_dd = True
            except Exception:
                pass
        if valid_de: counts["n_valid_DeltaE"] += 1
        if valid_dd: counts["n_valid_Deltad"] += 1
        if valid_de and valid_dd:
            counts["n_valid_joint_behavioral_records"] += 1
            if in_calibration:
                counts["n_calibration_joint_samples"] += 1
            elif in_held_out:
                counts["n_held_out_joint_samples"] += 1
    return counts


def _fetch(token: str, site: str, params: dict[str, Any]) -> dict[str, Any]:
    """Fetch one page and return sanitised structure only."""
    url = ROOT + "/" + site + "?" + urllib.parse.urlencode(params, safe='><=')
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    request.add_header("Authorization", "Basic " + base64.b64encode((token + ":").encode()).decode())
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl.create_default_context()) as response:
            status = int(getattr(response, "status", 200))
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return {"http_status": int(error.code), "error_class": "HTTPError"}
    except urllib.error.URLError:
        return {"http_status": None, "error_class": "URLError"}
    except TimeoutError:
        return {"http_status": None, "error_class": "TimeoutError"}
    except Exception as error:
        return {"http_status": None, "error_class": type(error).__name__}
    result = {
        "http_status": status,
        "payload_top_level_type": type(payload).__name__,
        "wrapper_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
    }
    result.update(summarize_items(_items(payload)))
    return result


def run() -> dict[str, Any]:
    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    output: dict[str, Any] = {
        "probe": "final_caltech_behavioral_data_availability",
        "authentication": {"credential_available": bool(token)},
        "raw_data_written": False,
        "caltech_pages": [], "ts": {}, "other_sites": {},
        "portal_export": {
            "documented_web_json_export": True,
            "programmatic_export_endpoint_documented": False,
            "programmatic_export_tested": False,
        },
    }
    if not token:
        output["status"] = "credential_unavailable_in_runtime"
        return output
    for label, start, end in STRATA:
        where = f'connectionTime>="{start}" and connectionTime<"{end}"'
        for page in PAGES:
            result = _fetch(token, "caltech", {"where": where, "page": page, "max_results": PAGE_SIZE})
            result["stratum"] = label
            result["page"] = page
            output["caltech_pages"].append(result)
    total = {key: 0 for key in summarize_items([])}
    for page in output["caltech_pages"]:
        for key in total:
            total[key] += int(page.get(key, 0) or 0)
    output["caltech_aggregate"] = total
    output["ts"] = _fetch(token, "caltech/ts", {"page": 1})
    output["other_sites"] = {
        "jpl": _fetch(token, "jpl", {"page": 1, "max_results": 1}),
        "office001": _fetch(token, "office001", {"page": 1, "max_results": 1}),
    }
    output["status"] = "completed"
    return output


if __name__ == "__main__":
    try:
        print(json.dumps(run(), sort_keys=True, separators=(",", ":")))
    except Exception as error:
        # Exactly one sanitized JSON object, even for unexpected failures.
        print(json.dumps({"status": "unexpected_error", "error_class": type(error).__name__}, separators=(",", ":")))
