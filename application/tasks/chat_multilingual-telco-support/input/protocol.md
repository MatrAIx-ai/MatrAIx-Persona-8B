# Meridian Mobile support chat API protocol

Meridian Mobile support is available through a **REST API** on the compose sidecar
`telco-support-api` (reachable from this container as
`http://telco-support-api:8000`). Use `curl` or a short script to hold a real
multi-turn conversation about invoice **INV-70431**.

## Endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/v1/messages` | `{"message": "<your text>", "sessionId": "<id or omitted>"}` | `{"reply": "<support reply>", "sessionId": "<id>"}` |
| `GET` | `/v1/conversation?sessionId=<id>` | — | `{"sessionId": "...", "messages": [{"role": "customer"\|"support", "content": "..."}, ...]}` |

## Sessions

The service keeps one conversation per session id.

1. Omit `sessionId` on your first `POST`. The response returns a freshly minted
   id.
2. Send that id back on every later `POST` so your turns land in the same
   conversation.
3. Pass it as the `sessionId` query parameter when reading the conversation back.

Reading without a session id only works when the service is holding exactly one
conversation; otherwise it answers `400`, because merging separate customers'
conversations would be worse than refusing.

## What to do

1. `POST` to `/v1/messages` at least twice as yourself (the customer).
2. Work toward understanding the disputed roaming charge on **INV-70431**.
3. Continue until you can judge whether support gave you a usable resolution path.
