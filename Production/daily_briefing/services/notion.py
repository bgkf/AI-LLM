import os
from datetime import datetime, timedelta, timezone

import requests

BASE_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers():
    return {
        "Authorization": f"Bearer {os.environ.get('NOTION_API_KEY', '')}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def fetch_tasks_and_updates():
    api_key = os.environ.get("NOTION_API_KEY")
    if not api_key:
        return {"ok": False, "error": "NOTION_API_KEY not set"}

    try:
        results = {"tasks": [], "recent_pages": []}

        search_resp = requests.post(
            f"{BASE_URL}/search",
            headers=_headers(),
            json={
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 10,
            },
            timeout=15,
        )
        search_resp.raise_for_status()

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        for page in search_resp.json().get("results", []):
            edited = page.get("last_edited_time", "")
            title = _extract_title(page)
            url = page.get("url", "")

            if edited:
                edited_dt = datetime.fromisoformat(edited.replace("Z", "+00:00"))
                if edited_dt >= cutoff:
                    results["recent_pages"].append({
                        "title": title,
                        "url": url,
                        "edited": edited,
                    })

        return {"ok": True, **results}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _extract_title(page):
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            parts = prop.get("title", [])
            if parts:
                return "".join(p.get("plain_text", "") for p in parts)
    title_list = page.get("properties", {}).get("title", {}).get("title", [])
    if title_list:
        return "".join(p.get("plain_text", "") for p in title_list)
    return "(Untitled)"
