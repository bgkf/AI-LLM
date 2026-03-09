# local-llm-agents

A collection of tool-calling agents that run against a local [llama.cpp](https://github.com/ggerganov/llama.cpp) server. Each agent is an independent Python script that communicates with the server over HTTP using the OpenAI-compatible API.

## Prerequisites

- llama.cpp built and installed with `llama-server`
- A tool-calling capable model (e.g. Llama 3, Mistral, Qwen 2.5)
- Python 3.9+

## Setup

```bash
cd ~/projects/local-llm-agents
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .
```

## Using the filesystem agent in the terminal

**Step 1 — Set your allowed directory**

Open `agents/fs_agent.py` and update `ALLOWED_DIR` to the directory you want the agent to have access to:

```python
ALLOWED_DIR = "/path/to/your/directory"
```

The agent can only read and write files within this directory. Access to anything outside it will be denied.

**Step 2 — Start llama-server** (leave this running in its own terminal window)

```bash
llama-server --model your-model.gguf --port 8080
```

**Step 3 — Activate your venv** (in a second terminal window)

```bash
cd ~/projects/local-llm-agents
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

## Structure

```
local-llm-agents/
├── agents/
│   ├── __init__.py       # an empty file
│   └── fs_agent.py       # Filesystem agent — list, read, and write local files
├── shared/
│   ├── __init__.py       # an empty file
│   ├── safety.py         # Safe path validation (prevents directory traversal)
│   └── tools.py          # Filesystem tool definitions and execute_tool logic
├── pyproject.toml        # Makes the project root importable as a package
├── requirements.txt
└── README.md
```

## Agents

**`fs_agent.py`** — Gives the model sandboxed access to a local directory via tool calling. Set `ALLOWED_DIR` at the top of the file to control which directory the model can access.

## Shared

**`shared/tools.py`** — Exports `filesystem_tools` (tool definitions for list, read, write) and `execute_tool` (the execution logic). Import these into any agent that needs filesystem access.

**`shared/safety.py`** — Exports `is_safe_path`, which uses `os.path.realpath` to resolve symlinks and prevent directory traversal attacks before any file operation.

## Adding a New Agent

1. Create a new file in `agents/`
2. Import tool definitions and `execute_tool` from `shared/tools.py`
3. Combine tool sets as needed (e.g. `tools = filesystem_tools + web_tools`)
4. Implement the agentic loop following the pattern in `fs_agent.py`
