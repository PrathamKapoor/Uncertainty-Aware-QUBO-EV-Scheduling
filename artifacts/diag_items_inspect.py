"""Credential-safe inspection of the Caltech API's _items wrapper.

Builds on diag_loader_path.py. The first probe established:
  - Authentication succeeds (HTTP 200)
  - The payload top-level type is dict
  - The payload wrapper keys are: ["_items", "_links", "_meta"]
  - payload.get("items") / .get("sessions") / .get("results") all returned
    None or []; "items_source_in_payload" was "empty"

This probe inspects the STRUCTURE of _items itself, without printing any
field value. It checks:
  - whether _items is a list, dict, or other
  - its length
  - the top-level field NAMES (and types) of the first record inside _items
  - whether userInputs is present; its type; its length; the keys of the
    first userInput entry
  - the field NAMES inside _links and _meta (without values)
  - the field NAMES of the first record's userInputs[*] (without values)

PRIVACY GUARANTEES (enforced at runtime):

  * The token is read by Python's os.environ; never by the agent.
  * No token value, length, hash, prefix, suffix, base64, or Authorization
    header value is printed.
  * No field value of any record is printed. Only type tags.
  * No record (or any portion of one) is printed in any form.
  * No URL containing credentials is printed (the URL has no credentials).
  * Nothing is written to disk. Output is JSON to stdout only.

USAGE (PowerShell, from repo root):

    PS> python artifacts/diag_items_inspect.py

Paste the entire JSON output back to the agent.
"""
from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


ENDPOINT = "https://ev.caltech.edu/api/v1/sessions/caltech?page=1&max_results=5"
TIMEOUT_S = 20.0

# The fields Stage 1 / Stage 9 frozen methodology expects to be present
# in a session record and inside userInputs[*]. These are the names we
# will report structural presence for. We never read their values.
EXPECTED_RECORD_FIELDS = [
    "sessionID", "sessionId",
    "connectionTime", "disconnectTime",
    "kWhDelivered",
    "userInputs",
    "siteID",
]

EXPECTED_USERINPUT_FIELDS = [
    "kWhRequested",
    "requestedDeparture",
    "modifiedAt", "createdAt",
]


def _type_tag(v: Any) -> str:
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
        # Try ISO-8601 detection without exposing the value.
        if len(v) == 0:
            return "str_empty"
        try:
            from datetime import datetime
            datetime.fromisoformat(v.replace("Z", "+00:00"))
            return "iso8601_str"
        except Exception:
            return f"str_len_{len(v)}"
    if isinstance(v, list):
        return f"list_len_{len(v)}"
    if isinstance(v, dict):
        return f"dict_keys_{len(v)}"
    return type(v).__name__


def _summarize_wrapper(wrapper: Any) -> Dict[str, Any]:
    """Return top-level field names + sanitized type tags. No values."""
    if not isinstance(wrapper, dict):
        return {"_wrapper_type": type(wrapper).__name__}
    return {k: _type_tag(v) for k, v in wrapper.items()}


def _summarize_record(rec: Any) -> Dict[str, Any]:
    """Top-level field NAMES of one record + type tags. No values."""
    if not isinstance(rec, dict):
        return {"_record_type": type(rec).__name__}
    out: Dict[str, Any] = {"_fields": {k: _type_tag(v) for k, v in rec.items()}}
    # Specifically mark which expected fields are present.
    out["_expected_field_presence"] = {
        f: (f in rec) for f in EXPECTED_RECORD_FIELDS
    }
    # userInputs structure (if present)
    if "userInputs" in rec:
        ui = rec["userInputs"]
        if isinstance(ui, list):
            out["_userInputs_is_list"] = True
            out["_userInputs_len"] = len(ui)
            if len(ui) > 0 and isinstance(ui[0], dict):
                out["_userInputs_first_keys"] = sorted(ui[0].keys())
                # Mark which expected userInput fields are present.
                out["_userInputs_first_expected_field_presence"] = {
                    f: (f in ui[0]) for f in EXPECTED_USERINPUT_FIELDS
                }
            else:
                out["_userInputs_first_type"] = (
                    type(ui[0]).__name__ if len(ui) > 0 else "empty"
                )
        elif isinstance(ui, dict):
            out["_userInputs_is_list"] = False
            out["_userInputs_keys"] = sorted(ui.keys())
        else:
            out["_userInputs_type"] = type(ui).__name__
    return out


def _run() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    out["token_present"] = bool(token)
    out["which_env_var"] = (
        "ACN_API_TOKEN" if os.environ.get("ACN_API_TOKEN")
        else ("ACNPORTAL_TOKEN" if os.environ.get("ACNPORTAL_TOKEN") else "none")
    )
    if not token:
        out["auth_outcome"] = "no_token_in_env"
        out["http_status_codes"] = {}
        out["items_is_list"] = None
        out["items_len"] = None
        out["items_type"] = None
        out["first_record_summary"] = None
        out["_links_summary"] = None
        out["_meta_summary"] = None
        out["pagination_meta_field_names"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None
        return out

    ctx = ssl.create_default_context()
    req = urllib.request.Request(ENDPOINT, headers={"Accept": "application/json"})
    token_b64 = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {token_b64}")

    http_status_codes: Dict[int, int] = {}
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx) as resp:
            status = int(getattr(resp, "status", 200))
            http_status_codes[status] = http_status_codes.get(status, 0) + 1
            raw = resp.read()
    except urllib.error.HTTPError as e:
        http_status_codes[int(e.code)] = http_status_codes.get(int(e.code), 0) + 1
        out["auth_outcome"] = f"http_{e.code}"
        out["http_status_codes"] = http_status_codes
        out["items_is_list"] = None
        out["items_len"] = None
        out["items_type"] = None
        out["first_record_summary"] = None
        out["_links_summary"] = None
        out["_meta_summary"] = None
        out["pagination_meta_field_names"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None
        return out
    except Exception as e:
        out["auth_outcome"] = f"exception_{type(e).__name__}"
        out["http_status_codes"] = http_status_codes
        out["items_is_list"] = None
        out["items_len"] = None
        out["items_type"] = None
        out["first_record_summary"] = None
        out["_links_summary"] = None
        out["_meta_summary"] = None
        out["pagination_meta_field_names"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None
        return out

    out["auth_outcome"] = "http_200" if status == 200 else f"http_{status}"
    out["http_status_codes"] = http_status_codes

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as e:
        out["json_parse_error"] = type(e).__name__
        out["items_is_list"] = None
        out["items_len"] = None
        out["items_type"] = None
        out["first_record_summary"] = None
        out["_links_summary"] = None
        out["_meta_summary"] = None
        out["pagination_meta_field_names"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None
        return out

    # Inspect _items structure.
    if not isinstance(payload, dict):
        out["items_is_list"] = None
        out["items_len"] = None
        out["items_type"] = None
        out["first_record_summary"] = None
        out["_links_summary"] = None
        out["_meta_summary"] = None
        out["pagination_meta_field_names"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None
        return out

    items = payload.get("_items")
    out["items_type"] = type(items).__name__ if items is not None else "missing"
    out["items_is_list"] = bool(isinstance(items, list))
    out["items_len"] = (len(items) if isinstance(items, list) else None)

    # First record (if any). Field names + types only.
    first = items[0] if isinstance(items, list) and len(items) > 0 else None
    if first is not None:
        rec_sum = _summarize_record(first)
        out["first_record_summary"] = rec_sum
        out["expected_record_fields_present"] = rec_sum.get("_expected_field_presence")
        out["expected_userinput_fields_present_in_first_userinput"] = rec_sum.get(
            "_userInputs_first_expected_field_presence"
        )
    else:
        out["first_record_summary"] = None
        out["expected_record_fields_present"] = None
        out["expected_userinput_fields_present_in_first_userinput"] = None

    # _links: field NAMES only.
    links = payload.get("_links")
    out["_links_summary"] = _summarize_wrapper(links) if isinstance(links, dict) else (
        {"_type": type(links).__name__} if links is not None else {"_present": False}
    )
    # If _links is a dict of {name: href/url/etc}, report only the outer keys.
    if isinstance(links, dict):
        out["_links_outer_keys"] = sorted(links.keys())
        # If a "next" key exists, report only that it exists (no value).
        out["_links_has_next_key"] = "next" in links

    # _meta: field NAMES only (pagination metadata).
    meta = payload.get("_meta")
    if isinstance(meta, dict):
        out["_meta_summary"] = {k: _type_tag(v) for k, v in meta.items()}
        out["pagination_meta_field_names"] = sorted(meta.keys())
    else:
        out["_meta_summary"] = (
            {"_type": type(meta).__name__} if meta is not None else {"_present": False}
        )
        out["pagination_meta_field_names"] = None

    return out


if __name__ == "__main__":
    result = _run()
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.stdout.write("\n")
