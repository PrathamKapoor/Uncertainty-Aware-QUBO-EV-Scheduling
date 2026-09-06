"""Credential-safe loader-path diagnostic probe.

This script is INTENDED TO BE RUN BY THE USER in their PowerShell session
where ACN_API_TOKEN is set. It performs the minimum authenticated request
needed to determine why stage5.uncertainty.load_real_uncertainty returns
zero samples in the user's environment.

PRIVACY GUARANTEES (the script enforces them at runtime):

  * The token value is read from os.environ by Python itself, never by the
    agent. The script does NOT print the token, its length, its hash, its
    prefix, its suffix, or any header that contains it.
  * No Authorization header value is printed. The script does not log the
    request URL with credentials embedded; the URL is just a public API path.
  * No individual session record is printed. Aggregate counts only.
  * Field-name introspection is name+type only, never values.
  * The script writes nothing to disk. Output is JSON to stdout only.

USAGE (PowerShell, from repo root):

    PS> python artifacts/diag_loader_path.py

It will print a single JSON object to stdout. Paste that JSON back to the
agent. The script does not need the token to be visible to anything except
the Python interpreter that runs it.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# Public endpoint path. The query string carries NO credentials.
ENDPOINT = "https://ev.caltech.edu/api/v1/sessions/caltech?page=1&max_results=5"
TIMEOUT_S = 20.0


def _field_type_summary(v: Any) -> str:
    """Return a sanitized type tag for a value. Never include the value."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        if len(v) == 0:
            return "str_empty"
        # Try to identify ISO-8601 timestamps without exposing the value.
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return "iso8601_str"
        except Exception:
            pass
        return f"str_len_{len(v)}"
    if isinstance(v, list):
        return f"list_len_{len(v)}"
    if isinstance(v, dict):
        return f"dict_keys_{len(v)}"
    return type(v).__name__


def _summarize_record_keys(rec: Any) -> Dict[str, Any]:
    """Return top-level field names + sanitized type tags. No values."""
    if not isinstance(rec, dict):
        return {"_record_type": type(rec).__name__}
    out: Dict[str, Any] = {}
    for k, v in rec.items():
        out[k] = _field_type_summary(v)
    return out


def _summarize_user_inputs(user_inputs: Any) -> Dict[str, Any]:
    """Inspect userInputs structure (names only, no values)."""
    if not isinstance(user_inputs, list):
        return {"_userInputs_type": type(user_inputs).__name__}
    if len(user_inputs) == 0:
        return {"_userInputs_len": 0}
    # Inspect the first item only (typical shape). Do not print values.
    first = user_inputs[0]
    return {
        "_userInputs_len": len(user_inputs),
        "_userInputs_first_item_keys": list(first.keys()) if isinstance(first, dict) else type(first).__name__,
    }


def _run() -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    # 1. Token presence only. NEVER the value, length, hash, or any
    #    attribute that could be used to identify or reconstruct it.
    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    out["token_present"] = bool(token)
    out["which_env_var"] = (
        "ACN_API_TOKEN" if os.environ.get("ACN_API_TOKEN")
        else ("ACNPORTAL_TOKEN" if os.environ.get("ACNPORTAL_TOKEN") else "none")
    )
    if not token:
        out["auth_outcome"] = "no_token_in_env"
        out["http_status_codes"] = {}
        out["n_records_received"] = 0
        out["n_records_after_schema_gate"] = 0
        out["n_records_after_window_filter"] = 0
        out["n_records_with_valid_kWhRequested"] = 0
        out["n_records_with_valid_requestedDeparture"] = 0
        out["n_records_with_valid_kWhDelivered"] = 0
        out["n_records_with_valid_disconnectTime"] = 0
        out["n_records_with_valid_connectionTime"] = 0
        out["n_records_with_valid_DeltaE"] = 0
        out["n_records_with_valid_DeltaD"] = 0
        out["final_samples"] = 0
        out["n_pages_visited"] = 0
        out["payload_top_level_type"] = None
        out["payload_wrapper_keys"] = None
        out["payload_has_hateoas_next"] = None
        out["first_record_top_level_keys"] = None
        out["first_record_userInputs_summary"] = None
        return out

    # 2. Build request. Authorization header is constructed but NEVER logged.
    ctx = ssl.create_default_context()
    req = urllib.request.Request(ENDPOINT, headers={"Accept": "application/json"})
    token_b64 = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token_b64}")
    # We do NOT log the Authorization header value, the base64, the token, or
    # the URL with credentials. The URL itself is a public path; it contains
    # no credentials.

    http_status_codes: Dict[int, int] = {}
    payload_top_level_type: Optional[str] = None
    payload_wrapper_keys: Optional[List[str]] = None
    payload_has_hateoas_next: Optional[bool] = None
    n_pages_visited = 0
    n_records_received = 0
    n_after_schema_gate = 0
    n_after_window = 0
    n_with_kwh_requested = 0
    n_with_dep_requested = 0
    n_with_kwh_delivered = 0
    n_with_disconnect = 0
    n_with_connection = 0
    n_with_valid_delta_e = 0
    n_with_valid_delta_d = 0
    first_record_keys: Optional[List[str]] = None
    first_record_userinputs: Optional[Dict[str, Any]] = None

    # 3. Make the request and capture a sanitized per-stage breakdown.
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as resp:
            status = int(getattr(resp, "status", 200))
            http_status_codes[status] = http_status_codes.get(status, 0) + 1
            n_pages_visited = 1
            raw = resp.read()
    except urllib.error.HTTPError as e:
        http_status_codes[int(e.code)] = http_status_codes.get(int(e.code), 0) + 1
        out["auth_outcome"] = f"http_{e.code}"
        out["http_status_codes"] = http_status_codes
        out["n_records_received"] = 0
        out["n_records_after_schema_gate"] = 0
        out["n_records_after_window_filter"] = 0
        out["n_records_with_valid_kWhRequested"] = 0
        out["n_records_with_valid_requestedDeparture"] = 0
        out["n_records_with_valid_kWhDelivered"] = 0
        out["n_records_with_valid_disconnectTime"] = 0
        out["n_records_with_valid_connectionTime"] = 0
        out["n_records_with_valid_DeltaE"] = 0
        out["n_records_with_valid_DeltaD"] = 0
        out["final_samples"] = 0
        out["n_pages_visited"] = n_pages_visited
        out["payload_top_level_type"] = None
        out["payload_wrapper_keys"] = None
        out["payload_has_hateoas_next"] = None
        out["first_record_top_level_keys"] = None
        out["first_record_userInputs_summary"] = None
        return out
    except Exception as e:
        out["auth_outcome"] = f"exception_{type(e).__name__}"
        out["http_status_codes"] = http_status_codes
        out["n_records_received"] = 0
        out["n_records_after_schema_gate"] = 0
        out["n_records_after_window_filter"] = 0
        out["n_records_with_valid_kWhRequested"] = 0
        out["n_records_with_valid_requestedDeparture"] = 0
        out["n_records_with_valid_kWhDelivered"] = 0
        out["n_records_with_valid_disconnectTime"] = 0
        out["n_records_with_valid_connectionTime"] = 0
        out["n_records_with_valid_DeltaE"] = 0
        out["n_records_with_valid_DeltaD"] = 0
        out["final_samples"] = 0
        out["n_pages_visited"] = n_pages_visited
        out["payload_top_level_type"] = None
        out["payload_wrapper_keys"] = None
        out["payload_has_hateoas_next"] = None
        out["first_record_top_level_keys"] = None
        out["first_record_userInputs_summary"] = None
        return out

    out["auth_outcome"] = "http_200" if status == 200 else f"http_{status}"

    # 4. Parse the JSON. Inspect structure only; never print record values.
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        out["json_parse_error"] = type(e).__name__
        out["http_status_codes"] = http_status_codes
        out["n_records_received"] = 0
        out["final_samples"] = 0
        out["n_pages_visited"] = n_pages_visited
        out["payload_top_level_type"] = None
        out["payload_wrapper_keys"] = None
        out["payload_has_hateoas_next"] = None
        out["first_record_top_level_keys"] = None
        out["first_record_userInputs_summary"] = None
        return out

    payload_top_level_type = type(payload).__name__
    if isinstance(payload, dict):
        payload_wrapper_keys = sorted(payload.keys())
        payload_has_hateoas_next = "next" in payload
        # Mirror the loader's fallback chain (loader line 221):
        # items OR sessions OR results OR []
        items = (
            payload.get("items")
            or payload.get("sessions")
            or payload.get("results")
            or []
        )
        items_source = (
            "items" if payload.get("items") is not None
            else ("sessions" if payload.get("sessions") is not None
                  else ("results" if payload.get("results") is not None else "empty"))
        )
    elif isinstance(payload, list):
        items = payload
        items_source = "list_top_level"
    else:
        items = []
        items_source = "unexpected_type"

    # 5. Per-record per-stage breakdown. Same logic as the loader; values
    #    are NOT extracted, only counts.
    for rec in items:
        n_records_received += 1
        if first_record_keys is None and isinstance(rec, dict):
            first_record_keys = sorted(rec.keys())
            first_record_userinputs = _summarize_user_inputs(rec.get("userInputs"))

        # Stage: top-level field presence
        sid = rec.get("sessionID") or rec.get("sessionId") if isinstance(rec, dict) else None
        conn = rec.get("connectionTime") if isinstance(rec, dict) else None
        disc = rec.get("disconnectTime") if isinstance(rec, dict) else None
        kwh_d = rec.get("kWhDelivered") if isinstance(rec, dict) else None
        if conn is not None:
            n_with_connection += 1
        if disc is not None:
            n_with_disconnect += 1
        if kwh_d is not None:
            n_with_kwh_delivered += 1

        # userInputs extraction (loader line 233-247)
        user_inputs = rec.get("userInputs") or [] if isinstance(rec, dict) else []
        if not isinstance(user_inputs, list):
            user_inputs = []
        kwh_req = None
        dep_req = None
        if user_inputs:
            try:
                user_inputs_sorted = sorted(
                    user_inputs,
                    key=lambda u: (u.get("modifiedAt") or u.get("createdAt") or "")
                    if isinstance(u, dict) else "",
                )
                last_ui = user_inputs_sorted[-1] if user_inputs_sorted else None
            except Exception:
                last_ui = user_inputs[-1] if user_inputs else None
            if isinstance(last_ui, dict):
                kwh_req = last_ui.get("kWhRequested")
                dep_req = last_ui.get("requestedDeparture")
        if kwh_req is not None:
            n_with_kwh_requested += 1
        if dep_req is not None:
            n_with_dep_requested += 1

        # Schema gate (loader line 253): sid and conn and disc and kwh_d
        if not (sid and conn and disc and kwh_d is not None):
            continue
        n_after_schema_gate += 1

        # Window filter (loader line 268-274)
        try:
            conn_dt = datetime.fromisoformat(str(conn).replace("Z", "+00:00"))
        except Exception:
            continue
        in_cal = (conn_dt >= datetime(2018, 5, 1, tzinfo=timezone.utc)
                  and conn_dt <  datetime(2019, 7, 1, tzinfo=timezone.utc))
        in_ho = (conn_dt >= datetime(2019, 7, 1, tzinfo=timezone.utc)
                 and conn_dt <  datetime(2020, 1, 1, tzinfo=timezone.utc))
        if not (in_cal or in_ho):
            continue
        n_after_window += 1

        # Delta_e and Delta_d (loader line 277-290)
        try:
            delta_e = float(kwh_d) - float(kwh_req) if kwh_req is not None else None
        except (TypeError, ValueError):
            delta_e = None
        if delta_e is not None:
            n_with_valid_delta_e += 1
        try:
            if dep_req is not None and disc is not None:
                dep_dt = datetime.fromisoformat(str(dep_req).replace("Z", "+00:00"))
                disc_dt = datetime.fromisoformat(str(disc).replace("Z", "+00:00"))
                delta_d_min = (dep_dt - disc_dt).total_seconds() / 60.0
            else:
                delta_d_min = None
        except Exception:
            delta_d_min = None
        if delta_d_min is not None:
            n_with_valid_delta_d += 1

    out["http_status_codes"] = http_status_codes
    out["n_records_received"] = int(n_records_received)
    out["items_source_in_payload"] = items_source
    out["n_records_after_schema_gate"] = int(n_after_schema_gate)
    out["n_records_after_window_filter"] = int(n_after_window)
    out["n_records_with_valid_connectionTime"] = int(n_with_connection)
    out["n_records_with_valid_disconnectTime"] = int(n_with_disconnect)
    out["n_records_with_valid_kWhDelivered"] = int(n_with_kwh_delivered)
    out["n_records_with_valid_kWhRequested"] = int(n_with_kwh_requested)
    out["n_records_with_valid_requestedDeparture"] = int(n_with_dep_requested)
    out["n_records_with_valid_DeltaE"] = int(n_with_valid_delta_e)
    out["n_records_with_valid_DeltaD"] = int(n_with_valid_delta_d)
    out["final_samples"] = int(n_after_window)
    out["n_pages_visited"] = int(n_pages_visited)
    out["payload_top_level_type"] = payload_top_level_type
    out["payload_wrapper_keys"] = payload_wrapper_keys
    out["payload_has_hateoas_next"] = payload_has_hateoas_next
    out["first_record_top_level_keys"] = first_record_keys
    out["first_record_userInputs_summary"] = first_record_userinputs
    return out


if __name__ == "__main__":
    result = _run()
    # Print ONLY the sanitized JSON. No banner, no extra output.
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.stdout.write("\n")
