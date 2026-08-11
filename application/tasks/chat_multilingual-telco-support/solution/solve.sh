#!/bin/bash
set -euo pipefail

# Oracle smoke run: two turns in Turkish, then read the conversation back.
#
# The first turn opens the dispute and is answered in Turkish; the second asks for
# the line-item breakdown, which the sidecar only has in English. So a single
# oracle run exercises both an in-language reply and a fallback, which is what the
# verifier needs to produce a non-trivial language_match_rate.

API_BASE="http://telco-support-api:8000"

post() {
  curl -sS -X POST "${API_BASE}/v1/messages" \
    -H "Content-Type: application/json" \
    -d "$1"
}

# Turn 1 omits sessionId; the service mints one and returns it.
FIRST=$(post '{"message": "Merhaba, faturam beklediğimden yüksek geldi. Tanımadığım bir yurt dışı veri ücreti var, itiraz etmek istiyorum."}')
echo "${FIRST}"

SESSION_ID=$(printf '%s' "${FIRST}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["sessionId"])')
test -n "${SESSION_ID}"

# Turn 2 echoes the session id back so both turns land in one conversation.
post "$(python3 -c '
import json, sys
print(json.dumps({
    "message": "Fatura kalem dökümünü görebilir miyim?",
    "sessionId": sys.argv[1],
}, ensure_ascii=False))
' "${SESSION_ID}")"
echo

mkdir -p /app/output
curl -sS --get "${API_BASE}/v1/conversation" \
  --data-urlencode "sessionId=${SESSION_ID}" \
  -o /app/output/transcript.json
python3 -m json.tool /app/output/transcript.json > /dev/null
