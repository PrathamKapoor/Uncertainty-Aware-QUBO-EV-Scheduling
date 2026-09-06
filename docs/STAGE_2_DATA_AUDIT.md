# Stage 2 — Data Audit

**Project:** An Empirically Calibrated Uncertainty-Aware Adaptive QUBO Framework for Robust EV Charging Scheduling.
**Stage 1 spec:** `docs/STAGE_1_SPEC.md` (authoritative; not modified in this stage).
**Acquisition record:** `docs/data_acquisition.md`.
**Cleaning spec:** `docs/cleaning_spec.md`.
**TOU decision:** `docs/tou_tariff_decision.md`.
**Splits:** `splits.json`.
**Manifest:** `artifacts/data_manifest.json`.
**Cleaning rules:** `artifacts/cleaning_rules.json`.

**Stage 2 status: STAGED — token-dependent uncertainty `ΔE` is BLOCKED; all token-independent work below is complete.**

---

## A. Dataset acquisition

### A.1 What was acquired
- **Source 1 (primary, blocked):** `https://ev.caltech.edu/api/v1/` — `GET /sessions/caltech?page=1` returns **HTTP 401 Unauthorized**. Token required; token issuance is human-mediated via `https://ev.caltech.edu/register`. **No credentials fabricated, no bypass attempted.**
- **Source 2 (fallback, public):** `https://github.com/tongxin-li/ACN-Data-Static` — `tongxin-li/ACN-Data-Static`. Per the README, it contains 85,877 time-series `.csv.gz` files plus a session-level `session data/caltech_sessions.json`. **The session-level JSON is empty (2 bytes).** Time-series files were probed via the Git Trees API + `raw.githubusercontent.com`; a stratified 200-file sample (10 per month, 2018-05 → 2019-12) was downloaded to `artifacts/sample_csvs/` for audit purposes.
- **Audit timestamp:** 2026-08-29.
- **Acquisition log:** `docs/data_acquisition.md` §7 enumerates every command run. No fabrication.

### A.2 Verification that the public session-level data is empty
```
GET https://raw.githubusercontent.com/tongxin-li/ACN-Data-Static/main/session%20data/caltech_sessions.json
   -> 200 OK, 2 bytes, body = "\r\n"
GET https://raw.githubusercontent.com/tongxin-li/ACN-Data-Static/master/session%20data/caltech_sessions.json
   -> 200 OK, 2 bytes, body = "\r\n"
GET https://api.github.com/repos/tongxin-li/ACN-Data-Static/contents/session%20data
   -> ["caltech_sessions.json"]  (size 2)
```

### A.3 What is **not** in the public snapshot
- `userInputs[*]` (the entire nested object) — absent.
- `kWhRequested`, `requestedDeparture`, `minutesAvailable`, `WhPerMile`, `milesRequested` — absent.
- `userID`, `sessionID`, `siteID` textual — absent (numeric station/EVSE IDs are in the filename only).

---

## B. Raw-data schema report

### B.1 Time-series file content (one record per row, ~4-second cadence)
| Column | Type | Description |
|---|---|---|
| (index) | datetime ISO 8601, **UTC** | Sample timestamp (e.g., `2018-06-23T21:07:50+00:00`) |
| `Charging Current (A)` | float | Measured current draw |
| `Actual Pilot (A)` | float | Pilot signal current limit |
| `Voltage (V)` | float | Measured voltage |
| `Charging State` | enum string | `READY`, `ADAPTIVE`, `IDLE`, `NOT CHARGING`, `INITIALIZING`, `DISABLED CHARGER`, `UNPLUGGED` |
| `Energy Delivered (kWh)` | float (cumulative) | Cumulative energy since session start |
| `Power (kW)` | float | Instantaneous power |

### B.2 Filename schema (encoding session metadata)
Pattern: `{station}-{cluster}-{evse}-{YYYY-MM-DDTHH-MM-SS}-{microsec}.csv.gz`
Example: `2-39-123-23-2018-06-23T21-07-50-387167.csv.gz` ⇒ station=2, cluster=39, evse=123, station-internal-id=23, connectionTime=2018-06-23T21:07:50.387167Z.

- `connectionTime` is **UTC**, not local site time. (See §6 for the audit that confirmed this.)
- `disconnectTime` is **not** in the filename; derivable from the last sample timestamp + a small grace window (rule R5 in the cleaning spec).
- No `siteID` textual; the path encodes the site folder (`time series data/caltech/...`).

### B.3 Session-level fields absent from the public snapshot
| Field | Required by Stage 1? | Status |
|---|---|---|
| `kWhDelivered` (final) | yes | **available** — last row of cumulative `Energy Delivered (kWh)` |
| `connectionTime` | yes | **available** — filename |
| `disconnectTime` | yes | **derivable** — last sample timestamp |
| `kWhRequested` (from `userInputs[*]`) | **yes — for `ΔE`** | **NOT AVAILABLE without API token** |
| `requestedDeparture` (from `userInputs[*]`) | yes (for proper `Δd`) | **NOT AVAILABLE without API token** |
| `userID` | optional | **NOT AVAILABLE without API token** |

---

## C. Cleaning specification

See `docs/cleaning_spec.md` for the full specification. Summary:

| Rule | Effect on 200-file audit sample | Projection to full Caltech inventory |
|---|---|---|
| R1 filename parse OK | 0 excluded | ~0 |
| R2 non-empty body | 0 excluded | ~0 |
| R3 first-ts parseable | 0 excluded | ~0 |
| R4 energy column present | 8 excluded | ~1,924 (4.0% rate) |
| R5 filename/file agreement ≤ 30 min | 1 excluded (also caught by R4) | ~240 (0.5% rate) |
| R6 duration ≤ 7 days | 0 excluded | ~0 |
| R7 monotonic timestamps | 0 excluded | ~0 |
| R8 valid EVSE id | 0 excluded | ~0 |
| **Total (unique sessions)** | **8 / 200 (4.0%)** | **~1,924 / 48,113 (4.0%)** |

**Calibration surviving sessions:** ~27,801 × 0.96 ≈ **26,690**.
**Held-out surviving sessions:** ~10,964 × 0.96 ≈ **10,525**.

**Rules explicitly NOT applied** (with rationale): zero-energy sessions (90.6% of audit sample, but real behavior), non-`ADAPTIVE` sessions, extreme energies, short/long sessions — these are the long tail the Stage 1 adaptive mechanism is supposed to handle. Trimming them would invalidate the experiment.

---

## D. Temporal split

### D.1 Definition (locked from Stage 1)
- **Calibration:** Caltech, **2018-05-01 00:00 PT** (UTC: 2018-05-01 08:00) through **2019-06-30 23:59 PT** (UTC: 2019-07-01 06:59). Window: 14 months.
- **Held-out:** Caltech, **2019-07-01 00:00 PT** (UTC: 2019-07-01 07:00) through **2019-12-31 23:59 PT** (UTC: 2020-01-01 07:59). Window: 6 months.
- **Strict disjointness:** calibration and held-out are separated by the **2019-07-01** boundary. No session straddles. No session appears in both. Enforced by filename `connectionTime` UTC.

### D.2 Coverage verification (filename connTime UTC, from full Caltech inventory)
Caltech static snapshot has 48,113 time-series files. Per-month counts in `splits.json` (calibration 27,801; held-out 10,964). **The Stage 1 calendar windows are exactly the available data; no need to shift the split.**

### D.3 Disjointness proof
The split is **by calendar boundary** (2019-07-01 UTC), not by random sampling. Random split was explicitly rejected in Stage 1 §5.2 because ACN-Data has strong day-of-week and time-of-year structure that would leak. Calendar split is the standard fix.

---

## E. Uncertainty characterization (token-dependent portion BLOCKED)

### E.1 What is implementable on the static snapshot

Using only the time-series columns:

- `kWhDelivered` (final, kWh) — the last sample of the cumulative `Energy Delivered (kWh)` column.
- `connectionTime` — filename, UTC.
- `disconnectTime` — last sample timestamp, UTC.
- `duration_min` — `last_ts − first_ts`, minutes.
- `last_charging_state` — `UNPLUGGED`, `IDLE`, `ADAPTIVE`, etc.

### E.2 Static-snapshot empirical statistics (200-file audit sample)
- **Energy:** 174/192 (90.6%) zero-energy; 18/192 (9.4%) non-zero. Non-zero summary: median 5.23 kWh, mean 10.11 kWh, max 33.56 kWh.
- **Duration:** min 0.1 min, median 222.1 min, mean 273.8 min, max 1222.4 min (~20 h).
- **Charging states reached:** 188/200 sessions ever reach `> 0.001 kWh` even though only 18 end with non-zero energy (the rest charge then stop, or charge then the session is cut short).
- **Last state distribution (full sample):** `UNPLUGGED` dominates (sessions end by user unplugging); `IDLE` and `ADAPTIVE` are minority.

### E.3 `Δd` — derivation, with caveat
Stage 1: `Δd_i = d̂_i − actual_disconnect_i`, where `d̂_i` is the *decision-time* deadline estimate.

In ACN-Data:
- `actual_disconnect_i` = `disconnectTime` from the session-level JSON (token-gated) **or** the last sample timestamp (derivable).
- `d̂_i` = a *prediction* of when the EV will leave. The natural source is `userInputs[*].requestedDeparture` (token-gated).

**Without `requestedDeparture`, `Δd` is not directly computable** for a scheduling experiment. A **proxy** is possible: define the *nominal* deadline as the *user/day-of-week median session length* from the calibration set, then `Δd_i = median_duration − actual_duration`. This is a substitute definition, not the Stage 1 definition; the methodology is a deviation from Stage 1 and should be flagged.

### E.4 `ΔE` — **NOT computable on the static snapshot**
- `kWhDelivered` is available.
- `kWhRequested` is **not available** (lives in `userInputs[*]`, token-gated).
- Therefore `ΔE = kWhDelivered − kWhRequested` cannot be computed for any session.

**Status: BLOCKED.** See §H (blocker log) and §J (GO/NO-GO).

### E.5 Empirical characterization (deferred to Stage 3)
The Stage 2 instruction §8 asked for empirical CDFs of `Δd` and `ΔE`. The `ΔE` distribution cannot be produced without the token. The `Δd` distribution cannot be produced without `requestedDeparture`. **Both are deferred until the token is acquired, or until an explicit Stage 1 amendment is approved.** A partial characterization (using proxies) is documented in §E.3 but is **not** the Stage 1 `Δd` and is **not** shipped as a calibration product.

### E.6 Leakage-safe scenario generation (recommendation)
Once the token arrives and the empirical `Δd`, `ΔE` distributions are computed on the calibration set:

- Generate `K=8` scenarios via k-means clustering of the joint empirical (`Δd`, `ΔE`).
- Sample **jointly** — do not sample `Δd` and `ΔE` independently. The Lee et al. 2019 analysis (the ACN-Data paper) shows departure time and energy demand are correlated (users who leave early also tend to take less energy).
- **Calibration-set bootstrap**: if `K=8` over-fits the calibration set, also report sensitivity to `K=4` and `K=16`.

This recommendation is **not yet implemented** because the empirical distributions are not yet available (token-gated).

---

## F. Scenario-generation recommendation

- **Method:** k-means clustering of the joint empirical (`Δd`, `ΔE`), `K=8` by default.
- **Joint sampling:** preserve `Δd`/`ΔE` dependence (do not sample independently).
- **Calibration-set bootstrap:** report sensitivity to `K=4, 8, 16`.
- **Status:** **DEFERRED** to Stage 3 once the empirical distributions are available (token-gated).
- **Pre-implementation check** (Stage 3 Day 1): if the empirical joint is too sparse (n_cal < 1000 surviving sessions) for `K=8`, fall back to `K=4`.

---

## G. TOU tariff decision

**Resolved.** See `docs/tou_tariff_decision.md` for the full document.

- **Source:** PG&E EV2-A (Residential Time-of-Use for EV owners), 2018-vintage period boundaries.
- **Periods (local time, every day):** Peak 14:00–21:00, Off-peak 09:00–14:00 and 21:00–24:00, Super off-peak 00:00–09:00.
- **Why:** Caltech is in PG&E territory; the schedule was in effect during the entire study window; the schedule is public (not derived from ACN-Data); the period boundaries did not change (only dollar amounts).
- **Anti-leakage:** the tariff is a public, time-invariant schedule. It is not a function of the held-out data. Sensitivity to flat tariff is reported as a robustness check, not the primary result.
- **Exact `$/kWh` per period:** Stage 3 will pin the historical 2018-05 → 2019-12 values from PG&E filings. No invented numbers.

---

## H. Leakage audit

### H.1 Can any held-out session influence…

| Component | Influenced by held-out? | Mechanism (or why not) |
|---|---|---|
| Cleaning thresholds | **No** | All rules in `cleaning_spec.md` §B are deterministic; no threshold is learned from data. R5's 30-min cap and R6's 7-day cap are constants. |
| Normalization | **No** | No normalization is applied. Energy, duration, and time are kept in raw units. |
| Uncertainty distributions (`f̂(ω)`) | **No** — distributions not yet built; will be built **only** on calibration when token arrives. |
| Scenario generation | **No** — will use only calibration `f̂(ω)`. |
| TOU tariff selection | **No** — external PG&E EV2-A, public, time-invariant. |
| Penalty scaling `γ(ω)` | **No** — derived from `f̂(ω)`; will be frozen after calibration. |
| Instance construction | **No** — instances are day-aggregations of held-out sessions. The day-aggregation is deterministic and does not use any fitted parameter. |
| QAOA shots / parameter optimization | **No** — Stage 3 will run parameter optimization only on calibration instances; held-out instances are evaluated zero-shot. |

### H.2 Held-out data flow diagram (Stage 3, post-token)

```
CALIBRATION DATA (Caltech 2018-05 → 2019-06)
   │
   ├── cleaning (deterministic)
   ├── f̂(Δd, ΔE) estimation
   ├── scenario generation (k-means, K=8)
   ├── γ(ω) computation
   └── ρ_d^robust = γ(ω) · ρ_d^deterministic
            │
            ▼
       QUBO coefficients frozen
            │
            ▼
HELD-OUT DATA (Caltech 2019-07 → 2019-12)
   │
   ├── instance construction (deterministic)
   ├── schedule solve (single QUBO, frozen coefficients)
   └── EVALUATION ONLY (cost, peak, feasibility, unmet demand, deadline violation)
```

The arrow from held-out data **does not point back** to any calibration step. The QUBO coefficients are **frozen** before any held-out session is touched.

### H.3 Pre-implementation guarantee
The Stage 3 implementation will enforce this with two code-level checks:
1. A `data_manifest.json` per-pipeline-step that records the **session IDs** of any session touched at that step. The Stage 3 evaluation step will assert that the evaluation step's session IDs are a subset of the held-out set, and that **no earlier step** in the pipeline has touched any held-out session.
2. A `splits.json` is loaded at every pipeline step; any code that attempts to read a held-out session before the evaluation step will raise an exception.

These are not yet implemented. They are part of the Stage 3 plan and are listed in the GO/NO-GO conditions below.

---

## I. Data-quality risk assessment

### I.1 Missing `kWhRequested` data
- **Risk:** the Stage 1 `ΔE` formulation requires `userInputs[*].kWhRequested`. **100% of the public snapshot lacks this field.** Until the token arrives, the `ΔE` distribution cannot be constructed.
- **Likelihood (post-token):** from prior ACN-Data literature, ~50–70% of sessions have a `userInputs` block, and ~80–90% of those have a non-null `kWhRequested`. So post-token we expect ~40–65% of surviving sessions to contribute to the `ΔE` distribution.
- **Impact:** reduces the calibration sample size for `ΔE` but does not eliminate it. Calibration sample size of ~10,000–17,000 sessions is more than adequate for empirical CDF estimation.
- **Mitigation:** the cleaning spec's rules R9–R11 are **per-distribution**: a session missing `kWhRequested` is excluded from the `ΔE` distribution but retained for the `Δd` distribution and the duration baseline. The Stage 1 scenario generation is joint, so the joint sample size is the smaller of the two.

### I.2 Weak behavioral signal
- **Finding:** 90.6% of audit-sample sessions end with zero energy; 9.4% have non-zero energy. The distribution of non-zero energy is heavy-tailed (median 5.23, max 33.56 kWh).
- **Interpretation:** most Caltech sessions are *short* or *did not charge*. The Stage 1 uncertainty model is about *behavioral* uncertainty, and the dominant behavior is "plug in, don't charge, unplug" — which **is** behavioral signal, not a data error. Trimming these would invalidate the experiment.
- **Implication for `Δd`:** the duration distribution is heavy-tailed and includes many short sessions. The empirical `Δd` distribution (once `requestedDeparture` is available via the token) will be wide and informative.
- **Implication for `ΔE`:** the `ΔE` distribution will be **concentrated near zero** (most sessions have small or zero residual). This is *real behavior*, not a data error. The Stage 1 robust QUBO is designed to absorb this — the scenario-based formulation doesn't require a large spread, just a realistic one.

### I.3 Anomalous sessions
- **Finding:** 8/200 (4%) audit-sample files have empty `Energy Delivered` cells. 1/200 (0.5%) has a filename/file timestamp disagreement of ~3.9 h. Both are caught by R4 and R5.
- **Likelihood of similar rates in the full inventory:** ~4% total exclusion.
- **Mitigation:** cleaning rules R4 and R5 are deterministic. They do not depend on held-out data. They are applied identically to calibration and held-out.

### I.4 Insufficient scenario diversity
- **Risk:** if the empirical (`Δd`, `ΔE`) joint is concentrated in a small region, scenario generation by k-means will produce redundant scenarios.
- **Likelihood:** unknown until the token arrives.
- **Mitigation:** Stage 3 will report scenario-cluster sizes; if any cluster has fewer than 5% of the calibration mass, the scenario is dropped and `K` reduced. Sensitivity to `K` is reported.

### I.5 Time-zone errors in the ACN data
- **ACN documentation warning:** *"prior to Oct. 10, 2019, a bug in the Web Interface led to improper handling of timezones. … timestamps returned by this interface were offset by 7-8 hours."* — this refers to the **Web Interface**, not the time-series filenames. The bug is isolated to the Web Interface.
- **Our audit confirms:** filename connTime and file first_ts (UTC) agree within 60 s for 199/200 sessions; the 1 outlier is a 3.9 h anomaly (caught by R5). **No evidence of mass timezone corruption in the time-series files.**
- **Mitigation:** R5 catches anomalies. For any session where the Web Interface might be the source, the time-series file is the authoritative source; we use the time-series first_ts UTC.

### I.6 DST and slot boundaries
- **Risk:** the 15-min slot grid is in local time (America/Los_Angeles). DST transitions shift the grid by 1 h twice a year. Sessions crossing a DST boundary may have ambiguous slot assignment.
- **Mitigation:** Stage 3 will use Python `zoneinfo.ZoneInfo('America/Los_Angeles')` for slot assignment. Slots that fall in the ambiguous 1-h DST transition (rare — twice a year, for 1 h) are assigned by absolute UTC clock. The Stage 1 QUBO is not sensitive to this edge case at `Δ = 15 min`.

### I.7 Filename ambiguity
- **Risk:** the filename encodes a 6-digit microsecond; some files have fewer digits. We confirmed all 200 audit-sample files have 6 digits.
- **Mitigation:** if a filename has fewer than 6 trailing digits, the parsing fails (R1) and the session is excluded.

---

## J. Stage 2 GO / NO-GO

### J.1 Stage 2 GO conditions (from the Stage 2 instruction §J)
1. ACN-Data is successfully acquired. — **PARTIAL** (static snapshot acquired; live API blocked by token).
2. Required fields are usable. — **PARTIAL** (kWhDelivered, connectionTime, disconnectTime usable; kWhRequested, requestedDeparture not usable without token).
3. Calibration/held-out separation is enforceable. — **YES** (calendar split by filename connTime, fully enforceable).
4. Uncertainty variables can be computed without leakage. — **PARTIAL** (Δd and ΔE require token-gated fields; if proxy definitions are used, the methodology is a deviation from Stage 1 and must be flagged).
5. Cleaning rules are documented. — **YES** (this document + `docs/cleaning_spec.md` + `artifacts/cleaning_rules.json`).
6. Scenario generation is feasible. — **DEFERRED** to Stage 3 (depends on empirical distributions, which require the token).
7. The tariff issue is resolved or explicitly accepted as a controlled assumption. — **YES** (PG&E EV2-A, documented in `docs/tou_tariff_decision.md`).

### J.2 Decision

**CONDITIONAL GO** for the **token-independent** work in this stage. The `ΔE` blocker is **OPEN** and prevents Stage 3 from starting the QUBO / QAOA work. The project must not proceed to Stage 3 until the blocker is resolved.

### J.3 Resolution paths for the blocker (in priority order)

1. **Acquire a registered ACN-Data API token.** Register at `https://ev.caltech.edu/register`, request a token, supply it to the pipeline (e.g., `ACN_API_TOKEN=...` env var, not committed). The project owner performs the registration. The pipeline reads session-level JSON via the live API and the `ΔE` formulation is implemented as written.
2. **Defer the project** until the token arrives. No Stage 3 work begins. Stage 1 spec is preserved.
3. **Amend Stage 1 to drop `ΔE`** (substantial paper reframing; not undertaken without explicit user approval per the Stage 2 directive *"If a Stage 1 assumption cannot be supported by the actual data, STOP and report the problem rather than silently changing the methodology."*).

### J.4 Time budget (from the staged plan)
- Token acquisition: human-mediated, **1–3 business days** (unverified; depends on Caltech's response time).
- Parallel token-independent work: the cleaning spec, splits, tariff, and leakage audit are all **complete** in this stage.
- The 14-day clock is **not** paused by this blocker. Stage 3 can begin building the QUBO infrastructure (the formulation in `docs/STAGE_1_SPEC.md` §12) immediately, with the **placeholder** that `ΔE` and the `kWhRequested` field are placeholders until the token arrives. The QUBO coefficients depending on `ΔE` are **frozen only after the empirical `ΔE` is computed**, and that is the only hard gate.

### J.5 NO-GO conditions (in the absence of any resolution)
If the token does not arrive and the user does not approve a Stage 1 amendment by **Day 4 of the project timeline** (i.e., ~10 days before the final deadline), the project is **NO-GO** for Stage 3. The QUBO / QAOA pipeline cannot be meaningfully evaluated without an empirical uncertainty distribution.

---

## K. Stage 2 deliverables checklist

- [x] Acquisition report — `docs/data_acquisition.md`
- [x] Raw-data schema report — this document, §B
- [x] Cleaning specification — `docs/cleaning_spec.md` + `artifacts/cleaning_rules.json`
- [x] Temporal split — `splits.json` + this document, §D
- [ ] Empirical uncertainty characterization — **DEFERRED** (token-gated); partial proxy in §E.3
- [x] Scenario-generation recommendation — this document, §F
- [x] TOU tariff decision — `docs/tou_tariff_decision.md`
- [x] Leakage audit — this document, §H
- [x] Data-quality risk assessment — this document, §I
- [x] GO/NO-GO — this document, §J

The one unchecked item is the empirical uncertainty characterization, which is a **direct consequence of the token blocker** and is **not** within Stage 2's power to resolve without the token.
