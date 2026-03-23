"""
agent.py
--------
LangChain ReAct agent for the Computer Status Check workflow.

The agent follows a three-branch triage hierarchy and asks for explicit
human approval before every Jamf write action and every Linear mutation.

Usage (CLI):
    uv run python agent.py IT-5786
    uv run python agent.py IT-5786 --dry-run

Usage (import):
    from computer_status_agent.agent import run_agent
    result = run_agent("IT-5786")
"""
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool

from computer_status_agent.tools import ALL_TOOLS

load_dotenv()
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── System prompt ─────────────────────────────────────────────────────────────
_PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.txt"
_SYSTEM_PROMPT = _PROMPT_PATH.read_text()

# ReAct prompt template (LangChain standard format)
_REACT_TEMPLATE = (
    _SYSTEM_PROMPT
    + """

You have access to the following tools:
{tools}

Use this format strictly:
Thought: <your reasoning>
Action: <tool name, one of [{tool_names}]>
Action Input: <input to the tool as a JSON object>
Observation: <tool result>
... (repeat Thought/Action/Observation as needed)
Thought: I now have enough information to compose the final comment.
Final Answer: <paste the complete Linear comment here>

IMPORTANT — before calling any of these tools you MUST first print an
approval prompt and wait for the human to type 'yes':
  send_blank_push, run_jamf_policy, redeploy_jamf_framework,
  post_linear_comment, update_linear_issue, close_linear_issue

Begin!

Issue ID: {input}
{agent_scratchpad}
"""
)

_PROMPT = PromptTemplate.from_template(_REACT_TEMPLATE)


# ── Approval wrapper ──────────────────────────────────────────────────────────

# Tools that require interactive human approval before execution.
_APPROVAL_REQUIRED_TOOLS = {
    "send_blank_push",
    "run_jamf_policy",
    "redeploy_jamf_framework",
    "post_linear_comment",
    "update_linear_issue",
    "close_linear_issue",
}


def _wrap_with_approval(tool: BaseTool) -> BaseTool:
    """
    Wrap a LangChain tool so that it prompts the operator for confirmation
    in the terminal before executing. On 'no', returns a skipped message
    without calling the underlying tool.

    This wrapper is ONLY applied when DRY_RUN=false; in dry-run mode the
    underlying tools already no-op, so the approval step is informational.
    """
    original_run = tool._run

    def _run_with_approval(*args, **kwargs):
        print("\n" + "─" * 60)
        print(f"⚠️  APPROVAL REQUIRED — tool: {tool.name}")
        print(f"   Input: args={args!r}  kwargs={kwargs!r}")
        print("─" * 60)
        answer = input("   Type 'yes' to proceed or 'no' to skip: ").strip().lower()
        if answer == "yes":
            return original_run(*args, **kwargs)
        else:
            logger.info("Operator skipped tool %s", tool.name)
            return {"skipped": True, "message": f"Skipped by operator: {tool.name}"}

    tool._run = _run_with_approval
    return tool


def _build_tools() -> list[BaseTool]:
    """Return ALL_TOOLS, wrapping approval-required tools when not in dry-run."""
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    tools = []
    for t in ALL_TOOLS:
        if not dry_run and t.name in _APPROVAL_REQUIRED_TOOLS:
            tools.append(_wrap_with_approval(t))
        else:
            tools.append(t)
    return tools


# ── LLM ───────────────────────────────────────────────────────────────────────
def _build_llm() -> BaseChatModel:
    """Build LLM based on LLM_PROVIDER env var (default: anthropic)."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=4096,
            temperature=0,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            max_tokens=4096,
            temperature=0,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=os.environ.get("OLLAMA_MODEL", "llama3.3:70b"),
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=0,
        )
    elif provider == "llamacpp":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=os.environ.get("LLAMACPP_MODEL", "local-model"),
            base_url=os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1"),
            api_key="not-needed",
            max_tokens=4096,
            temperature=0,
        )
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            "Supported: anthropic, openai, ollama, llamacpp"
        )


# ── Agent ─────────────────────────────────────────────────────────────────────
def build_agent() -> AgentExecutor:
    llm = _build_llm()
    tools = _build_tools()
    agent = create_react_agent(llm=llm, tools=tools, prompt=_PROMPT)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        max_iterations=25,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )


def run_agent(issue_id: str) -> str:
    """
    Run the Computer Status Check agent against a single Linear issue.

    Args:
        issue_id: Linear issue identifier, e.g. 'IT-5786'.

    Returns:
        The final comment text (whether posted to Linear or printed in dry-run).
    """
    logger.info("Starting agent for issue %s (DRY_RUN=%s)", issue_id,
                os.environ.get("DRY_RUN", "false"))
    executor = build_agent()
    result = executor.invoke({"input": issue_id})
    output: str = result.get("output", "")
    logger.info("Agent completed for issue %s", issue_id)
    return output


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Computer Status Check agent — triage a Linear IT issue.",
    )
    parser.add_argument(
        "issue_id",
        help="Linear issue identifier or natural-language phrase, e.g. 'IT-5786' "
             "or 'computer status check IT-5786'",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Observe and report only — no Jamf mutations, no Linear writes.",
    )
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    output = run_agent(args.issue_id)
    print("\n" + "=" * 72)
    print("FINAL COMMENT:")
    print("=" * 72)
    print(output)


if __name__ == "__main__":
    main()
