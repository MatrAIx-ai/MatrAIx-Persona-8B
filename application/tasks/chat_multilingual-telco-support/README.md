# Multilingual telco support chat (REST API)

Does a support chatbot hold the user's own language, or does it slide into English
once the question gets harder? This task puts a persona in a billing dispute with
a mock telecom operator and measures which language each reply came back in,
relative to the persona's `primary_language`.

The task is **not** hardcoded to any one language. The verifier reads
`primary_language` from the persona and measures against that; Turkish is the
reference configuration, not the subject.

SUT: `environment/task-environments/application/chatbot-api-sidecar_multilingual-telco-support`
(service `telco-support-api`). Persona agent runtime: `application/shared-chat-persona`.

Requires **Docker Compose** (local `docker` environment).

## Smoke run

**No API key** — validates Docker, the sidecar, and the verifier:

```bash
uv run harbor run -p application/tasks/chat_multilingual-telco-support -a oracle
```

The oracle opens the dispute in Turkish (answered in Turkish) and then asks for a
line-item breakdown (answered in English), so a single run produces both an
in-language reply and a fallback rather than a degenerate all-or-nothing score.

**Full run** — Playground UI or terminal auto mode: [Application Quickstart](../../../docs/quickstart.md).

## What is measured, and what is not

**Measured** — which language each assistant reply is written in, compared with the
persona's declared `primary_language`:

- the share of replies in the persona's language
- the language of the first reply
- how many times the reply language changed mid-conversation
- whether the measurement was possible at all

**Not measured:**

- **Translation quality.** A reply in the right language is counted as adherent
  even if the wording is poor.
- **Whether the bot was helpful.** That lives in `task_outcome`. A bot can answer
  perfectly in the wrong language, or uselessly in the right one, and this task
  keeps the two apart on purpose.
- **The persona's own language use.** Nothing in `instruction.md` or
  `input/context.md` tells the persona which language to write in. Instructing it
  would measure compliance with our instruction rather than natural behaviour, and
  would invalidate the result.
- **Reward.** `reward.txt` stays 1/0 on artifact presence and schema validity
  only. A bot that answers every turn in the wrong language still scores 1 — the
  question is what happened, not whether it was good.

### Limits of the language detection

Detection is deliberately deterministic and offline — language-exclusive
characters plus function-word lists, no `langdetect`-style library, because a
non-deterministic detector would flake in CI. That buys reproducibility at a cost:

- Short replies carry little signal and are the most likely to be misread.
- Proper nouns, invoice ids, code blocks, and numbers are language-neutral filler
  that dilutes the score.
- Closely related languages can be confused where their function words overlap.
- Only the four languages the SUT speaks are modelled; anything else is scored as
  undetermined rather than forced into the nearest match.

Replies below the confidence threshold are reported as `undetermined` rather than
being silently assigned. When the persona has no `primary_language` at all —
which is true of roughly half the checked-in dev sample, including the default
smoke persona `0042` — the verifier emits
`measurement_status: persona_language_unknown` and omits the match-rate facet
instead of contributing a misleading number to the batch average.

## Persona cohort

The checked-in `persona_strategy.json` is the **smoke** variant: stratified over
`primary_language` across English, Spanish, and German, **one** persona per cell,
three trials total. Those three values all exist in
`persona/schema/dimensions.json` **and** in the checked-in dev sample, so the
cohort resolves without the 1M pool.

Two constraints explain the numbers, and both are easy to break by accident:

- **`sampleSizePerValueGroup` is 1 because the German cell holds only 2 personas**
  in the whole dev sample. A smoke cohort exists to show the instrument runs, not
  to carry statistical weight, so one per cell buys headroom in every cell.
  Within-cell variance is the production variant's job. German stays in the
  cohort despite being the thinnest cell — it carries the strongest signal in the
  SUT's behaviour matrix (1 of 6 intents in-language), so dropping it would
  remove the most interesting column.
- **`sources` is deliberately empty.** The two German personas come from
  *different* sources (`wiki` and `real_human_survey`), so any source allow-list
  drops the German cell below capacity and the launch fails outright
  ([thin coverage raises an error](../../task-spec/docs/authoring-bundle.md#ensuring-pool-coverage)
  rather than silently under-sampling). `persona_strategy.json` is strict JSON and
  cannot carry a comment, which is why this warning lives here.

**Production variant** — wider cohort including Turkish, sampled from the 1M pool
([import instructions](../../../README.md#import-persona-1m-optional)):

```json
{
  "schemaVersion": "1.0",
  "sources": [],
  "defaultMode": "stratified",
  "pool": "persona/datasets/matraix-persona-1m",
  "dimensionFilters": {
    "primary_language": ["English", "Spanish", "German", "Turkish"]
  },
  "stratifyFields": ["primary_language"],
  "sampleSizePerValueGroup": 4
}
```

The four values are exactly the languages the verifier can detect
(`PERSONA_LANGUAGE_CODES` in `tests/test_state.py`) and the SUT can speak. Adding
a fifth to the filter without extending both would fill a whole stratum with
`persona_language_unsupported` rows — honest, but not a measurement. Widening the
cohort means widening the detector's word lists and the sidecar's phrasebook
first.

`"Turkish"` is worth a note: it appears in the dataset but **not** in the
`primary_language` value list in `persona/schema/dimensions.json`. Retrieval
compares filter values to persona records as plain strings
(`persona_1m_pool.py` `_matches_filters`), so it works — but the schema and the
data disagree, which is flagged as an open question in the PR.

To reproduce the batch report for review, run the production cohort above and
export the batch PDF from Playground **Runs → job → Download PDF**.

## Layout

```
application/tasks/chat_multilingual-telco-support/
├── task.toml
├── instruction.md              persona-facing goal, no language instruction
├── input/
│   ├── chatbot.yaml            transport + session fields (see note below)
│   ├── context.md              invoice / account background
│   ├── protocol.md             REST + session contract for the agent
│   └── self_report_schema.yaml persona debrief, incl. language experience
├── persona_strategy.json       smoke cohort (see above)
├── reporting.json              language facets distributed per segment
├── solution/solve.sh           oracle smoke
└── tests/
    ├── verifier_env.sh         copied from task-spec/shared, unmodified
    ├── test.sh                 runs the verifier, writes reward.txt
    └── test_state.py           verifier
```

`input/chatbot.yaml` **must** declare both session fields as `sessionId`. The
harness only threads a session when the task asks it to, and this SUT refuses a
session-less conversation read once a cohort has more than one conversation open.
The reasoning is inline in that file.

`tests/verifier_env.sh` is a byte-identical copy of
`application/task-spec/shared/verifier_env_with_tests_dir.sh` — the survey /
chatbot / web variant, which resolves `TESTS_DIR` as well as the verifier output
directory. The plain `verifier_env.sh` in the same folder omits `TESTS_DIR` and is
what the computer-use tasks use.

`tests/test.sh` follows the two real chat tasks (`chat_meal-planning-nutrition`,
`chat_openbb-corporate-action-honesty`) rather than
`example-chat-api_support_chatbot`. It runs `python3 test_state.py` directly,
because `structured_output.json` is written by the verifier's `main()` and a bare
`pytest` invocation never calls it — the reference task's uvx+pytest shape leaves
the reporting layer empty. Following the real tasks also drops an `apt-get` and a
uv download from the verifier phase, taking the oracle smoke from 3m16s to 31s.

`tests/test_state.py` keeps its `test_*` functions so the file can still be run
under pytest by hand, but the verifier path does not depend on them.

## Suggested setup (non-binding)

- Agent: `persona-user-sim` (host), which is what Mode **auto** picks for chat.
- Playground label: **Multilingual telco support**, task kind **Chat**.
- Model: any persona model with solid non-English generation; the measurement is
  about the SUT's language, but a persona that cannot write its own language
  produces a conversation the SUT was never given a chance to match.
