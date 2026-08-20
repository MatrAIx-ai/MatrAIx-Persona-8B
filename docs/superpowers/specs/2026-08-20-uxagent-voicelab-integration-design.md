# UXAgent–VoiceLab Integration Design

## Problem

MatrAIx currently evaluates the ten `application/tasks/chat_vita-*` automotive scenarios through the `persona-user-sim` chat path and a generic sidecar contract at `/v1/messages`. The VoiceLab persona-provider contract requires a different lifecycle:

1. create or update a persona session;
2. call VoiceLab chat with that persona session;
3. preserve vehicle decisions, tool execution, state, and safety evidence for the existing verifier.

UXAgent provides the desired dual-system persona behavior, but its upstream runtime is tied to Playwright, DOM observations, and browser actions. Pointing upstream UXAgent directly at `/api/chat` or `/api/agent/chat` is therefore not viable.

## Decision

Add a Harbor persona agent named `persona-uxagent`. Implement a clean-room conversational policy inspired by UXAgent's published dual-system architecture, without copying upstream source code or prompts, and connect it to VoiceLab through a narrow API client.

The integration will:

- implement the published fast-loop concepts (`perceive → plan → act`) and slow-loop concepts (`reflect → wonder → memory update`) with original MatrAIx code and prompts;
- expose one executable policy action: `send_message`;
- create one VoiceLab persona session per Harbor trial;
- use `/api/agent/chat` for automotive turns because the current Vita verifiers require decision, tool, vehicle-state, and safety evidence;
- migrate all ten current `chat_vita-*` tasks to use this agent through the job/default-agent selection path;
- keep existing task oracle and verifier contracts unchanged;
- fail explicitly rather than silently falling back to `persona-user-sim`.

## Non-goals

- Driving VoiceLab through Chromium or testing its visual UI.
- Vendoring the full UXAgent repository.
- Adding a long-running UXAgent sidecar service.
- Changing VoiceLab safety policy or allowing persona context to override vehicle runtime gates.
- Adding cross-trial, cross-task, driver-level, or trip-level memory.
- Persisting VoiceLab persona sessions in MatrAIx.

## Architecture

### `PersonaUXAgent`

A Harbor `BaseAgent` implementation composed with the existing `PersonaMixin`.

Responsibilities:

- load the trial persona using the established persona path/template mechanism;
- prepare the persona trial through `_prepare_persona_trial`;
- obtain task configuration and trial identity;
- run `UXAgentTrialRunner`;
- emit Harbor trajectory data and trial events;
- expose the new `persona-uxagent` agent name through the existing registry/factory path.

It must not contain HTTP serialization or reasoning-loop internals.

### `VoiceLabPersonaClient`

A narrow asynchronous client for the provider contract.

Configuration:

- base URL from a dedicated environment variable, with the contract's local URL as the documented development value;
- optional `APP_PASSWORD` value sent only as `x-app-password`;
- bounded request timeout;
- no secret values in prompts, logs, trajectories, or output artifacts.

Operations:

- `create_session(payload)` → `POST /api/persona/session`;
- `agent_chat(payload)` → `POST /api/agent/chat`.

The client validates required response fields and raises typed errors for transport, HTTP, and schema failures. It does not implement a fallback transport.

### `ConversationalUXPolicy`

A clean-room implementation of the published UXAgent reasoning architecture for conversational tasks.

Retained concepts:

- persona-conditioned perception;
- short- and long-term memory pieces;
- plan generation;
- reflection, wondering, and memory consolidation;
- an asynchronous slow loop while the turn loop is active.

Replaced concepts:

- DOM/HTML observations become a structured conversation observation containing task intent, latest user utterance, assistant response, vehicle state, runtime context, tool result, and prior turn evidence;
- browser action prompts become a conversational action schema with one action: `send_message`;
- click/select/navigate targets and Playwright environment dependencies are removed.

The policy returns exactly one Vietnamese driver utterance per turn. It does not invoke VoiceLab itself.

### `UXAgentTrialRunner`

Owns the per-trial lifecycle:

1. derive a unique session ID from the Harbor trial identity;
2. map the MatrAIx persona and task context to the provider payload;
3. create the VoiceLab persona session;
4. initialize `ConversationalUXPolicy` with persona and task intent;
5. run at most the task's configured `maxTurns`;
6. send each generated utterance through `VoiceLabPersonaClient.agent_chat`;
7. feed the full VoiceLab response back into the next policy observation;
8. write transcript, application result, memory trace, and ATIF-compatible trajectory evidence;
9. cancel and await the slow-loop task during cleanup.

The runner does not delete the VoiceLab active persona at trial end. `DELETE /api/persona/active` is global and can race when trials run concurrently. Every chat request explicitly carries `personaSessionId`, which provides trial isolation.

## Data Contract

### Persona session mapping

The adapter maps existing MatrAIx persona data into:

```json
{
  "sessionId": "<harbor-trial-identity>",
  "source": "matraix-uxagent",
  "driver": {
    "name": "<persona name when available>",
    "persona": "<compact persona description>",
    "communicationStyle": "<derived communication style when available>",
    "traits": [],
    "preferences": {}
  },
  "context": {
    "mood": "<task/persona value when available>",
    "tripPurpose": "<task value when available>",
    "stressLevel": "<task/persona value when available>",
    "fatigueLevel": "<task/persona value when available>",
    "roadSituation": "<task value when available>"
  },
  "notes": []
}
```

Optional source values are omitted rather than fabricated. The adapter sends only fields available from the persona and task inputs.

### Chat request

Each turn sends:

```json
{
  "message": "<one persona-conditioned Vietnamese utterance>",
  "drivingContext": "<task vehicle-motion context>",
  "intent": "<task scenario intent>",
  "personaSessionId": "<harbor-trial-identity>"
}
```

### Chat response preservation

The integration preserves these VoiceLab fields without semantic rewriting:

- `reply`;
- `decision`;
- `vehicleState`;
- `action`;
- `toolResult`;
- `capabilityIds`;
- `runtimeContext`.

That shape maintains the evidence expected by the existing Vita task verifiers and reporting configuration.

## Task Migration

The migration covers the current automotive chat catalog:

- `chat_vita-climate-temperature`;
- `chat_vita-climate-clarification`;
- `chat_vita-passenger-window-50`;
- `chat_vita-trunk-driving-guardrail`;
- `chat_vita-trunk-confirmation`;
- `chat_vita-climate-tool-recovery`;
- `chat_vita-climate-conflict-repair`;
- `chat_vita-window-progressive-disclosure`;
- `chat_vita-trunk-cancellation`;
- `chat_vita-confirmation-context-switch`.

The task instructions, oracle payloads, verifier scripts, and reporting metrics remain authoritative. The generator and job/default-agent selection are updated once so generated and checked-in tasks do not diverge.

## Failure Semantics

- Persona-session transport, HTTP, or response-schema failure: record a structured failure event and fail the trial before chat begins.
- Chat transport, HTTP, or response-schema failure: record the completed turn evidence and structured failure, then fail the trial.
- Policy output outside the `send_message` schema: fail the trial; do not reinterpret arbitrary model output as a message.
- Turn limit reached: finish normally with the evidence collected so far and the task's existing verifier deciding success.
- Cleanup failure: preserve the primary failure, record cleanup failure separately, and ensure the slow-loop task is cancelled and awaited.

There is no silent fallback to `persona-user-sim`, `/api/chat`, or the old `/v1/messages` sidecar path.

## Clean-room Attribution

The UXAgent README advertises an MIT license, but upstream commit `4d3b1f1c1fef93c5e2ea7d104153ea164ba1acbd` contains no license file and GitHub reports no detected license. MatrAIx therefore must not copy or adapt UXAgent source code, prompt text, tests, or other expressive implementation material.

The repository will include a provenance notice recording:

- project name and URL `https://github.com/neuhai/UXAgent`;
- the upstream commit inspected;
- that UXAgent's published dual-system concepts informed the architecture;
- that all MatrAIx implementation code and prompts were written independently.

Playwright, Flask, Hydra, Selenium, and other browser/UI-only UXAgent dependencies are not added to MatrAIx.

## Verification

### Unit tests

- persona YAML and task context map to the provider-session payload without fabricated optional values;
- `APP_PASSWORD` maps to `x-app-password` and is absent from recorded artifacts;
- chat requests always include the per-trial `personaSessionId`;
- the policy accepts only `send_message` and produces one utterance per turn;
- slow-loop cleanup cancels and awaits background work;
- new agent name resolves through Harbor's factory and persona-agent context.

### Contract tests

With a deterministic mock HTTP server:

- assert the exact `POST /api/persona/session` request;
- assert ordered `POST /api/agent/chat` requests;
- return decision/tool/vehicle-state evidence and assert it reaches transcript, application result, trajectory, and verifier inputs unchanged;
- assert transport, HTTP, malformed JSON, and missing-field failures are explicit and contain no secret values.

### Behavioral smoke test

Run one representative Vita task end to end with `persona-uxagent` against a configured VoiceLab instance. The proof must show:

1. one persona session created for the trial;
2. at least one `/api/agent/chat` turn carrying that session ID;
3. VoiceLab decision/tool/vehicle-state evidence in task artifacts;
4. the existing verifier completing against those artifacts.

After that smoke passes, run the focused Vita and agent-registration test suites covering the migrated catalog.

## Acceptance Criteria

- `persona-uxagent` is selectable as a Harbor persona agent.
- Each Vita trial creates exactly one isolated VoiceLab persona session.
- Every turn calls `/api/agent/chat` with the trial's `personaSessionId`.
- Driver utterances are generated by the clean-room UXAgent-inspired dual-system policy, not the old user simulator.
- Existing Vita verifier-required response evidence is preserved.
- All ten current Vita tasks use the new integration through a single generator/default mapping.
- Secrets never appear in prompts or generated artifacts.
- API and schema failures fail visibly; no compatibility fallback remains.
- A representative end-to-end Vita task passes the existing verifier against VoiceLab.
