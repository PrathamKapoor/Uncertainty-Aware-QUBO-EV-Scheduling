# Stage 10 — Appendix E: Real-Data Execution Protocol

**Purpose.** When the ACN_API_TOKEN becomes available, this protocol is the **only** sequence of operations that should be executed. It contains **no methodology decisions**: the configuration is loaded from `artifacts/final_experiment_config.json` (frozen) and the entire pipeline is data-agnostic (only the data source changes).

**When the token is unavailable, this protocol is not executed.** No real-data result exists. The manuscript reports the methodology as validated and the real-data experiment as PENDING.

---

## E.1 Pre-execution checklist (operational)

1. Verify `ACN_API_TOKEN` is set in the environment.
2. Verify `https://ev.caltech.edu/api/v1/sessions/caltech?page=1` returns 200 OK (probe with the token).
3. Verify the frozen configuration in `artifacts/final_experiment_config.json` is unchanged from `stage7.v1`.
4. Verify the configuration hash (`artifacts/final_config_hash.json`) matches.
5. Record the execution timestamp and the API endpoint in `artifacts/stage9_experiment_start.json` (or its successor).
6. **No** modification of any methodology parameter.

## E.2 Data acquisition

1. Acquire Caltech session records from `2018-05-01` to `2020-01-01` UTC using `acnportal` `DataClient` with the token.
2. Use the `sessions/caltech` endpoint.
3. Paginate via HATEOAS `next` link; 25 sessions per page.
4. Save raw response to `artifacts/real_raw_sessions.json`.
5. Compute SHA-256 of the raw file; record in the acquisition manifest.
6. Record every HTTP status code and every retry in the acquisition manifest.

## E.3 Schema validation

1. For each session record, verify the presence of:
   - `sessionID` (or `sessionId`)
   - `connectionTime` (UTC)
   - `disconnectTime` (UTC)
   - `kWhDelivered` (float)
   - `userInputs[*].kWhRequested` (last `modifiedAt`)
   - `userInputs[*].requestedDeparture` (last `modifiedAt`)
   - `siteID`
2. If the schema does not contain the required fields, **STOP**. Do not substitute proxies.

## E.4 Cleaning

Apply exactly the rules in `docs/cleaning_spec.md` and `artifacts/cleaning_rules.json` (rules R1-R11 from Stage 2). Do not inspect method performance before deciding exclusions.

## E.5 Temporal split

- Calibration: `2018-05-01T00:00:00+00:00` to `2019-07-01T00:00:00+00:00` (exclusive end).
- Held-out: `2019-07-01T00:00:00+00:00` to `2020-01-01T00:00:00+00:00` (exclusive end).
- Verify `intersection(cal, ho) = empty`.
- Verify that the `UncertaintySample.calibration` boolean is set correctly per session.

## E.6 Real uncertainty

1. For each session:
   - `DeltaE = E_delivered - E_requested` (from `userInputs[*].kWhRequested`, last `modifiedAt`).
   - `Delta d = (d_requested - d_actual)` in minutes (last `modifiedAt`).
2. Save calibration and held-out samples separately to `artifacts/real_calibration_samples.json` and `artifacts/real_heldout_samples.json`.
3. Compute descriptive statistics for both ΔE and Δ d.
4. Compute joint (Δ d, ΔE) distribution on calibration only.
5. **Do not** use held-out samples to fit the distribution.

## E.7 Scenario generation

1. On calibration (Δ d, ΔE) joint, run k-means with K=8 (frozen) using the seed `20260829 + 8`.
2. Standardize using calibration mean/std; apply to all scenarios.
3. Save scenarios to `artifacts/real_scenarios_K8.json`.
4. Save K=4 and K=16 sensitivity to `artifacts/real_scenarios_K{4,16}.json` for diagnostic only.

## E.8 Compute γ (calibration only)

1. For each EV in the headline instance (`toy_B_3x4` with 3 EVs), Monte-Carlo over the calibration joint to compute `sigma_i = std(R_i(omega))` and `R_bar_i = mean(R_i(omega))` per EV.
2. Aggregate: `gamma = 1 + alpha * mean(sigma_i / R_bar_i)` with `alpha = 1.0` (frozen).
3. Save to `artifacts/real_calibration_parameters.json`.
4. **Freeze γ immediately.** Do not modify on held-out data.

## E.9 Build F0 / F1 / F2 / F3

1. F0: deterministic QUBO with the frozen penalties.
2. F1: scenario-averaged robust QUBO with the corrected Stage 6 scenario transformation (variable set fixed; M_window diagonal on out-of-window slots; R_i modified by DeltaE).
3. F2: F1 with `rho_d <- gamma * rho_d`.
4. F3: oracle. Realized (Δ d, ΔE) at evaluation time. **Analysis only.**

## E.10 Run exact and QAOA

1. Exact classical solution for all 2^11 = 2048 bitstrings (11 qubits is small).
2. QAOA with the frozen configuration: p=1, COBYLA, seeds [0,1,2], shots 1024.
3. Save raw QAOA output (parameters, samples, counts) per seed.

## E.11 Held-out evaluation

1. For each held-out session, apply the F0/F1/F2/F3 schedule.
2. Compute the four-metric feasibility (`qubo_feasible`, `energy_feasible`, `site_feasible`, `deadline_feasible`) and the aggregate.
3. Compute cost, unmet energy, peak load, deadline-violation rate, site-cap-violation rate.

## E.12 Statistical analysis

1. Primary comparison: F2 vs F0 on P(feasible), paired bootstrap 95% CI.
2. Secondary comparisons: F1 vs F0, F2 vs F1 (Bonferroni α = 0.05 / 3).
3. Secondary outcomes: cost, unmet, deadline, site violations.
4. Do not redefine the primary endpoint. Do not change α based on the result.

## E.13 Real-data figures and tables

1. Generate the figures in `artifacts/stage10_figure_manifest.json` (R1-R8) and the tables in `artifacts/stage10_table_manifest.json` (R-T1 to R-T8).
2. Programmatic generation from machine-readable artifacts only. No manual transcription.
3. Every number must trace to an artifact.

## E.14 Number-consistency re-audit

1. Re-run `artifacts/stage10_number_audit.json` and `artifacts/stage10_claim_audit.json`.
2. Verify that every numerical claim in the manuscript maps to an artifact.
3. Verify that no synthetic value has been substituted for a real-data value.
4. Verify that the frozen configuration hash is unchanged.

## E.15 Update manuscript

1. Populate the real-data tables in `docs/STAGE_10_PAPER.md` (R-T1 to R-T8) with real values.
2. Update the abstract and conclusion with the real empirical result.
3. Run `artifacts/stage10_claim_audit.json` re-validation.
4. Re-run `artifacts/stage10_terminology_audit.json` re-validation.

## E.16 Token-arrival prohibitions

When the token arrives, the research team is NOT permitted to:

- Modify α, K, γ, M_window, ρ_d, ρ_p, ρ_cap, or any other frozen parameter.
- Modify the temporal split.
- Modify the cleaning rules.
- Modify the feasibility definition.
- Modify the QAOA configuration.
- Modify the QAOA seeds.
- Selectively remove difficult sessions.
- Redefine ΔE or Δ d signs.
- Selectively report favorable seeds or sites.
- Re-run until a preferred result appears.
- Change the primary endpoint.
- Call exploratory analysis preregistered.
- Claim quantum advantage.

The only permitted action is: **execute the protocol, then report the result honestly**.

If a genuine implementation error is discovered:

1. Document it independently.
2. Demonstrate the error.
3. Apply a transparent correction.
4. Re-run the affected analyses.
5. Record the correction in the manuscript.

Otherwise: the frozen methodology remains frozen. The real result is what it is.
