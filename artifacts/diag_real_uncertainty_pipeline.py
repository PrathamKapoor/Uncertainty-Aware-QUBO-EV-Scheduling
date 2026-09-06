"""Credential-safe post-_items pipeline diagnostic.

This script is INTENDED TO BE RUN BY THE USER in their PowerShell
session where ACN_API_TOKEN is set. It walks the loader pipeline
against the live ACN-Data API, but reports AGGREGATE COUNTS ONLY.

The wrapper-key fix for "_items" is already in stage5/uncertainty.py.
This diagnostic tests what happens AFTER _items extraction:

  - Does the schema gate (sid/conn/disc/kwh_d) pass?
  - Does connectionTime parse?
  - Is connectionTime in the frozen window?
  - Is userInputs present, and if so what is its shape?
  - Inside userInputs, are kWhRequested / requestedDeparture present?
  - After extraction, are valid DeltaE and DeltaD produced?
  - Is pagination followed correctly?

PRIVACY GUARANTEES (enforced at runtime):

  * The token is read from os.environ by Python itself, never by the
    agent. The script does NOT print, log, hash, base64-encode, or
    otherwise expose the token's value, length, prefix, or suffix.
  * No Authorization header value is printed.
  * No request URL containing credentials is printed.
  * No individual session record is printed. Aggregate counts only.
  * Field-name introspection is name+type only, never values.
  * No timestamp, no ID, no kWh value is ever printed.
  * Nothing is written to disk. Output is JSON to stdout only.
  * Bounded to 10 pages (max_results=25 each = up to 250 records).

USAGE (PowerShell, from repo root):

    PS> python artifacts/diag_real_uncertainty_pipeline.py

It will print a single JSON object to stdout. Paste the JSON back to
the agent.
"""
from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

# Diagnostic-only compatibility: reuse the strict parser already verified for
# the live API in Stage 5. This changes only structural counting/window
# classification in this probe; it does not change the loader or methodology.
# Make this work under the documented `python artifacts/...py` invocation.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from stage5.uncertainty import _parse_api_timestamp as _parse_diagnostic_timestamp


BASE_URL = "https://ev.caltech.edu/api/v1/sessions/caltech"
PAGE_SIZE = 25
MAX_PAGES = 10
TIMEOUT_S = 30.0

# Frozen temporal split (Stage 1 / Stage 7 / final_experiment_config.json).
CAL_START = datetime(2018, 5, 1, tzinfo=timezone.utc)
CAL_END = datetime(2019, 7, 1, tzinfo=timezone.utc)
HO_START = datetime(2019, 7, 1, tzinfo=timezone.utc)
HO_END = datetime(2020, 1, 1, tzinfo=timezone.utc)

# Format-class regexes for connectionTime / disconnectTime. Used by the
# diagnostic only; the loader continues to use datetime.fromisoformat.
# These classify a string into one of a small number of sanitized
# buckets WITHOUT exposing the value. The diagnostic reports per-page
# counts of each format class so we can identify whether the API
# returns a non-ISO-8601 representation that the loader's current
# parser does not accept.
ISO8601_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
ISO8601_OFFSET_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?[+-]\d{2}:?\d{2}$"
)
ISO8601_NAIVE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")
SPACE_SEPARATED_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z| UTC)?$"
)
RFC1123_RE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} "
    r"\d{2}:\d{2}:\d{2} (GMT|UT|UTC|EST|EDT|CST|CDT|MST|MDT|PST|PDT|Z)$"
)
INT_RE = re.compile(r"^-?\d+$")


def _classify_timestamp_format(v: Any) -> str:
    """Return a sanitized format-class tag for a timestamp-like value.

    NEVER include the value or any prefix/suffix. The result is one of:
      - 'iso8601_z'           : YYYY-MM-DDTHH:MM:SS[.fff]Z
      - 'iso8601_offset'      : YYYY-MM-DDTHH:MM:SS[.fff]+HH:MM or +HHMM
      - 'iso8601_naive'       : YYYY-MM-DDTHH:MM:SS[.fff]  (no tz)
      - 'space_separated'     : YYYY-MM-DD HH:MM:SS[...]  (with optional tz)
      - 'epoch_seconds_int'  : integer in epoch-seconds range (10 digits)
      - 'epoch_milliseconds_int' : integer in epoch-ms range (13 digits)
      - 'int_other'           : integer not in epoch range
      - 'str_other'           : non-empty string not matching any class
      - 'str_empty'           : empty string
      - 'null'                : None
      - 'not_string'          : bool / list / dict / other type
    """
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "not_string"
    if isinstance(v, (list, dict)):
        return "not_string"
    if isinstance(v, float):
        return "not_string"
    if isinstance(v, int):
        if v >= 10**12 and v < 10**14:
            return "epoch_milliseconds_int"
        if v >= 10**8 and v < 10**11:
            return "epoch_seconds_int"
        return "int_other"
    if isinstance(v, str):
        if len(v) == 0:
            return "str_empty"
        if ISO8601_Z_RE.match(v):
            return "iso8601_z"
        if ISO8601_OFFSET_RE.match(v):
            return "iso8601_offset"
        if ISO8601_NAIVE_RE.match(v):
            return "iso8601_naive"
        if SPACE_SEPARATED_RE.match(v):
            return "space_separated"
        if RFC1123_RE.match(v):
            return "rfc1123_http_date"
        if INT_RE.match(v):
            # Numeric string; could be an epoch.
            try:
                iv = int(v)
                if iv >= 10**12 and iv < 10**14:
                    return "epoch_milliseconds_int"
                if iv >= 10**8 and iv < 10**11:
                    return "epoch_seconds_int"
                return "int_other"
            except Exception:
                return "str_other"
        return "str_other"
    return "not_string"


# ---------------------------------------------------------------------------
# Helpers: type-only introspection. NEVER include values.
# ---------------------------------------------------------------------------

def _type_tag(v: Any) -> str:
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
        # ISO-8601 detection (no value exposure).
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return "iso8601_str"
        except Exception:
            return f"str_len_{len(v)}"
    if isinstance(v, list):
        return f"list_len_{len(v)}"
    if isinstance(v, dict):
        return f"dict_keys_{len(v)}"
    return type(v).__name__


def _summarize_user_inputs_presence(ui: Any) -> Dict[str, Any]:
    """Aggregate presence of kWhRequested and requestedDeparture inside userInputs.

    The per-record loader takes the LAST userInput (sorted by modifiedAt or
    createdAt) and reads kWhRequested / requestedDeparture from that entry.
    We track both:
      - the per-record loader's "last entry" view (which is what the loader
        actually reads)
      - the union view (any entry has it)

    This lets us distinguish "API returns the field but the last entry is
    empty" from "API never returns the field".
    """
    if ui is None:
        return {
            "shape": "null",
            "last_entry_has_kwh_requested": False,
            "last_entry_has_requested_departure": False,
            "any_entry_has_kwh_requested": False,
            "any_entry_has_requested_departure": False,
            "n_entries": 0,
        }
    if isinstance(ui, list):
        n = len(ui)
        if n == 0:
            return {
                "shape": "list_empty",
                "last_entry_has_kwh_requested": False,
                "last_entry_has_requested_departure": False,
                "any_entry_has_kwh_requested": False,
                "any_entry_has_requested_departure": False,
                "n_entries": 0,
            }

        def _key(e: Any) -> str:
            if isinstance(e, dict):
                return str(e.get("modifiedAt") or e.get("createdAt") or "")
            return ""

        try:
            sorted_entries = sorted(ui, key=_key)
            last = sorted_entries[-1]
        except Exception:
            last = ui[-1]
        last_has_kwh = isinstance(last, dict) and "kWhRequested" in last
        last_has_dep = isinstance(last, dict) and "requestedDeparture" in last
        any_has_kwh = any(isinstance(e, dict) and "kWhRequested" in e for e in ui)
        any_has_dep = any(isinstance(e, dict) and "requestedDeparture" in e for e in ui)
        return {
            "shape": f"list_len_{n}",
            "last_entry_has_kwh_requested": bool(last_has_kwh),
            "last_entry_has_requested_departure": bool(last_has_dep),
            "any_entry_has_kwh_requested": bool(any_has_kwh),
            "any_entry_has_requested_departure": bool(any_has_dep),
            "n_entries": int(n),
        }
    if isinstance(ui, dict):
        return {
            "shape": "dict",
            "last_entry_has_kwh_requested": "kWhRequested" in ui,
            "last_entry_has_requested_departure": "requestedDeparture" in ui,
            "any_entry_has_kwh_requested": "kWhRequested" in ui,
            "any_entry_has_requested_departure": "requestedDeparture" in ui,
            "n_entries": 1,
        }
    return {
        "shape": type(ui).__name__,
        "last_entry_has_kwh_requested": False,
        "last_entry_has_requested_departure": False,
        "any_entry_has_kwh_requested": False,
        "any_entry_has_requested_departure": False,
        "n_entries": 0,
    }


def _redact_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    """Defensive redaction: never echo token-shaped values as values."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) >= 40 and "/" not in v and " " not in v:
            if k.lower() in (
                "acn_api_token", "token", "acnportal_token",
                "authorization", "url", "next_url",
            ):
                out[k] = "<redacted>"
                continue
        out[k] = v
    return out
def _introspect_links(links_obj: Any) -> Dict[str, Any]:
    """Return a sanitized view of a HATEOAS _links container.

    The ACN API returns _links.next / _links.last / _links.self / _links.parent
    whose values may be:
      - a plain string (relative or absolute URL), OR
      - a dict of the form {"href": "...", "method": "..."} (HATEOAS), OR
      - None.

    This helper reports ONLY the structural type and (for dicts) the key
    names. It NEVER echoes URL values, href values, method values, or any
    field content. The objective is to determine the *shape* so the
    pagination code can dispatch correctly, not to capture URLs.
    """
    if links_obj is None:
        return {"present": False, "type": "null"}
    if isinstance(links_obj, dict):
        out_keys: Dict[str, Any] = {}
        for k, v in links_obj.items():
            entry: Dict[str, Any] = {"type": _type_tag(v)}
            if isinstance(v, dict):
                # Report key names only; never any value.
                entry["dict_keys"] = sorted(v.keys())
                # Indicate WHICH key carries the navigation URL, but do not
                # print its value. Convention is "href"; we surface it only
                # when present so the diagnostic shows what the API uses.
                entry["url_bearing_key"] = (
                    "href" if "href" in v else None
                )
            out_keys[str(k)] = entry
        return {"present": True, "type": "dict", "members": out_keys}
    return {"present": True, "type": type(links_obj).__name__}


def _extract_next_url(raw_next: Any) -> Optional[str]:
    """Return the navigation URL string from a raw _links.next value.

    NEVER log or echo the resolved URL. Handles three shapes:
      - str  -> returned as-is (urljoin will resolve it later).
      - dict -> uses v["href"] ONLY IF v["href"] is a non-empty string.
                Otherwise returns None. Never echoes v["href"] itself.
      - None / list / other -> None.
    """
    if isinstance(raw_next, str):
        if len(raw_next) == 0:
            return None
        return raw_next
    if isinstance(raw_next, dict):
        candidate = raw_next.get("href")
        if isinstance(candidate, str) and len(candidate) > 0:
            return candidate
        return None
    return None


# ---------------------------------------------------------------------------
# Main diagnostic
# ---------------------------------------------------------------------------

def _run() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "auth": {},
        "pagination": {},
        "schema": {},
        "field_parsing": {},
        "temporal_filter": {},
        "cleaning": {},
        "uncertainty": {},
        "userInputs_aggregate": {},
        "loader_branch_counts": {},
    }

    # 1. AUTH block
    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    out["auth"]["token_present"] = bool(token)
    out["auth"]["which_env_var"] = (
        "ACN_API_TOKEN" if os.environ.get("ACN_API_TOKEN")
        else ("ACNPORTAL_TOKEN" if os.environ.get("ACNPORTAL_TOKEN") else "none")
    )
    if not token:
        out["auth"]["auth_outcome"] = "no_token_in_env"
        out["auth"]["sanitized_http_status"] = None
        return out

    ctx = ssl.create_default_context()
    pages_visited = 0
    http_status_codes: Dict[str, int] = {}
    next_url: Optional[str] = f"{BASE_URL}?page=1&max_results={PAGE_SIZE}"
    n_records_received = 0
    raw_payloads_seen = 0
    pages_with_items = 0
    pages_empty_items = 0
    n_links_next_followed = 0
    n_links_next_unavailable = 0
    _meta_seen: Optional[Dict[str, Any]] = None

    _meta_field_names: Optional[List[str]] = None
    # Structure-only introspection of _links on the first occurrence.
    _links_structure: Optional[Dict[str, Any]] = None

    # Pipeline counters
    n_top_sessionID = 0
    n_top_sessionId = 0
    n_top_connectionTime = 0
    n_top_disconnectTime = 0
    n_top_kWhDelivered = 0
    n_top_userInputs_present = 0
    n_top_userInputs_null = 0
    n_top_userInputs_other = 0
    n_userInputs_list_empty = 0
    n_userInputs_list_nonempty = 0
    n_userInputs_dict_shape = 0
    n_userInputs_any_has_kwh_requested = 0
    n_userInputs_any_has_requested_departure = 0
    n_userInputs_last_has_kwh_requested = 0
    n_userInputs_last_has_requested_departure = 0
    n_last_modifiedAt_or_createdAt = 0
    n_no_modifiedAt_or_createdAt = 0

    n_schema_gate_pass = 0
    n_schema_gate_fail_missing_sid = 0
    n_schema_gate_fail_missing_conn = 0
    n_schema_gate_fail_missing_disc = 0
    n_schema_gate_fail_missing_kwh_d = 0
    n_schema_gate_fail_other = 0

    n_conn_parseable = 0
    n_conn_unparseable = 0
    n_in_calibration_window = 0
    n_in_held_out_window = 0
    n_outside_window = 0
    n_window_skipped_in_loader = 0

    n_kwh_d_numeric = 0
    n_kwh_d_non_numeric = 0
    n_kwh_req_numeric = 0
    n_kwh_req_non_numeric = 0
    n_dep_req_parseable = 0
    n_dep_req_unparseable = 0
    n_disc_parseable = 0
    n_disc_unparseable = 0

    # Per-format-class counters for connectionTime and disconnectTime.
    # Each counter is a dict mapping a sanitized format-class tag to the
    # number of records whose value fell in that class. The diagnostic
    # uses this to identify the actual API timestamp representation
    # WITHOUT exposing the value.
    n_conn_format_class: Dict[str, int] = {}
    n_disc_format_class: Dict[str, int] = {}

    n_valid_delta_e = 0
    n_valid_delta_d = 0
    n_valid_joint = 0
    n_appended_to_samples = 0

    n_cleaned_by_r9 = 0
    n_cleaned_by_r10 = 0
    n_with_valid_both_after_cleaning = 0

    # Per-page helper: fetch a single URL with the token's Basic auth header.
    # Returns (status_int, raw_bytes) on success, or (None, error_category_str)
    # on any failure (HTTPError, URLError, timeout, JSON parse). Never logs
    # or echoes the token, the URL with credentials, or the request object.
    def _fetch(url: str) -> Tuple[Optional[int], Any]:
        try:
            r = urllib.request.Request(url, headers={"Accept": "application/json"})
            token_b64 = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
            r.add_header("Authorization", f"Basic {token_b64}")
            with urllib.request.urlopen(r, timeout=TIMEOUT_S, context=ctx) as resp:
                status = int(getattr(resp, "status", 200))
                http_status_codes[str(status)] = http_status_codes.get(str(status), 0) + 1
                return status, resp.read()
        except urllib.error.HTTPError as e:
            http_status_codes[str(int(e.code))] = http_status_codes.get(
                str(int(e.code)), 0
            ) + 1
            return int(e.code), "http_error"
        except urllib.error.URLError:
            # URLError has a .reason attribute. Do NOT print it: it can
            # carry host/port/network context. Report only the sanitized
            # category.
            return None, "url_error"
        except TimeoutError:
            return None, "timeout"
        except Exception:
            return None, "unknown_error"

    # Build the final out-block from running counters. Called after every
    # successful page AND on every early-return path so the user always
    # sees the running statistics for the records that were received.
    def _write_summary(reason: str) -> Dict[str, Any]:
        out["pagination"] = {
            "pages_visited": pages_visited,
            "max_pages_limit": MAX_PAGES,
            "page_size": PAGE_SIZE,
            "n_records_received": n_records_received,
            "pages_with_items": pages_with_items,
            "pages_empty_items": pages_empty_items,
            "n_pages_with_next_link_followed": n_links_next_followed,
            "n_pages_without_next_link": n_links_next_unavailable,
            "_meta_field_names": _meta_field_names,
            "_meta_value_types_first_page": _meta_seen,
            "_links_structure_first_page": _links_structure,
            "stopped_reason": reason,
        }

        out["schema"] = {
            "n_records_received": n_records_received,
            "top_level_sessionID_present": n_top_sessionID,
            "top_level_sessionId_present": n_top_sessionId,
            "top_level_connectionTime_present": n_top_connectionTime,
            "top_level_disconnectTime_present": n_top_disconnectTime,
            "top_level_kWhDelivered_present": n_top_kWhDelivered,
            "top_level_userInputs_present": n_top_userInputs_present,
            "top_level_userInputs_null": n_top_userInputs_null,
            "top_level_userInputs_other_shape": n_top_userInputs_other,
            "userInputs_list_empty": n_userInputs_list_empty,
            "userInputs_list_nonempty": n_userInputs_list_nonempty,
            "userInputs_dict_shape": n_userInputs_dict_shape,
            "userInputs_other_shape": (
                n_top_userInputs_other
                - n_userInputs_list_empty
                - n_userInputs_list_nonempty
                - n_userInputs_dict_shape
            ),
            "any_entry_has_kwh_requested": n_userInputs_any_has_kwh_requested,
            "any_entry_has_requested_departure": n_userInputs_any_has_requested_departure,
            "last_entry_has_kwh_requested": n_userInputs_last_has_kwh_requested,
            "last_entry_has_requested_departure": n_userInputs_last_has_requested_departure,
            "n_with_modifiedAt_or_createdAt_in_userInputs": n_last_modifiedAt_or_createdAt,
            "n_without_modifiedAt_or_createdAt_in_userInputs": n_no_modifiedAt_or_createdAt,
        }
        out["field_parsing"] = {
            "kWhDelivered_numeric": n_kwh_d_numeric,
            "kWhDelivered_non_numeric": n_kwh_d_non_numeric,
            "kWhRequested_numeric": n_kwh_req_numeric,
            "kWhRequested_non_numeric": n_kwh_req_non_numeric,
            "kWhRequested_absent": (
                n_records_received - n_kwh_req_numeric - n_kwh_req_non_numeric
            ),
            "disconnectTime_parseable": n_disc_parseable,
            "disconnectTime_unparseable": n_disc_unparseable,
            "requestedDeparture_parseable": n_dep_req_parseable,
            "requestedDeparture_unparseable": n_dep_req_unparseable,
            "requestedDeparture_absent": (
                n_records_received - n_dep_req_parseable - n_dep_req_unparseable
            ),
        }
        out["temporal_filter"] = {
            "n_records_entering_conn_parse": n_schema_gate_pass,
            "connectionTime_parseable": n_conn_parseable,
            "connectionTime_unparseable": n_conn_unparseable,
            "connectionTime_format_classes": n_conn_format_class,
            "n_inside_calibration_window": n_in_calibration_window,
            "n_inside_held_out_window": n_in_held_out_window,
            "n_outside_window": n_outside_window,
            "n_window_skipped_in_loader": n_window_skipped_in_loader,
        }
        out["timestamp_format"] = {
            "connectionTime_classes": n_conn_format_class,
            "disconnectTime_classes": n_disc_format_class,
        }
        out["cleaning"] = {
            "n_records_entering_cleaning": n_appended_to_samples,
            "r9_kwh_requested_missing": n_cleaned_by_r9,
            "r10_requested_departure_missing": n_cleaned_by_r10,
            "n_with_valid_kwh_requested_and_parseable_dep_requesture": n_with_valid_both_after_cleaning,
        }
        out["uncertainty"] = {
            "valid_DeltaE": n_valid_delta_e,
            "valid_DeltaD": n_valid_delta_d,
            "valid_joint_DeltaE_and_DeltaD": n_valid_joint,
            "n_appended_to_samples": n_appended_to_samples,
        }
        out["loader_branch_counts"] = {
            "n_records": n_records_received,
            "n_skipped_schema_gate": n_schema_gate_fail_other,
            "n_skipped_window": n_window_skipped_in_loader,
            "n_valid": n_appended_to_samples,
            "http_status_codes": http_status_codes,
        }
        out["userInputs_aggregate"] = {
            "n_userInputs_null": n_top_userInputs_null,
            "n_userInputs_list_empty": n_userInputs_list_empty,
            "n_userInputs_list_nonempty": n_userInputs_list_nonempty,
            "n_userInputs_dict_shape": n_userInputs_dict_shape,
            "n_userInputs_other_shape": (
                n_top_userInputs_other
                - n_userInputs_list_empty
                - n_userInputs_list_nonempty
                - n_userInputs_dict_shape
            ),
        }
        out["auth"] = {
            "token_present": True,
            "which_env_var": out["auth"]["which_env_var"],
            "auth_outcome": (
                "http_200" if "200" in http_status_codes
                else (
                    f"http_{list(http_status_codes.keys())[0]}"
                    if http_status_codes else "no_status"
                )
            ),
            "sanitized_http_status": (
                int(list(http_status_codes.keys())[0])
                if http_status_codes else None
            ),
            "raw_payloads_seen": raw_payloads_seen,
        }
        return out

    # Pagination loop. Continues processing records that have been
    # received, even if a later page's request fails.
    while next_url and pages_visited < MAX_PAGES:
        pages_visited += 1
        status, fetch_result = _fetch(next_url)
        if status is None:
            # Fetch failed (URLError / timeout / unknown). Persist the
            # partial running statistics and report the sanitized category.
            _write_summary(reason=f"fetch_failure_{fetch_result}_on_page_{pages_visited}")
            return _redact_keys(out)
        if fetch_result == "http_error":
            _write_summary(reason=f"http_error_on_page_{pages_visited}")
            return _redact_keys(out)
        raw = fetch_result
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as e:
            _write_summary(reason=f"json_parse_error_{type(e).__name__}_on_page_{pages_visited}")
            return _redact_keys(out)
        raw_payloads_seen += 1

        # Capture _meta structure on first occurrence.
        if isinstance(payload, dict) and _meta_field_names is None:
            meta = payload.get("_meta")
        # Capture _links structure on first occurrence (structure-only,
        # never values).
        if isinstance(payload, dict) and _links_structure is None:
            if "_links" in payload or isinstance(payload.get("_links"), dict):
                _links_structure = _introspect_links(payload.get("_links"))

                _meta_seen = {k: _type_tag(v) for k, v in meta.items()}
                _meta_field_names = sorted(meta.keys())

        # Same extraction logic as the (current, fixed) loader, with one
        # technical fix: resolve the HATEOAS next URL via urljoin so that
        # BOTH absolute (https://ev.caltech.edu/.../page=2) AND relative
        # (?page=2&max_results=25 or /api/v1/sessions/caltech?page=2)
        # HATEOAS next URLs work. Without urljoin, urllib raises
        # URLError on a relative next URL.
        next_url = None
        items: List[Any] = []
        if isinstance(payload, list):
            items = payload
            # If a list is returned without HATEOAS, advance by page.
            next_url = (
                f"{BASE_URL}?page={pages_visited + 1}&max_results={PAGE_SIZE}"
                if pages_visited < MAX_PAGES else None
            )
        elif isinstance(payload, dict):
            items = (
                payload.get("_items")
                or payload.get("items")
                or payload.get("sessions")
                or payload.get("results")
                or []
            )
            # Determine the raw next-link value. The ACN API nests the
            # pagination URL inside _links.next and may either return it
            # as a plain string OR as a HATEOAS dict
            # ({"href": "...", "method": "..."}). Both shapes are accepted
            # via the _extract_next_url helper. The resolved URL itself
            # is NEVER printed or logged.
            raw_next = payload.get("next")
            if raw_next is None and isinstance(payload.get("_links"), dict):
                raw_next = payload["_links"].get("next")
            next_str = _extract_next_url(raw_next)
            if next_str:
                # urljoin handles absolute, root-relative, and
                # query-only relative URLs uniformly. After urljoin the
                # value lives only inside the local `next_url` variable
                # and is used as the input to the next _fetch() call; it
                # is never printed, hashed, or written to disk.
                next_url = urljoin(next_url or BASE_URL, next_str)
                # Sanity: the joined URL must still be on the ev.caltech.edu
                # host (defense against a maliciously-crafted HATEOAS
                # pointing at a third party). If not, treat as no next.
                if not next_url.startswith("https://ev.caltech.edu/"):
                    next_url = None

        else:
            break

        if not items:
            pages_empty_items += 1
        else:
            pages_with_items += 1

        for rec in items:
            n_records_received += 1

            if not isinstance(rec, dict):
                n_top_userInputs_other += 1
                continue

            if rec.get("sessionID") is not None:
                n_top_sessionID += 1
            if rec.get("sessionId") is not None:
                n_top_sessionId += 1
            if rec.get("connectionTime") is not None:
                n_top_connectionTime += 1
            if rec.get("disconnectTime") is not None:
                n_top_disconnectTime += 1
            if rec.get("kWhDelivered") is not None:
                n_top_kWhDelivered += 1

            ui = rec.get("userInputs")
            if ui is None:
                n_top_userInputs_null += 1
            elif isinstance(ui, list):
                n_top_userInputs_present += 1
                if len(ui) == 0:
                    n_userInputs_list_empty += 1
                else:
                    n_userInputs_list_nonempty += 1
            elif isinstance(ui, dict):
                n_top_userInputs_present += 1
                n_userInputs_dict_shape += 1
            else:
                n_top_userInputs_other += 1

            ui_summary = _summarize_user_inputs_presence(ui)
            if ui_summary.get("any_entry_has_kwh_requested"):
                n_userInputs_any_has_kwh_requested += 1
            if ui_summary.get("any_entry_has_requested_departure"):
                n_userInputs_any_has_requested_departure += 1
            if ui_summary.get("last_entry_has_kwh_requested"):
                n_userInputs_last_has_kwh_requested += 1
            if ui_summary.get("last_entry_has_requested_departure"):
                n_userInputs_last_has_requested_departure += 1

            if isinstance(ui, list):
                has_mod = any(
                    isinstance(e, dict) and (e.get("modifiedAt") or e.get("createdAt"))
                    for e in ui
                )
                if has_mod:
                    n_last_modifiedAt_or_createdAt += 1
                else:
                    n_no_modifiedAt_or_createdAt += 1

            conn_str = rec.get("connectionTime")
            disc_str = rec.get("disconnectTime")
            kwh_d_raw = rec.get("kWhDelivered")
            if isinstance(kwh_d_raw, (int, float)) and not isinstance(kwh_d_raw, bool):
                n_kwh_d_numeric += 1
            else:
                n_kwh_d_non_numeric += 1
            disc_class = _classify_timestamp_format(disc_str)
            n_disc_format_class[disc_class] = n_disc_format_class.get(disc_class, 0) + 1
            if isinstance(disc_str, str):
                try:
                    _parse_diagnostic_timestamp(disc_str)
                    n_disc_parseable += 1
                except Exception:
                    n_disc_unparseable += 1
            else:
                n_disc_unparseable += 1

            kwh_req_value: Any = None
            dep_req_value: Any = None
            if isinstance(ui, list) and ui:

                def _key(e: Any) -> str:
                    if isinstance(e, dict):
                        return str(e.get("modifiedAt") or e.get("createdAt") or "")
                    return ""

                try:
                    sorted_entries = sorted(ui, key=_key)
                    last = sorted_entries[-1]
                except Exception:
                    last = ui[-1]
                if isinstance(last, dict):
                    kwh_req_value = last.get("kWhRequested")
                    dep_req_value = last.get("requestedDeparture")
            elif isinstance(ui, dict):
                kwh_req_value = ui.get("kWhRequested")
                dep_req_value = ui.get("requestedDeparture")

            kwh_req_numeric = False
            dep_req_parseable = False
            if kwh_req_value is not None:
                if isinstance(kwh_req_value, (int, float)) and not isinstance(
                    kwh_req_value, bool
                ):
                    kwh_req_numeric = True
                    n_kwh_req_numeric += 1
                else:
                    n_kwh_req_non_numeric += 1
            if dep_req_value is not None:
                if isinstance(dep_req_value, str):
                    try:
                        _parse_diagnostic_timestamp(dep_req_value)
                        dep_req_parseable = True
                        n_dep_req_parseable += 1
                    except Exception:
                        n_dep_req_unparseable += 1
                else:
                    n_dep_req_unparseable += 1

            sid_for_gate = rec.get("sessionID") or rec.get("sessionId")
            kwh_d_for_gate = rec.get("kWhDelivered")
            schema_pass = (
                bool(sid_for_gate)
                and bool(conn_str)
                and bool(disc_str)
                and (kwh_d_for_gate is not None)
            )
            if not schema_pass:
                if not sid_for_gate:
                    n_schema_gate_fail_missing_sid += 1
                if not conn_str:
                    n_schema_gate_fail_missing_conn += 1
                if not disc_str:
                    n_schema_gate_fail_missing_disc += 1
                if kwh_d_for_gate is None:
                    n_schema_gate_fail_missing_kwh_d += 1
                n_schema_gate_fail_other += 1
                continue
            n_schema_gate_pass += 1

            conn_dt: Optional[datetime] = None
            conn_class = _classify_timestamp_format(conn_str)
            n_conn_format_class[conn_class] = n_conn_format_class.get(conn_class, 0) + 1
            if isinstance(conn_str, str):
                try:
                    conn_dt = _parse_diagnostic_timestamp(conn_str)
                    n_conn_parseable += 1
                except Exception:
                    n_conn_unparseable += 1
            else:
                n_conn_unparseable += 1
            if conn_dt is None:
                continue
            in_cal = (conn_dt >= CAL_START) and (conn_dt < CAL_END)
            in_ho = (conn_dt >= HO_START) and (conn_dt < HO_END)
            if in_cal:
                n_in_calibration_window += 1
            elif in_ho:
                n_in_held_out_window += 1
            else:
                n_outside_window += 1
                n_window_skipped_in_loader += 1
                continue

            n_appended_to_samples += 1

            if kwh_req_value is None:
                n_cleaned_by_r9 += 1
            if dep_req_value is None:
                n_cleaned_by_r10 += 1

            delta_e: Optional[float] = None
            if kwh_req_value is not None and kwh_d_for_gate is not None:
                try:
                    delta_e = float(kwh_d_for_gate) - float(kwh_req_value)
                except (TypeError, ValueError):
                    delta_e = None
            if delta_e is not None:
                n_valid_delta_e += 1
            delta_d: Optional[float] = None
            if dep_req_value is not None and disc_str is not None:
                try:
                    dep_dt = _parse_diagnostic_timestamp(dep_req_value)
                    disc_dt = _parse_diagnostic_timestamp(disc_str)
                    delta_d = (dep_dt - disc_dt).total_seconds() / 60.0
                except Exception:
                    delta_d = None
            if delta_d is not None:
                n_valid_delta_d += 1
            if delta_e is not None and delta_d is not None:
                n_valid_joint += 1
            if (
                kwh_req_value is not None
                and dep_req_value is not None
                and kwh_req_numeric
                and dep_req_parseable
            ):
                n_with_valid_both_after_cleaning += 1

        # Pagination: did the page have a next link?
        if next_url:
            n_links_next_followed += 1
        else:
            n_links_next_unavailable += 1
            break

    # Loop completed normally (no fetch failure).
    _write_summary(
        reason=(
            "no next link"
            if n_links_next_unavailable > 0
            else "max_pages reached"
        )
    )
    return _redact_keys(out)
if __name__ == "__main__":
    result = _run()
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.stdout.write("\n")
