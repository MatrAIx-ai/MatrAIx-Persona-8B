# ICHRA Metal Tier Choice — Ohio

Measures which metal tier (bronze / silver / gold) a working-age Ohio adult
buys when an employer replaces its group plan with an ICHRA whose monthly
allowance is scaled by age band.

## Design

The employer allowance is a function of the persona's own age:

| Age | Monthly allowance |
|---|---|
| 27-35 | $500 |
| 36-45 | $1,000 |
| 46-64 | $1,500 |

Each persona reads that table in `input/context.md`, finds its own row, and
answers once. `q_allowance_band` records which band the persona placed itself
in, so allowance is a recorded variable rather than an assumption — cross-tab
`q_tier_choice` against it to get the tier mix per allowance level.

Age-scaled ICHRA contributions are permitted (the allowance may vary with age
in line with the premium age curve), so this mirrors a design an Ohio employer
could actually offer.

**Allowance and age are confounded by construction.** A bronze skew in the
$500 band cannot be separated into "young people buy bronze" versus "a small
allowance buys bronze" — the design ties them together. If you need those
pulled apart, run a second job with a flat allowance across all ages and
difference the two.

`q_tier_if_more` adds a +$250 counterfactual, giving a one-step elasticity read
without a full within-subject battery.

## Known result

In the first run of this task, 28 of 100 personas chose a metal tier strictly
worse than one their allowance also covered in full — the leftover allowance is
forfeited, so the richer plan was free to them. A paired A/B against
[`survey_ichra-metal-tier-ohio-salient`](../survey_ichra-metal-tier-ohio-salient/README.md)
showed the rate is not an artifact of how this task words the forfeit rule:
making the rule prominent moved it 28% → 27%. Write-up and raw rationales:
[analysis/ichra-metal-tier-ohio/](../../../analysis/ichra-metal-tier-ohio/).

## Premium anchors

`input/context.md` carries real Ohio plan-year-2026 figures — median
on-exchange premium by tier at ages 27 / 30 / 40 / 50 / 55 / 64, non-tobacco,
Rating Area 11 (Columbus area), plus median deductible and out-of-pocket max by
tier. Premiums nearly triple from age 27 to 64 under the federal age curve, so
the allowance bands buy very different plans: $500 covers a bronze plan outright
at 27, while $1,500 does not reach gold at 64.

## Persona targeting

`persona_strategy.json` filters to age brackets 25-34 through 55-64, North
America, employed full- or part-time, stratified evenly across the four age
brackets at n=100.

Three limits worth knowing before reading results:

- **Age is bracketed, and the brackets do not line up with the allowance
  bands.** The pool carries 25-34 / 35-44 / 45-54 / 55-64, while the bands cut
  at 27-35 / 36-45 / 46-64. Personas in the 35-44 bracket straddle the $500 and
  $1,000 bands and resolve it themselves in `q_allowance_band` — which is why
  that answer is recorded rather than inferred.
- **There is no state dimension.** `region` is continental ("North America").
  Ohio enters through the scenario text and the premium table, not through
  persona attributes — these are North American working adults reasoning about
  an Ohio offer, not verified Ohio residents.
- **n=100 requires the `matraix-persona-1m` pool.** The checked-in
  `matraix-persona-dev-sample` holds only 65 personas matching these filters.
