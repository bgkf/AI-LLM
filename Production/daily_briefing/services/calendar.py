import csv
import io
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone


GAM_PATH = os.environ.get("GAM_PATH", os.path.expanduser("~/bin/gam7/gam"))
GAM_USER = os.environ.get("GAM_USER", "<USER_NAME")


def fetch_events(target_date):
    try:
        pacific = timezone(timedelta(hours=-7))
        day_start = datetime(
            target_date.year, target_date.month, target_date.day,
            tzinfo=pacific,
        )
        day_end = day_start + timedelta(days=1)

        result = subprocess.run(
            [
                GAM_PATH, "calendar", GAM_USER, "print", "events",
                "timemin", day_start.isoformat(),
                "timemax", day_end.isoformat(),
                "singleevents",
                "fields", "summary,start,end,attendees,location,description,htmlLink",
                "formatjson",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or f"GAM exited {result.returncode}"}

        reader = csv.DictReader(io.StringIO(result.stdout))
        events = []
        for row in reader:
            raw = row.get("JSON", "")
            if not raw:
                continue
            # GAM formatjson + CSV quoting can produce \\" sequences that
            # break json.loads — collapse them to escaped quotes.
            fixed = raw.replace('\\\\"', '\\"')
            try:
                evt = json.loads(fixed)
            except json.JSONDecodeError:
                continue

            summary = evt.get("summary")
            if not summary:
                continue

            start_raw = evt.get("start", {}).get("dateTime", evt.get("start", {}).get("date"))
            end_raw = evt.get("end", {}).get("dateTime", evt.get("end", {}).get("date"))

            attendees = []
            for a in evt.get("attendees", []):
                if a.get("self"):
                    continue
                name = a.get("displayName") or a.get("email", "").split("@")[0]
                first = re.split(r"[\s.]+", name)[0]
                attendees.append(first.title())

            zoom_link = None
            location = evt.get("location", "")
            if "zoom.us" in location:
                zoom_link = location.split("?")[0]
            elif "zoom.us" in evt.get("description", ""):
                match = re.search(r"https://[\w.]*zoom\.us/j/\d+", evt.get("description", ""))
                if match:
                    zoom_link = match.group(0)

            events.append({
                "start": start_raw,
                "end": end_raw,
                "title": summary,
                "attendees": attendees,
                "zoom_link": zoom_link,
                "html_link": evt.get("htmlLink"),
            })

        events.sort(key=lambda e: e.get("start") or "")

        return {"ok": True, "events": events}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
