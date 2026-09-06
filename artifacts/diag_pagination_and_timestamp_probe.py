"""Credential-safe pagination + timestamp structural probe.

This script runs AFTER the corrected post-_items pipeline diagnostic.
It addresses two technical compatibility issues:

  TASK 1 — PAGINATION 404
    Why does following _links.next.href produce HTTP 404?
    The probe compares:
      * the structural shape of the initial page-1 URL,
      * the structural shape of the href extracted from _links.next.href,
      * the sanitized HTTP status from a GET to the extracted href,
      * the sanitized HTTP status from a GET to a manually reconstructed
        BASE_URL?page=2&max_results=PAGE_SIZE,
    and reports a verdict classifying the failure mode.

  TASK 2 — TIMESTAMP FORMAT
    What timestamp format does the live API actually return?
    The probe classifies each connectionTime / disconnectTime by STRUCTURAL
    FEATURES ONLY (length, character histograms, positions of T / Z / - /
    : / space / +, ends_with_Z) and emits a structural format tag.

PRIVACY GUARANTEES (enforced at runtime):

  * Token value, prefix, suffix, hash, length, base64 NEVER printed.
  * Authorization header NEVER printed.
  * Request URL value (page-1, href, reconstructed) NEVER printed.
  * Href value NEVER printed.
  * Timestamp value NEVER printed.
  * Session ID / record content NEVER printed.
  * Nothing is written to disk. JSON goes to stdout only.

USAGE (PowerShell, from repo root):

    PS> $env:ACN_API_TOKEN = "<your token>"
    PS> python artifacts/diag_pagination_and_timestamp_probe.py

Paste the resulting JSON back to the agent.
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
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, parse_qsl


BASE_URL = "https://ev.caltech.edu/api/v1/sessions/caltech"
PAGE_SIZE = 25
TIMEOUT_S = 30.0


# ---------------------------------------------------------------------------
# Privacy-preserving introspection helpers (no value leakage).
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
        return f"str_len_{len(v)}"
    if isinstance(v, list):
        return f"list_len_{len(v)}"
    if isinstance(v, dict):
        return f"dict_keys_{len(v)}"
    return type(v).__name__


def _url_leading_class(url: Any) -> str:
    """Classify the leading characters of a URL. Never echo the URL value.

    This is the critical signal for urljoin correctness. A href returned
    without a leading '/' or scheme will be resolved RELATIVE TO THE
    PARENT of the current path, producing a doubled path that 404s.
    """
    if not isinstance(url, str):
        return "non_string"
    if url.startswith("https://"):
        return "https_absolute"
    if url.startswith("http://"):
        return "http_absolute"
    if url.startswith("/"):
        return "root_relative"
    if url.startswith("?"):
        return "query_only"
    if "://" in url[:20]:
        return "scheme_relative_other"
    # Distinguish: href with NO leading slash AND no scheme is the bug case
    # (urljoin resolves it relative to the parent of the current path).
    # We test this by checking the first non-letter-or-digit character
    # position; for hrefs that DO start with a path, the first char is
    # alphanumeric (path segment), not '/' or '?' or ':' or '#'.
    if not url.startswith(("http://", "https://", "/", "?")) and "/" in url:
        if ":" not in url[:url.find("/")]:
            return "path_relative_no_slash"
        return "scheme_relative_other"
    return "path_relative_with_slash"


def _url_shape(url: Any) -> Dict[str, Any]:
    """Return STRUCTURAL shape of a URL. NEVER echo the URL value."""
    if not isinstance(url, str):
        return {"type": _type_tag(url), "leading_class": _url_leading_class(url)}
    try:
        parsed = urlparse(url)
    except Exception as e:
        return {"parse_error": type(e).__name__, "type": "str"}
    path_parts = [p for p in parsed.path.split("/") if p]
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    query_key_names = sorted(set(k for k, _ in query_pairs))
    return {
        "scheme": parsed.scheme or None,
        "host_class": _type_tag(parsed.hostname),
        "port_class": _type_tag(parsed.port),
        "host_equal_to_ev_caltech_edu": (
            parsed.hostname == "ev.caltech.edu" if parsed.hostname else None
        ),
        "path_depth": len(path_parts),
        "path_first_segment_class": (
            _type_tag(path_parts[0]) if path_parts else None
        ),
        "path_last_segment_class": (
            _type_tag(path_parts[-1]) if path_parts else None
        ),
        "path_equal_to_BASE_URL_path": (
            parsed.path == "/api/v1/sessions/caltech"
        ),
        "query_key_count": len(query_key_names),
        "query_key_names": query_key_names,
        "has_page_param": "page" in query_key_names,
        "has_max_results_param": "max_results" in query_key_names,
        "has_where_param": "where" in query_key_names,
        "has_sort_param": "sort" in query_key_names,
        "query_value_classes": {k: _type_tag(v) for k, v in query_pairs},
        "fragment_present": bool(parsed.fragment),
        "leading_class": _url_leading_class(url),
    }


# ---------------------------------------------------------------------------
# Timestamp structural classifier (no value leakage).
# ---------------------------------------------------------------------------


def _string_features(s: Any) -> Optional[Tuple]:
    """Return a hashable tuple of structural features. NEVER includes value.

    Returns None for None; a length-1 tuple for non-strings / empty strings.
    """
    if s is None:
        return None
    if not isinstance(s, str):
        return (type(s).__name__,)
    if len(s) == 0:
        return ("empty",)
    return (
        len(s),
        s.count("T"),
        s.count("Z"),
        s.count("-"),
        s.count("/"),
        s.count(":"),
        s.count(" "),
        s.count("."),
        s.count("+"),
        s.endswith("Z"),
        bool(re.search(r"\.\d+", s)),
        s.find("T"),
        s.find("/"),
        s.find(":"),
        s.find(" "),
        s.find("+"),
        s.find("-"),
        s[0].isdigit() if s else False,
        s[-1].isdigit() if s else False,
        sum(c.isdigit() for c in s),
        sum(c.isalpha() for c in s),
    )


def _features_to_dict(feat: Optional[Tuple]) -> Dict[str, Any]:
    if feat is None:
        return {"type": "null"}
    if feat == ("empty",):
        return {"type": "str_empty"}
    if len(feat) == 1:
        return {"type": feat[0]}
    return {
        "length": feat[0],
        "T_count": feat[1],
        "Z_count": feat[2],
        "hyphen_count": feat[3],
        "slash_count": feat[4],
        "colon_count": feat[5],
        "space_count": feat[6],
        "dot_count": feat[7],
        "plus_count": feat[8],
        "ends_with_Z": feat[9],
        "has_fractional": feat[10],
        "T_position": feat[11],
        "first_slash_position": feat[12],
        "first_colon_position": feat[13],
        "first_space_position": feat[14],
        "first_plus_position": feat[15],
        "first_minus_position": feat[16],
        "starts_with_digit": feat[17],
        "ends_with_digit": feat[18],
        "digit_count": feat[19],
        "letter_count": feat[20],
    }


def _classify_features(feat: Optional[Tuple]) -> List[str]:
    """Map a feature tuple to candidate format tags. NEVER echo values."""
    if feat is None:
        return ["null"]
    if feat == ("empty",):
        return ["empty_string"]
    if len(feat) == 1:
        return ["non_string"]

    length, T_count, Z_count, hyph, slash, colon, space, dot, plus = (
        feat[0], feat[1], feat[2], feat[3], feat[4], feat[5], feat[6], feat[7], feat[8]
    )
    ends_Z = feat[9]
    has_frac = feat[10]
    first_minus = feat[16]
    digit_count = feat[19]
    letter_count = feat[20]

    cls: List[str] = []

    # ISO-8601 date has exactly 2 hyphens (YYYY-MM-DD at positions 4 and 7).
    # A third hyphen OR a hyphen AFTER the date (first_minus > 7) OR an
    # explicit '+' signals a UTC offset like -07:00 / +00:00.
    iso_offset_signal = (
        (hyph >= 3)
        or (plus > 0)
        or (hyph == 2 and first_minus > 7)
    )

    if T_count > 0:
        if ends_Z:
            cls.append("iso8601_z")
        elif iso_offset_signal:
            cls.append("iso8601_offset")
        else:
            cls.append("iso8601_naive")
        if has_frac:
            cls.append("iso8601_with_fractional")
        if colon == 0:
            cls.append("iso8601_t_no_colon")
        # Catch tz-abbrev like "...Z PST" or "...+0000 PST" — has a space
        # in the tail AND no offset/Z detected AND letters present after
        # the time.
        if space > 0 and not iso_offset_signal and not ends_Z:
            cls.append("iso8601_t_with_tz_abbrev_candidate")
    elif slash > 0:
        if colon > 0:
            cls.append("slash_date_with_time")
        else:
            cls.append("slash_date_only")
    elif hyph > 0 and colon == 0 and slash == 0:
        cls.append("date_only_candidate")
    elif space > 0 and colon > 0 and T_count == 0:
        cls.append("space_separated_datetime_candidate")
    elif digit_count == length and length > 0:
        if length == 10:
            cls.append("epoch_seconds_string")
        elif length == 13:
            cls.append("epoch_milliseconds_string")
        elif length > 13:
            cls.append("epoch_large_string")
        else:
            cls.append("all_digits_short_string")
    elif letter_count > 0 and hyph > 0:
        cls.append("text_with_month_name_candidate")
    else:
        cls.append("nonstandard_string")

    if not cls:
        cls.append("unknown_string")
    return cls



def _length_bucket(n: int) -> str:
    if n < 10:
        return "lt_10"
    if n < 15:
        return "lt_15"
    if n < 20:
        return "lt_20"
    if n < 25:
        return "lt_25"
    if n < 30:
        return "lt_30"
    return "ge_30"


# ---------------------------------------------------------------------------
# HTTP fetch (never logs URL or token).
# ---------------------------------------------------------------------------


def _fetch(url: str, token: str) -> Tuple[Optional[int], Any]:
    """Fetch a URL with Basic auth. Never logs URL or token value."""
    try:
        r = urllib.request.Request(url, headers={"Accept": "application/json"})
        token_b64 = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        r.add_header("Authorization", f"Basic {token_b64}")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(r, timeout=TIMEOUT_S, context=ctx) as resp:
            return int(getattr(resp, "status", 200)), resp.read()
    except urllib.error.HTTPError as e:
        return int(e.code), "http_error"
    except urllib.error.URLError:
        return None, "url_error"
    except TimeoutError:
        return None, "timeout"
    except Exception as e:
        # Catch ValueError from urlopen on a malformed URL, etc. Do NOT
        # include the URL or any wrapper object — only the error class name.
        return None, f"unknown_error_{type(e).__name__}"


# ---------------------------------------------------------------------------
# Defensive redaction (catches any accidental long-string echo).
# ---------------------------------------------------------------------------


def _redact(out: Any) -> Any:
    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(x) for x in obj]
        if isinstance(obj, str):
            if len(obj) >= 40 and "/" not in obj and " " not in obj:
                return "<redacted_long_string>"
            return obj
        return obj

    return walk(out)


# ---------------------------------------------------------------------------
# Main probe.
# ---------------------------------------------------------------------------


def _run() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "auth": {},
        "pagination_probe": {},
        "timestamp_probe": {},
    }

    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    out["auth"]["token_present"] = bool(token)
    out["auth"]["which_env_var"] = (
        "ACN_API_TOKEN" if os.environ.get("ACN_API_TOKEN")
        else ("ACNPORTAL_TOKEN" if os.environ.get("ACNPORTAL_TOKEN") else "none")
    )
    if not token:
        out["auth"]["auth_outcome"] = "no_token_in_env"
        return _redact(out)

    # ------------------------------------------------------------------
    # PAGINATION PROBE
    # ------------------------------------------------------------------
    page1_url = f"{BASE_URL}?page=1&max_results={PAGE_SIZE}"
    page1_shape = _url_shape(page1_url)
    out["pagination_probe"]["page1_url_shape"] = page1_shape

    status1, body1 = _fetch(page1_url, token)
    out["pagination_probe"]["page1_status"] = status1
    out["auth"]["auth_outcome"] = (
        f"http_{status1}" if status1 is not None else "no_status"
    )
    if status1 is not None:
        out["auth"]["sanitized_http_status"] = int(status1)
    else:
        out["auth"]["sanitized_http_status"] = None

    if status1 != 200 or not isinstance(body1, bytes):
        out["pagination_probe"]["verdict"] = (
            f"page1_not_200_status_{status1}"
        )
        return _redact(out)

    try:
        payload1 = json.loads(body1.decode("utf-8"))
    except Exception as e:
        out["pagination_probe"]["verdict"] = (
            f"page1_json_parse_error_{type(e).__name__}"
        )
        return _redact(out)

    raw_next: Any = None
    if isinstance(payload1, dict):
        links = payload1.get("_links")
        if isinstance(links, dict):
            raw_next = links.get("next")

    if isinstance(raw_next, dict):
        out["pagination_probe"]["_links_next_shape"] = {
            "type": "dict",
            "dict_key_names": sorted(raw_next.keys()),
            "url_bearing_key_present": "href" in raw_next,
            "value_type_per_key": {
                k: _type_tag(raw_next[k]) for k in raw_next
            },
        }
        candidate = raw_next.get("href")
        href: Optional[str] = (
            candidate if isinstance(candidate, str) and len(candidate) > 0 else None
        )
    else:
        out["pagination_probe"]["_links_next_shape"] = {"type": _type_tag(raw_next)}
        href = None

    if href is None:
        out["pagination_probe"]["verdict"] = "no_href_extractable"
        return _redact(out)

    # CRITICAL: capture href shape WITHOUT storing the href value.
    href_shape = _url_shape(href)
    out["pagination_probe"]["href_shape"] = href_shape

    # Issue GET to the href as returned by the API.
    href_status, _ = _fetch(href, token)
    out["pagination_probe"]["href_request_status"] = href_status

    # Reconstruct a URL manually using the known BASE_URL pattern.
    candidate2_url = f"{BASE_URL}?page=2&max_results={PAGE_SIZE}"
    candidate2_shape = _url_shape(candidate2_url)
    out["pagination_probe"]["reconstructed_url_shape"] = candidate2_shape
    candidate2_status, _ = _fetch(candidate2_url, token)
    out["pagination_probe"]["reconstructed_url_status"] = candidate2_status

    # Structural comparison (page 1 vs href vs reconstructed).
    page1_keys = set(page1_shape.get("query_key_names", []))
    href_keys = set(href_shape.get("query_key_names", []))
    out["pagination_probe"]["href_query_keys_added"] = sorted(href_keys - page1_keys)
    out["pagination_probe"]["href_query_keys_removed"] = sorted(page1_keys - href_keys)
    out["pagination_probe"]["href_path_equal_to_PAGE_URL_path"] = (
        href_shape.get("path_equal_to_BASE_URL_path")
        == page1_shape.get("path_equal_to_BASE_URL_path")
    )
    out["pagination_probe"]["href_host_equal_to_PAGE_URL_host"] = (
        href_shape.get("host_equal_to_ev_caltech_edu")
        == page1_shape.get("host_equal_to_ev_caltech_edu")
    )
    out["pagination_probe"]["href_leading_class"] = href_shape.get("leading_class")
    out["pagination_probe"]["page1_leading_class"] = page1_shape.get("leading_class")
    out["pagination_probe"]["href_path_depth"] = href_shape.get("path_depth")
    out["pagination_probe"]["page1_path_depth"] = page1_shape.get("path_depth")
    out["pagination_probe"]["href_scheme"] = href_shape.get("scheme")
    out["pagination_probe"]["href_host_equal_to_ev_caltech_edu"] = (
        href_shape.get("host_equal_to_ev_caltech_edu")
    )

    # Verdict.
    if href_status == 200 and candidate2_status == 200:
        verdict = "both_200_href_is_valid"
    elif href_status != 200 and candidate2_status == 200:
        # The HATEOAS href the API emitted is broken, but manual page
        # numbering works. Cause D: API-generated invalid HATEOAS link.
        verdict = "href_fails_reconstructed_succeeds_api_emits_invalid_href"
    elif href_status == 200 and candidate2_status != 200:
        verdict = "href_succeeds_reconstructed_fails_unexpected"
    else:
        verdict = "both_fail_check_auth_or_host"

    # If leading_class is path_relative_no_slash, urljoin would produce
    # a wrong URL. Flag this regardless of whether the request happened
    # to succeed for some other reason.
    leading = href_shape.get("leading_class")
    if leading in ("path_relative_no_slash", "path_relative_with_slash"):
        verdict = (
            f"{verdict}_AND_href_leading_is_{leading}_urljoin_will_mangle"
        )
    out["pagination_probe"]["verdict"] = verdict

    # ------------------------------------------------------------------
    # TIMESTAMP PROBE (uses page-1 records only; bounded; sanitized)
    # ------------------------------------------------------------------
    items: List[Any] = []
    if isinstance(payload1, dict):
        raw_items = payload1.get("_items")
        if isinstance(raw_items, list):
            items = raw_items
    elif isinstance(payload1, list):
        items = payload1

    out["timestamp_probe"]["n_records_examined"] = len(items)

    conn_groups: Dict[Tuple, int] = {}
    disc_groups: Dict[Tuple, int] = {}
    conn_cls: Dict[str, int] = {}
    disc_cls: Dict[str, int] = {}
    conn_lens: Dict[str, int] = {}
    disc_lens: Dict[str, int] = {}
    conn_seen = 0
    disc_seen = 0

    for rec in items:
        if not isinstance(rec, dict):
            continue
        conn = rec.get("connectionTime")
        disc = rec.get("disconnectTime")

        if conn is not None:
            conn_seen += 1
            f = _string_features(conn)
            conn_groups[f] = conn_groups.get(f, 0) + 1
            for c in _classify_features(f):
                conn_cls[c] = conn_cls.get(c, 0) + 1
            if f and len(f) > 1:
                bucket = _length_bucket(f[0])
                conn_lens[bucket] = conn_lens.get(bucket, 0) + 1

        if disc is not None:
            disc_seen += 1
            f = _string_features(disc)
            disc_groups[f] = disc_groups.get(f, 0) + 1
            for c in _classify_features(f):
                disc_cls[c] = disc_cls.get(c, 0) + 1
            if f and len(f) > 1:
                bucket = _length_bucket(f[0])
                disc_lens[bucket] = disc_lens.get(bucket, 0) + 1

    out["timestamp_probe"]["connectionTime_seen"] = conn_seen
    out["timestamp_probe"]["disconnectTime_seen"] = disc_seen
    out["timestamp_probe"]["connectionTime_n_distinct_shapes"] = len(conn_groups)
    out["timestamp_probe"]["disconnectTime_n_distinct_shapes"] = len(disc_groups)
    # Build deterministic, hashable string keys for each feature tuple
    # so we can safely invert the dict (use the hashable key as the OUTER
    # key, the feature-dict as the inner value). The tuple itself is the
    # source of truth; _features_to_dict is purely a presentation layer.
    conn_sigs: Dict[str, int] = {}
    conn_sig_features: Dict[str, Dict[str, Any]] = {}
    for k, v in conn_groups.items():
        d = _features_to_dict(k)
        # json.dumps with sorted keys is deterministic and only contains
        # primitives, so it produces a stable, hashable, JSON-safe string.
        sig_key = json.dumps(d, sort_keys=True, default=str)
        conn_sigs[sig_key] = v
        conn_sig_features[sig_key] = d
    disc_sigs: Dict[str, int] = {}
    disc_sig_features: Dict[str, Dict[str, Any]] = {}
    for k, v in disc_groups.items():
        d = _features_to_dict(k)
        sig_key = json.dumps(d, sort_keys=True, default=str)
        disc_sigs[sig_key] = v
        disc_sig_features[sig_key] = d
    out["timestamp_probe"]["connectionTime_shape_signatures"] = conn_sig_features
    out["timestamp_probe"]["disconnectTime_shape_signatures"] = disc_sig_features
    out["timestamp_probe"]["connectionTime_format_classifications"] = conn_cls
    out["timestamp_probe"]["disconnectTime_format_classifications"] = disc_cls
    out["timestamp_probe"]["connectionTime_length_buckets"] = conn_lens
    out["timestamp_probe"]["disconnectTime_length_buckets"] = disc_lens

    return _redact(out)


if __name__ == "__main__":
    result = _run()
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True, default=str))
    sys.stdout.write("\n")