# Agentic Tools Dashboard

An interactive browser dashboard + LLM agent for exploring which AI and productivity tools are installed across Acme's device fleet, including their MCP connections and extensions.

---

## Project Structure

```
Agentic_Tools_Dashboard/
├── config.json          ← Centralised paths and settings
├── requirements.txt
├── pyproject.toml
├── api/
│   └── main.py          ← FastAPI backend (serves dashboard + API)
├── dashboard/
│   └── index.html       ← Single-page interactive dashboard
├── agent/
│   └── agent.py         ← LLM agent (synchronous, tool-calling)
└── shared/
    ├── config.py        ← Config loader
    └── data.py          ← Data loading and query utilities
```

---

## Prerequisites

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Docker running with `llama.cpp` serving `qwen2.5:7B-Q4_K_M` on port `12434` (for the agent only)
- The latest Agentic Tools JSON file synced to `~/GitHub/Agentic_Tools/`

---

## Setup

```bash
# Clone / navigate to the project directory
cd Agentic_Tools_Dashboard

# Install dependencies with uv
uv sync

# Or with pip
pip install -r requirements.txt
```

---

## Running the Dashboard

```bash
# Start the FastAPI server (serves the dashboard at http://localhost:8000)
uv run uvicorn api.main:app --reload

# Then open your browser to:
open http://localhost:8000
```

The dashboard will automatically read the most recently modified `.json` file from the `data_dir` configured in `config.json`.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the dashboard HTML |
| `GET` | `/api/data` | Full raw device records |
| `GET` | `/api/tools` | Tool overview (install counts + connections) |
| `GET` | `/api/tools/{tool_name}` | Detail for a single tool |
| `GET` | `/api/devices` | Device list with optional filters |
| `GET` | `/api/connections` | All connections with optional filters |

### Query Parameters

**`/api/devices`**
- `serial_number` — partial match on serial number
- `hostname` — partial match on computer name
- `tool` — only devices with this tool installed

**`/api/connections`**
- `name` — partial match on connection/extension name
- `tool` — only connections for this tool

Interactive docs available at: `http://localhost:8000/docs`

---

## Running the LLM Agent

> Requires Docker + llama.cpp running at the URL in `config.json`.

```bash
# Interactive REPL
uv run python -m agent.agent

# Single query mode
uv run python -m agent.agent --query "Which computers have Cursor installed?"

# Verbose mode (shows tool calls)
uv run python -m agent.agent --query "What MCP connections does Cursor use?" --verbose
```

### Example Questions

- *"Which tool is installed on the most computers?"*
- *"Show me all devices with the Linear MCP connection in Cursor."*
- *"Which computers have both Claude and Cursor installed?"*
- *"How many unique connections does Cursor have?"*
- *"What's on the computer with serial number G7TQX0FHFJ?"*

---

## Configuration (`config.json`)

```json
{
  "data_dir": "/Path/To/GitHub/Agentic_Tools",
  "api": { "host": "0.0.0.0", "port": 8000 },
  "llm": {
    "base_url": "http://localhost:12434/engines/llama.cpp/v1",
    "model": "qwen2.5:7B-Q4_K_M"
  },
  "agent": {
    "sandbox_dir": "/Path/To/GitHub/Agentic_Tools",
    "filesystem_access": "read_only"
  }
}
```

Edit this file to point `data_dir` and `sandbox_dir` to your local Agentic Tools folder, or to adjust the LLM server URL and model.

---

## Data Format

The dashboard reads the **most recently modified `.json` file** in `data_dir`. Each file is a JSON array of device records:

```json
[
  {
    "collected_at": "2026-04-01T00:23:31Z",
    "device": {
      "hostname": "computerName",
      "serial_number": "abcde12345",
      "os_version": "26.4",
      "current_user": "userName"
    },
    "tools": {
      "cursor": {
        "installed": true,
        "version": "2.6.21",
        "connections": [
          { "name": "Linear", "type": "mcp", "command": "", "enabled": true }
        ]
      }
    }
  }
]
```
