"""Agentic Tools — LLM Agent (synchronous, tool-calling).

Uses an OpenAI-compatible endpoint served by Docker llama.cpp
(model: qwen2.5:7B-Q4_K_M) to answer natural-language questions
about the Agentic Tools dataset.

Usage:
  uv run python -m agent.agent
  uv run python -m agent.agent --query "Which computers have Cursor installed?"
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Allow project-root imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse

import openai

from shared.config import CONFIG
from shared.data import (
    get_all_connections,
    get_all_devices,
    get_tool_detail,
    get_tool_overview,
    load_raw_data,
)

# ── LLM Client ──────────────────────────────────────────────────────────────

client = openai.OpenAI(
    base_url=CONFIG["llm"]["base_url"],
    api_key="not-required",  # llama.cpp doesn't need an API key
)

MODEL  = CONFIG["llm"]["model"]
MAX_TOKENS = CONFIG["llm"]["max_tokens"]
TEMPERATURE = CONFIG["llm"]["temperature"]

# ── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "list_tools_overview",
            "description": (
                "Get an overview of all tracked agentic tools. Returns each tool's name, "
                "how many computers it is installed on, and the list of unique connections "
                "or extensions used with it across all devices."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tool_detail",
            "description": (
                "Get detailed information for a single tool, including a per-device breakdown "
                "and a ranked list of connections with how many computers each is on."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": (
                            "The tool identifier. One of: claude, chatgpt, cursor, gemini, "
                            "raycast, warp, visual_studio_code, comet, superhuman, bear, "
                            "ticktick, perplexity."
                        ),
                    }
                },
                "required": ["tool_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_devices",
            "description": (
                "List all devices in the dataset. Optionally filter by serial number, "
                "hostname/computer name, or whether a specific tool is installed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "serial_number": {
                        "type": "string",
                        "description": "Partial match on device serial number.",
                    },
                    "hostname": {
                        "type": "string",
                        "description": "Partial match on computer hostname.",
                    },
                    "tool": {
                        "type": "string",
                        "description": "Only return devices that have this tool installed.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_connections",
            "description": (
                "List all unique connections and extensions across every tool. "
                "Optionally filter by connection name or tool name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Partial match on connection or extension name.",
                    },
                    "tool": {
                        "type": "string",
                        "description": "Only return connections for this tool.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read a file from the sandboxed Agentic Tools directory "
                f"({CONFIG['agent']['sandbox_dir']}). Access is read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": (
                            "Path relative to the sandbox root. "
                            "Example: 'Agentic Tools - 2026-04-01.json'"
                        ),
                    }
                },
                "required": ["relative_path"],
            },
        },
    },
]

# ── Tool Dispatch ────────────────────────────────────────────────────────────

def _dispatch(name: str, args: dict) -> Any:
    """Execute the named tool with the given arguments and return a JSON-serialisable result."""

    if name == "list_tools_overview":
        return get_tool_overview()

    elif name == "get_tool_detail":
        tool_name = args.get("tool_name", "").strip().lower()
        known = CONFIG["tools"]
        if tool_name not in known:
            return {"error": f"Unknown tool '{tool_name}'. Known: {known}"}
        return get_tool_detail(tool_name)

    elif name == "list_devices":
        return get_all_devices(
            serial_number=args.get("serial_number"),
            hostname=args.get("hostname"),
            tool=args.get("tool"),
        )

    elif name == "list_connections":
        return get_all_connections(
            name=args.get("name"),
            tool=args.get("tool"),
        )

    elif name == "read_file":
        sandbox = Path(CONFIG["agent"]["sandbox_dir"])
        rel = args.get("relative_path", "")
        target = (sandbox / rel).resolve()

        # Safety: must stay within sandbox
        if not str(target).startswith(str(sandbox.resolve())):
            return {"error": "Access denied: path is outside the sandbox directory."}
        if not target.exists():
            return {"error": f"File not found: {rel}"}
        if target.is_dir():
            return {"error": "Path is a directory, not a file."}

        try:
            with open(target, "r") as f:
                content = f.read(32_000)  # cap at 32KB to avoid flooding context
            return {"content": content}
        except Exception as e:
            return {"error": str(e)}

    else:
        return {"error": f"Unknown tool: {name}"}


# ── Agent Loop ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an AI assistant with read-only access to Wellthy's Agentic Tools dataset.
This dataset contains information about which AI/productivity tools (Claude, Cursor, ChatGPT, etc.)
are installed on company computers, and what connections or extensions are configured with each tool.

You can answer questions about:
- Which tools are most popular across the fleet
- Which computers have a specific tool installed
- What connections/MCP integrations are used with each tool
- Details about individual devices by serial number or hostname

Always be concise and accurate. When referencing numbers, be precise.
If a question is ambiguous, ask for clarification before calling tools."""


def run_agent(user_query: str, verbose: bool = False) -> str:
    """
    Run one turn of the agent loop for the given user query.
    Returns the final assistant response as a string.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_query},
    ]

    max_iterations = 6

    for iteration in range(max_iterations):
        if verbose:
            print(f"\n[Agent] Iteration {iteration + 1} — calling LLM…")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

        msg = response.choices[0].message

        # No tool calls → final answer
        if not msg.tool_calls:
            return msg.content or ""

        # Append assistant message with tool calls
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call and append results
        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            if verbose:
                print(f"  → Tool call: {fn_name}({fn_args})")

            result = _dispatch(fn_name, fn_args)
            result_str = json.dumps(result, indent=2)

            if verbose:
                preview = result_str[:300] + ("…" if len(result_str) > 300 else "")
                print(f"  ← Result: {preview}")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })

    return "Agent reached maximum iterations without a final answer."


# ── Interactive REPL ─────────────────────────────────────────────────────────

def repl():
    """Simple interactive REPL for querying the agent."""
    print("\n⚡ Agentic Tools Agent")
    print(f"   Model  : {MODEL}")
    print(f"   Server : {CONFIG['llm']['base_url']}")
    print(f"   Data   : {CONFIG['data_dir']}")
    print("   Type 'exit' or Ctrl+C to quit.\n")

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if query.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        if not query:
            continue

        print("\nAgent: ", end="", flush=True)
        try:
            answer = run_agent(query, verbose=False)
            print(answer)
        except openai.APIConnectionError:
            print(
                "[Error] Could not connect to the LLM server. "
                f"Is Docker running and the server up at {CONFIG['llm']['base_url']}?"
            )
        except Exception as e:
            print(f"[Error] {e}")

        print()


# ── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agentic Tools LLM Agent")
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Run a single query and exit (non-interactive mode).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show tool calls and results.",
    )
    args = parser.parse_args()

    if args.query:
        try:
            result = run_agent(args.query, verbose=args.verbose)
            print(result)
        except openai.APIConnectionError:
            print(
                f"[Error] Cannot connect to LLM at {CONFIG['llm']['base_url']}. "
                "Ensure Docker and llama.cpp are running."
            )
            sys.exit(1)
    else:
        repl()
