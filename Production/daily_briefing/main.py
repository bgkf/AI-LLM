#!/usr/bin/env python3
"""Daily briefing: pulls calendar events, Linear deadlines, Notion updates,
and Slack saves. Saves structured JSON for the Swift notification app.

Usage:
    python3 main.py --tomorrow        # next business day (default)
    python3 main.py --today           # current day (morning briefing)
    python3 main.py --merge-file F    # read Slack/Notion JSON from file F, fetch calendar/Linear normally
    python3 main.py --no-notify       # skip the macOS notification
"""

import base64
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from services.calendar import fetch_events
from services.linear import fetch_upcoming_issues
from services.notion import fetch_tasks_and_updates
from services.slack import fetch_recent_saves
from services.mcp_fetch import fetch_slack_saves, fetch_notion_updates
from services.html_report import generate_html

PROJECT_DIR = Path(__file__).parent
BRIEFING_JSON = PROJECT_DIR / "briefing.json"
BRIEFING_HTML = PROJECT_DIR / "briefing.html"
APP_BUNDLE = PROJECT_DIR / "DailyBriefing.app"
NOTIFY_APP = APP_BUNDLE / "Contents" / "MacOS" / "DailyBriefing"


def get_target_date(mode):
    today = date.today()
    if mode == "today":
        return today
    weekday = today.weekday()
    if weekday == 4:  # Friday → Monday
        return today + timedelta(days=3)
    if weekday == 5:  # Saturday → Monday
        return today + timedelta(days=2)
    if weekday == 6:  # Sunday → Monday
        return today + timedelta(days=1)
    return today + timedelta(days=1)


def format_time(iso_str):
    if not iso_str or "T" not in iso_str:
        return iso_str or ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%-I:%M %p")
    except ValueError:
        return iso_str


def build_briefing(target, external=None, use_mcp=False):
    target_str = target.strftime("%A, %B %-d")
    is_today = target == date.today()
    label = "Today" if is_today else target.strftime("%A")

    data = {
        "target_date": target.isoformat(),
        "target_label": label,
        "target_display": target_str,
        "calendar": [],
        "linear": [],
        "notion": [],
        "slack": [],
        "errors": [],
    }

    cal = fetch_events(target)
    if cal["ok"]:
        conflicts = []
        events = cal["events"]
        for i in range(1, len(events)):
            prev_end = events[i - 1]["end"]
            curr_start = events[i]["start"]
            if prev_end and curr_start and "T" in prev_end and "T" in curr_start:
                try:
                    gap = datetime.fromisoformat(curr_start) - datetime.fromisoformat(prev_end)
                    if gap <= timedelta(0):
                        conflicts.append(f"{events[i-1]['title']} overlaps {events[i]['title']}")
                    elif gap <= timedelta(minutes=5):
                        conflicts.append(f"{events[i-1]['title']} → {events[i]['title']} (back-to-back)")
                except ValueError:
                    pass

        for e in events:
            data["calendar"].append({
                "time": f"{format_time(e['start'])}–{format_time(e['end'])}",
                "title": e["title"],
                "attendees": e["attendees"],
                "zoom": e["zoom_link"] is not None,
                "html_link": e.get("html_link"),
            })
        if conflicts:
            data["conflicts"] = conflicts
    else:
        data["errors"].append(f"Calendar: {cal['error']}")

    lin = fetch_upcoming_issues()
    if lin["ok"]:
        for i in lin["issues"]:
            data["linear"].append({
                "id": i["id"],
                "title": i["title"],
                "status": i["status"],
                "due": i["due"],
                "url": i["url"],
            })
    else:
        data["errors"].append(f"Linear: {lin['error']}")

    if external and "notion" in external:
        data["notion"] = external["notion"]
    elif use_mcp:
        data["notion"] = fetch_notion_updates()
    else:
        notion = fetch_tasks_and_updates()
        if notion["ok"]:
            for p in notion.get("recent_pages", []):
                data["notion"].append({"title": p["title"]})
        else:
            data["errors"].append(f"Notion: {notion['error']}")

    if external and "slack" in external:
        data["slack"] = external["slack"]
    elif use_mcp:
        data["slack"] = fetch_slack_saves()
    else:
        slack = fetch_recent_saves()
        if slack["ok"]:
            for s in slack["saves"]:
                data["slack"].append({
                    "channel": s["channel"],
                    "user": s["user"],
                    "text": s["text"],
                })
        else:
            data["errors"].append(f"Slack: {slack['error']}")

    return data


def print_briefing(data):
    print(f"BRIEFING FOR {data['target_display'].upper()}\n")

    if data["calendar"]:
        print("CALENDAR")
        for e in data["calendar"]:
            line = f"  {e['time']}  {e['title']}"
            if e["attendees"]:
                line += f"  ({', '.join(e['attendees'][:4])})"
            if e["zoom"]:
                line += "  [Zoom]"
            print(line)
        for c in data.get("conflicts", []):
            print(f"  *** {c}")
    else:
        print("CALENDAR\n  No meetings.")

    if data["linear"]:
        print("\nLINEAR (due within 7 days)")
        for i in data["linear"]:
            print(f"  {i['id']}  {i['title']}  [{i['status']}]  due {i['due']}")
    else:
        print("\nLINEAR\n  No upcoming deadlines.")

    if data["notion"]:
        print("\nNOTION (updated last 24h)")
        for p in data["notion"]:
            print(f"  {p['title']}")
    else:
        print("\nNOTION\n  No recent updates.")

    if data["slack"]:
        print("\nSLACK SAVES (last 7 days)")
        for s in data["slack"]:
            print(f"  #{s['channel']}  @{s['user']}: {s['text']}")
    else:
        print("\nSLACK SAVES\n  Nothing saved recently.")

    for err in data.get("errors", []):
        print(f"\n  [!] {err}")


def notify_from_json():
    """Read existing briefing.json, generate HTML, and launch notification."""
    if not BRIEFING_JSON.exists():
        print(f"Error: {BRIEFING_JSON} not found. Run with --today or --tomorrow first.")
        sys.exit(1)

    data = json.loads(BRIEFING_JSON.read_text())
    print_briefing(data)

    BRIEFING_HTML.write_text(generate_html(data))
    print(f"\nHTML saved to {BRIEFING_HTML}")

    if NOTIFY_APP.exists():
        subprocess.run([str(NOTIFY_APP)], check=False)
    else:
        print(f"Notification app not found at {NOTIFY_APP} — skipping alert.")


def notify_from_stdin():
    """Read briefing JSON from stdin, generate HTML, and launch notification."""
    data = json.loads(sys.stdin.read())
    print_briefing(data)

    BRIEFING_HTML.write_text(generate_html(data))
    print(f"\nHTML saved to {BRIEFING_HTML}")

    if NOTIFY_APP.exists():
        subprocess.run([str(NOTIFY_APP)], check=False)
    else:
        print(f"Notification app not found at {NOTIFY_APP} — skipping alert.")


def main():
    if "--from-json" in sys.argv:
        notify_from_json()
        return

    if "--from-stdin" in sys.argv:
        notify_from_stdin()
        return

    mode = "tomorrow"
    if "--today" in sys.argv:
        mode = "today"

    external = None
    if "--merge-b64" in sys.argv:
        idx = sys.argv.index("--merge-b64")
        external = json.loads(base64.b64decode(sys.argv[idx + 1]))
    elif "--merge-file" in sys.argv:
        idx = sys.argv.index("--merge-file")
        merge_path = Path(sys.argv[idx + 1])
        if not merge_path.is_absolute():
            merge_path = PROJECT_DIR / merge_path
        external = json.loads(merge_path.read_text())
        merge_path.unlink(missing_ok=True)

    use_mcp = "--use-mcp" in sys.argv

    target = get_target_date(mode)
    data = build_briefing(target, external=external, use_mcp=use_mcp)
    print_briefing(data)

    BRIEFING_JSON.write_text(json.dumps(data, indent=2))
    BRIEFING_HTML.write_text(generate_html(data))
    print(f"\nJSON saved to {BRIEFING_JSON}")
    print(f"HTML saved to {BRIEFING_HTML}")

    if "--no-notify" not in sys.argv:
        if NOTIFY_APP.exists():
            subprocess.run([str(NOTIFY_APP)], check=False)
        else:
            print(f"Notification app not found at {NOTIFY_APP} — skipping alert.")


if __name__ == "__main__":
    main()
