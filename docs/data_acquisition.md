# ACN-Data Acquisition Record

**Stage:** Stage 2 — ACN-Data acquisition and audit.
**Status:** **HARD BLOCKER for Stage 1 uncertainty model.** See §H.
**Acquisition timestamp:** 2026-08-29.
**Auditor note:** The Stage 1 spec assumed that `kWhRequested` from `userInputs[*]` would be available. The investigation below shows that this field is gated behind a registered API token and is **not present** in the only public, tokenless data path (the static time-series snapshot). This is not a missing-file issue; it is a hard methodology blocker for the Stage 1 `ΔE = kWhDelivered − kWhRequested` formulation.

---

## 1. Acquisition attempt — official Caltech ACN API

### 1.1 Endpoint and credential requirement
- Base URL: `https://ev.caltech.edu/api/v1/`
- Session endpoint: `sessions/caltech`, `sessions/jpl`, `sessions/office001`
- Authentication: HTTP Basic, **token as username, blank password**, per `acnportal` source.
- Token issuance: requires registration at `https://ev.caltech.edu/register` (the registration page was inspected; it is a human-approval flow with email confirmation, not a self-service token grant).

### 1.2 Probe results
Direct `GET` to `https://ev.caltech.edu/api/v1/sessions/caltech?page=1` returned:

```
HTTP 401 UNAUTHORIZED
```

A tokenless probe with the README's example filter returned the same 401. No session-level metadata is accessible without a token.

### 1.3 Registration blocker
The `https://ev.caltech.edu/register` form is a human-mediated flow ("By registering you help us demonstrate to the usefulness of ACN-Data…"). The project has no automated way to complete it. This is a credentialing blocker, not a data blocker. The acquisition **must not** be completed by:
- bypassing access controls,
- fabricating credentials,
- reusing a third party's token.

The audit therefore proceeded to the only **publicly downloadable** alternative: the static time-series snapshot.

---

## 2. Acquisition — public static snapshot (`tongxin-li/ACN-Data-Static`)

### 2.1 Source
- Repository: `https://github.com/tongxin-li/ACN-Data-Static`
- License: not bundled; per the README, users are referred to the official ACN-Data terms.
- Coverage: 2018–2020 across Caltech (5 garages), JPL, office_01.

### 2.2 Files acquired
- `session data/caltech_sessions.json` — **verified empty** (2 bytes: `"\r\n"`). Confirmed via `GET` to both `main` and `master` branches.
- `time series data/caltech/California_Garage_01/*.csv.gz` — 31,860 session time-series files.
- `time series data/caltech/California_Garage_02/*.csv.gz` — 15,589 files.
- `time series data/caltech/S_Wilson_Garage_01/*.csv.gz` — 2,703 files.
- `time series data/caltech/N_Wilson_Garage_01/*.csv.gz` — 6,299 files.
- `time series data/caltech/LIGO_01/*.csv.gz` — 229 files.
- `time series data/jpl/Arroyo_Garage_01/*.csv.gz` — 27,723 files.
- `time series data/office_01/Parking_Lot_01/*.csv.gz` — 1,474 files.

### 2.3 File inventory check (no bulk download performed)
The full ~85,877-file archive was not pulled. The audit was performed by reading a single representative time-series file (a 2019-10-31 office_01 session, ~25 KB) to confirm the schema, plus directory listings via the GitHub API. **Bulk download of the time-series archive is feasible** but, as documented below, is **not sufficient** for the Stage 1 `ΔE` formulation.

---

## 3. Raw-data schema audit (static time-series, the only tokenless path)

### 3.1 Time-series file content (one record per row, sampled at ~4-second cadence)

| Column | Type | Description |
|---|---|---|
| (index) | datetime ISO 8601, UTC | Sample timestamp; e.g. `2019-10-31T14:21:10+00:00` |
| `Charging Current (A)` | float | Measured current draw |
| `Actual Pilot (A)` | float | Pilot signal current limit |
| `Voltage (V)` | float | Measured voltage |
| `Charging State` | enum string | `READY`, `ADAPTIVE`, `IDLE` (and others) |
| `Energy Delivered (kWh)` | float (cumulative) | Cumulative energy since session start |
| `Power (kW)` | float | Instantaneous power |

### 3.2 Session-level fields in the filename (derivable, not from file content)
The filename pattern (e.g. `2-39-123-23-2018-05-01T17-11-32-081386.csv.gz`) encodes:
- `2-39-123-23` — station/EVSE identifier,
- `2018-05-01T17-11-32-081386` — `connectionTime` to microsecond precision, in local site time.

**`disconnectTime`** is **not** in the filename; it is derivable from the last timestamp in the file (plus a small grace window for the trailing idle state).

### 3.3 Fields present in the official schema (token-gated) that are **absent** in the static snapshot
| Field | In static snapshot? | In live API? | Required by Stage 1? |
|---|---|---|---|
| `connectionTime` | **Partial** — in filename only | ✓ | Yes (decision-time `â_i`) |
| `disconnectTime` | **Derivable** — last timestamp | ✓ | Yes (decision-time `d̂_i`) |
| `kWhDelivered` | ✓ (last row of `Energy Delivered (kWh)`) | ✓ | Yes |
| `userInputs[*].kWhRequested` | **NO** | ✓ | **Yes — `ΔE` undefined without it** |
| `userInputs[*].requestedDeparture` | **NO** | ✓ | Optional (`Δd` proxy) |
| `userID` | **NO** | ✓ | Optional (not required by Stage 1) |
| `sessionID` | **NO** | ✓ | Optional |
| `siteID` | ✓ (in filename) | ✓ | Yes (site filtering) |

**Conclusion:** the static snapshot provides `kWhDelivered` (via cumulative energy at session end) and a usable proxy for `connectionTime` and `disconnectTime`. It does **not** provide `kWhRequested` or any `userInputs` field.

---

## 4. Stage 1 uncertainty variables — feasibility audit

Stage 1 (locked) defines:
- `Δd_i = d̂_i − actual_disconnect_i`
- `ΔE_i = kWhDelivered_i − kWhRequested_i`

### 4.1 `Δd` — derivable from static data (with caveats)
- `d̂_i` (decision-time deadline estimate) is **not** present in the static snapshot. Stage 1 implicitly equates `d̂_i` to the actual `disconnectTime`, which collapses `Δd` to zero by construction. To get a meaningful `Δd` distribution we need `requestedDeparture` (from `userInputs`), which is also absent.
- **Without `requestedDeparture`, `Δd` is undefined.** A working alternative is to use the **observed session length** (last-timestamp − connectionTime) and define `Δd` against a learned "typical session length" baseline (e.g., user/day-of-week median). This is a **substitute for the Stage 1 definition**, not a faithful implementation of it. Stage 1 §4.1 acknowledges this kind of proxy for arrival deviation, but for departure deviation it is silent.

### 4.2 `ΔE` — **NOT derivable** from static data
- `kWhDelivered` is available.
- `kWhRequested` is **not** in the static snapshot in any form.
- Therefore `ΔE` cannot be computed for any session in the public data.

**This is a hard methodology blocker for Stage 1 §4.** Stage 1 explicitly required `kWhRequested` from `userInputs`. Without a registered API token, the dataset cannot support the Stage 1 `ΔE` formulation as written.

---

## 5. Two paths forward — both require user decision

### 5.1 Path A — acquire an ACN-Data API token (preferred, faithful to Stage 1)
- Action: project owner registers at `https://ev.caltech.edu/register`, receives a token, and supplies it to the pipeline.
- Once token is supplied, the full Stage 1 acquisition path (sections 1–14 of Stage 2 instructions) can be executed.
- **Time cost:** token issuance is human-mediated (likely 1–3 business days per Caltech's typical response time, unverified).
- **Risk:** token may be denied or delayed. The 14-day timeline does not absorb >2 business days of token wait.

### 5.2 Path B — degrade the uncertainty model to use only static data
- Drop `ΔE` entirely. Use only `Δd` (defined against a session-length baseline, with the caveats in §4.1).
- The Stage 1 robust formulation (scenario-based expected cost & expected unmet demand) still functions: the "scenario" only perturbs departure time, not energy demand. The penalty-weight scaling `γ(ω)` reduces to a function of departure-noise variance only.
- This **changes the scientific claim** of the project: the central behavioral uncertainty becomes departure time, not energy-demand deviation. The paper's "energy uncertainty" framing must be removed or reframed.
- **This requires an explicit Stage 1 amendment, not a silent substitution.** Per the Stage 2 instruction: *"If a Stage 1 assumption cannot be supported by the actual data, STOP and report the problem rather than silently changing the methodology."*

---

## 6. What is *not* a blocker

- **Time-series access to `kWhDelivered`, `connectionTime` (via filename), `disconnectTime` (via last timestamp)** — fully available.
- **Caltech coverage 2018-05 → 2019-12** — the static snapshot's Caltech directories include 2018-05 (first files in `California_Garage_01`) through 2020 (latest files). The Stage 1 temporal split (2018-05→2019-06 calibration, 2019-07→2019-12 held-out) is **enforceable** on the Caltech data.
- **Site cap and EVSE structure** — derivable from the filename-encoded station IDs and known site configs (Caltech has 54 EVSEs across 5 garages; ACN-Sim provides this).

---

## 7. Audit log (commands run, no fabrication)

```
# Probe live API
GET https://ev.caltech.edu/api/v1/sessions/caltech?page=1                  -> 401
GET https://ev.caltech.edu/api/v1/sessions/caltech?where=...&page=1        -> 401
GET https://ev.caltech.edu/register                                        -> human-mediated form
GET https://ev.caltech.edu/caltech_sessions.json                           -> 404

# Inspect static snapshot
GET https://raw.githubusercontent.com/tongxin-li/ACN-Data-Static/main/session%20data/caltech_sessions.json
                                                                            -> 2 bytes ("\r\n") on main and master
GET https://api.github.com/repos/tongxin-li/ACN-Data-Static/contents/session%20data
                                                                            -> only caltech_sessions.json (2 bytes)

# Verify time-series schema (one file)
GET https://raw.githubusercontent.com/tongxin-li/ACN-Data-Static/main/time%20series%20data/office_01/Parking_Lot_01/19-102-260-1635-2019-10-31T14-21-10-330888.csv.gz
                                                                            -> 7 columns: timestamp, Charging Current, Actual Pilot, Voltage, Charging State, Energy Delivered (cumulative), Power

# List directory sizes via GitHub API
GET .../contents/time%20series%20data/caltech/California_Garage_01        -> confirms 31,860 files, names start 2018-05-01
```

No fabrication of credentials, no bypass of access controls, no fabrication of session-level fields.

---

## 8. Manifest (machine-readable, to be expanded once acquisition is unblocked)

| Field | Value |
|---|---|
| `acquisition.source` | `tongxin-li/ACN-Data-Static` (partial, time-series only) + `ev.caltech.edu` API (blocked) |
| `acquisition.method` | HTTP GET via `urllib.request` |
| `acquisition.timestamp` | 2026-08-29 |
| `acquisition.files_total_probed` | 1 (representative time-series) + directory listings |
| `acquisition.caltech_sessions_json_size` | 2 bytes (empty) |
| `acquisition.time_series_schema` | 7 columns: timestamp, Charging Current, Actual Pilot, Voltage, Charging State, Energy Delivered (cumulative), Power |
| `acquisition.stage1_uncertainty_fields_available` | `kWhDelivered` (yes), `kWhRequested` (NO), `connectionTime` (partial — filename), `disconnectTime` (derivable — last timestamp) |

---

## 9. Data manifest JSON (artifact stub)

```json
{
  "acquisition": {
    "source_primary": "https://ev.caltech.edu/api/v1/",
    "source_secondary": "https://github.com/tongxin-li/ACN-Data-Static",
    "acquired_at": "2026-08-29",
    "live_api_status": "401 UNAUTHORIZED (token required)",
    "static_snapshot_status": "available, time-series only, caltech_sessions.json is empty",
    "credential_status": "BLOCKED — token issuance is human-mediated, no fabricated credentials"
  },
  "raw_schema_static_timeseries": [
    "timestamp (ISO8601 UTC, sample index)",
    "Charging Current (A)",
    "Actual Pilot (A)",
    "Voltage (V)",
    "Charging State",
    "Energy Delivered (kWh) [cumulative]",
    "Power (kW)"
  ],
  "raw_schema_filename": {
    "pattern": "{siteId}-{stationId}-{clusterId}-{evseId}-{connectionTime}.csv.gz",
    "extracts": ["siteId", "stationId", "connectionTime"],
    "missing_in_filename": ["disconnectTime", "kWhRequested", "userInputs"]
  },
  "stage1_uncertainty_field_status": {
    "kWhDelivered": "available (last row of cumulative column)",
    "kWhRequested": "NOT AVAILABLE without API token",
    "connectionTime": "partial (filename, local time)",
    "disconnectTime": "derivable (last timestamp + grace)",
    "userInputs": "NOT AVAILABLE without API token"
  },
  "blocker": "Stage 1 ΔE = kWhDelivered - kWhRequested cannot be computed from public data alone. kWhRequested lives only in userInputs, which requires a registered API token."
}
```

---

## 10. Recommended next action (requires user input)

**STOP and request user decision** between:

1. **Supply a registered ACN-Data API token** so that the Stage 1 uncertainty model can be implemented faithfully. The token should be added to a `.env` file at the project root (not committed) and the project owner should run acquisition.
2. **Defer the project** until a token is available. The Stage 1 spec is not implementable without one.
3. **Amend Stage 1 to drop `ΔE`** and reframe the uncertainty model around `Δd` (departure deviation, defined against a learned session-length baseline). This is a substantial change to the scientific claim of the paper and should not be undertaken without explicit approval.

Until one of the three is chosen, **no further Stage 2 work proceeds** — per the Stage 2 instruction *"STOP and report the problem rather than silently changing the methodology."*
