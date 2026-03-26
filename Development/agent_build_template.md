## Agent Build Template

\============================================================ <br>
HOW TO USE THIS TEMPLATE <br>
\============================================================ <br>
1. Fill in every section marked with [ ]
2. Delete any section that doesn't apply to your agent
3. Paste the completed template into your LLM chat
4. The LLM will ask clarifying questions before building
5. Save completed templates alongside the agent they produced 

\============================================================ 


### PART 1 — AGENT OVERVIEW
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


### PART 2 — INPUTS AND OUTPUTS
> What goes in and what comes out?

**Input — how will the agent be invoked?**
[ ] Interactive terminal (user types questions in a loop) <br>
[ ] Single question passed as a command-line argument <br>
[ ] Reads from a file or folder <br>
[ ] Called from another Python script <br>
[ ] Other: _______________ <br>

**Input description:**
[ What will the user actually provide? e.g. "A topic name as a
  string", "A folder path containing .txt files", "A URL" ]

**Output — what should the agent produce?** 
[ ] Text answer printed to terminal <br>
[ ] Structured data (JSON, CSV) <br>
[ ] A file written to disk (specify format below) <br>
[ ] A summary or report <br>
[ ] An action taken (API call, email sent, etc.) <br>
[ ] Other: _______________ <br>

**Output description:**
[ Describe the output in detail. e.g. "A markdown file named
  {topic}.md containing: a summary paragraph, a bullet list of
  key facts, and a list of source URLs." ]


### PART 3 — TOOLS
> What can the agent do? List each capability you need. <br>
> If you are unsure, describe the capability and let the LLM <br>
> suggest the right tool implementation. <br>

**Tool 1:** <br>
Name: [ e.g. "web_search" ] <br>
What it does: [ e.g. "Searches DuckDuckGo for a query" ] <br>
Input: [ e.g. "A search query string" ] <br>
Output: [ e.g. "Top 3 results with title, URL, and summary" ] <br>
External dependency?: [ e.g. "ddgs package, no API key needed" ] <br>

**Tool 2:** <br>
Name: [ ] <br>
What it does: [ ] <br>
Input: [ ] <br>
Output: [ ] <br>
External dependency?: [ ] <br>

**Tool 3:** <br>
Name: [ ] <br>
What it does: [ ] <br>
Input: [ ] <br>
Output: [ ] <br>
External dependency?: [ ] <br>

[ Add more tools as needed, or write "unsure — suggest tools
  based on the goal" and let the LLM propose them ]


## PART 4 — MEMORY
> Does the agent need to remember things? <br>

**In-session memory** (remembers within a single run): <br>
[ ] Yes  [ ] No <br>

**Persistent memory** (remembers across separate runs): <br>
[ ] Yes  [ ] No <br>

**What should be remembered?** <br>
[ e.g. "Previous search queries to avoid repeating them",
  "The user's name and preferences", "Nothing — stateless is fine" ]


### PART 5 — LOCAL SETUP
> How will this agent run? <br>

**LLM:** <br>
[ ] Qwen3 Coder via llama.cpp (local, no API key) <br>
[ ] Other local model via llama.cpp: _______________ <br>
[ ] Anthropic API (Claude): _______________ <br>
[ ] OpenAI API (GPT): _______________ <br>
[ ] Other cloud API: _______________ <br>

**llama-server URL (if using local model):** [ e.g. http://127.0.0.1:8080 ] <br>

**Package manager:** <br>
[ ] uv <br>
[ ] pip3 with virtual environment <br>
[ ] bun <br>
[ ] Other: _______________ <br>

**Python version:** [ e.g. 3.9, 3.11 ] <br>


### PART 6 — CONSTRAINTS AND PREFERENCES
> What boundaries should the agent respect? <br>

**Things the agent must NOT do:** <br>
[ e.g. "Must not write files outside the project directory",
  "Must not make more than 3 web searches per query",
  "Must not store personally identifiable information" ]

**Error handling preference:** <br>
[ ] Strict — crash loudly so I can see what went wrong <br>
[ ] Graceful — catch errors and continue with a message <br>
[ ] Graceful with logging — catch errors and write to a log file <br>

**Streaming preference:** <br>
[ ] Stream tokens to terminal in real time <br>
[ ] Wait for complete response before printing <br>
[ ] Not important <br>

**Verbosity preference:** <br>
[ ] Show reasoning steps (verbose=True) <br>
[ ] Silent except for final answer <br>
[ ] Not important <br>


### PART 7 — PACKAGE STRUCTURE PREFERENCE
> How should the code be organised? <br>

[ ] Standard package structure (config, memory, prompts, tools/, agent, run) <br>
[ ] Single file — everything in one agent.py (imports, tools, LLM setup, <br>
    prompt, agent, executor, and invocation all in one place — good for <br>
    simple agents where a full package structure isn't worth the overhead) <br>
[ ] I have a preference: _______________ <br>


### PART 8 — EXAMPLES
> Optional but very helpful. Give 2-3 concrete examples of the <br>
> agent working correctly. These help the LLM understand the <br>
> exact behaviour you want. <br>

**Example 1:** <br>
Input:  [ e.g. "Summarise recent news about llama.cpp" ] <br>
Output: [ e.g. "Creates llama_cpp.md with a 3-paragraph summary
          and 5 bullet points of key facts" ] <br>

**Example 2:** <br>
Input:  [ ] <br>
Output: [ ] <br>

**Example 3:** <br>
Input:  [ ] <br>
Output: [ ] <br>


### PART 9 — KNOWN UNKNOWNS
> What are you unsure about? What tradeoffs are you aware of? <br>
> This section tells the LLM where you want its input most. <br>

[ e.g. "I'm not sure if I need memory for this — what would you
  recommend?",
  "I don't know the best way to handle rate limits on the API",
  "I'm unsure whether to use one tool or three for this task" ] <br>


\============================================================ <br>
INSTRUCTIONS TO THE LLM (include this section in your prompt) <br>
\============================================================ <br>

You are an expert LangChain agent developer. I want you to build
a complete Python package for a LangChain agent based on the
specification above. <br>

Before writing any code: <br>

1. EVALUATE the specification. Identify any ambiguities, gaps,
   or potential problems with the proposed design. <br>

2. ASK clarifying questions if any section is unclear or
   underspecified. Number each question. <br>

3. PROPOSE ALTERNATIVES if there is a simpler or more robust
   way to accomplish the stated goal. Explain the tradeoff. <br>

4. CONFIRM the final design with me before building. <br>

Once confirmed, build the complete package with: <br>
- Folder structure matching PART 7 <br>
- All files fully implemented, not stubbed <br>
- Docstrings on every tool following the LangChain pattern: <br>
    what it does / use this when / example input <br>
- Error handling per PART 6 <br>
- A README.md explaining setup and usage <br>
- A requirements.txt <br>

The agent must run locally with no API key using llama.cpp
at the URL specified in PART 5, via LangChain's ChatOpenAI
with base_url pointing at the local server. <br>

\============================================================
