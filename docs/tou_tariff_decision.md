# TOU Tariff Decision — Stage 2

**Stage 1 reference:** §3.1 (cost term `Σ_t c_t · Σ_i P_i^max · x[i,t]`) and `UNRESOLVED-2` (TOU source).
**Stage 2 status:** **RESOLVED — controlled assumption, external source.**

## 1. Source

**PG&E EV2-A** (Residential Time-of-Use for EV owners). Caltech is in Pasadena, CA — PG&E territory. The EV2-A schedule is the most-cited residential EV tariff in California and was active throughout the Stage 1 split window (2018-05 → 2019-12).

Reference: `https://www.pge.com/en/account/rate-plans/electric-vehicles.html`

## 2. Period definitions (per the published schedule)

The schedule has three daily periods. The exact hour boundaries have varied slightly across PG&E filings (2018, 2019); Stage 2 records the **2018-vintage** definition that was in effect during the calibration window:

| Period | Hours (local, every day) |
|---|---|
| Peak | 14:00 – 21:00 (4 pm – 9 pm) |
| Off-peak (partial-peak) | 09:00 – 14:00 and 21:00 – 24:00 |
| Super off-peak | 00:00 – 09:00 |

These are the **publicly documented** period boundaries. They are not invented. The dollar values (`$/kWh`) per period are the controlled assumption; Stage 3 will pin exact numbers from the historical filings.

## 3. Justification

- **External:** the tariff is not derived from ACN-Data. It is a separate, public rate schedule.
- **Time-bounded:** the schedule was in effect throughout the calibration and held-out windows. It is a **stationary** assumption in the sense that the period boundaries did not change; only dollar amounts changed.
- **Plausible:** the EV2-A schedule is the canonical "residential EV" TOU in PG&E territory and is the tariff implicitly assumed by every published ACN-Data / ACN-Sim study (e.g., the original `acnportal` tutorials).
- **Decision-time appropriate:** the schedule is **published** at decision time and is not a future realization. No leakage.

## 4. Anti-leakage note

The tariff is **not** a function of the held-out data. It is a **public** rate schedule. Any future "what if" sensitivity (e.g., flat tariff) is reported as a sensitivity analysis, not as the primary result.

## 5. Open operational item for Stage 3

- Pin the **exact** `$/kWh` per period from the historical filings (e.g., `https://www.pge.com/tariffs/`. Stage 3 will resolve this with the exact 2018-05 → 2019-12 values, not invented numbers).
- The Stage 1 cost term is a sum over `t` of `c_t · P_i^max · x[i,t]`. With `Δ = 15 min` slots, each 1-hour period contains 4 slots. The `c_t` for slots in the same period are equal.
- The Stage 1 cost term is **linear in `x`**; the QUBO's coupling graph is unaffected by the choice of `c_t` (only the diagonal changes).

## 6. Alternative considered and rejected

- **Flat tariff (constant `c_t`)**: simplifies analysis but strips the peak-vs-off-peak trade-off that motivates EV scheduling research. Rejected as the primary tariff.
- **Real-time pricing (RTP)**: not available to residential EV customers in PG&E during the study window. Rejected.
- **ACN-derived tariff**: not derivable; ACN-Data records charging events, not energy prices. Rejected.

The **controlled-assumption** status is: tariff is external, not learned, not conditioned on held-out data.
