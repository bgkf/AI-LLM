import os
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://slack.com/api"


def fetch_recent_saves():
    token = os.environ.get("SLACK_USER_TOKEN")
    if not token:
        return {"ok": False, "error": "SLACK_USER_TOKEN not set"}

    try:
        headers = {"Authorization": f"Bearer {token}"}
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        cutoff_date = cutoff.strftime("%Y-%m-%d")

        resp = requests.get(
            f"{BASE_URL}/search.messages",
            headers=headers,
            params={
                "query": f"is:saved after:{cutoff_date}",
                "sort": "timestamp",
                "sort_dir": "desc",
                "count": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("ok"):
            return {"ok": False, "error": data.get("error", "Unknown Slack error")}

        saves = []
        for msg in data.get("messages", {}).get("matches", []):
            saves.append({
                "channel": msg.get("channel", {}).get("name", "unknown"),
                "user": msg.get("username", "unknown"),
                "text": (msg.get("text", "")[:120] + "...") if len(msg.get("text", "")) > 120 else msg.get("text", ""),
                "link": msg.get("permalink", ""),
                "ts": msg.get("ts", ""),
            })

        return {"ok": True, "saves": saves}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
