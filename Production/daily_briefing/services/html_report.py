"""Generates an HTML briefing report from structured data."""

from datetime import datetime, timezone, timedelta


def generate_html(data):
    pacific = timezone(timedelta(hours=-7))
    now = datetime.now(pacific)
    date_str = data.get("target_display", "")
    label = data.get("target_label", "Tomorrow")

    sections = []

    # Calendar
    if data["calendar"]:
        rows = []
        for e in data["calendar"]:
            zoom = ' <span class="tag zoom">Zoom</span>' if e["zoom"] else ""
            attendees = ""
            if e["attendees"]:
                attendees = f' <span class="attendees">{", ".join(e["attendees"][:4])}</span>'
            title = e["title"]
            if e.get("html_link"):
                title = f'<a href="{e["html_link"]}">{title}</a>'
            rows.append(
                f'<tr><td class="time">{e["time"]}</td>'
                f'<td>{title}{zoom}{attendees}</td></tr>'
            )
        conflicts_html = ""
        for c in data.get("conflicts", []):
            conflicts_html += f'<div class="conflict">⚠️ {c}</div>'
        sections.append(f"""
        <div class="section">
            <h2>📅 Calendar</h2>
            <table>{"".join(rows)}</table>
            {conflicts_html}
        </div>""")
    else:
        no_mtg = "No meetings today." if label == "Today" else "No meetings."
        sections.append(f'<div class="section"><h2>📅 Calendar</h2><p class="empty">{no_mtg}</p></div>')

    # Linear
    if data["linear"]:
        rows = []
        for i in data["linear"]:
            issue_id = i["id"]
            if i.get("url"):
                issue_id = f'<a href="{i["url"]}">{issue_id}</a>'
            rows.append(
                f'<tr><td class="issue-id">{issue_id}</td>'
                f'<td>{i["title"]}</td>'
                f'<td><span class="tag status">{i["status"]}</span></td>'
                f'<td class="due">due {i["due"]}</td></tr>'
            )
        sections.append(f"""
        <div class="section">
            <h2>🎯 Linear — Due This Week</h2>
            <table>{"".join(rows)}</table>
        </div>""")
    else:
        sections.append('<div class="section"><h2>🎯 Linear</h2><p class="empty">No upcoming deadlines.</p></div>')

    # Notion
    if data["notion"]:
        items = "".join(f"<li>{p['title']}</li>" for p in data["notion"])
        sections.append(f"""
        <div class="section">
            <h2>📝 Notion — Updated Recently</h2>
            <ul>{items}</ul>
        </div>""")
    else:
        sections.append('<div class="section"><h2>📝 Notion</h2><p class="empty">No recent updates.</p></div>')

    # Slack
    if data["slack"]:
        items = []
        for s in data["slack"]:
            items.append(f'<li><strong>#{s["channel"]}</strong> — @{s["user"]}: {s["text"]}</li>')
        sections.append(f"""
        <div class="section">
            <h2>💬 Slack Saves</h2>
            <ul>{"".join(items)}</ul>
        </div>""")
    else:
        sections.append('<div class="section"><h2>💬 Slack Saves</h2><p class="empty">Nothing saved recently.</p></div>')

    # Errors
    errors_html = ""
    if data.get("errors"):
        err_items = "".join(f"<li>{e}</li>" for e in data["errors"])
        errors_html = f'<div class="section errors"><h2>⚠️ Errors</h2><ul>{err_items}</ul></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Briefing — {date_str}</title>
<style>
    :root {{
        --bg: #1a1a2e;
        --card: #16213e;
        --text: #e0e0e0;
        --muted: #888;
        --accent: #4fc3f7;
        --border: #2a2a4a;
    }}
    @media (prefers-color-scheme: light) {{
        :root {{
            --bg: #f5f5f5;
            --card: #ffffff;
            --text: #1a1a1a;
            --muted: #666;
            --accent: #0277bd;
            --border: #e0e0e0;
        }}
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro", system-ui, sans-serif;
        background: var(--bg);
        color: var(--text);
        padding: 2rem;
        max-width: 720px;
        margin: 0 auto;
    }}
    h1 {{
        font-size: 1.5rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }}
    .date {{
        color: var(--muted);
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
    }}
    .section {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }}
    h2 {{
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 0.75rem;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
    }}
    tr {{ border-bottom: 1px solid var(--border); }}
    tr:last-child {{ border-bottom: none; }}
    td {{
        padding: 0.5rem 0.5rem 0.5rem 0;
        vertical-align: top;
        font-size: 0.9rem;
    }}
    .time {{
        white-space: nowrap;
        color: var(--accent);
        font-weight: 500;
        min-width: 140px;
    }}
    .issue-id {{
        font-family: "SF Mono", monospace;
        color: var(--accent);
        font-size: 0.85rem;
        white-space: nowrap;
    }}
    td a {{
        color: inherit;
        text-decoration: none;
        border-bottom: 1px dotted var(--muted);
    }}
    td a:hover {{
        border-bottom-color: var(--accent);
    }}
    .due {{
        color: var(--muted);
        white-space: nowrap;
        font-size: 0.85rem;
    }}
    .tag {{
        display: inline-block;
        font-size: 0.75rem;
        padding: 0.1rem 0.4rem;
        border-radius: 4px;
        margin-left: 0.4rem;
        vertical-align: middle;
    }}
    .zoom {{ background: #1a56db; color: #fff; }}
    .status {{ background: var(--border); color: var(--text); }}
    .attendees {{
        color: var(--muted);
        font-size: 0.85rem;
        margin-left: 0.4rem;
    }}
    .conflict {{
        margin-top: 0.5rem;
        padding: 0.5rem;
        background: rgba(255, 152, 0, 0.15);
        border-radius: 6px;
        font-size: 0.85rem;
    }}
    ul {{
        list-style: none;
        padding: 0;
    }}
    li {{
        padding: 0.4rem 0;
        border-bottom: 1px solid var(--border);
        font-size: 0.9rem;
    }}
    li:last-child {{ border-bottom: none; }}
    .empty {{ color: var(--muted); font-size: 0.9rem; }}
    .errors {{ border-color: #c62828; }}
    .generated {{
        text-align: center;
        color: var(--muted);
        font-size: 0.75rem;
        margin-top: 1.5rem;
    }}
</style>
</head>
<body>
    <h1>{label} — {date_str}</h1>
    {"".join(sections)}
    {errors_html}
    <div class="generated">Generated {now.strftime("%-I:%M %p PT")}</div>
</body>
</html>"""
