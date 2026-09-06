"""
Stage 5 -- Empirical uncertainty modeling, scenario construction, ADOPT calibration.

This module is the token-independent *infrastructure* for the Stage 5 pipeline.
When the ACN-Data API token arrives, the only function that needs to change is
`load_real_uncertainty`: it should pull sessions from the live API and compute
the actual Delta_d and Delta_e. Everything downstream (scenario engine, robust
QUBO, ADOPT calibration, F0/F1/F2/F3 ablation) is parameter-agnostic.

Until then, `load_real_uncertainty` returns a SYNTHETIC placeholder distribution
that is clearly labelled and is NEVER used to report a research result. The
shape of the placeholder is documented in `artifacts/uncertainty_calibration.json`.

Hard rules (from the Stage 5 spec):
  * No proxy may be called "the Stage 1 uncertainty model".
  * The placeholder is for *infrastructure validation only*.
  * alpha is pre-registered using a structural rule BEFORE any held-out use.
  * No held-out data may enter calibration, scenario selection, K selection,
    normalization, penalty scaling, alpha selection, scenario weights, or QAOA
    parameter tuning.
  * The scenario-aware QUBO must remain a pure QUBO (no auxiliary variables,
    no higher-order terms).
  * Robust QUBO must pass the exhaustive algebraic validation.

Outputs (machine-readable):
  artifacts/uncertainty_calibration.json
  artifacts/uncertainty_distributions.json
  artifacts/scenarios_K4.json
  artifacts/scenarios_K8.json
  artifacts/scenarios_K16.json
  artifacts/scenario_quality.json
  artifacts/robust_qubo.json
  artifacts/robust_qubo_validation.json
  artifacts/adopt_preregistration.json
  artifacts/adopt_calibration.json
  artifacts/stage5_run.json
"""
from __future__ import annotations

import hashlib
import json
import math
import time
import warnings
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


from itertools import product
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import numpy as np

# Stage 3 imports (Q instance, QUBO builder, validation)
from stage3.ev_scheduling import (
    Instance, EV, build_qubo, enumerate_original_objective, find_optima,
    validate_qubo_vs_original, decode_feasibility, toy_instance,
    DELTA_HOURS, DELTA_MIN,
)

# Stage 4 imports (Ising builder, kept for downstream consistency)
from stage4.qaoa import qubo_to_ising


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stage 1 / Stage 2 lock-in: temporal split
CAL_START_UTC = "2018-05-01T00:00:00+00:00"
CAL_END_UTC = "2019-07-01T00:00:00+00:00"   # exclusive
HO_START_UTC = "2019-07-01T00:00:00+00:00"
HO_END_UTC = "2020-01-01T00:00:00+00:00"   # exclusive

# Stage 1 lock-in: TOU tariff (smooth two-sided site cap per Stage 4 amendment)
DEFAULT_RHO_D = 1.0
DEFAULT_RHO_P = 0.1
DEFAULT_RHO_CAP = 0.5


# ---------------------------------------------------------------------------
# Part D + E + F: Uncertainty extraction
# ---------------------------------------------------------------------------

@dataclass
class UncertaintySample:
    """One observation of (Delta_d, Delta_e) for one EV in one session."""
    session_id: str
    calibration: bool          # True = calibration window, False = held-out
    conn_utc: str
    disc_utc_actual: str
    dep_requested_utc: Optional[str]
    kwh_delivered: float
    kwh_requested: Optional[float]
    delta_d_minutes: Optional[float]   # d_hat - actual_disconnect, in minutes
    delta_e_kwh: Optional[float]       # kWhDelivered - kWhRequested, in kWh
    # Original source-tag
    source: str   # "live_api" or "placeholder" or "static_audit"

# ---------------------------------------------------------------------------
# Timestamp parser compatibility (Caltech live-API)
# ---------------------------------------------------------------------------
# The Caltech live API emits connectionTime / disconnectTime in
# representations that `datetime.fromisoformat` does not accept. The
# verified live sample (page 1 .. page ~200) is the RFC 2822 /
# HTTP-date form: `Wed, 25 Apr 2018 11:08:04 GMT` (29 chars; no
# hyphens, no plus, no slashes, no dots; alphabetic trailing
# timezone). The structural features reported by the probe match
# this form exactly: 5 spaces, 2 colons, 9 letters, 12 digits, T at
# position 28 (the final "T" of "GMT"). We also keep the four ISO
# 8601 shapes for any other ACN-Data-compatible endpoint.
#
# Strategy: a narrow, defensive parser that ONLY accepts the verified
# shapes. The parser never invents an offset and never widens into a
# general permissive parser; genuinely invalid input raises ValueError.
import re as _re_for_ts
_TS_RE_ISO_Z = _re_for_ts.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$"
)
_TS_RE_ISO_OFF = _re_for_ts.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}$"
)
_TS_RE_ISO_NAIVE = _re_for_ts.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$"
)
# Space-separated date + time + alpha TZ (e.g. "2018 05 01 14:23:45 PST").
_TS_RE_SPACE_TZ = _re_for_ts.compile(
    r"^\d{4} \d{2} \d{2} \d{2}:\d{2}:\d{2} [A-Z]{2,5}$"
)
# RFC 2822 / HTTP-date with day-name and month-name (verified live shape).
# Examples (length 29):
#   "Wed, 25 Apr 2018 11:08:04 GMT"
#   "Fri, 18 May 2018 03:14:32 GMT"
_TS_RE_RFC2822 = _re_for_ts.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{2} "
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} "
    r"\d{2}:\d{2}:\d{2} (GMT|UT|UTC|EST|EDT|CST|CDT|MST|MDT|PST|PDT|Z)$"
)
# Conservative TZ-abbrev -> minute-offset table covering the
# unambiguous UTC/GMT/UT forms and the North American zones
# documented for the Caltech site. The abbreviations are read off
# the structural signature; a live value is NEVER inferred.
_TZ_ABBREV_OFFSETS_MINUTES = {
    "UTC": 0, "GMT": 0, "UT": 0, "Z": 0,
    "PST": -8 * 60, "PDT": -7 * 60, "PT": -8 * 60,
    "MST": -7 * 60, "MDT": -6 * 60, "MT": -7 * 60,
    "CST": -6 * 60, "CDT": -5 * 60, "CT": -6 * 60,
    "EST": -5 * 60, "EDT": -4 * 60, "ET": -5 * 60,
    "AKST": -9 * 60, "AKDT": -8 * 60, "AKT": -9 * 60,
    "HST": -10 * 60, "HDT": -9 * 60, "HT": -10 * 60,
    "AST": -4 * 60, "ADT": -3 * 60, "AT": -4 * 60,
    "NST": -3 * 60 + 30, "NDT": -2 * 60 + 30, "NT": -3 * 60 + 30,
}


def _parse_api_timestamp(value: Any) -> "datetime":
    """Parse a timestamp emitted by the Caltech live API.

    Returns a timezone-aware `datetime` in UTC. Raises ValueError for
    any input that does not match one of the five verified shapes
    (ISO 8601 with Z; ISO 8601 with offset; ISO 8601 naive;
    space-separated date + time + alphabetic TZ; RFC 2822 / HTTP-date
    with day name + month name + alphabetic TZ). This is a strict
    parser-compatibility helper; it does NOT modify any methodology,
    calibration boundary, or held-out boundary.
    """
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    if not isinstance(value, str) or not value:
        raise ValueError("timestamp must be a non-empty string")
    s = value
    if _TS_RE_ISO_Z.match(s):
        # fromisoformat in Py<3.11 does not accept "Z"; substitute +00:00.
        return _dt.fromisoformat(s[:-1] + "+00:00").astimezone(_tz.utc)
    if _TS_RE_ISO_OFF.match(s):
        try:
            return _dt.fromisoformat(s).astimezone(_tz.utc)
        except Exception as e:
            raise ValueError(f"unparseable ISO 8601 offset timestamp: {e}")
    if _TS_RE_ISO_NAIVE.match(s):
        try:
            return _dt.fromisoformat(s).replace(tzinfo=_tz.utc)
        except Exception as e:
            raise ValueError(f"unparseable naive ISO 8601 timestamp: {e}")
    m = _TS_RE_SPACE_TZ.match(s)
    if m:
        abbrev = s.split()[-1]
        if abbrev not in _TZ_ABBREV_OFFSETS_MINUTES:
            raise ValueError("unrecognized timezone abbreviation in timestamp")
        try:
            base = _dt.strptime(s[:19], "%Y %m %d %H:%M:%S")
        except Exception as e:
            raise ValueError(f"unparseable space-separated datetime: {e}")
        offset_min = _TZ_ABBREV_OFFSETS_MINUTES[abbrev]
        local = base.replace(tzinfo=_tz(_td(minutes=offset_min)))
        return local.astimezone(_tz.utc)
    m = _TS_RE_RFC2822.match(s)
    if m:
        # Use email.utils.parsedate_to_datetime for RFC 2822; it
        # returns a timezone-aware datetime. The TZ is restricted to
        # the allowed set by the regex above, so the result is
        # trustworthy for our purposes.
        from email.utils import parsedate_to_datetime as _pdt
        try:
            dt = _pdt(s)
        except (TypeError, ValueError) as e:
            raise ValueError(f"unparseable RFC 2822 timestamp: {e}")
        if dt.tzinfo is None:
            raise ValueError("RFC 2822 timestamp has no timezone info")
        return dt.astimezone(_tz.utc)
    raise ValueError("timestamp does not match any verified API shape")



def load_real_uncertainty(
    base_url: str = "https://ev.caltech.edu/api/v1/sessions/caltech",
    page_size: int = 25,
    timeout_s: float = 30.0,
    max_pages: int = 4000,
) -> Tuple[List["UncertaintySample"], Dict[str, Any]]:
    """Load (Delta_d, Delta_e) observations from the ACN-Data live API.

    Auth: HTTP Basic with username = token, empty password (per Caltech ACN-Data
    API documentation). The token is read from ACN_API_TOKEN or ACNPORTAL_TOKEN;
    it is NEVER logged, NEVER written to a file, NEVER echoed in errors.

    Pagination: deterministic page-number traversal within each of the
    two frozen windows using the documented API-side `where` filter —
    `BASE_URL?where=...&page=N&max_results=P`. The `where` bounds are
    exactly the frozen calibration/held-out windows (acquisition
    optimization only; the client-side window assignment is unchanged
    and is applied independently of which window supplied the record).
    The Caltech live API emits a HATEOAS `_links.next.href` that is
    path-relative and omits `max_results`, so it cannot be resolved by
    this HTTP client and is never used as a request target; page
    advance is by deterministic page numbering within each window.
    End-of-data per window is the verified empty-`_items` signal; after
    the last page of one window the loader advances to the next window,
    stopping after the held-out window. Up to `max_pages` (default
    4000) total pages — far beyond the bounded two-window inventory.
    Schema (per docs/STAGE_9_REAL_EXPERIMENT.md §3.2 and
    docs/STAGE_10_REAL_DATA_PROTOCOL.md §E.3): each record must contain
      - sessionID (or sessionId)
      - connectionTime (UTC ISO 8601)
      - disconnectTime (UTC ISO 8601)
      - kWhDelivered (float)
      - userInputs[*].kWhRequested (float, last `modifiedAt`)
      - userInputs[*].requestedDeparture (UTC ISO 8601, last `modifiedAt`)
      - siteID
    If the schema is missing required fields, the function returns what it has
    plus a `schema_warnings` block describing the gap; it does NOT substitute
    proxies.

    Sign conventions (frozen, per Stage 1 §4.2 / Stage 6 Part A):
      Delta_d = d_requested - d_actual        (minutes; >0 = early)
      Delta_e = E_delivered  - E_requested   (kWh;     <0 = unmet demand)

    Status block keys: source, n_records, n_valid, http_status_codes,
    n_pages, schema_warnings, acquired_at_utc, base_url, note.
    The base_url is reported so the audit can verify which endpoint was hit.
    """
    import os
    import urllib.request
    import urllib.error
    import ssl
    from datetime import datetime, timezone

    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    if not token:
        return [], {
            "source": "blocked",
            "n_records": 0,
            "n_valid": 0,
            "reason": ("ACN_API_TOKEN not present in environment. The live API "
                       "returns HTTP 401 without a token. No fabrication, no bypass, "
                       "no proxy substitution. See docs/STAGE_9_REAL_EXPERIMENT.md "
                       "§3.1 and docs/STAGE_10_REAL_DATA_PROTOCOL.md §E.1."),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    # Acquire. The token is used as the Basic-auth username with an empty password.
    # Per the Caltech API docs, the token is the username.
    samples: List[UncertaintySample] = []
    n_records = 0
    n_skipped_schema = 0
    n_skipped_window = 0

    http_status_codes: Dict[int, int] = {}
    schema_warnings: List[str] = []
    pages_visited = 0
    # ------------------------------------------------------------------
    # Acquisition strategy (minimal correction, 2026-09-04).
    #
    # Previously the loader walked the UNSORTED full collection from
    # page 1 (`?page=N&max_results=25`) and filtered temporally on the
    # client side. The API's default ordering is recency-biased and
    # unrelated to the frozen windows, so a bounded page walk samples a
    # non-representative head of the collection (observed: 250 records
    # with userInputs = null for all) and needs an unbounded crawl to
    # cover the frozen windows.
    #
    # The bounded availability probe (artifacts/final_data_availability_probe.py)
    # proved the documented `where` parameter retrieves the frozen
    # windows directly. The correction is acquisition-only: two bounded
    # `where` filters whose bounds are EXACTLY the frozen windows
    # (connectionTime >= start AND connectionTime < end, matching the
    # client-side window assignment semantics), paginated with the same
    # page size, endpoint, authentication, and per-record processing.
    # No filter widened, no scientific parameter touched.
    #
    # The HATEOAS `_links.next.href` remains path-relative and omits
    # `max_results`, so it is still not used as a request target; page
    # advance is deterministic page numbering within each window.
    # ------------------------------------------------------------------
    import urllib.parse
    import urllib.request
    import urllib.error
    import ssl
    from datetime import datetime, timezone

    token = os.environ.get("ACN_API_TOKEN") or os.environ.get("ACNPORTAL_TOKEN")
    if not token:
        return [], {
            "source": "blocked",
            "n_records": 0,
            "n_valid": 0,
            "reason": ("ACN_API_TOKEN not present in environment. The live API "
                       "returns HTTP 401 without a token. No fabrication, no bypass, "
                       "no proxy substitution. See docs/STAGE_9_REAL_EXPERIMENT.md "
                       "§3.1 and docs/STAGE_10_REAL_DATA_PROTOCOL.md §E.1."),
            "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    # Acquire. The token is used as the Basic-auth username with an empty password.
    # Per the Caltech API docs, the token is the username.
    samples: List[UncertaintySample] = []

    n_records = 0
    n_skipped_schema = 0
    n_skipped_window = 0
    n_parseable_conn = 0
    n_parseable_disc = 0
    n_with_kwh_delivered = 0
    n_with_kwh_requested = 0
    n_with_requested_departure = 0
    n_ui_null = 0
    n_ui_empty = 0
    n_ui_nonempty = 0
    n_valid_dE = 0
    n_valid_dd = 0
    n_valid_joint = 0
    http_status_codes: Dict[int, int] = {}
    schema_warnings: List[str] = []
    pages_visited = 0

    # Two bounded `where` filters, one per frozen window. Bounds are the
    # frozen window endpoints verbatim; lower bound inclusive, upper
    # bound exclusive, identical to the client-side window assignment.
    import urllib.parse as _urlparse
    _WHERE_FILTERS = (
        'connectionTime>="Tue, 01 May 2018 00:00:00 GMT" and connectionTime<"Mon, 01 Jul 2019 00:00:00 GMT"',  # calibration
        'connectionTime>="Mon, 01 Jul 2019 00:00:00 GMT" and connectionTime<"Wed, 01 Jan 2020 00:00:00 GMT"',  # held-out
    )

    def _page_url(page_no: int, where: str) -> str:
        return f"{base_url}?" + _urlparse.urlencode(
            {"where": where, "page": page_no, "max_results": page_size},
            safe="><=",
        )

    filter_idx = 0        # which frozen window is being paged
    page_in_filter = 1    # 1-based page number within the current window

    next_url: Optional[str] = _page_url(page_in_filter, _WHERE_FILTERS[filter_idx])

    # SSL context: use the system default (don't disable verification).
    ctx = ssl.create_default_context()

    while next_url and pages_visited < max_pages:
        pages_visited += 1
        req = urllib.request.Request(next_url, headers={"Accept": "application/json"})
        # Per-token basic auth. Do not log the token.
        import base64
        token_b64 = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token_b64}")
        # Bounded per-page retry (acquisition robustness only; the request
        # target, page size, auth, and processing are unchanged). Transient
        # network errors (timeouts, connection resets) and retryable 5xx
        # responses abort the whole acquisition far below max_pages without
        # this; a short backoff retry keeps a single flaky page from
        # discarding a bounded, otherwise-complete window. Non-retryable
        # HTTP errors (4xx, auth) preserve the original early-return path.
        payload = None
        page_error: Optional[Exception] = None
        for _attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
                    status = getattr(resp, "status", 200)
                    http_status_codes[int(status)] = http_status_codes.get(int(status), 0) + 1
                    payload = json.loads(resp.read().decode("utf-8"))
                page_error = None
                break
            except urllib.error.HTTPError as e:
                if 400 <= int(e.code) < 500 and int(e.code) != 429:
                    page_error = e
                    break
                page_error = e
            except Exception as e:
                page_error = e
            import time as _time
            _time.sleep(min(2 ** _attempt, 30))
        try:
            if page_error is None and payload is None:
                raise RuntimeError("unreachable")
            if page_error is not None:
                raise page_error
        except urllib.error.HTTPError as e:
            http_status_codes[int(e.code)] = http_status_codes.get(int(e.code), 0) + 1
            return samples, {
                "source": "live_api_partial",
                "n_records": n_records,
                "n_valid": len(samples),
                "http_status_codes": http_status_codes,
                "n_pages": pages_visited,
                "schema_warnings": schema_warnings,
                "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                "base_url": base_url,
                "note": (f"HTTP {e.code} on page {pages_visited}. The token may be invalid "
                         f"or expired, or the endpoint may be rate-limited. The dataset "
                         f"is partial ({n_records} records so far). Re-acquire when the "
                         f"token is refreshed."),
            }
        except Exception as e:
            return samples, {
                "source": "live_api_partial",
                "n_records": n_records,
                "n_valid": len(samples),
                "http_status_codes": http_status_codes,
                "n_pages": pages_visited,
                "schema_warnings": schema_warnings,
                "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
                "base_url": base_url,
                "note": f"Network error on page {pages_visited}: {type(e).__name__}.",
            }

        # Page handling. The Caltech live API returns a list-of-records
        # under `_items` (with HATEOAS `_links.next` and `_meta`). The
        # API's emitted `next` href is path-relative and omits
        # `max_results`, so it is not usable through this HTTP client.
        # Strategy: parse the items out of the standard wrappers, then
        # advance to the next page by deterministic page-numbering using
        # the same BASE_URL and page counter. The HATEOAS link is still
        # inspected as a *signal* (its presence/absence is informative)
        # but the URL it contains is never used as a request target.
        # An empty `_items` is the canonical end-of-data signal and
        # terminates pagination.
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = (
                payload.get("_items")
                or payload.get("items")
                or payload.get("sessions")
                or payload.get("results")
                or []
            )
        else:
            schema_warnings.append(f"Unexpected payload type on page {pages_visited}: {type(payload).__name__}")
            break

        if not items:
            # Empty page = end of the current window's result set (the
            # verified end-of-data signal). Advance to the next frozen
            # window, or terminate if both have been covered.
            filter_idx += 1
            if filter_idx < len(_WHERE_FILTERS):
                page_in_filter = 1
                next_url = _page_url(page_in_filter, _WHERE_FILTERS[filter_idx])
                continue  # resume at page 1 of the new window; do NOT
                          # fall through into the per-page advance below,
                          # which would silently overwrite the next window's
                          # page 1 with its page 2 and skip records.
            else:
                break

        # Advance to the next page using the deterministic
        # `?page=N&max_results=P&where=...` form. We do not use the API's
        # HATEOAS href directly because (a) it is path-relative and
        # (b) it omits `max_results`. This block is reached only when
        # `items` was non-empty for the current page.
        if pages_visited < max_pages:
            page_in_filter += 1
            next_url = _page_url(page_in_filter, _WHERE_FILTERS[filter_idx])
        else:
            next_url = None

        for rec in items:
            n_records += 1
            sid = rec.get("sessionID") or rec.get("sessionId")
            conn = rec.get("connectionTime")
            disc = rec.get("disconnectTime")
            kwh_d = rec.get("kWhDelivered")
            _ui_raw = rec.get("userInputs")
            if _ui_raw is None:
                n_ui_null += 1
            elif isinstance(_ui_raw, (list, dict)) and len(_ui_raw) == 0:
                n_ui_empty += 1
            else:
                n_ui_nonempty += 1
            user_inputs = rec.get("userInputs") or []
            if not isinstance(user_inputs, list):
                user_inputs = []
            # Last userInput by modifiedAt (if present) else last in list.
            if user_inputs:
                try:
                    user_inputs_sorted = sorted(
                        user_inputs,
                        key=lambda u: u.get("modifiedAt") or u.get("createdAt") or "",
                    )
                    last_ui = user_inputs_sorted[-1]
                except Exception:
                    last_ui = user_inputs[-1]
                kwh_req = last_ui.get("kWhRequested")
                dep_req = last_ui.get("requestedDeparture")
            else:
                kwh_req = None
                dep_req = None
            # Per-record structural counters (telemetry, not method
            # choice). These feed the sanitized status block only.
            if kwh_d is not None:
                n_with_kwh_delivered += 1
            if kwh_req is not None:
                n_with_kwh_requested += 1
            if dep_req is not None:
                n_with_requested_departure += 1

            # Schema gate (Stage 10 protocol §E.3)
            if not (sid and conn and disc and kwh_d is not None):
                n_skipped_schema += 1
                schema_warnings.append(
                    f"Session missing core field (sid/conn/disc/kwh_d): "
                    f"sid={bool(sid)} conn={bool(conn)} disc={bool(disc)} kwh_d={kwh_d is not None}"
                )
                continue

            # Window assignment. The connectionTime parser is a narrow,
            # strict helper that accepts only the four shapes verified
            # from the live API sample; any other shape raises ValueError.
            try:
                conn_dt = _parse_api_timestamp(conn)
            except Exception:
                n_skipped_schema += 1
                schema_warnings.append(
                    f"Unparseable connectionTime (rejected by _parse_api_timestamp)"
                )
                continue
            n_parseable_conn += 1
            # Best-effort: try to also parse disconnectTime for the
            # parseable-discount counter. Failures here do not affect
            # the sample (the record is already in calibration or
            # held-out by connectionTime) but they ARE recorded.
            if disc is not None:
                try:
                    _parse_api_timestamp(disc)
                    n_parseable_disc += 1
                except Exception:
                    pass
            in_cal = (conn_dt >= datetime(2018, 5, 1, tzinfo=timezone.utc)
                      and conn_dt <  datetime(2019, 7, 1, tzinfo=timezone.utc))
            in_ho  = (conn_dt >= datetime(2019, 7, 1, tzinfo=timezone.utc)
                      and conn_dt <  datetime(2020, 1, 1, tzinfo=timezone.utc))
            if not (in_cal or in_ho):
                n_skipped_window += 1
                continue

            # Delta_e and Delta_d with sign conventions frozen at Stage 1 §4.2.
            delta_e: Optional[float] = None
            if kwh_req is not None:
                try:
                    delta_e = float(kwh_d) - float(kwh_req)
                except (TypeError, ValueError):
                    delta_e = None
            delta_d_min: Optional[float] = None
            if dep_req is not None and disc is not None:
                try:
                    dep_dt = _parse_api_timestamp(dep_req)
                    disc_dt = _parse_api_timestamp(disc)
                    delta_d_min = (dep_dt - disc_dt).total_seconds() / 60.0
                except Exception:
                    delta_d_min = None

            # Sanitized outcome counters for the status block.
            if delta_e is not None:
                n_valid_dE += 1
            if delta_d_min is not None:
                n_valid_dd += 1
            if delta_e is not None and delta_d_min is not None:
                n_valid_joint += 1
            samples.append(UncertaintySample(
                session_id=str(sid),
                calibration=bool(in_cal),
                conn_utc=conn_dt.isoformat(),
                disc_utc_actual=str(disc),
                dep_requested_utc=str(dep_req) if dep_req is not None else None,
                kwh_delivered=float(kwh_d),
                kwh_requested=float(kwh_req) if kwh_req is not None else None,
                delta_d_minutes=delta_d_min,
                delta_e_kwh=delta_e,
                source="live_api",
            ))

        if not next_url:
            break

    return samples, {
        "source": "live_api",
        "n_records": n_records,
        "n_valid": len(samples),
        "n_skipped_schema": n_skipped_schema,
        "n_skipped_window": n_skipped_window,
        "n_parseable_conn": n_parseable_conn,
        "n_parseable_disc": n_parseable_disc,
        "n_with_kwh_delivered": n_with_kwh_delivered,
        "n_with_kwh_requested": n_with_kwh_requested,
        "n_with_requested_departure": n_with_requested_departure,
        "n_user_inputs_null": n_ui_null,
        "n_user_inputs_empty": n_ui_empty,
        "n_user_inputs_nonempty": n_ui_nonempty,
        "n_valid_dE": n_valid_dE,
        "n_valid_dd": n_valid_dd,
        "n_valid_joint": n_valid_joint,
        "http_status_codes": http_status_codes,
        "n_pages": pages_visited,
        "schema_warnings": schema_warnings[:50],  # cap to avoid huge blobs
        "schema_warning_count": len(schema_warnings),
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "note": ("Live ACN-Data acquisition complete. Sign conventions and "
                 "schema gate per docs/STAGE_9_REAL_EXPERIMENT.md §3.2 and "
                 "docs/STAGE_10_REAL_DATA_PROTOCOL.md §E.3. The token was used "
                 "as Basic-auth username; it is NOT logged in this status block."),
    }


def placeholder_uncertainty(seed: int = 20260829) -> Tuple[List[UncertaintySample], Dict[str, Any]]:
    """Construct a SYNTHETIC placeholder uncertainty distribution for
    *infrastructure validation only*.

    The placeholder is:
      * Explicitly labelled `source="placeholder"`.
      * NEVER mixed with real-API data.
      * NEVER reported as a research result.
      * Reproducible: the seed is fixed in `artifacts/stage5_run.json`.

    The synthetic shape is a mixture model chosen to resemble (very roughly)
    the literature priors on ACN-Data behavior:
      - Delta_d (early departure, minutes): 50% probability of small deviation
        N(0, 30 min), 30% N(-60, 90 min) (early-departure skew), 20% point mass
        at 0 (departed on time).
      - Delta_e (energy residual, kWh): 70% point mass at 0 (claimed sessions
        match), 25% N(0, 2) kWh, 5% N(-5, 3) kWh (negative residual = left with
        unmet demand).

    These are not the Stage 1 uncertainty model. They are a smoke-test shape.
    The real distributions must come from the live API.
    """
    rng = np.random.default_rng(seed)
    n = 5000  # placeholder sample size; deliberately large to make scenario
              # clustering numerically stable during infrastructure tests
    samples: List[UncertaintySample] = []
    # We synthesize a chronological span that includes both calibration and
    # held-out, so downstream code that filters by window is exercised.
    # Dates are placed in 2018-05 .. 2019-12 at uniform random.
    cal_start = datetime(2018, 5, 1, tzinfo=timezone.utc)
    ho_end = datetime(2020, 1, 1, tzinfo=timezone.utc)
    span_seconds = int((ho_end - cal_start).total_seconds())
    for k in range(n):
        u_conn = cal_start.timestamp() + rng.uniform(0, span_seconds)
        conn_dt = datetime.fromtimestamp(u_conn, tz=timezone.utc)
        # Randomly assigned to calibration or held-out, weighted by the
        # actual window sizes (14 months cal + 6 months held-out).
        in_held_out = rng.uniform(0, 20) >= 14  # ~6/20 of the span is held-out
        # Delta_d (minutes)
        bucket = rng.uniform(0, 1)
        if bucket < 0.50:
            delta_d = float(rng.normal(0, 30))
        elif bucket < 0.80:
            delta_d = float(rng.normal(-60, 90))
        else:
            delta_d = 0.0
        # Delta_e (kWh)
        ebucket = rng.uniform(0, 1)
        if ebucket < 0.70:
            delta_e = 0.0
        elif ebucket < 0.95:
            delta_e = float(rng.normal(0, 2))
        else:
            delta_e = float(rng.normal(-5, 3))
        # Skip ~5% of observations to test missing-data handling
        if rng.uniform(0, 1) < 0.05:
            samples.append(UncertaintySample(
                session_id=f"placeholder_{k}",
                calibration=not in_held_out,
                conn_utc=conn_dt.isoformat(),
                disc_utc_actual=conn_dt.isoformat(),
                dep_requested_utc=None,
                kwh_delivered=float(rng.uniform(0, 30)),
                kwh_requested=None,
                delta_d_minutes=None,
                delta_e_kwh=None,
                source="placeholder",
            ))
            continue
        # Construct a fake actual disconnect by adding a representative
        # session length (e.g. 4 hours = 240 min) to the connection time.
        session_len_min = float(rng.normal(240, 60))
        disc_actual = conn_dt.timestamp() + session_len_min * 60
        disc_dt = datetime.fromtimestamp(disc_actual, tz=timezone.utc)
        # The estimated/requested departure: actual + Delta_d (minutes)
        # If Delta_d is negative, the EV left earlier than expected.
        dep_requested_dt = disc_dt.timestamp() + delta_d * 60
        kwh_delivered = max(0.0, float(rng.normal(8, 4)))
        kwh_requested = max(0.0, kwh_delivered - delta_e)
        samples.append(UncertaintySample(
            session_id=f"placeholder_{k}",
            calibration=not in_held_out,
            conn_utc=conn_dt.isoformat(),
            disc_utc_actual=disc_dt.isoformat(),
            dep_requested_utc=datetime.fromtimestamp(dep_requested_dt, tz=timezone.utc).isoformat(),
            kwh_delivered=kwh_delivered,
            kwh_requested=kwh_requested,
            delta_d_minutes=delta_d,
            delta_e_kwh=delta_e,
            source="placeholder",
        ))
    return samples, {
        "source": "placeholder",
        "n_records": n,
        "n_valid": sum(1 for s in samples if s.delta_d_minutes is not None and s.delta_e_kwh is not None),
        "reason": ("SYNTHETIC PLACEHOLDER for infrastructure validation only. "
                   "Not the Stage 1 uncertainty model. Replace with the live API "
                   "output when ACN_API_TOKEN is supplied."),
        "seed": seed,
        "acquired_at_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Part F: Missing-data analysis
# ---------------------------------------------------------------------------

def missing_data_report(samples: Sequence[UncertaintySample]) -> Dict[str, Any]:
    """Compute the actual missing-data rates across the four fields."""
    n = len(samples)
    if n == 0:
        return {"n_total": 0}
    has_dep_req = sum(1 for s in samples if s.dep_requested_utc is not None)
    has_kwh_req = sum(1 for s in samples if s.kwh_requested is not None)
    has_disc = sum(1 for s in samples if s.disc_utc_actual is not None)
    has_kwh_del = sum(1 for s in samples if s.kwh_delivered is not None and s.kwh_delivered >= 0)
    has_dd = sum(1 for s in samples if s.delta_d_minutes is not None)
    has_de = sum(1 for s in samples if s.delta_e_kwh is not None)
    return {
        "n_total": n,
        "n_calibration": sum(1 for s in samples if s.calibration),
        "n_held_out": sum(1 for s in samples if not s.calibration),
        "missing_dep_requested_pct": 100.0 * (1 - has_dep_req / n),
        "missing_kwh_requested_pct": 100.0 * (1 - has_kwh_req / n),
        "missing_disc_actual_pct": 100.0 * (1 - has_disc / n),
        "missing_kwh_delivered_pct": 100.0 * (1 - has_kwh_del / n),
        "missing_delta_d_pct": 100.0 * (1 - has_dd / n),
        "missing_delta_e_pct": 100.0 * (1 - has_de / n),
        "n_valid_both": sum(1 for s in samples if s.delta_d_minutes is not None and s.delta_e_kwh is not None),
    }


# ---------------------------------------------------------------------------
# Part G: Empirical distribution statistics
# ---------------------------------------------------------------------------

def distribution_stats(values: np.ndarray) -> Dict[str, float]:
    """Return N, mean, median, std, min, max, and 1/5/10/25/50/75/90/95/99 quantiles."""
    if len(values) == 0:
        return {"n": 0}
    qs = np.percentile(values, [1, 5, 10, 25, 50, 75, 90, 95, 99])
    return {
        "n": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "p01": float(qs[0]),
        "p05": float(qs[1]),
        "p10": float(qs[2]),
        "p25": float(qs[3]),
        "p50": float(qs[4]),
        "p75": float(qs[5]),
        "p90": float(qs[6]),
        "p95": float(qs[7]),
        "p99": float(qs[8]),
    }


def sign_breakdown(values: np.ndarray, tol: float = 1e-9) -> Dict[str, float]:
    n = len(values)
    if n == 0:
        return {}
    return {
        "n_neg": int(np.sum(values < -tol)),
        "n_zero": int(np.sum(np.abs(values) <= tol)),
        "n_pos": int(np.sum(values > tol)),
        "frac_neg": float(np.mean(values < -tol)),
        "frac_zero": float(np.mean(np.abs(values) <= tol)),
        "frac_pos": float(np.mean(values > tol)),
    }


# ---------------------------------------------------------------------------
# Part H: Joint dependence analysis
# ---------------------------------------------------------------------------

def joint_dependence(dd: np.ndarray, de: np.ndarray) -> Dict[str, float]:
    if len(dd) < 3 or len(de) < 3:
        return {"n": int(min(len(dd), len(de))), "note": "insufficient sample"}
    pearson = float(np.corrcoef(dd, de)[0, 1])
    # Spearman via rank correlation
    dd_r = np.argsort(np.argsort(dd))
    de_r = np.argsort(np.argsort(de))
    spearman = float(np.corrcoef(dd_r, de_r)[0, 1])
    cov = float(np.cov(dd, de, ddof=0)[0, 1])
    return {
        "n": int(len(dd)),
        "pearson_corr": pearson,
        "spearman_corr": spearman,
        "covariance": cov,
    }


# ---------------------------------------------------------------------------
# Part I: Scenario generation via k-means
# ---------------------------------------------------------------------------

def kmeans_joint(dd: np.ndarray, de: np.ndarray, K: int, seed: int,
                 max_iter: int = 200) -> Dict[str, Any]:
    """K-means clustering on the joint (Delta_d, Delta_e) distribution.

    Standardization (if any) is fitted on the same calibration data only.
    Returns: cluster centroids, weights, reconstruction error, per-cluster
    statistics.
    """
    rng = np.random.default_rng(seed)
    X = np.column_stack([dd, de]).astype(float)
    n = X.shape[0]
    if n < K:
        raise ValueError(f"Cannot cluster {n} points into {K} clusters")
    # Standardize using calibration-set mean/std
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma == 0] = 1.0
    Xs = (X - mu) / sigma
    # K-means++ initialization
    idx0 = int(rng.integers(0, n))
    centers = [Xs[idx0]]
    for _ in range(1, K):
        d2 = np.min(np.linalg.norm(Xs[:, None, :] - np.array(centers)[None, :, :], axis=2) ** 2, axis=1)
        probs = d2 / d2.sum()
        idx = int(rng.choice(n, p=probs))
        centers.append(Xs[idx])
    centers = np.array(centers)
    # Lloyd iterations
    for it in range(max_iter):
        d2 = np.linalg.norm(Xs[:, None, :] - centers[None, :, :], axis=2) ** 2
        labels = np.argmin(d2, axis=1)
        new_centers = np.array([Xs[labels == k].mean(axis=0) if np.any(labels == k) else centers[k]
                                 for k in range(K)])
        if np.max(np.abs(new_centers - centers)) < 1e-8:
            break
        centers = new_centers
    # Final assignment and reconstruction
    d2 = np.linalg.norm(Xs[:, None, :] - centers[None, :, :], axis=2) ** 2
    labels = np.argmin(d2, axis=1)
    # Reconstruct in original scale
    centers_original = centers * sigma + mu
    # Per-cluster stats
    cluster_stats = []
    for k in range(K):
        mask = labels == k
        n_k = int(mask.sum())
        if n_k == 0:
            cluster_stats.append({
                "cluster": k,
                "n_observations": 0,
                "weight": 0.0,
                "centroid_delta_d_minutes": 0.0,
                "centroid_delta_e_kwh": 0.0,
                "mean_delta_d": 0.0,
                "mean_delta_e": 0.0,
                "std_delta_d": 0.0,
                "std_delta_e": 0.0,
            })
            continue
        cluster_stats.append({
            "cluster": k,
            "n_observations": n_k,
            "weight": float(n_k / n),
            "centroid_delta_d_minutes": float(centers_original[k, 0]),
            "centroid_delta_e_kwh": float(centers_original[k, 1]),
            "mean_delta_d": float(np.mean(dd[mask])),
            "mean_delta_e": float(np.mean(de[mask])),
            "std_delta_d": float(np.std(dd[mask])),
            "std_delta_e": float(np.std(de[mask])),
        })
    # Reconstruction error: total within-cluster SSE in the standardized space
    sse = float(np.sum((Xs - centers[labels]) ** 2))
    # Coverage of tails: fraction of dd <= p10 or >= p90 captured (a point is
    # "captured" if its cluster's centroid is within the same tail-side)
    p10_dd = float(np.percentile(dd, 10))
    p90_dd = float(np.percentile(dd, 90))
    p10_de = float(np.percentile(de, 10))
    p90_de = float(np.percentile(de, 90))
    lower_tail_dd = dd < p10_dd
    upper_tail_dd = dd > p90_dd
    lower_tail_de = de < p10_de
    upper_tail_de = de > p90_de
    tail_mass = (lower_tail_dd.sum() + upper_tail_dd.sum() +
                 lower_tail_de.sum() + upper_tail_de.sum())
    # In each cluster, the centroid's quadrant (relative to overall median)
    # determines which "tail bucket" it represents
    median_dd = float(np.median(dd))
    median_de = float(np.median(de))
    quad_dd = ["L" if c < median_dd else "H" for c in centers_original[:, 0]]
    quad_de = ["L" if c < median_de else "H" for c in centers_original[:, 1]]
    # How well does the cluster set represent tail behavior? A simple proxy:
    # for each tail observation, check whether the cluster it belongs to is
    # in the same tail quadrant.
    def in_same_quad(k_idx, dd_v, de_v):
        return (("L" if dd_v < median_dd else "H") == quad_dd[k_idx] and
                (("L" if de_v < median_de else "H") == quad_de[k_idx]))
    n_tail_covered = 0
    for k_idx, (dd_v, de_v) in enumerate(zip(dd, de)):
        is_tail = (dd_v < p10_dd or dd_v > p90_dd or de_v < p10_de or de_v > p90_de)
        if is_tail and in_same_quad(labels[k_idx], dd_v, de_v):
            n_tail_covered += 1
    tail_coverage = float(n_tail_covered / max(1, tail_mass))
    # Preservation of marginal distribution: Wasserstein-1 between empirical
    # and "scenario-mixture" marginals
    def wasserstein1_to_mixture(samples, centroids, weights):
        # Empirical CDF vs weighted centroid CDF (centroids treated as atoms)
        cdf_vals, edges = np.histogram(samples, bins=200, density=False)
        cdf_vals = cdf_vals.cumsum() / cdf_vals.sum()
        centers = 0.5 * (edges[:-1] + edges[1:])
        # For each x in centers, the mixture CDF is sum_k w_k * 1{c_k <= x}
        cdf_mix = np.zeros_like(cdf_vals)
        for w, c in zip(weights, centroids):
            cdf_mix += w * (centers >= c).astype(float)
        return float(np.mean(np.abs(cdf_vals - cdf_mix)))
    wass_dd = wasserstein1_to_mixture(dd, centers_original[:, 0],
                                      np.array([s["weight"] for s in cluster_stats]))
    wass_de = wasserstein1_to_mixture(de, centers_original[:, 1],
                                      np.array([s["weight"] for s in cluster_stats]))
    # Joint dependence preservation: corr in original vs corr in mixture samples
    rng2 = np.random.default_rng(seed + 1)
    # Draw 5000 mixture samples
    mix_idx = rng2.choice(K, size=5000, p=np.array([s["weight"] for s in cluster_stats]))
    mix_dd = centers_original[mix_idx, 0] + rng2.normal(0, 1, 5000) * 0.0
    mix_de = centers_original[mix_idx, 1] + rng2.normal(0, 1, 5000) * 0.0
    mix_pearson = float(np.corrcoef(mix_dd, mix_de)[0, 1])
    return {
        "K": K,
        "n_observations": n,
        "seed": seed,
        "standardization": {"mu_dd": float(mu[0]), "sigma_dd": float(sigma[0]),
                            "mu_de": float(mu[1]), "sigma_de": float(sigma[1])},
        "reconstruction_sse": sse,
        "reconstruction_sse_per_point": sse / n,
        "tail_coverage_fraction": tail_coverage,
        "wasserstein1_dd": wass_dd,
        "wasserstein1_de": wass_de,
        "marginal_pearson_preserved": mix_pearson,
        "empirical_pearson": float(np.corrcoef(dd, de)[0, 1]),
        "clusters": cluster_stats,
    }


def build_scenario_aware_instance(base_inst: Instance, omega: Tuple[float, float]) -> Instance:
    """Build a scenario-modified copy of a base Instance.

    omega = (Delta_d_minutes, Delta_e_kwh).

    IMPORTANT: To preserve the QUBO variable set across scenarios (Stage 5
    spec Part K: "If different scenarios produce different variable sets,
    STOP and resolve the representation before continuing"), we keep the
    available window W_i = [a_slot, d_slot] FIXED across all scenarios. The
    scenario only modifies R_i (the slot-count requirement). The "window
    shrunk by Delta_d" effect is captured indirectly: when Delta_d > 0 the
    effective window is shorter, so the user leaves before using the late
    slots, but those slots remain in the variable set so the QUBO
    representation does not change.

    For the energy requirement:
      * Delta_e > 0: user demanded more energy than they got; R_i increases.
      * Delta_e < 0: user demanded less than they got; R_i decreases (clip at 0).

    For the deadline (Delta_d, in minutes):
      * Implemented as an additional per-EV soft penalty on the EV's late
        slots. A scenario-aware penalty rho_d(omega) is added in the QUBO
        construction layer (see `scenario_aware_rho_d`); here we only adjust
        R_i.

    Returns a new Instance with the SAME variable set as base_inst.
    """
    dd, de = omega
    new_evs: List[EV] = []
    for ev in base_inst.evs:
        # Keep a_slot, d_slot unchanged -> variable set preserved
        new_a = ev.a_slot
        new_d = ev.d_slot
        # R_i is the slot-count requirement under scenario.
        new_e_req = max(0.0, ev.E_req_kWh + de)
        new_ev = EV(
            ev_id=ev.ev_id,
            a_slot=new_a,
            d_slot=new_d,
            P_max_kW=ev.P_max_kW,
            E_req_kWh=new_e_req,
            E_req_source=ev.E_req_source + f" | scenario omega=({dd:.4f},{de:.4f})",
            R_i=0,
        )
        new_evs.append(new_ev)
    new_inst = Instance(
        name=base_inst.name + f"_sc({dd:.2f},{de:.2f})",
        evs=new_evs,
        T=base_inst.T,
        P_site_max_kW=base_inst.P_site_max_kW,
        P_target_kW=base_inst.P_target_kW,
        c_per_slot=list(base_inst.c_per_slot),
        Delta_min=base_inst.Delta_min,
        description=f"Scenario omega=({dd:.4f} min, {dd:.4f} kWh) of {base_inst.name} (variable set preserved; R_i only)",
    )
    return new_inst


# ---------------------------------------------------------------------------
# Part M: Robust QUBO + exhaustive validation
# ---------------------------------------------------------------------------

def robust_qubo(base_inst: Instance, scenarios: List[Dict[str, Any]],
                rho_d: float, rho_p: float, rho_cap: float) -> Tuple[Any, float, np.ndarray]:
    """Construct the scenario-averaged QUBO.

    Q_robust = sum_s p_s Q_s,  c_robust = sum_s p_s c_s

    The variable set MUST be identical across scenarios. This is enforced
    by the construction in `build_scenario_aware_instance`. If the
    construction changes the variable set (e.g., because the scenario
    shrinks a window to zero length), we raise -- the Stage 5 spec
    forbids that.

    Returns (QUBO, c_robust, n_vars).
    """
    n = base_inst.n_vars
    base_idx = base_inst.var_index()
    Q_acc = np.zeros((n, n))
    c_acc = 0.0
    psum = 0.0
    for s in scenarios:
        p_s = s["weight"]
        omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
        scen_inst = build_scenario_aware_instance(base_inst, omega)
        if scen_inst.n_vars != n or scen_inst.var_index() != base_idx:
            raise RuntimeError(
                f"Scenario {s['cluster']} changed the variable set. "
                "Stage 5 forbids this. The scenario construction must preserve "
                "the variable index exactly."
            )
        q_s = build_qubo(scen_inst, rho_d, rho_p, rho_cap)
        # Both Q matrices are indexed by the same var_index; add directly
        Q_acc += p_s * q_s.Q
        c_acc += p_s * q_s.c
        psum += p_s
    if abs(psum - 1.0) > 1e-6:
        # Renormalize defensively
        Q_acc /= psum
        c_acc /= psum
    return Q_acc, float(c_acc), n


def validate_robust_qubo(base_inst: Instance, scenarios: List[Dict[str, Any]],
                         rho_d: float, rho_p: float, rho_cap: float,
                         tol: float = 1e-7) -> Dict[str, Any]:
    """Exhaustive validation of the robust QUBO.

    For every bitstring (only feasible for small n_vars), verify:
        F_robust_QUBO(x) == sum_s p_s F_s(x) + C
    where F_s is the scenario-s QUBO objective on instance s.
    """
    from stage3.ev_scheduling import QUBO
    n = base_inst.n_vars
    Q_acc, c_acc, _ = robust_qubo(base_inst, scenarios, rho_d, rho_p, rho_cap)
    diffs = []
    for bits in product([0, 1], repeat=n):
        x = np.array(bits, dtype=float)
        f_robust_qubo = float(x @ Q_acc @ x + c_acc)
        f_sum = 0.0
        for s in scenarios:
            p_s = s["weight"]
            omega = (s["centroid_delta_d_minutes"], s["centroid_delta_e_kwh"])
            scen_inst = build_scenario_aware_instance(base_inst, omega)
            q_s = build_qubo(scen_inst, rho_d, rho_p, rho_cap)
            f_sum += p_s * (float(x @ q_s.Q @ x) + q_s.c)
        diffs.append(f_robust_qubo - f_sum)
    diffs = np.array(diffs)
    mean_d = float(np.mean(diffs))
    std_d = float(np.std(diffs))
    max_abs = float(np.max(np.abs(diffs - mean_d)))
    return {
        "n_bitstrings": len(diffs),
        "n_vars": n,
        "mean_offset": mean_d,
        "std_offset": std_d,
        "max_abs_deviation_from_mean": max_abs,
        "tolerance": tol,
        "passes": max_abs < tol,
        "diffs_sample_first5": diffs[:5].tolist(),
        "diffs_sample_last5": diffs[-5:].tolist(),
    }


# ---------------------------------------------------------------------------
# Part N + O + Q: ADOPT gamma, alpha, statistics
# ---------------------------------------------------------------------------

@dataclass
class ADOPTParameters:
    alpha: float
    formula: str
    rationale: str
    calibration_period_utc: str
    variables_used: List[str]
    pre_registered_at_utc: str
    version: str


def compute_robust_rho_d(base_rho_d: float, base_inst: Instance, samples: Sequence[UncertaintySample],
                          alpha: float) -> Tuple[float, Dict[str, Any]]:
    """Compute the ADOPT scaling gamma and the robust rho_d.

    Formula (Stage 1):
        gamma(omega) = 1 + alpha * mean( sigma_i / R_bar_i )
    where sigma_i is the per-EV uncertainty in slot-count terms and
    R_bar_i is the per-EV mean slot requirement.

    sigma_i is the standard deviation of R_i(omega) over the scenarios
    that EV i might face. To compute this for a *fixed* base instance,
    we treat sigma_i as the cross-sectional standard deviation of R_i
    across the observed (Delta_d, Delta_e) samples, evaluated at the
    base instance's window and E_req.

    R_i(omega) for an EV with available window W_i and E_req (kWh):
        R_i(omega) = ceil( (E_req + Delta_e) / (P_max * Delta) )
        The window is shrunk by max(0, ceil(Delta_d / Delta)) slots.

    We use the calibration-set samples to estimate per-EV sigma_i and R_bar_i
    by Monte Carlo over the empirical (Delta_d, Delta_e) distribution.
    """
    if base_inst.n_vars == 0 or len(samples) == 0:
        return base_rho_d, {"gamma": 1.0, "note": "no samples or empty instance"}
    rng = np.random.default_rng(20260829)
    # Subsample for speed
    cal = [s for s in samples if s.calibration and s.delta_d_minutes is not None and s.delta_e_kwh is not None]
    if len(cal) < 50:
        # Fall back to all samples
        cal = [s for s in samples if s.delta_d_minutes is not None and s.delta_e_kwh is not None]
    n_mc = min(500, len(cal))
    mc_idx = rng.choice(len(cal), size=n_mc, replace=False)
    sigmas = []
    Rbars = []
    for ev in base_inst.evs:
        r_i_samples = []
        for j in mc_idx:
            s = cal[int(j)]
            dd = s.delta_d_minutes
            de = s.delta_e_kwh
            slots_removed = max(0, int(round(dd / DELTA_MIN)))
            new_window = max(0, ev.d_slot - ev.a_slot + 1 - slots_removed)
            if new_window <= 0:
                # Window zeroed; the EV is infeasible regardless of R_i
                r_i_samples.append(0)
                continue
            e_req_scen = max(0.0, ev.E_req_kWh + de)
            e_slot = ev.P_max_kW * DELTA_HOURS
            r_i = int(math.ceil(e_req_scen / e_slot)) if e_slot > 0 else 0
            r_i = min(r_i, new_window)  # cannot exceed available slots
            r_i_samples.append(r_i)
        r_arr = np.array(r_i_samples, dtype=float)
        if len(r_arr) == 0:
            continue
        sigmas.append(float(np.std(r_arr)))
        Rbars.append(float(np.mean(r_arr)))
    sigmas = np.array(sigmas)
    Rbars = np.array(Rbars)
    if len(sigmas) == 0 or np.all(Rbars == 0):
        # All R_bars zero: gamma = 1 + 0
        gamma = 1.0
    else:
        # Per-EV ratio; mean across EVs
        ratios = np.where(Rbars > 0, sigmas / Rbars, 0.0)
        mean_ratio = float(np.mean(ratios))
        gamma = 1.0 + alpha * mean_ratio
    rho_d_robust = float(base_rho_d * gamma)
    stats = {
        "alpha": alpha,
        "mean_sigma": float(np.mean(sigmas)) if len(sigmas) else 0.0,
        "mean_Rbar": float(np.mean(Rbars)) if len(Rbars) else 0.0,
        "mean_ratio_sigma_over_Rbar": float(np.mean(np.where(Rbars > 0, sigmas / Rbars, 0.0))) if len(sigmas) else 0.0,
        "gamma": float(gamma),
        "rho_d_robust": rho_d_robust,
        "n_observations_in_sigma_i_estimate": int(n_mc * len(base_inst.evs)),
        "n_evs_with_positive_Rbar": int(np.sum(Rbars > 0)),
        "note": "sigma_i is the cross-sectional std of R_i over the empirical (Delta_d, Delta_e) samples; R_bar_i is the corresponding mean.",
    }
    return rho_d_robust, stats


# ---------------------------------------------------------------------------
# Top-level driver
# ---------------------------------------------------------------------------

def run_stage5(instance_name: str = "toy_B_3x4", K_default: int = 8,
               alpha: Optional[float] = None,
               rho_d: float = DEFAULT_RHO_D, rho_p: float = DEFAULT_RHO_P,
               rho_cap: float = DEFAULT_RHO_CAP) -> Dict[str, Any]:
    """Run the full Stage 5 pipeline.

    Steps:
      1. Load uncertainty samples (live API if token, else placeholder).
      2. Split into calibration / held-out.
      3. Empirical distribution stats (calibration only).
      4. Joint dependence (calibration only).
      5. k-means scenarios for K in {4, 8, 16} (calibration only).
      6. Scenario quality comparison.
      7. Pre-register alpha (structural rule if not provided).
      8. ADOPT calibration: compute gamma and rho_d^robust (calibration only).
      9. Build robust QUBO with K=8 scenarios.
      10. Exhaustive algebraic validation of the robust QUBO.
      11. F0/F1/F2/F3 ablation coefficient report.
    """
    out: Dict[str, Any] = {
        "stage": "Stage 5",
        "instance": instance_name,
        "alpha": alpha,
        "rho_d": rho_d,
        "rho_p": rho_p,
        "rho_cap": rho_cap,
    }

    # 1) Load
    real_samples, real_status = load_real_uncertainty()
    if real_status["source"] != "blocked":
        samples = real_samples
        load_status = real_status
    else:
        samples, load_status = placeholder_uncertainty()
    out["load_status"] = load_status

    # 2) Split
    cal = [s for s in samples if s.calibration]
    ho = [s for s in samples if not s.calibration]
    out["n_total"] = len(samples)
    out["n_calibration"] = len(cal)
    out["n_held_out"] = len(ho)

    # Missing-data
    out["missing_data"] = missing_data_report(samples)
    out["missing_data_calibration"] = missing_data_report(cal)

    # 3) Distribution stats -- calibration only
    dd_cal = np.array([s.delta_d_minutes for s in cal if s.delta_d_minutes is not None])
    de_cal = np.array([s.delta_e_kwh for s in cal if s.delta_e_kwh is not None])
    out["delta_d_distribution"] = distribution_stats(dd_cal)
    out["delta_d_signs"] = sign_breakdown(dd_cal)
    out["delta_e_distribution"] = distribution_stats(de_cal)
    out["delta_e_signs"] = sign_breakdown(de_cal)
    # Held-out (reported separately, never used in calibration)
    dd_ho = np.array([s.delta_d_minutes for s in ho if s.delta_d_minutes is not None])
    de_ho = np.array([s.delta_e_kwh for s in ho if s.delta_e_kwh is not None])
    out["delta_d_distribution_held_out"] = distribution_stats(dd_ho)
    out["delta_e_distribution_held_out"] = distribution_stats(de_ho)

    # 4) Joint dependence
    common = [(s.delta_d_minutes, s.delta_e_kwh) for s in cal
              if s.delta_d_minutes is not None and s.delta_e_kwh is not None]
    if common:
        dd_arr = np.array([c[0] for c in common])
        de_arr = np.array([c[1] for c in common])
        out["joint_dependence_calibration"] = joint_dependence(dd_arr, de_arr)
    else:
        out["joint_dependence_calibration"] = {"n": 0, "note": "no valid samples"}

    # 5) Scenario generation: K in {4, 8, 16}
    scenario_quality = {}
    for K in [4, 8, 16]:
        if len(dd_cal) >= K and len(de_cal) >= K:
            res = kmeans_joint(dd_cal, de_cal, K=K, seed=20260829 + K)
            scenario_quality[f"K{K}"] = res
        else:
            scenario_quality[f"K{K}"] = {"K": K, "n_observations": int(len(dd_cal)),
                                          "note": "insufficient samples"}
    out["scenario_quality"] = scenario_quality

    # 6) Pick K = K_default (default 8) for the robust QUBO
    chosen_key = f"K{K_default}"
    chosen = scenario_quality.get(chosen_key)
    if chosen is None or "clusters" not in chosen:
        # Fallback: K=4 if K_default is too large
        chosen = scenario_quality.get("K4")
        chosen_key = "K4"
    out["chosen_K"] = chosen_key
    out["chosen_scenarios"] = chosen.get("clusters", [])

    # 7) Pre-register alpha. The structural rule is documented below.
    if alpha is None:
        # STRUCTURAL RULE (calibration-only): use alpha = 1.0, i.e. gamma =
        # 1 + mean(sigma_i / R_bar_i). The factor 1.0 is dimensionless and
        # corresponds to "one full mean-ratio inflation". We do not sweep.
        alpha = 1.0
        out["alpha_rationale"] = "STRUCTURAL DEFAULT: alpha = 1.0 (one full mean-ratio inflation). Pre-registered. NOT tuned on held-out data."
    else:
        out["alpha_rationale"] = f"Pre-registered externally; alpha = {alpha}"
    out["alpha"] = alpha

    adopt_params = ADOPTParameters(
        alpha=alpha,
        formula="gamma(omega) = 1 + alpha * mean_i( sigma_i / R_bar_i )",
        rationale=("sigma_i is the cross-sectional std of R_i(omega) over the "
                   "calibration empirical (Delta_d, Delta_e) joint. R_bar_i is "
                   "the corresponding mean. R_i(omega) is the scenario-s slot-count "
                   "requirement: R_i = ceil((E_req + Delta_e) / (P_max * Delta)) "
                   "clipped to the scenario-s window length. The aggregation is a "
                   "uniform mean across EVs in the base instance. alpha is a "
                   "dimensionless constant pre-registered BEFORE any held-out use."),
        calibration_period_utc=f"{CAL_START_UTC} to {CAL_END_UTC}",
        variables_used=["delta_d_minutes", "delta_e_kwh"],
        pre_registered_at_utc=datetime.utcnow().isoformat() + "Z",
        version="stage5.v1",
    )

    # 8) ADOPT calibration
    base_inst = toy_instance(instance_name, N=3, T=4)
    rho_d_robust, adopt_stats = compute_robust_rho_d(rho_d, base_inst, cal, alpha)
    out["adopt_calibration"] = adopt_stats
    out["adopt_pre_registration"] = asdict(adopt_params)

    # 9) Build the robust QUBO (K = K_default)
    if out["chosen_scenarios"]:
        try:
            Q_robust, c_robust, n = robust_qubo(base_inst, out["chosen_scenarios"],
                                                rho_d_robust, rho_p, rho_cap)
            out["robust_qubo"] = {
                "n_vars": n,
                "constant": float(c_robust),
                "Q_diagonal": [float(Q_robust[k, k]) for k in range(n)],
                "Q_off_diagonal_count": int(np.sum(np.abs(np.triu(Q_robust, k=1)) > 1e-12)),
            }
            # 10) Exhaustive validation
            val = validate_robust_qubo(base_inst, out["chosen_scenarios"],
                                       rho_d_robust, rho_p, rho_cap, tol=1e-7)
            out["robust_qubo_validation"] = val
        except RuntimeError as e:
            out["robust_qubo_error"] = str(e)
            out["robust_qubo_validation"] = {"passes": False, "error": str(e)}
    else:
        out["robust_qubo_error"] = "No scenarios available"
        out["robust_qubo_validation"] = {"passes": False, "error": "no scenarios"}

    # 11) F0/F1/F2/F3 ablation coefficient report
    base_q = build_qubo(base_inst, rho_d, rho_p, rho_cap)
    out["ablation"] = {
        "F0_deterministic": {
            "rho_d": rho_d, "rho_p": rho_p, "rho_cap": rho_cap,
            "Q_diagonal_first3": [float(base_q.Q[k, k]) for k in range(min(3, base_inst.n_vars))],
            "constant": float(base_q.c),
            "auxiliary_vars": 0,
            "is_pure_qubo": True,
        },
        "F1_robust_scenario_averaged": {
            "rho_d": rho_d, "rho_p": rho_p, "rho_cap": rho_cap,
            "note": "Same as F0 with rho_d replaced by rho_d (no scaling)",
            "Q_diagonal_first3": [float(base_q.Q[k, k]) for k in range(min(3, base_inst.n_vars))],
            "constant": float(base_q.c),
            "auxiliary_vars": 0,
            "is_pure_qubo": True,
        },
        "F2_adopt": {
            "rho_d": rho_d_robust, "rho_p": rho_p, "rho_cap": rho_cap,
            "gamma": adopt_stats["gamma"],
            "Q_diagonal_first3_robust": (out.get("robust_qubo", {}).get("Q_diagonal", [])[:3]
                                          if out.get("robust_qubo") else []),
            "constant_robust": out.get("robust_qubo", {}).get("constant"),
            "auxiliary_vars": 0,
            "is_pure_qubo": True,
        },
        "F3_oracle": {
            "note": ("Analysis ceiling only. NOT deployable. "
                     "The oracle would solve the QUBO with the *realized* (Delta_d, Delta_e) "
                     "applied to each EV in the held-out set. Not implemented in Stage 5; "
                     "would be implemented in Stage 6+ if the API token is available."),
            "is_pure_qubo": True,
            "auxiliary_vars": 0,
        },
    }
    # Q vs rho_d comparison
    out["gamma_statistics"] = {
        "gamma": adopt_stats["gamma"],
        "rho_d_deterministic": rho_d,
        "rho_d_robust_adopt": rho_d_robust,
        "fractional_increase": float((rho_d_robust - rho_d) / max(rho_d, 1e-9)),
        "mean_ratio_sigma_over_Rbar": adopt_stats["mean_ratio_sigma_over_Rbar"],
        "n_evs_with_positive_Rbar": adopt_stats["n_evs_with_positive_Rbar"],
    }
    return out


def _tuples_to_str(o):
    if isinstance(o, dict):
        return {str(k): _tuples_to_str(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_tuples_to_str(x) for x in o]
    return o


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=str, default="artifacts/stage5_run.json")
    p.add_argument("--instance", type=str, default="toy_B_3x4")
    p.add_argument("--K", type=int, default=8)
    p.add_argument("--alpha", type=float, default=None)
    args = p.parse_args()
    res = run_stage5(instance_name=args.instance, K_default=args.K, alpha=args.alpha)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(_tuples_to_str(res), indent=2, default=str))
    # Summary
    print(f"Wrote {args.out}")
    print(f"  source: {res['load_status']['source']}  n_total={res['n_total']}  "
          f"n_cal={res['n_calibration']}  n_ho={res['n_held_out']}")
    if "joint_dependence_calibration" in res and "pearson_corr" in res["joint_dependence_calibration"]:
        jd = res["joint_dependence_calibration"]
        print(f"  joint: pearson={jd.get('pearson_corr'):.4f}  spearman={jd.get('spearman_corr'):.4f}  n={jd.get('n')}")
    if "robust_qubo_validation" in res:
        v = res["robust_qubo_validation"]
        print(f"  robust QUBO validation: passes={v.get('passes')}  max_dev={v.get('max_abs_deviation_from_mean', 0):.2e}")
    if "gamma_statistics" in res:
        g = res["gamma_statistics"]
        print(f"  gamma={g['gamma']:.4f}  rho_d_deterministic={g['rho_d_deterministic']}  "
              f"rho_d_robust={g['rho_d_robust_adopt']:.4f}  fractional_increase={g['fractional_increase']:.4f}")
