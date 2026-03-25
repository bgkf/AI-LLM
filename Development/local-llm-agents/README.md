# local-llm-agents

A collection of tool-calling agents that run against a local [llama.cpp](https://github.com/ggerganov/llama.cpp) server. Each agent is an independent Python script that communicates with the server over HTTP using the OpenAI-compatible API. Includes a FastAPI backend and web dashboard for exploring the deep sea creature dataset.

## Prerequisites

- llama.cpp built and installed with `llama-server`
- A tool-calling capable model (e.g. Llama 3, Mistral, Qwen 2.5)
- Python 3.9+

## Setup

```bash
cd ~/AI-LLM/local-llm-agents
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .
```
## Configuration

All paths and server settings are managed in `config.json` at the project root:

```json
{
  "allowed_dir": "/path/to/your/directory",
  "data_dir": "/path/to/your/data_directory",
  "api_port": 8000,
  "llama_server_url": "http://localhost:8080"
}
```

- `allowed_dir` — the directory the filesystem agent can read and write. Do not include a trailing slash.
- `data_dir` — the directory containing `creatures.json`. Can be moved anywhere as long as this path is updated.
- `api_port` — the port the FastAPI server runs on.
- `llama_server_url` — the URL of the running llama-server instance.

Both `fs_agent.py` and `api/main.py` read from this file via `shared/config.py`.

## Using the filesystem agent in the terminal

**Step 1 — Update `config.json`** with your `allowed_dir` and `llama_server_url`.

**Step 2 — Start llama-server** (leave this running in its own terminal window)

```bash
llama-server --model your-model.gguf --port 8080
```

**Step 3 — Activate your venv** (in a second terminal window)

```bash
cd ~/AI-LLM/local-llm-agents
source .venv/bin/activate
```

**Step 4 — Run the agent**

```bash
python agents/fs_agent.py
```

You will see a `You:` prompt. Type your message and the agent will route it through the LLM, execute any tool calls, and print the response.

**To stop the agent and deactivate the venv:**

```bash
exit        # stop the agent
deactivate  # restore your shell's original Python environment
```

## Using the async agent

The async agent demonstrates two async patterns against the FastAPI server:

- **Pattern 1 — Concurrent startup fetch**: fetches all 5 data sources simultaneously with `asyncio.gather` on startup, then answers questions from the combined in-memory dataset.
- **Pattern 2 — Fan-out per creature**: type `profile <creature name>` to concurrently fetch the creature's full detail, food-web, zone, and specimens from 4 simultaneous API requests, then assemble a complete profile for the LLM to reason about.

```bash
# ensure the FastAPI server is running first (see below)
python agents/async_agent.py
```

**Example prompts for async agent:**
- `How many bioluminescent creatures are in each habitat zone?`
- `Which expedition discovered the most creatures and what region were they in?`
- `profile Goblin Shark` — triggers Pattern 2 fan-out
- `profile Anglerfish`

## Chat history

Chat history is stored in memory for the duration of the session only — the `messages` list in `fs_agent.py` accumulates the full conversation and is passed to the LLM on each turn. When you type `exit` or close the terminal, the history is lost. There is currently no persistence between sessions.

## Running the dashboards

**Step 1 — Update `config.json`** with your `data_dir` and `api_port`.

**Step 2 — Start the FastAPI server** (in its own terminal window, venv active)

```bash
uv run uvicorn api.main:app --reload --port 8000
```

**Step 3 — Open the dashboard**

Open the dashboard files directly in your browser. Navigate between them using the nav bar at the top of each page.

### Creature Database (`dashboard/index.html`)
- Filterable data table with bioluminescence and zone filters
- Depth range chart, bioluminescence donut, zone breakdown
- Creature detail card with joined expedition data

### Research Expeditions (`dashboard/expeditions.html`)
- Chronological expedition timeline from 1872–2009
- Expand any expedition to see discovered creatures
- Detail panel chains `/expeditions/{id}` → `/creatures/{id}` per creature

### Collections Map (`dashboard/collections.html`)
- World map with a marker per institution (coloured by specimen condition)
- Click a marker to highlight all holdings of that institution and open a side panel
- Side panel lists all specimens held, condition, display status, and acquisition year
- Filter by condition (live / preserved / skeleton) and on-display status

## API Chaining

The API demonstrates several chained request patterns:

| Endpoint | Chains |
|---|---|
| `GET /creatures/{id}` | expedition + zone + specimens joined in one response |
| `GET /creatures/{id}/food-web` | predators and prey resolved from relationships.json |
| `GET /expeditions/{id}` | all discovered creatures joined in |
| `GET /zones/{name}` | all resident creatures joined in |
| `GET /specimens/{id}` | creature detail joined in |

## Structure

```
local-llm-agents/
├── agents/
│   ├── __init__.py
│   ├── fs_agent.py             # Filesystem agent — interactive terminal chat
│   └── async_agent.py          # Async agent — concurrent API fetch patterns
├── cli/
│   ├── __init__.py
│   └── deepseacli.py           # CLI tool — creature, expedition, export, chain, info
├── api/
│   ├── __init__.py
│   └── main.py                 # FastAPI server — all routes with chaining
├── dashboard/
│   ├── index.html              # Creature database dashboard
│   ├── expeditions.html        # Research expeditions timeline
│   └── collections.html        # Museum/aquarium collections world map
├── data/
│   ├── creatures.json          # 12 deep sea species
│   ├── expeditions.json        # 6 research expeditions (1872–2009)
│   ├── zones.json              # 4 habitat zones with environmental data
│   ├── relationships.json      # Predator/prey relationship table
│   └── specimens.json          # ~31 museum/aquarium specimen records
├── shared/
│   ├── __init__.py
│   ├── config.py               # Loads config.json
│   ├── safety.py               # Safe path validation
│   └── tools.py                # Filesystem tool definitions and execute_tool
├── config.json                 # Project-wide configuration
├── pyproject.toml              # Makes project root importable
├── requirements.txt
└── README.md
```

## Agents

**`fs_agent.py`** — Gives the model sandboxed access to a local directory via tool calling. Set `ALLOWED_DIR` at the top of the file to control which directory the model can access.

**`async_agent.py`** - Uses `asyncio` and `aiohttp` to make asynchronous API calls - while waiting for one response, other tasks run.

## Shared

**`shared/config.py`** — Loads `config.json` from the project root and exposes it as a dict. Import `config` from here in any module that needs a path or setting.

**`shared/tools.py`** — Exports `filesystem_tools` (tool definitions for list, read, write) and `execute_tool` (the execution logic). Import these into any agent that needs filesystem access.

**`shared/safety.py`** — Exports `is_safe_path`, which uses `os.path.realpath` to resolve symlinks and prevent directory traversal attacks before any file operation.

## Adding a New Agent

1. Create a new file in `agents/`
2. Import tool definitions and `execute_tool` from `shared/tools.py`
3. Import `config` from `shared/config.py` for any paths or settings
4. Combine tool sets as needed (e.g. `tools = filesystem_tools + web_tools`)
5. Implement the agentic loop following the pattern in `fs_agent.py`

## CLI Tool

The CLI tool provides quick access to the database without running an agent. Requires the FastAPI server to be running.

```bash
python cli/deepseacli.py <command>
```

### Commands

**Creatures**
```bash
python cli/deepseacli.py creature list
python cli/deepseacli.py creature get "Goblin Shark"
python cli/deepseacli.py creature search --zone "Bathyal Zone"
python cli/deepseacli.py creature search --bioluminescent
python cli/deepseacli.py creature foodweb "Anglerfish"
```

**Expeditions**
```bash
python cli/deepseacli.py expedition list
python cli/deepseacli.py expedition get "HMS Challenger"
```

**Specimens**
```bash
python cli/deepseacli.py specimens "Vampire Squid"
```

**Export**
```bash
python cli/deepseacli.py export creatures --format csv
python cli/deepseacli.py export creatures --format json --out creatures_full.json
python cli/deepseacli.py export expeditions --format csv --out expeditions.csv
```

**Chain** — live API chain demo showing each request as it fires
```bash
python cli/deepseacli.py chain "Goblin Shark"
```

**Info** — API status and config
```bash
python cli/deepseacli.py info
```

### Output formats

All commands support `--output` / `-o`:
- `table` — formatted terminal output (default)
- `json` — raw JSON
- `csv` — comma-separated values

Export commands use `--format` instead, and support `--out <filename>` to write to a file.

## CLI Tool

`cli/deepseacli.py` is a terminal tool for querying the database without opening a browser. Requires the FastAPI server to be running.

```bash
# creature commands
python cli/deepseacli.py creature list
python cli/deepseacli.py creature get "Goblin Shark"
python cli/deepseacli.py creature get "Goblin Shark" --output json
python cli/deepseacli.py creature search --zone "Bathyal Zone"
python cli/deepseacli.py creature search --bioluminescent
python cli/deepseacli.py creature foodweb "Anglerfish"

# expedition commands
python cli/deepseacli.py expedition list
python cli/deepseacli.py expedition get "Valdivia"

# specimen holdings
python cli/deepseacli.py specimens "Firefly Squid"

# export — pipe to a file
python cli/deepseacli.py export creatures --format csv > creatures.csv
python cli/deepseacli.py export expeditions --format json > expeditions.json

# chain demo — shows each API request firing with timing
python cli/deepseacli.py chain "Goblin Shark"

# project info and API health check
python cli/deepseacli.py info
```

All table commands accept `--output json` to return raw JSON instead.
