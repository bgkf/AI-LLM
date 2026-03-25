"""
tools/linear_tools.py
----------------------
LangChain tools for interacting with the Linear API.
"""
from __future__ import annotations

import logging
import os

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

LINEAR_API_KEY = os.environ.get("LINEAR_API_KEY", "")
_GQL_URL = "https://api.linear.app/graphql"
_HEADERS = {"Authorization": LINEAR_API_KEY, "Content-Type": "application/json"}


def _gql(query: str, variables: dict | None = None) -> dict:
    resp = httpx.post(
        _GQL_URL,
        json={"query": query, "variables": variables or {}},
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


@tool
def get_linear_issue(issue_id: str) -> dict:
    """
    Fetch a Linear issue by identifier (e.g. 'IT-5786').

    Returns a dict with: id, identifier, title, description, status,
    assignee, dueDate, url, labels, createdAt, updatedAt.
    """
    query = """
    query GetIssue($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        url
        createdAt
        updatedAt
        dueDate
        state { name type }
        assignee { name email }
        labels { nodes { name } }
      }
    }
    """
    # Linear accepts both UUID and identifier like "IT-1234"
    data = _gql(query, {"id": issue_id})
    issue = data.get("data", {}).get("issue", {})
    if not issue:
        return {"error": f"Issue {issue_id} not found"}

    return {
        "id": issue["id"],
        "identifier": issue["identifier"],
        "title": issue["title"],
        "description": issue.get("description", ""),
        "status": issue.get("state", {}).get("name", ""),
        "status_type": issue.get("state", {}).get("type", ""),
        "assignee": issue.get("assignee", {}).get("name", "Unassigned"),
        "due_date": issue.get("dueDate"),
        "url": issue.get("url"),
        "labels": [n["name"] for n in issue.get("labels", {}).get("nodes", [])],
        "created_at": issue.get("createdAt"),
        "updated_at": issue.get("updatedAt"),
    }


@tool
def post_linear_comment(issue_id: str, body: str) -> dict:
    """
    Post a Markdown-formatted comment to a Linear issue.

    Args:
        issue_id: The UUID of the issue (from get_linear_issue).
        body: Markdown comment text.

    Returns:
        dict with 'comment_id' on success, or 'error' on failure.
    """
    mutation = """
    mutation CreateComment($issueId: String!, $body: String!) {
      commentCreate(input: { issueId: $issueId, body: $body }) {
        success
        comment { id }
      }
    }
    """
    data = _gql(mutation, {"issueId": issue_id, "body": body})
    result = data.get("data", {}).get("commentCreate", {})
    if result.get("success"):
        return {"comment_id": result["comment"]["id"]}
    return {"error": "Comment creation failed", "raw": data}


@tool
def update_linear_issue(
    issue_id: str,
    due_date: str | None = None,
    title: str | None = None,
) -> dict:
    """
    Update the due date and/or title of a Linear issue.

    Use this to:
      - Prepend the return date to the title when the user is OOO, e.g.
        "[Back 2026-03-14] acme-username Computer Status Check"
      - Extend the due date when the user is OOO.

    Args:
        issue_id: The UUID of the issue (from get_linear_issue 'id' field).
        due_date: New due date in YYYY-MM-DD format (optional).
        title:    New full title string (optional). Build the full title
                  before passing — this overwrites, it does not append.

    Returns:
        dict with 'success' bool and updated field values.
    """
    input_fields: dict = {}
    if due_date:
        input_fields["dueDate"] = due_date
    if title:
        input_fields["title"] = title

    if not input_fields:
        return {"error": "No fields provided to update_linear_issue"}

    mutation = """
    mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
        issue { id title dueDate }
      }
    }
    """
    data = _gql(mutation, {"id": issue_id, "input": input_fields})
    result = data.get("data", {}).get("issueUpdate", {})
    updated = result.get("issue", {})
    return {
        "success": result.get("success", False),
        "title": updated.get("title"),
        "due_date": updated.get("dueDate"),
    }


# State IDs for the IT team — fetched once and hardcoded for speed.
# Re-run `Linear:list_issue_statuses team=IT` if these ever change.
_IT_STATE_IDS = {
    "Done":       "c6a4658d-4c0f-4c23-abed-8e8959cd0328",
    "Canceled":   "36bb832a-d008-4707-bb0d-ade730d7ed07",
    "In Progress":"09bf044d-fc3a-41b5-af42-aa36d58cf4c8",
    "Todo":       "dd0c9416-d7d5-4d0c-b26f-005280ace591",
    "Blocked":    "2737ffa2-ee45-4189-add3-13ed16b0c6b1",
}


@tool
def close_linear_issue(issue_id: str, reason: str) -> dict:
    """
    Mark a Linear issue as Done (closed).

    Only call this when the issue is fully resolved — i.e. the computer
    is confirmed to be checking in, updating inventory, and Superman is
    working normally.  Always post the final comment BEFORE closing.

    Args:
        issue_id: The UUID of the issue (from get_linear_issue 'id' field).
        reason:   One-sentence human-readable reason for closure, e.g.
                  "Blank push succeeded and inventory updated within 15 min."
                  This is logged but not posted separately — include it in
                  the comment body before calling this tool.

    Returns:
        dict with 'success' bool and 'state' name.
    """
    state_id = _IT_STATE_IDS["Done"]
    mutation = """
    mutation CloseIssue($id: String!, $stateId: String!) {
      issueUpdate(id: $id, input: { stateId: $stateId }) {
        success
        issue { id title state { name } }
      }
    }
    """
    data = _gql(mutation, {"id": issue_id, "stateId": state_id})
    result = data.get("data", {}).get("issueUpdate", {})
    issue = result.get("issue", {})
    logger.info(
        "close_linear_issue: %s → %s (reason: %s)",
        issue_id, issue.get("state", {}).get("name"), reason,
    )
    return {
        "success": result.get("success", False),
        "state": issue.get("state", {}).get("name"),
        "title": issue.get("title"),
    }
