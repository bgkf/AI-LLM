import os
from datetime import datetime, timedelta, timezone

import requests

GRAPHQL_URL = "https://api.linear.app/graphql"


def fetch_upcoming_issues():
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        return {"ok": False, "error": "LINEAR_API_KEY not set"}

    try:
        seven_days = (
            datetime.now(timezone.utc) + timedelta(days=7)
        ).strftime("%Y-%m-%d")

        query = """
        query {
          viewer {
            assignedIssues(
              filter: {
                dueDate: { lte: "%s" }
                state: { type: { nin: ["completed", "canceled"] } }
              }
              orderBy: updatedAt
              first: 20
            ) {
              nodes {
                identifier
                title
                dueDate
                state { name }
                url
              }
            }
          }
        }
        """ % seven_days

        resp = requests.post(
            GRAPHQL_URL,
            json={"query": query},
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        issues = []
        for node in data["data"]["viewer"]["assignedIssues"]["nodes"]:
            issues.append({
                "id": node["identifier"],
                "title": node["title"],
                "status": node["state"]["name"],
                "due": node["dueDate"],
                "url": node["url"],
            })

        return {"ok": True, "issues": issues}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
