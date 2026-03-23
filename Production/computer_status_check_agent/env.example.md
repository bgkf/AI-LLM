# ──────────────────────────────────────────────────────────────────────────────
# Computer Status Check Agent — Environment Variables
# Copy this file to .env and fill in all required values.
# ──────────────────────────────────────────────────────────────────────────────

# ── LLM Provider ─────────────────────────────────────────────────────────────
# Choose ONE provider and set the corresponding variables.
# The agent uses LangChain, so any LangChain-compatible chat model works.
# Update _build_llm() in agent.py to match your chosen provider.

# Provider name: anthropic | openai | ollama | llamacpp
LLM_PROVIDER=anthropic

# -- Anthropic (default) --
ANTHROPIC_API_KEY=sk-ant-...
# ANTHROPIC_MODEL=claude-sonnet-4-20250514

# -- OpenAI --
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o

# -- Ollama (local) --
# Runs locally via ollama serve; no API key needed.
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3.3:70b

# -- llama.cpp / llama-server (local, Docker or native) --
# Start the server: docker run -p 8080:8080 ghcr.io/ggerganov/llama.cpp:server -m /models/model.gguf
# Or natively:      llama-server -m model.gguf --port 8080
# Uses the OpenAI-compatible endpoint exposed by llama-server.
# LLAMACPP_BASE_URL=http://localhost:8080/v1
# LLAMACPP_MODEL=local-model

# ── Linear (required) ─────────────────────────────────────────────────────────
LINEAR_API_KEY=lin_api_...

# ── Jamf Pro (required) ───────────────────────────────────────────────────────
JAMF_URL=https://acme.jamfcloud.com
JAMF_CLIENT_ID=your-jamf-oauth2-client-id
JAMF_CLIENT_SECRET=your-jamf-oauth2-client-secret

# ── Google / GAM (required for OOO check) ─────────────────────────────────────
# GAM binary — confirmed path: ~/bin/gam7/gam (also accessible as `gam` in PATH)
GAM_PATH=~/bin/gam7/gam
# GAMCFGDIR — path to the GAMADV-XTD3 config directory (contains gam.cfg,
# oauth2service.json, etc.). Required if your GAM config is not at ~/.gam/
GAMCFGDIR=~/GAMConfig
GOOGLE_DOMAIN=acme.com

# ── Slack (required for OOO check) ────────────────────────────────────────────
# Bot token scopes required: users:read, users:read.email, users.profile:read
SLACK_BOT_TOKEN=xoxb-...

# ── Okta (required for Okta activity check) ───────────────────────────────────
# Domain: e.g. acme.okta.com  (no https://)
OKTA_DOMAIN=acme.okta.com
# API token with okta.logs.read scope (SSWS token)
OKTA_API_TOKEN=00...

# ── Okta Workflows (optional — for Jamf framework redeploy) ───────────────────
OKTA_REDEPLOY_WORKFLOW_URL=https://...

# ── Agent behaviour ───────────────────────────────────────────────────────────
# DRY_RUN=true  → observe and report only, no Jamf mutations, no Linear writes
# DRY_RUN=false → live mode (default); approval prompts shown before each action
DRY_RUN=false

# Log level: DEBUG | INFO | WARNING | ERROR
LOG_LEVEL=INFO
