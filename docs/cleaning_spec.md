# Stage 2 — Cleaning Specification

**Source dataset:** ACN-Data static time-series snapshot (Caltech), `tongxin-li/ACN-Data-Static`.
**Audit sample:** 200 Caltech time-series files stratified across 2018-05 → 2019-12 (10 files / month).
**Blocker:** `userInputs[*].kWhRequested` not present in the public snapshot; see `data_acquisition.md` §H and `STAGE_2_DATA_AUDIT.md` §I.

This document is **leakage-safe by construction.** All exclusion rules are deterministic and apply identically to calibration and held-out. None of the rules depend on statistics fit on held-out data. The cleaning pipeline must run on the *full* Caltech file inventory; the per-month filename counts in §A are pre-split inventory, not used for any decision.

---

## A. Raw inventory (Caltech, filename-derived)

Caltech static snapshot: **48,113** time-series files across 5 garages. Monthly file counts (filename `connectionTime` UTC, see `STAGE_2_DATA_AUDIT.md` §6):

| Year-Month | Files | Window |
|---|---:|---|
| 2018-05 | 2,334 | calibration |
| 2018-06 | 2,046 | calibration |
| 2018-07 | 2,263 | calibration |
| 2018-08 | 2,693 | calibration |
| 2018-09 | 2,736 | calibration |
| 2018-10 | 2,653 | calibration |
| 2018-11 | 1,539 | calibration |
| 2018-12 | 1,462 | calibration |
| 2019-01 | 1,515 | calibration |
| 2019-02 | 1,410 | calibration |
| 2019-03 | 1,689 | calibration |
| 2019-04 | 1,883 | calibration |
| 2019-05 | 1,816 | calibration |
| 2019-06 | 1,762 | calibration |
| 2019-07 | 1,495 | **held-out** |
| 2019-08 | 1,951 | **held-out** |
| 2019-09 | 1,988 | **held-out** |
| 2019-10 | 2,184 | **held-out** |
| 2019-11 | 1,903 | **held-out** |
| 2019-12 | 1,443 | **held-out** |

Calibration total: 27,801. Held-out total: 10,964. **Enforceable** from filename connTime.

---

## B. Cleaning rules (deterministic, applied in order)

For each session, parse the filename (extract `station`, `cluster`, `evse`, `connTime` UTC, `microsec`) and the time-series body (extract `first_ts`, `last_ts`, `energy_kwh_max`, `rows`, `state_last`). Apply:

| # | Rule | Condition | Rationale | Action | Deterministic? | Affects |
|---|---|---|---|---|---|---|
| 1 | File parse OK | Filename matches regex `\d+-\d+-\d+-\d+-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-\d+` | Required to extract connTime / station / EVSE | **Keep** if OK; **exclude** if not | Yes | Bad filenames |
| 2 | Non-empty body | `rows >= 2` | Empty file has no behavior | **Keep**; **exclude** if not | Yes | Empty files |
| 3 | First-sample timestamp parseable | `datetime.fromisoformat(first_ts)` succeeds | Required for duration & offset checks | **Keep**; **exclude** if not | Yes | Malformed rows |
| 4 | Energy column non-empty | At least one row has a parseable `Energy Delivered (kWh)` value | Required to compute `kWhDelivered` | **Keep**; **exclude** if all energy cells empty | Yes | 8/200 (4%) in sample |
| 5 | Filename/file timestamp agreement | `|first_ts_UTC - filename_connTime_UTC| <= 1800 s (30 min)` | Catch filename mislabels and data-pipeline errors | **Keep**; **exclude** if > 30 min | Yes | 1/200 (0.5%) in sample (one 3.9h outlier) |
| 6 | Session duration sanity | `0 < (last_ts - first_ts) <= 7 days` | Negative or multi-week durations are data errors, not behavior | **Keep**; **exclude** if outside range | Yes | Rare; bound the upper end at 7 days = 10,080 min |
| 7 | Monotonic timestamps | `last_ts >= first_ts` | Catches clock-rollback artifacts | **Keep**; **exclude** if not | Yes | Should be subsumed by rule 6 |
| 8 | EVSE ID valid | `0 < int(evse) < 1000` | The Caltech site uses 1–~56 EVSEs (per `acnportal` Caltech site config); large numbers are not legitimate | **Keep**; **exclude** if not | Yes | None expected |

Each rule produces one exclusion reason code; the union of all rules' reasons is recorded per session.

---

## C. Effect of cleaning (on 200-file audit sample)

| Rule | Excluded | % |
|---|---:|---:|
| 1: filename parse | 0 | 0.0% |
| 2: empty body | 0 | 0.0% |
| 3: timestamp parse | 0 | 0.0% |
| 4: energy column | 8 | 4.0% |
| 5: filename/file agree | 1 | 0.5% |
| 6/7: duration sanity | 0 | 0.0% |
| 8: EVSE ID valid | 0 | 0.0% |
| **Any rule** | **8** | **4.0%** |
| Surviving sessions | 192 | 96.0% |

Projection to full inventory: ~27,801 × 0.96 ≈ **26,690 calibration sessions**; ~10,964 × 0.96 ≈ **10,525 held-out sessions**. These numbers are for the static-snapshot universe. They do **not** include the token-gated session-level metadata.

---

## D. Rules explicitly NOT applied

The following are **not** exclusion rules:

1. **Zero-energy sessions** (`energy_kwh < 0.001`): 174/192 (90.6%) of audit-sample sessions end with effectively zero energy. These are *real behavior* (the EV plugged in, did not charge, unplugged). The Stage 1 paper's claim is about *behavioral uncertainty*; these are part of the behavioral distribution. **No exclusion.**
2. **Sessions that never reach `ADAPTIVE` state**: same rationale. These are users who plugged in but never requested charge. **No exclusion.**
3. **Extreme energy values** (e.g., `> 50 kWh`): none in the sample, but if present would be *behavioral* and would **not** be excluded. The Stage 1 robust QUBO is designed to absorb them.
4. **Short sessions** (`< 5 min`): real behavior (user plugged in, changed mind, unplugged). **No exclusion.**
5. **Long sessions** (`> 24h`): real behavior (EV left overnight). **No exclusion** (subject to rule 6's 7-day cap).

Stage 1's adaptive mechanism is supposed to handle the long tail of behavior. Trimming it would defeat the experiment.

---

## E. Rules that REQUIRE the API token (not implementable on the static snapshot)

The Stage 1 uncertainty variable `ΔE = kWhDelivered − kWhRequested` requires `userInputs[*].kWhRequested`, which is only in the token-gated session-level JSON. Once a token is available:

| # | Field | Transform | Missing handling |
|---|---|---|---|
| 9 | `userInputs[*].kWhRequested` | For each session, take the **last** `userInput.modifiedAt` value (most recent user-stated energy request) | If no `userInputs` or no `kWhRequested` field, **exclude** the session from the `ΔE` distribution only; keep for the `Δd` distribution |
| 10 | `userInputs[*].requestedDeparture` | Take last `requestedDeparture` per session | If missing, **exclude** from the `Δd` distribution only; keep for the `ΔE` distribution |
| 11 | `userInputs[*].minutesAvailable` | Take last `minutesAvailable` per session | If missing, **exclude** from any duration baseline fit |

These rules are **per-uncertainty-variable**, not global, so a session missing `kWhRequested` can still contribute to the `Δd` distribution. The Stage 1 spec (§5.2 of Stage 1) implicitly assumes both fields are available; the cleaning spec here is stricter and only excludes from the relevant distribution.

---

## F. Determinism guarantee

Every rule in §B and §E is a **pure function of the session's own fields and the rule constants**. No rule uses summary statistics, distributions, thresholds learned from held-out data, or session-relative comparisons. The cleaning pipeline is reproducible from the raw data and the rule file alone.

A canonical rules file `artifacts/cleaning_rules.json` is generated alongside this document.

---

## G. Audit statistics to record

After cleaning, the pipeline must record:

- `raw_count`, `valid_count`, `excluded_count`,
- `exclusion_reasons` (a dict of reason code → count),
- `calibration_count`, `held_out_count`,
- per-window summary: `kWhDelivered` mean/median/std, duration mean/median/std, `kWhDelivered > 0` rate.

These are written to `artifacts/cleaning_stats.json` in Stage 3 (data preparation phase) once the full Caltech file inventory is processed.
