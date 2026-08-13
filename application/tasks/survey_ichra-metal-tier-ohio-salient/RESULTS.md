# A/B result: forfeit-rule salience does not move tier choice

Both arms have been run. **The manipulation had no effect.** Making the
forfeit rule prominent did not reduce the dominated-choice rate.

## Runs

| Arm | Job | Trials |
|---|---|---|
| Control (`survey_ichra-metal-tier-ohio`) | `pg-survey-ichra-metal-tier-ohio-668679a2` | 100/100 succeeded |
| Treatment (this task) | `pg-survey-ichra-metal-tier-ohio-salient-8f156186` | 99/100 succeeded |

Identical persona ids, seed 42, `anthropic/claude-sonnet-4-6`, pool
`persona/datasets/matraix-persona-1m`, 25 per age bracket. One treatment trial
failed on an Anthropic read timeout; that persona is dropped from **both** arms,
so every figure below is paired on the same 99.

## Outcome

Dominated choice = persona picked a tier when a richer tier was also fully
covered by its allowance, priced at the age-bracket midpoint.

| Arm | Dominated | Rate |
|---|---|---|
| Control — rule buried as 5th of 9 bullets | 28/99 | 28% |
| Treatment — rule bolded, restated concretely | 27/99 | 27% |

Tier mix moved no further: bronze 12 → 12, silver 64 → 63, gold 23 → 24,
declines 0 → 0.

By band, flat exactly where an effect would have to appear:

| Band | n | Control | Treatment |
|---|---|---|---|
| $500 (27-35) | 25 | 0 | 0 |
| $1,000 (36-45) | 24 | 11 | 12 |
| $1,500 (46-64) | 50 | 17 | 15 |

The $500 band is 0 in both because nothing is dominated there — the allowance
genuinely does not reach gold at those ages.

## Paired switching

92 of 99 personas chose the **identical** tier in both arms. The 7 who moved
went both directions — 3 silver→gold, 2 gold→silver, 1 bronze→silver, 1
silver→bronze. Symmetric movement at that scale is noise, not treatment.

## Why it failed to move

Treatment personas did the arithmetic correctly and chose down anyway:

> "My $1,500 allowance covers it fully with $669 left over, so I pay nothing
> out of pocket... Gold at $991 is also within reach, but Silver..."

They knew gold was free. They knew the leftover was identical either way.

**Zero personas in either arm used forfeit language** — "forfeit", "leftover",
"goes back", "never see it" — anywhere in their tier rationales, including the
27 treatment personas who chose dominated tiers with the bolded rule two
paragraphs above the question. The rule was read and did not enter the
decision.

What these personas optimize is a felt sense of appropriate coverage
("reasonable middle ground", "responsible for a family"), not the actual
budget constraint. Silver reads as the sensible choice regardless of price.

## What follows

Per the decision rule fixed before the run: the rate held, so **salience is not
the constraint and the control finding was not an instrument artifact.**
Disclosure is not the lever — stating the rule harder does not change behavior.

The untested alternative is removing the arithmetic instead of explaining it:
label each covered tier "$0/month to you" and default-select the richest
covered plan, rather than showing premiums and expecting the employee to reason
from allowance to dominance. That is a different manipulation — presentation of
the choice set, not disclosure of a rule — and would need its own arm.

## Scope

Simulated North American working adults reasoning about a real Ohio PY2026
price sheet. This establishes that the pattern is robust to wording. It is not
evidence that 27% of real Ohio employees behave this way.
