# ICHRA Metal Tier Choice — Ohio (salient-forfeit arm)

Treatment arm of a paired A/B against
[`survey_ichra-metal-tier-ohio`](../survey_ichra-metal-tier-ohio/README.md).

## What this tests

The control run produced a striking result: **28 of 100 personas chose a metal
tier strictly worse than one their allowance also covered in full.** At age 40
on a $1,000 allowance, gold runs $709 — fully covered — yet 11 personas took
bronze or silver. Their rationales show they saw the option and declined it:

> "Gold would also fit within the allowance at $991, but Silver strikes a
> reasonable middle ground... without overpaying."

There is no overpaying. Unused allowance is forfeited, so every plan priced at
or below the allowance costs the persona the same: nothing. The personas
applied a household don't-overspend heuristic to a use-it-or-lose-it benefit.

Two explanations fit that result equally well, and the control run cannot
separate them:

1. **Behavioral.** People really do reason this way about an unfamiliar
   benefit, and the same thing would happen at a real open enrollment.
2. **Instrument artifact.** The control context states the forfeit rule once,
   unemphasized, as the fifth of nine bullets. The personas may simply not
   have weighted it.

## The manipulation

This arm changes **salience only — no new facts.** Two edits to
`input/context.md`:

- The existing forfeit bullet is bolded and spelled out ("the leftover money
  goes back to your employer, you never see it").
- A bolded paragraph after the allowance table restates the same rule in
  concrete terms ("picking a $400 plan on a $1,000 allowance forfeits $600").

`questionnaire.yaml`, `instruction.md`, `reporting.json`,
`persona_strategy.json`, and `tests/` are byte-identical to the control. Verify
before trusting any comparison:

```bash
diff -r application/tasks/survey_ichra-metal-tier-ohio \
        application/tasks/survey_ichra-metal-tier-ohio-salient
```

Only `context.md`, `task.toml` (name and tags), and this README should differ.

## Running it as a pair

Launch this arm against **the same 100 persona ids and the same seed** as the
control run. Personas carry no memory across trials, so pairing costs nothing
and removes persona heterogeneity from the comparison entirely — each persona
acts as its own control.

The outcome measure is the **dominated-choice rate**: the share of personas
choosing a tier when a richer tier was also fully covered by their allowance.
Control = 28/100. Compute it by mapping each persona's age bracket to its
midpoint premium, then comparing the chosen tier against the richest tier
priced at or below the allowance.

Read the result as follows:

- **Rate drops sharply** → the control finding was largely an instrument
  artifact. The behavioral claim does not hold, and the number to quote is
  this arm's.
- **Rate holds** → salience is not the constraint. The don't-overspend
  heuristic survives being told plainly, which is a real enrollment-design
  problem worth acting on.

Either way the answer is useful; only one of them is a finding about people.

## Outcome

Both arms have been run. The rate held — 28/99 control versus 27/99 treatment,
with 92 of 99 personas choosing the identical tier in both. Salience is not the
constraint. See
[analysis/ichra-metal-tier-ohio/RESULTS.md](../../../analysis/ichra-metal-tier-ohio/RESULTS.md).
