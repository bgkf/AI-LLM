# AI Agent & Automation Learning Guide
### A Prompt Reference for Skill-Building with Claude
---
## How to Use This Guide
Each section maps to a core skill area. Under each section you'll find:
- **What you're building toward** — the end goal
- **Starter prompts** — copy/paste these to kick off a session
- **Progression prompts** — use these as you level up
- **Portfolio prompt** — turn the work into a GitHub-ready project 
Work through sections in order, or jump to what's most relevant. Every prompt
is designed to produce working, runnable code and real explanations — not
just theory.
---
## Section 1: Python for Automation & APIs
**Goal:** Write Python that calls APIs, manipulates data, and automates
repetitive tasks.
### Starter Prompts
```
"Teach me how to call a REST API in Python using the requests library.
Show me a working example that fetches data, handles errors, and parses
the JSON response. Explain each line."
```
```
"Give me a Python script that reads a CSV file, filters rows based on a
condition, and writes the result to a new file. Walk me through the logic."
```
```
"Show me how to use environment variables in Python to store API keys
safely. Include a .env file setup with python-dotenv."
```
### Progression Prompts
```
"I can call APIs and read files. Now show me how to chain multiple API
calls together — where the output of one call is the input to the next.
Use a real-world example like fetching a user, then fetching their orders."
```
```
"Teach me async Python with asyncio and aiohttp. Show me how to make
multiple API calls in parallel and combine the results."
```
```
"Show me how to build a simple Python CLI tool using argparse that accepts
flags and runs different automation tasks based on input."
```

---
## Section 2: LLM-Powered Automations
**Goal:** Build small but real tools that use an LLM to read inputs and
produce actionable outputs.
### Starter Prompts
```
"Help me build a Python script that reads a text file of system alerts
and uses the OpenAI (or Anthropic) API to suggest a fix for each one.
Show the full working script with API call, prompt design, and output."
```
```
"I want to build an LLM-powered triage tool. It reads incoming support
tickets from a list, classifies each one as low/medium/high priority,
and writes a short suggested response. Build this step by step."
```
```
"Teach me prompt engineering for automation tasks. Show me how to write
system prompts and user prompts that produce structured, parseable outputs
like JSON from an LLM."
```
### Progression Prompts
```
"My LLM automation works but the outputs are inconsistent. Teach me how
to use output parsing, retry logic, and validation to make it reliable."
```
```
"Show me how to make my LLM tool stateful — so it remembers previous
alerts or tickets it has seen and avoids repeating suggestions."
```
```
"Add a simple logging system to my LLM automation so every input, prompt
sent, and response received is saved to a timestamped log file."
```

---
## Section 3: AI Agents with LangChain
**Goal:** Understand and build agents that use tools, memory, and reasoning
loops.
### Starter Prompts
```
"Explain what an AI agent is versus a simple LLM API call. Then show me
the simplest possible LangChain agent in Python — one that has one tool
and can decide when to use it."
```
```
"Build me a LangChain agent that has two tools: one that searches the web
and one that reads a local file. Show me how the agent decides which tool
to call based on the user's question."
```
```
"Teach me how LangChain's memory works. Show me how to give an agent
short-term memory so it can refer back to earlier parts of a conversation."
```
### Progression Prompts
```
"I have a working LangChain agent. Now show me how to add a custom tool —
one I write myself in Python — and register it so the agent can use it."
```
```
"Show me how to stream a LangChain agent's output to the terminal in
real time, so I can see its reasoning steps as it works."
```
```
"What are the most common failure modes for LangChain agents in
production? Show me how to handle tool errors, infinite loops, and
unexpected LLM outputs gracefully."
```

---
## Section 4: Multi-Agent Systems with LangGraph or CrewAI
**Goal:** Build systems where multiple agents collaborate, divide tasks, and
supervise each other.
### Starter Prompts
```
"Explain the difference between LangGraph and CrewAI. For someone building
operational AI agents, when would I choose one over the other? Give me
a concrete example use case for each."
```
```
"Build me a simple two-agent CrewAI system: one agent that researches a
topic and one that writes a summary based on the research. Show the full
working code."
```
```
"Show me how LangGraph models an agent workflow as a graph. Build a simple
example where different nodes handle different steps of a task, with
conditional routing between them."
```
### Progression Prompts
```
"I want to build a multi-agent system that monitors a folder for new files,
routes each file to the right specialist agent based on content type, and
writes a report. Design the architecture with me first, then build it."
```
```
"Show me how to add a supervisor agent to my CrewAI system — one that
reviews the other agents' outputs and sends work back for revision if
quality is too low."
```
```
"How do I test a multi-agent system? Show me how to write unit tests for
individual agents and integration tests for the full pipeline."
```

---
## Section 5: Deploying & Supervising Autonomous Agents
**Goal:** Move agents from scripts to running systems that operate reliably
without constant babysitting.
### Starter Prompts
```
"What does it mean to 'deploy' an AI agent? Walk me through the options:
running as a cron job, a FastAPI service, a cloud function, or a
containerized app. What are the tradeoffs?"
```
```
"Show me how to wrap my Python AI agent in a simple FastAPI app so it
can be triggered by an HTTP request and returns results as JSON."
```
```
"Teach me how to containerize my AI agent with Docker. Show me a minimal
Dockerfile and how to run it locally, then how to push it to Docker Hub."
```
### Progression Prompts
```
"Show me how to add observability to my deployed agent: structured logging,
error alerting, and a simple dashboard to see how many tasks it ran and
how many failed."
```
```
"My agent runs autonomously but sometimes goes off the rails. Teach me
patterns for human-in-the-loop oversight — ways to pause the agent and
require approval before it takes certain actions."
```
```
"Show me how to schedule my agent to run on a recurring basis using a
cloud scheduler (like GitHub Actions, AWS EventBridge, or a simple cron).
Include how to handle failures and retries."
```

---
## Quick-Reference: Prompt Patterns That Work Well
| Situation | Prompt Pattern |
|---|---|
| Learning something new | `"Teach me X. Show a working example, then explain
each part."` |
| Debugging | `"Here's my code and the error I'm getting. Diagnose what's
wrong and fix it."` |
| Going deeper | `"I understand the basics of X. What do I need to know next,
and why does it matter?"` |
| Production-proofing | `"My script works locally. What would break in
production? Make it production-ready."` |
| Portfolio polish | `"Make this project look like it was built by a
professional. What's missing?"` |
---
## Suggested Learning Order
1. **Python automation & APIs** — foundation for everything else
2. **LLM API calls + prompt design** — learn to talk to models reliably
3. **LangChain single agents** — add tools and reasoning loops
4. **Multi-agent systems** — LangGraph or CrewAI
5. **Deployment & supervision** — make it real and durable

---
*Use this file as a living reference. Add your own prompts as you discover
what works.*
