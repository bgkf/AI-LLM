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

## Chat history

Chat history is stored in memory for the duration of the session only — the `messages` list in `fs_agent.py` accumulates the full conversation and is passed to the LLM on each turn. When you type `exit` or close the terminal, the history is lost. There is currently no persistence between sessions.

## Running the dashboard

**Step 1 — Update `config.json`** with your `data_dir` and `api_port`.

**Step 2 — Start the FastAPI server** (in its own terminal window, venv active)

```bash
uv run uvicorn api.main:app --reload --port 8000
```

**Step 3 — Open the dashboard**

Open `dashboard/index.html` directly in your browser. The dashboard connects to the FastAPI server at `http://localhost:8000`.

The dashboard includes:
- Filterable data table (by name, bioluminescence, habitat zone)
- Depth range chart for all species
- Bioluminescence breakdown
- Creature detail card (click any row)


## Structure

```
local-llm-agents/
├── agents/
│   ├── __init__.py
│   └── fs_agent.py         # Filesystem agent — list, read, and write local files
├── api/
│   ├── __init__.py
│   └── main.py             # FastAPI server — serves creature data with filtering
├── dashboard/
│   └── index.html          # Web dashboard — charts, table, and detail card
├── data/
│   └── creatures.json      # Deep sea creature dataset (12 species)
├── shared/
│   ├── __init__.py
│   ├── config.py           # Loads config.json and exposes it to all modules
│   ├── safety.py           # Safe path validation (prevents directory traversal)
│   └── tools.py            # Filesystem tool definitions and execute_tool logic
├── config.json             # Project-wide configuration (paths, ports, URLs)
├── pyproject.toml          # Makes the project root importable as a package
├── requirements.txt
└── README.md
```

## Agents

**`fs_agent.py`** — Gives the model sandboxed access to a local directory via tool calling. Set `ALLOWED_DIR` at the top of the file to control which directory the model can access.

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
