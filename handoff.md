# handoff.md — Stage 9 / Stage 10 continuity pointer

**Date of this handoff:** 2026-08-30 (resumed session).
**Authoritative continuity document:** [`docs/TOKEN_HANDOFF.md`](docs/TOKEN_HANDOFF.md).
**Project root:** `C:/Projects/uncertainity_aware_quantum_opt`.

**2026-08-30 update:** A token was disclosed via the chat during this
session. The agent refused to use it (it must be supplied only via the
`ACN_API_TOKEN` or `ACNPORTAL_TOKEN` environment variable). The token
string is NOT present in any file in the repository; the user is advised
to revoke that token and re-issue. See `docs/TOKEN_HANDOFF.md` §11 and
`artifacts/token_leak_incident_2026-08-30.json` for the full incident
record.

This file exists because the harness's "resume from handoff.md" procedure
looks for a top-level `handoff.md`. The project's own handoff procedure is
`docs/TOKEN_HANDOFF.md`; that file is the source of truth. This file is a
short pointer so a fresh agent session can orient itself in one read.

---

## 1. One-paragraph state

The project is an uncertainty-aware QUBO framework for EV charging
scheduling (Stages 1-8 complete, methodology frozen at
`artifacts/final_experiment_config.json` version `stage7.v1`). Stage 9 is
the real-data experiment, BLOCKED on the ACN-Data API token. The
`docs/TOKEN_HANDOFF.md` document records that the token was received and
authenticated in a prior session, but the token is supplied only through
the `ACN_API_TOKEN` (or `ACNPORTAL_TOKEN`) environment variable and is
**NEVER** written to a file. In this resumed session, the token is **not
in the environment**, so the real experiment REFUSES to run (per the
Stage 9 directive: STOP rather than pretend).

The methodology is ready, the infrastructure is now complete, the live-API
fetcher is implemented, and the Stage 9 driver is implemented. Setting
`ACN_API_TOKEN` and running `python -m stage9.real_experiment` will execute
the entire E.2-E.15 protocol end-to-end with the frozen methodology.

## 2. What to read first (in this order)

1. `docs/TOKEN_HANDOFF.md` — full handoff including the session-continuity
   log in §10.
2. `docs/STAGE_9_REAL_EXPERIMENT.md` — the real-experiment directive and
   planned procedure (§3).
3. `docs/STAGE_10_REAL_DATA_PROTOCOL.md` — the 20-step execution protocol
   (Appendix E of the paper).
4. `docs/STAGE_10_PAPER.md` — the manuscript, with PENDING placeholders in
   §7 that get populated by the real experiment.
5. `artifacts/final_experiment_config.json` — the frozen methodology. The
   raw-file SHA-256 is `4a08e1e65587cc904521ff1bfc955b30671a5cb3485664d8b75f1ad93d9013b3`.
   This MUST remain unchanged.
6. `artifacts/stage9_experiment_start.json` — the blocker record from the
   prior session. Status: BLOCKED.

## 3. What was done in this session (resumed 2026-08-30)

- Read the handoff and verified the repo state.
- Implemented `stage5/uncertainty.py::load_real_uncertainty` (was
  `NotImplementedError`). It now fetches from the Caltech live API with
  HTTP Basic auth, HATEOAS pagination, strict schema gating, and frozen
  Δd/ΔE sign conventions. The token is never logged.
- Implemented `stage9/real_experiment.py`: the single executable that
  runs the E.2-E.15 protocol end-to-end. Refuses to run without the
  token. Refuses on config tamper. Namespaces outputs as `artifacts/real_*`
  so the Stage 1-8 artifacts are preserved.
- Verified the frozen config hash is unchanged.
- Token-security audit on the new code: no leaks.
- Did NOT execute the real experiment (no token in env).
- Did NOT modify the frozen methodology, the Stage 10 paper, or the
  Stage 1-8 artifacts.

## 4. What the next session must do

1. If `ACN_API_TOKEN` is supplied in the environment, run
   `python -m stage9.real_experiment` from the repo root. The driver will:
   - Acquire real data from `https://ev.caltech.edu/api/v1/sessions/caltech`.
   - Apply R9-R11 cleaning, the frozen temporal split, the K=8 scenario
     k-means (seed = 20260829 + 8).
   - Freeze γ on calibration only.
   - Build F0/F1/F2/F3 with the frozen penalties.
   - Run exact classical + QAOA (p=1, COBYLA, seeds [0,1,2], shots 1024).
   - Evaluate on held-out, compute paired bootstrap CIs (F2 vs F0 primary;
     Bonferroni-corrected F1 vs F0, F2 vs F1 secondary).
   - Write all artifacts to `artifacts/real_*.json` and
     `artifacts/stage9_*.json`. Re-verify the methodology hash unchanged.
2. Populate the PENDING placeholders in `docs/STAGE_10_PAPER.md` §7 from
   the new artifacts. The driver does NOT touch the paper (by design;
   the paper update is a separate editorial step).
3. Re-run `artifacts/stage10_number_audit.json` and
   `artifacts/stage10_claim_audit.json` with the real values.

## 5. Hard prohibitions (per Stage 9 directive and TOKEN_HANDOFF.md)

- Do NOT modify any frozen parameter (K, α, γ, M_window, ρ_d, ρ_p, ρ_cap,
  P_target, P_site_max, QAOA p, optimizer, seeds, shots, Δ, temporal
  split, cleaning rules, feasibility definition, sign conventions).
- Do NOT selectively remove difficult sessions.
- Do NOT re-run until a preferred result appears.
- Do NOT call exploratory analysis preregistered.
- Do NOT claim quantum advantage.
- Do NOT substitute the synthetic Stage 7/8 results for real data.
- Do NOT write the token to any artifact, filename, log, exception, or
  git-tracked file.

The only permitted action is: **execute the protocol, then report the
result honestly**.

## 6. Files added or modified in this session

| Path | Change |
|---|---|
| `stage5/uncertainty.py` | `load_real_uncertainty` live-API fetcher implemented |
| `stage9/__init__.py` | New module marker |
| `stage9/real_experiment.py` | New driver (E.2-E.15) |
| `docs/TOKEN_HANDOFF.md` | §10 added (session-continuity log) |
| `handoff.md` | This file |
| `artifacts/final_experiment_config.json` | UNCHANGED (frozen) |
| `docs/STAGE_10_PAPER.md` | UNCHANGED (placeholders PENDING) |
| All Stage 1-8 artifacts | UNCHANGED |

## 7. Pointers to the next handoff

When this session's work is complete, update §10 of `docs/TOKEN_HANDOFF.md`
with the new session's findings, refresh this `handoff.md` to point to the
latest state, and leave the Stage 1-8 artifacts untouched. The frozen
methodology in `artifacts/final_experiment_config.json` (version
`stage7.v1`) remains the source of truth for all numeric claims.
