"""
tools/__init__.py
-----------------
Exports ALL_TOOLS — the list of LangChain tools passed to the ReAct agent.
Import order reflects the triage hierarchy:
  1. Issue fetch + parse
  2. Branch 1 checks (multi-device)
  3. Branch 2 checks (MDM investigation)
  4. Remediation actions (require human approval)
  5. Linear output (always last)
"""
from computer_status_agent.tools.linear_tools import (
    get_linear_issue,
    post_linear_comment,
    update_linear_issue,
    close_linear_issue,
)
from computer_status_agent.tools.jamf_tools import (
    get_jamf_computer,
    get_user_email,
    check_other_devices,
    check_macos_update,
    resolve_pending_policies,
    send_blank_push,
    run_jamf_policy,
    redeploy_jamf_framework,
)
from computer_status_agent.tools.user_tools import (
    check_user_ooo,
    check_okta_activity,
)
from computer_status_agent.tools.parse_tool import parse_issue_description_tool

ALL_TOOLS = [
    # ── Step 1: always first ──────────────────────────────────────────────────
    get_linear_issue,
    parse_issue_description_tool,

    # ── Step 2: Branch 1 — multiple devices ──────────────────────────────────
    check_other_devices,

    # ── Step 3: Branch 2 — MDM investigation ─────────────────────────────────
    get_jamf_computer,
    get_user_email,
    check_macos_update,
    resolve_pending_policies,
    check_user_ooo,
    check_okta_activity,

    # ── Step 4: Remediation (all require explicit human approval) ─────────────
    send_blank_push,
    run_jamf_policy,
    redeploy_jamf_framework,

    # ── Step 5: Linear output (always in this order) ──────────────────────────
    post_linear_comment,
    update_linear_issue,
    close_linear_issue,
]

__all__ = ["ALL_TOOLS"]
