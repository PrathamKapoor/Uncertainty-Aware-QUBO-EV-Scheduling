"""Stage 9 -- Real ACN-Data experiment driver.

The driver is the operational implementation of
docs/STAGE_10_REAL_DATA_PROTOCOL.md sections E.2 through E.15. It runs
end-to-end with the FROZEN methodology from artifacts/final_experiment_config.json
(stage7.v1) and the FROZEN cleaning rules in artifacts/cleaning_rules.json.

Hard rules (per the Stage 9 directive and TOKEN_HANDOFF.md):

  * No parameter, penalty, scenario, K, alpha, gamma, M_window, QAOA setting,
    seed, temporal split, or cleaning rule may be modified based on real data.
  * No fabrication. No proxy substitution. No silent retries.
  * If the token is absent, REFUSE to run. Do not pretend the real experiment
    was executed. Do not substitute the synthetic Stage 7/8 results.
  * The token is read from ACN_API_TOKEN or ACNPORTAL_TOKEN. It is NEVER
    written to a file, NEVER logged, NEVER echoed in errors.
  * Every artifact written here is namespaced "real_*" to avoid clobbering
    the Stage 1-8 artifacts in artifacts/.
"""
