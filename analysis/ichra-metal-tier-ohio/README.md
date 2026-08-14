# ICHRA metal-tier choice — Ohio

Analysis output spanning two task arms. It lives here rather than inside either
task because it covers both.

| Task | Role |
|---|---|
| [`survey_ichra-metal-tier-ohio`](../../application/tasks/survey_ichra-metal-tier-ohio/) | control — forfeit rule stated once, unemphasized |
| [`survey_ichra-metal-tier-ohio-salient`](../../application/tasks/survey_ichra-metal-tier-ohio-salient/) | treatment — same rule made prominent |

The write-up is [RESULTS.md](RESULTS.md).

## Reproducing the underlying data

Source jobs: `pg-survey-ichra-metal-tier-ohio-668679a2` (control) and
`pg-survey-ichra-metal-tier-ohio-salient-8f156186` (treatment) — same 100
persona ids, seed 42, `anthropic/claude-sonnet-4-6`, pool
`persona/datasets/matraix-persona-1m`, `perCell: 25` across the four age
brackets.

Per-trial answers and free-text rationales live under
`jobs/<job>/<trial>/artifacts/app/output/survey_result.json`, joined to persona
attributes via `jobs/<job>/<trial>/persona_meta.json` → `persona_path`. `jobs/`
is gitignored, so those artifacts are local to whoever ran the job.

The figures in RESULTS.md come from four `askRationale` questions —
`q_tier_choice`, `q_tier_if_more`, `q_switch_driver`, `q_subsidy_tradeoff` —
796 rationales in total across both arms.

The dominated-choice flag is derived, not recorded: map each persona's
`age_bracket` to its midpoint (25-34 → 30, 35-44 → 40, 45-54 → 50, 55-64 → 60),
look up the median on-exchange premium per tier at that age, and compare the
chosen tier against the richest tier priced at or below the persona's
allowance.

A flat CSV of all 796 rationales was deliberately left out of the repo to stay
inside the data policy on generated dumps. It is a short script away from the
job artifacts, and available on request from whoever ran the jobs.
