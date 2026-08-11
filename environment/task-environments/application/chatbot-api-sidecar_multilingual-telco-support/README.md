# chatbot-api-sidecar_multilingual-telco-support

Local Meridian Mobile billing-dispute REST endpoint for chat tasks.
Persona agent runtime: `application/shared-chat-persona`.

Service name `telco-support-api` (port 8000, reachable in-compose as
`http://telco-support-api:8000`). Endpoints match the Acme reference sidecar:
`GET /health`, `GET /ready`, `POST /v1/messages`, `GET /v1/conversation`.

## Why the language behaviour is uneven

This mock is the measurement substrate for language-adherence tasks, so a
uniformly correct bot would be useless: every persona would score identically
and the batch report would show no distribution. The bot is therefore localized
*partially*, in a way that mirrors how real systems fail. Behaviour is a pure
function of the customer message — no randomness, no clock, no network — so the
same transcript reproduces byte-for-byte.

Partial support is expressed as **missing phrasebook entries** in
`_REPLIES[intent]`; the fallback rule is a single lookup. To change coverage,
add or remove a language entry rather than editing control flow.

## Behaviour matrix

Reply language per (intent, detected customer language):

| Intent | Turkish | English | Spanish | German | Other |
|---|---|---|---|---|---|
| `greeting` | Turkish | English | Spanish | German | English |
| `dispute_open` | Turkish | English | Spanish | **English** | English |
| `generic` | Turkish | English | **English** | **English** | English |
| `bill_breakdown` | **English** | English | **English** | **English** | English |
| `refund_policy` | **English** | English | **English** | **English** | English |
| `status_check` | **Spanish** | **Spanish** | **German** | **Spanish** | **Spanish** |

Bold = the bot does not answer in the customer's language.

**This gradient is a property of the fixture, not a finding.** English keeps 5 of
6 intents in-language, Turkish 3, Spanish 2, German 1 — those numbers were chosen
so every cohort produces a non-zero signal with a clear ordering, which is what
makes the measuring instrument testable. They say nothing about how real telco
support treats German speakers. Meridian Mobile is invented; do not quote this
table as a result. A mock's job is to exercise the verifier, not to produce
evidence.

Three distinct failure modes are seeded:

1. **Tiered localization** — the deeper the intent, the thinner the coverage.
   `bill_breakdown` and `refund_policy` are English-only for *every* customer,
   including full-support languages. A Turkish speaker gets Turkish greetings
   and a Turkish dispute confirmation, then English the moment they ask for
   line items.
2. **Partial locales** — Spanish stops after `dispute_open`, German after
   `greeting`. Both degrade silently to English rather than erroring.
3. **Locale-fallback bug** — `status_check` detects the customer's language and
   then answers in a *third* language (neither theirs nor English), simulating
   a misconfigured fallback chain that leaks a non-English default locale. This
   is deliberately distinguishable from the English fallback above, so a
   verifier can separate "degraded to English" from "answered in the wrong
   language entirely".

Intent keywords cover all four languages. That matters: if `bill_breakdown`
only matched English words, the deep-intent fallback would fire for English
speakers alone and the task would measure nothing.

## Session scoping (required, not optional)

Conversation state is keyed by session id, and `GET /v1/conversation` filters by
the `sessionId` query parameter.

This is a correctness requirement rather than a nicety. Playground reuses one
sidecar process for a whole cohort when a service is registered as a shared
sidecar (`chatbot_shared_sidecar.py`), and that path never resets state between
trials. The harness also builds `transcript.json` from `GET /v1/conversation`
rather than from the agent's own turn record (`chat_eval.py`
`_write_output_artifacts`). A single global message list would therefore hand
trial *N* the accumulated messages of trials *1..N* — and a language-adherence
measurement taken over a contaminated transcript is worse than no measurement,
because it fails silently.

Contract:

- `POST /v1/messages` accepts an optional `sessionId`, mints one when absent, and
  returns it so the harness can echo it on later turns.
- `GET /v1/conversation?sessionId=<id>` returns only that conversation. An
  unknown id returns an empty list rather than a merged or invented one, so the
  verifier fails artifact validation instead of scoring the wrong thing.
- A bare `GET /v1/conversation` is a convenience for manual `curl` against a
  single-session instance. With more than one session it returns HTTP 400 rather
  than merging, because merging is precisely the bug this scoping prevents.
- Session ids come from a counter, not a UUID or timestamp, keeping the service
  free of randomness and clock reads.

## What this sidecar does not expose

The bot's internal language detection is **not** returned by any endpoint. The
observable surface is reply text only, which is what a verifier should measure —
whether the bot "detected correctly" is an internal belief, not evidence. A
verifier that wants a language signal must detect it from the transcript
itself.

Detection inside `server.py` is intentionally naive (language-specific
characters plus a small stopword list) because this is the system under test,
not the measuring instrument.
