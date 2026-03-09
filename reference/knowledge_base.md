# AI Agents Course — Local Knowledge Base

## Course Info
This is Lesson 2 of the AI Agents with LangChain course.
The course is taught using Qwen3 Coder running locally via llama.cpp.
The student completed Lesson 1 successfully on the first attempt.

## My LLM Setup
- Model: Qwen3 Coder (GGUF format)
- Runtime: llama.cpp (llama-server)
- Context window: 32768 tokens
- Host: 127.0.0.1, Port: 8080
- API key: not required (local)

## Frameworks I Have Looked At
- LangChain: main framework for this course (MIT license)
- LangGraph: advanced stateful agents, made by LangChain team
- CrewAI: multi-agent collaboration
- Pydantic AI: type-safe, minimal abstractions
- Smolagents: code-first agents from HuggingFace

## Package Manager
Using pip3 with a virtual environment (or uv as an alternative).
Virtual environment name: agents-course

## Lessons Completed
- Lesson 1: Simple agent with one tool (calculator). DONE.
- Lesson 2: Agent with two tools (web search + file reader). DONE.
- Lesson 3: Memory — short-term and persistent. DONE.
- Lesson 4: Custom tools — all three patterns. DONE.
- Lesson 5: Streaming — real time terminal output. DONE.
- Lesson 6: Failure modes — errors, loops, bad output. IN PROGRESS.

---

## Python Project Configuration

Files that define and manage what a Python project is and what it requires.

### pyproject.toml
The modern Python project configuration file. Declares the project name,
Python version requirement, and the packages required to run it.
When you run `uv add langchain`, uv writes the entry here automatically.
The source of truth for what the project needs. You can edit it directly
or let uv manage it via `uv add` and `uv remove`.

### uv.lock
The lockfile. Where pyproject.toml says "I need langchain >= 0.3.0",
the lockfile records the exact version actually installed — every package
and every transitive package, pinned precisely. Guarantees that anyone
running `uv sync` gets an identical environment. Managed entirely by uv,
never edited by hand. Should be committed to version control.

### requirements.txt
The older, simpler alternative to pyproject.toml. A plain list of
package names and optional version constraints. Used with pip:
  pip install -r requirements.txt
Not uv-native but universally understood. If you are using uv,
pyproject.toml is preferred and requirements.txt can be dropped.

### main.py
A placeholder entry point created automatically by `uv init`.
Contains a stub `print("Hello...")` and can be deleted or repurposed.
In the agent package, run.py serves this role instead.

### The relationship between these files (uv workflow)
```
pyproject.toml   ← declares what the project needs (you or uv edits this)
uv.lock          ← pins exact versions of everything (uv manages this)
.venv/           ← the actual installed packages (uv builds from lockfile)
```

---

## Terminology

### LLM API Call vs AI Agent
A plain LLM API call is one-shot: prompt in, response out, no loop.
An AI agent wraps the LLM in a Reason → Act → Observe loop, giving it
tools it can invoke and the ability to take multiple steps before
producing a final answer. The LLM becomes a controller/planner rather
than just a text predictor.

### Tokens
The unit of text an LLM works with — not characters, not words, but
chunks in between. Roughly 1 token ≈ 0.75 words ≈ 4 characters in English.
Common short words are usually 1 token. Rare or long words get split into
multiple tokens. Numbers and punctuation are unpredictable.

Why tokens matter for agents:
- Context window: the maximum tokens the model can hold at once (system
  prompt + conversation history + tool definitions + tool results +
  response all count toward this limit).
- Speed: local models process tokens sequentially — more tokens = slower.
- The model has no memory between separate runs. What looks like memory
  in a chatbot is the full conversation history being re-sent every time.

My context window: 32768 tokens (set via --ctx-size in llama-server).
At this size, context limits are not a practical concern for early lessons.

### Docstring
The triple-quoted string immediately after a Python function definition.
In regular Python it is documentation for humans. In a LangChain agent,
LangChain extracts the docstring and sends it to the LLM as part of the
prompt — it becomes the instructions the model reads to decide whether
and how to use that tool.

A good tool docstring has three parts:
1. What the tool does (action + what it returns)
2. When to use it — "Use this when..." — this drives routing decisions
3. An example input — helps the model format arguments correctly

Docstring quality directly equals tool routing quality. A vague docstring
leads to wrong tool selection or malformed arguments.

### Tool Routing
The process by which the agent decides which tool to call for a given
question. There are no if/else rules in the code — the LLM reads the
docstrings of all available tools and the user's question, then decides
which tool (if any) to invoke. This decision is made via natural language
reasoning, not programmatic logic.

### Context Window
The maximum number of tokens an LLM can process at once — its working
memory. Everything in a single request counts toward this limit: system
prompt, conversation history, tool definitions, tool results, and the
model's own response. When the limit is hit, earlier content becomes
invisible to the model.

### Temperature
Controls randomness in the model's outputs. At temperature=0 the model
always picks the highest-probability next token (deterministic). Higher
values introduce randomness. For agents, temperature=0 is preferred
because it reduces reasoning failures like looping.

### Looping (Agent Loop / Runaway Loop)
The normal agent loop is Reason → Act → Observe → Repeat until done.
A runaway loop is when the model fails to recognize the stopping
condition and keeps calling tools indefinitely. More likely at higher
temperatures or with weaker models. Prevented with max_iterations in
AgentExecutor.

### Virtual Environment
An isolated Python installation scoped to a single project. Prevents
dependency conflicts between projects (e.g. two projects needing
different versions of the same library). Created with either:
  python3 -m venv agents-course   (pip3 approach, must activate manually)
  uv init agents-course           (uv approach, activates automatically)

### uv
A modern Python package and environment manager written in Rust.
Faster than pip, handles virtual environments automatically, and removes
the need to manually run 'source activate' each session. Increasingly
the community standard. Key commands:
  uv init        create a new project
  uv add         install a package
  uv run         run a script inside the environment

### ReAct
Stands for Reason + Act. The pattern underlying most LLM agents:
the model reasons about what to do, acts by calling a tool, observes
the result, then reasons again. Repeats until it has enough information
to produce a final answer.

### Short-Term Memory (in-session)
Conversation history stored in a Python object (ChatMessageHistory)
during a single script run. The full history is injected into the
{history} placeholder in the prompt before every invoke(). Lost when
the script ends. Implemented with RunnableWithMessageHistory in LangChain.

### Persistent Memory (cross-session)
Conversation history saved to disk (e.g. a JSON file) so it survives
between script runs. On startup the history is loaded from the file;
after each turn it is saved back. The agent can remember conversations
from previous sessions.

### RunnableWithMessageHistory
The LangChain wrapper that adds memory to any agent or chain. It
intercepts every invoke(), loads the history into {history} before
the call, and appends the new turn to history after the call.

### session_id
A string key used to separate conversation histories. Each unique
session_id gets its own independent history. Useful for multi-user
apps where each user needs their own memory context.

### History = Memory
There is no special memory module storing facts. The entire conversation
history is re-sent to the model as tokens on every invoke(). Memory is
just the growing list of past messages. This means long conversations
consume more tokens on every subsequent call — an important constraint
for production agents.

### Tool Patterns (three ways to define a tool)

Pattern 1 — @tool decorator (simplest):
  Single string input. Good for quick, single-argument tools.
  The function docstring IS the tool description.

Pattern 2 — @tool with args_schema (Pydantic):
  Use when the tool needs multiple inputs or typed validation.
  Define a Pydantic BaseModel as the schema. Field(description="...")
  on each argument teaches the LLM what each argument means.
  Field descriptions act like docstrings for individual parameters.

Pattern 3 — StructuredTool.from_function (most explicit):
  Wraps an existing function without modifying it.
  Name and description are set separately from the function.
  Best for wrapping library functions or team codebases.

### The Tool Contract
Every tool must follow three rules:
  1. Accept only JSON-serialisable inputs (str, int, float, bool)
  2. Return a string — the agent reads tool output as text
  3. NEVER raise an unhandled exception — always catch errors and
     return an error message string. An uncaught exception crashes
     the agent loop entirely.

### Pydantic / BaseModel
A Python library for data validation using type annotations.
Used in LangChain tool Pattern 2 to define typed, validated
inputs for tools with multiple arguments. Field(description="...")
provides per-argument documentation that the LLM reads.

### Streaming
Instead of waiting for the full response before printing,
streaming sends tokens as they are generated. Requires
streaming=True on ChatOpenAI and using async methods.

Three levels:
  astream()        — yields final answer chunks only
  astream_events() — yields every event (tool calls, tokens, etc.)
  Custom handler   — filters astream_events() into formatted output

Key event types in astream_events():
  on_tool_start       — tool is about to be called
  on_tool_end         — tool has returned its result
  on_chat_model_stream — one token from the LLM
  on_chain_end        — AgentExecutor finished

### async / await / asyncio
Python's concurrency system. All LangChain streaming methods
are async (prefixed with 'a': astream, astream_events).
asyncio.run(main()) is the entry point that starts the async
event loop. flush=True in print() forces tokens to appear
immediately rather than buffering.

### SSE (Server-Sent Events)
The protocol llama.cpp uses to stream tokens over HTTP.
LangChain connects to this when streaming=True is set.
Tokens arrive one at a time over a persistent HTTP connection
rather than in a single response at the end.

### Completions
The original term for what an LLM does — it completes text.

### Agent Failure Modes (the six most common)
1. Unhandled tool exception — crashes the agent loop entirely.
   Fix: try/except inside every tool, return errors as strings.
2. Unusable tool output — tool returns dict/None instead of string.
   Fix: always return a formatted string from tools.
3. Runaway loop — agent keeps calling tools without finishing.
   Fix: max_iterations + definitive (non-ambiguous) tool output.
4. LLM ignores tool — answers from training data instead of tool.
   Fix: stronger docstring + explicit system prompt directive.
5. Malformed tool call — LLM emits bad JSON the executor can't parse.
   Fix: handle_parsing_errors=True on AgentExecutor.
6. Tool timeout — network call or heavy compute hangs indefinitely.
   Fix: wrap tool body with a timeout (signal.SIGALRM on macOS/Linux).

Two distinct layers of defence:

| Layer        | What breaks                                   | How you fix it                                          |
|--------------|-----------------------------------------------|---------------------------------------------------------|
| Python layer | Exceptions, wrong types, timeouts             | try/except, type checks, signals                        |
| LLM layer    | Bad reasoning, ignored tools, malformed output| Prompt engineering, executor settings, behavioural governors |

### handle_parsing_errors
AgentExecutor parameter. When True, if the LLM emits a malformed
tool call that can't be parsed, the error is sent back to the LLM
as a message rather than crashing. The model gets a chance to
self-correct on the next iteration. Always set in production.

### Tool Contract (full)
Every tool must:
  1. Return a string — never dict, list, int, or None
  2. Catch all exceptions — return error string, never raise
  3. Have a timeout — wrap any I/O, network, or slow operations
  4. Return definitive output — ambiguous results cause retry loops

### with_timeout decorator
A Python pattern using signal.SIGALRM (macOS/Linux only) to raise
a TimeoutError if a function takes longer than N seconds.
Use asyncio.wait_for() instead for Windows or async code.
Given the beginning of something, the model predicts what comes next.
The output is called the "completion."

Two endpoints:
  /v1/completions      — raw text in, raw text out (legacy)
  /v1/chat/completions — conversation messages in, assistant reply out
                         (what LangChain uses)

llama.cpp implements the same endpoint names as OpenAI intentionally,
making any OpenAI-compatible client (like LangChain's ChatOpenAI) work
against a local model by simply changing base_url.
