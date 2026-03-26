# Agent Build Template
============================================================
HOW TO USE THIS TEMPLATE
============================================================
1. Fill in every section marked with [ ]
2. Delete any section that doesn't apply to your agent
3. Paste the completed template into your LLM chat
4. The LLM will ask clarifying questions before building
5. Save completed templates alongside the agent they produced
============================================================


## PART 1 — AGENT OVERVIEW
> What does this agent do in plain language?

**Agent name:**
[ A short name for the agent, e.g. "Research Assistant" ]

**One-line description:**
[ What does this agent do? e.g. "Searches the web and summarises
  findings into a structured report saved to a local file." ]

**Primary goal:**
[ What is the agent trying to accomplish overall? Be specific.
  Bad:  "Help me with research"
  Good: "Given a topic, search the web for recent information,
        extract key facts, and write a structured markdown summary
        to a file named after the topic." ]


## PART 2 — INPUTS AND OUTPUTS
> What goes in and what comes out?

**Input — how will the agent be invoked?**
[ ] Interactive terminal (user types questions in a loop)
[ ] Single question passed as a command-line argument
[ ] Reads from a file or folder
[ ] Called from another Python script
[ ] Other: _______________

**Input description:**
[ What will the user actually provide? e.g. "A topic name as a
  string", "A folder path containing .txt files", "A URL" ]

**Output — what should the agent produce?**
[ ] Text answer printed to terminal
[ ] Structured data (JSON, CSV)
[ ] A file written to disk (specify format below)
[ ] A summary or report
[ ] An action taken (API call, email sent, etc.)
[ ] Other: _______________

**Output description:**
[ Describe the output in detail. e.g. "A markdown file named
  {topic}.md containing: a summary paragraph, a bullet list of
  key facts, and a list of source URLs." ]


## PART 3 — TOOLS
> What can the agent do? List each capability you need.
> If you are unsure, describe the capability and let the LLM
> suggest the right tool implementation.

**Tool 1:**
Name: [ e.g. "web_search" ]
What it does: [ e.g. "Searches DuckDuckGo for a query" ]
Input: [ e.g. "A search query string" ]
Output: [ e.g. "Top 3 results with title, URL, and summary" ]
External dependency?: [ e.g. "ddgs package, no API key needed" ]

**Tool 2:**
Name: [ ]
What it does: [ ]
Input: [ ]
Output: [ ]
External dependency?: [ ]

**Tool 3:**
Name: [ ]
What it does: [ ]
Input: [ ]
Output: [ ]
External dependency?: [ ]

[ Add more tools as needed, or write "unsure — suggest tools
  based on the goal" and let the LLM propose them ]


## PART 4 — MEMORY
> Does the agent need to remember things?

**In-session memory** (remembers within a single run):
[ ] Yes  [ ] No

**Persistent memory** (remembers across separate runs):
[ ] Yes  [ ] No

**What should be remembered?**
[ e.g. "Previous search queries to avoid repeating them",
  "The user's name and preferences", "Nothing — stateless is fine" ]


## PART 5 — LOCAL SETUP
> How will this agent run?

**LLM:**
[ ] Qwen3 Coder via llama.cpp (local, no API key)
[ ] Other local model via llama.cpp: _______________
[ ] Anthropic API (Claude): _______________
[ ] OpenAI API (GPT): _______________
[ ] Other cloud API: _______________

**llama-server URL (if using local model):** [ e.g. http://127.0.0.1:8080 ]

**Package manager:**
[ ] uv
[ ] pip3 with virtual environment
[ ] bun
[ ] Other: _______________

**Python version:** [ e.g. 3.9, 3.11 ]


## PART 6 — CONSTRAINTS AND PREFERENCES
> What boundaries should the agent respect?

**Things the agent must NOT do:**
[ e.g. "Must not write files outside the project directory",
  "Must not make more than 3 web searches per query",
  "Must not store personally identifiable information" ]

**Error handling preference:**
[ ] Strict — crash loudly so I can see what went wrong
[ ] Graceful — catch errors and continue with a message
[ ] Graceful with logging — catch errors and write to a log file

**Streaming preference:**
[ ] Stream tokens to terminal in real time
[ ] Wait for complete response before printing
[ ] Not important

**Verbosity preference:**
[ ] Show reasoning steps (verbose=True)
[ ] Silent except for final answer
[ ] Not important


## PART 7 — PACKAGE STRUCTURE PREFERENCE
> How should the code be organised?

[ ] Standard package structure (config, memory, prompts, tools/, agent, run)
[ ] Single file — everything in one agent.py (imports, tools, LLM setup,
    prompt, agent, executor, and invocation all in one place — good for
    simple agents where a full package structure isn't worth the overhead)
[ ] I have a preference: _______________


## PART 8 — EXAMPLES
> Optional but very helpful. Give 2-3 concrete examples of the
> agent working correctly. These help the LLM understand the
> exact behaviour you want.

**Example 1:**
Input:  [ e.g. "Summarise recent news about llama.cpp" ]
Output: [ e.g. "Creates llama_cpp.md with a 3-paragraph summary
          and 5 bullet points of key facts" ]

**Example 2:**
Input:  [ ]
Output: [ ]

**Example 3:**
Input:  [ ]
Output: [ ]


## PART 9 — KNOWN UNKNOWNS
> What are you unsure about? What tradeoffs are you aware of?
> This section tells the LLM where you want its input most.

[ e.g. "I'm not sure if I need memory for this — what would you
  recommend?",
  "I don't know the best way to handle rate limits on the API",
  "I'm unsure whether to use one tool or three for this task" ]


============================================================
INSTRUCTIONS TO THE LLM (include this section in your prompt)
============================================================

You are an expert LangChain agent developer. I want you to build
a complete Python package for a LangChain agent based on the
specification above.

Before writing any code:

1. EVALUATE the specification. Identify any ambiguities, gaps,
   or potential problems with the proposed design.

2. ASK clarifying questions if any section is unclear or
   underspecified. Number each question.

3. PROPOSE ALTERNATIVES if there is a simpler or more robust
   way to accomplish the stated goal. Explain the tradeoff.

4. CONFIRM the final design with me before building.

Once confirmed, build the complete package with:
- Folder structure matching PART 7
- All files fully implemented, not stubbed
- Docstrings on every tool following the LangChain pattern:
    what it does / use this when / example input
- Error handling per PART 6
- A README.md explaining setup and usage
- A requirements.txt

The agent must run locally with no API key using llama.cpp
at the URL specified in PART 5, via LangChain's ChatOpenAI
with base_url pointing at the local server.

============================================================
