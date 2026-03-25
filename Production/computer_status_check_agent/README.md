# Computer Status Check Agent

LangChain ReAct agent that automates the **Computer Status Check** Linear workflow for ACME IT.

When a `*Computer Status Check*` issue is created in Linear, this agent:
1. Parses the structured issue description (inventory date, check-in date, uptime, Superman status, pending policies, etc.)
2. Classifies the failure mode — **INVENTORY**, **CHECKIN**, and/or **UPTIME**
3. Checks if the user is OOO via **Gmail vacation responder**, **Google Calendar OOO events** (both via GAM), and **Slack custom status**
4. Queries Jamf Pro for the current device state
5. Takes the prescribed first-response action (blank push, cancel failed commands, resolve pending policies)
6. Posts a structured Markdown comment back to Linear

---

## Requirements

| Tool | Version | Notes |
|------|---------|-------|
| Python | ≥ 3.13 | Managed by uv |
| [uv](https://docs.astral.sh/uv/) | ≥ 0.4 | Package + env manager |
| [GAM / GAMADV-XTD3](https://github.com/taers232c/GAMADV-XTD3) | Any | Must be configured with domain-wide delegation |
| Jamf Pro API credentials | — | OAuth2 client credentials (API Role) |
| Slack Bot Token | — | Scopes: `users:read`, `users:read.email`, `users.profile:read` |
| LLM API Key | — | See [LLM Providers](#llm-providers) below |

---

## Setup

```bash
# 1. Clone
git clone <repo> computer-status-agent
cd computer-status-agent

# 2. Create .env from template
cp .env.example .env
# Edit .env and fill in all values

# 3. Install dependencies with uv (creates .venv automatically)
uv sync

# 4. (Optional) Install additional LLM provider packages
uv pip install -e ".[openai]"          # OpenAI / llama.cpp support
uv pip install -e ".[ollama]"          # Ollama support
uv pip install -e ".[all-providers]"   # All providers

# 5. Verify GAM is working
gam version
gam user username@acme.com show vacation
```

---

## LLM Providers

The agent supports multiple LLM backends via LangChain. Set `LLM_PROVIDER` in `.env` to switch providers.

### Anthropic (default)

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514    # optional, this is the default
```

No extra install needed — `langchain-anthropic` is a core dependency.

### OpenAI

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o                        # optional, this is the default
```

```bash
uv pip install -e ".[openai]"
```

### Ollama (local)

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434      # optional, this is the default
OLLAMA_MODEL=llama3.3:70b                   # optional, this is the default
```

```bash
# Install the provider package
uv pip install -e ".[ollama]"

# Start Ollama and pull a model
ollama serve
ollama pull llama3.3:70b
```

No API key needed — runs entirely local.

### llama.cpp / llama-server (local)

```env
LLM_PROVIDER=llamacpp
LLAMACPP_BASE_URL=http://localhost:8080/v1  # optional, this is the default
LLAMACPP_MODEL=local-model                  # optional, this is the default
```

```bash
# Install the provider package (uses OpenAI-compatible endpoint)
uv pip install -e ".[openai]"

# Start the server — Docker:
docker run -p 8080:8080 -v /path/to/models:/models \
  ghcr.io/ggerganov/llama.cpp:server \
  -m /models/your-model.gguf

# Or natively:
llama-server -m model.gguf --port 8080
```

No API key needed — uses the OpenAI-compatible API that llama-server exposes.

> **Note:** Local models need strong tool-use / function-calling capabilities for the ReAct agent loop to work reliably. Models with < 30B parameters may struggle with the multi-step triage workflow.

---

## Running

```bash
# Triage a single issue (observe + comment, no Jamf mutations)
uv run python agent.py IT-5786 --dry-run

# Live run (will send blank push, run policies etc.)
uv run python agent.py IT-5786

# Or via the installed script entry point
uv run csa-run IT-5786 --dry-run
```

---

## Project Structure

```
computer-status-agent/
├── agent.py                    # LangChain ReAct agent entry point
├── tools/
│   ├── __init__.py             # Exports ALL_TOOLS
│   ├── parse_tool.py           # LangChain wrapper for the parser
│   ├── linear_tools.py         # get_linear_issue, post_linear_comment, update_linear_issue
│   ├── jamf_tools.py           # Jamf Pro API tools
│   └── user_tools.py           # OOO check: GAM (Gmail + Calendar) + Slack
├── parsers/
│   └── issue_parser.py         # parse_issue_description() — pure Python, no LangChain
├── prompts/
│   └── system_prompt.txt       # Full agent system prompt + comment template
├── .env.example
├── pyproject.toml              # uv-managed dependencies
└── README.md
```

---

## GAM Commands Used

| Purpose | Command |
|---------|---------|
| Check Gmail vacation responder | `gam user <email> show vacation format` |
| Check Google Calendar OOO events | `gam user <email> print events after today before +14d eventtype outofoffice fields summary,start,end,status formatjson` |

GAM requires GAMADV-XTD3 with domain-wide delegation enabled for the Gmail and Calendar APIs.
[GAMADV-XTD3 install guide](https://github.com/taers232c/GAMADV-XTD3/wiki/How-to-Install-Advanced-GAM)

---

## Slack API

The agent uses three Slack Web API methods:

| Method | Purpose |
|--------|---------|
| `users.lookupByEmail` | Resolve email → Slack user ID |
| `users.profile.get` | Read `status_text`, `status_emoji`, `status_expiration` |
| `users.getPresence` | Read `active` / `away` presence |

OOO is flagged if the status text contains keywords like `ooo`, `vacation`, `pto`, etc.,
or if the status emoji is a known OOO emoji (palm tree, airplane, etc.).

---

## Environment Variables

See `.env.example` for all variables. Key ones:

| Variable | Required | Description |
|----------|----------|-------------|
| `LLM_PROVIDER` | — | `anthropic` (default), `openai`, `ollama`, or `llamacpp` |
| `ANTHROPIC_API_KEY` | if anthropic | Claude API key |
| `OPENAI_API_KEY` | if openai | OpenAI API key |
| `LINEAR_API_KEY` | ✅ | Linear personal API key |
| `JAMF_URL` | ✅ | e.g. `https://acme.jamfcloud.com` |
| `JAMF_CLIENT_ID` / `JAMF_CLIENT_SECRET` | ✅ | Jamf OAuth2 API Role credentials |
| `GAM_PATH` | ✅ | Full path to `gam` binary |
| `GAMCFGDIR` | ✅ | Path to GAMADV-XTD3 config directory |
| `GOOGLE_DOMAIN` | ✅ | e.g. `acme.com` |
| `SLACK_BOT_TOKEN` | ✅ | `xoxb-...` |
| `DRY_RUN` | — | `true` to suppress all mutations (default: `false`) |

---

## Development

```bash
# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy .
```
