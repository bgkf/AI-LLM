#! /bin/zsh

date=$(date +"%Y-%m-%d")
fileName="Agentic Tools - ${date}.json"

OKTA_WEBHOOK_URL="https://webhook_invoke.url"

curl -s \
  -X GET "$OKTA_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  --max-time 10 \
  --retry 2 | jq -r '.output' > ~/Github/Agentic_Tools/$fileName