# Daily Briefing

A personal daily-briefing tool for macOS: pulls today's (or tomorrow's) calendar,
Linear deadlines, recent Notion updates, and saved Slack messages into one JSON
file, renders it as an HTML page, and fires a native macOS notification that
opens the HTML when clicked.

```
┌─────────────┐     ┌────────────────┐     ┌──────────────┐     ┌───────────────────┐
│ data sources│ ──▶ │ briefing.json  │ ──▶ │ briefing.html│ ──▶ │ macOS notification │
│ (Cal/Linear/│     │ (structured)   │     │ (styled page)│     │ (DailyBriefing.app)│
│ Notion/Slack│     └────────────────┘     └──────────────┘     └───────────────────┘
└─────────────┘
```

## How data is fetched

| Source | Method | Auth |
|--------|--------|------|
| Calendar | GAM subprocess (`~/bin/gam7/gam`) | GAM service account (no tokens in `.env`) |
| Linear | Direct GraphQL API | `LINEAR_API_KEY` in `.env` |
| Slack | `claude -p` → Claude Code MCP connector | Claude Code's Slack connector |
| Notion | `claude -p` → Claude Code MCP connector | Claude Code's Notion connector |

Slack and Notion use Claude Code's already-authenticated MCP connectors
via the `claude` CLI in pipe mode. This avoids needing separate API tokens
for those services. Pass `--use-mcp` to enable this (the scheduled tasks do).

Fallback: `services/slack.py` and `services/notion.py` can hit the APIs
directly if you configure `SLACK_USER_TOKEN` and `NOTION_API_KEY` in `.env`
and omit `--use-mcp`.

## What's in this repo

| File | Purpose |
|---|---|
| `main.py` | Entry point. Builds the briefing, writes `briefing.html`, launches the notification app. |
| `services/calendar.py` | Google Calendar fetch via GAM (`singleevents`, `formatjson`). |
| `services/linear.py` | Linear GraphQL query for issues assigned to you, due within 7 days, not done/canceled. |
| `services/mcp_fetch.py` | Slack and Notion fetch via `claude -p` subprocess (uses MCP connectors). |
| `services/slack.py` | Direct Slack API fallback (`search.messages`, `is:saved`). Used when `--use-mcp` is not set. |
| `services/notion.py` | Direct Notion API fallback (search, last 24h). Used when `--use-mcp` is not set. |
| `services/html_report.py` | Renders `briefing.json` → `briefing.html` (dark/light aware, single-file, no external assets). |
| `DailyBriefing.swift` | Tiny macOS notification app. Reads `briefing.json`, shows a summary notification, opens `briefing.html` on click. |
| `DailyBriefing.app/` | Compiled bundle (machine-specific, don't rely on the committed binary). |
| `.env.example` | Template for API keys. |
| `context.md` | Detailed architecture notes and decisions from the approval-prompt refactor. |

## Prerequisites

- macOS (the notification app uses `UserNotifications`)
- Python 3.9+
- GAM 7 installed at `~/bin/gam7/gam` (or set `GAM_PATH` in `.env`)
- Claude Code CLI (`claude`) on PATH (for `--use-mcp` mode)
- Xcode Command Line Tools (`xcode-select --install`) for `swiftc`, if
  building the notification app

## Setup

### 1. Create virtualenv and install dependencies

```bash
cd ~/projects/daily-briefing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Build the notification app

```bash
mkdir -p DailyBriefing.app/Contents/MacOS
swiftc DailyBriefing.swift -o DailyBriefing.app/Contents/MacOS/DailyBriefing
```

Create `DailyBriefing.app/Contents/Info.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleIdentifier</key>
    <string>com.yourname.daily-briefing</string>
    <key>CFBundleName</key>
    <string>Daily Briefing</string>
    <key>CFBundleDisplayName</key>
    <string>Daily Briefing</string>
    <key>CFBundleExecutable</key>
    <string>DailyBriefing</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSUserNotificationAlertStyle</key>
    <string>alert</string>
</dict>
</plist>
```

Ad-hoc sign it:

```bash
codesign --force --deep --sign - DailyBriefing.app
```

The notification's icon shows the day-of-month it's briefing you about,
using the same `N.calendar` SF Symbol Calendar.app uses for its own dynamic
icon — rendered at runtime from `briefing.json`'s `target_date` and applied
via `NSApplication.shared.applicationIconImage`, so it needs no bundle
mutation or re-signing on each run.

Run it once by hand (`./DailyBriefing.app/Contents/MacOS/DailyBriefing`) and
approve the notification permission prompt.

### 3. Configure `.env`

```bash
cp .env.example .env
```

Required:
- **Linear**: personal API key from
  [linear.app/settings/api](https://linear.app/settings/api) → `LINEAR_API_KEY`

Optional (only if not using `--use-mcp`):
- **Slack**: `SLACK_USER_TOKEN` — a `xoxp-...` user token with `search:read` scope
- **Notion**: `NOTION_API_KEY` — internal integration token from
  [notion.so/my-integrations](https://www.notion.so/my-integrations)

Calendar uses GAM and needs no `.env` configuration. Set `GAM_PATH` and
`GAM_USER` if your GAM install differs from the defaults (`~/bin/gam7/gam`
and `<USER_NAME>`).

### 4. Test it

```bash
# With MCP (uses Claude Code for Slack/Notion)
~/projects/daily-briefing/.venv/bin/python3 ~/projects/daily-briefing/main.py --today --use-mcp

# Without MCP (uses API tokens in .env for everything)
source .venv/bin/activate
python3 main.py --today

# Skip the notification popup
python3 main.py --today --no-notify
```

## Claude Code scheduled tasks

Two scheduled tasks trigger the briefing automatically:

| Task | Schedule | Flag |
|---|---|---|
| `morning-briefing` | weekdays 9:11 AM | `--today` |
| `next-day-prep` | weekdays 4:46 PM | `--tomorrow` |

Both SKILL.md files contain a single bash command:

```
~/projects/daily-briefing/.venv/bin/python3 ~/projects/daily-briefing/main.py --today --use-mcp
```

This runs without any approval prompts. The bash permission pattern in
`~/.claude/settings.json` auto-allows it:

```json
"Bash(~/projects/daily-briefing/.venv/bin/python3 ~/projects/daily-briefing/main.py*)"
```

See `context.md` for the full history of permission classifier issues and
how they were resolved.

## `main.py` flags

| Flag | Description |
|---|---|
| `--today` | Target date is today |
| `--tomorrow` | Target date is next business day (Fri/Sat/Sun → Monday) |
| `--use-mcp` | Fetch Slack/Notion via `claude -p` MCP instead of direct API |
| `--merge-file F` | Read Slack/Notion data from file F instead of fetching |
| `--merge-b64 STR` | Read Slack/Notion data from base64-encoded JSON string |
| `--from-json` | Skip fetching, render + notify from existing `briefing.json` |
| `--from-stdin` | Read complete briefing JSON from stdin, render + notify |
| `--no-notify` | Skip the macOS notification |

## `briefing.json` schema

```json
{
  "target_date": "2026-07-16",
  "target_label": "Today",
  "target_display": "Thursday, July 16",
  "calendar": [
    {"time": "10:00 AM–11:00 AM", "title": "Team Meeting", "attendees": ["Alex", "Travis"], "zoom": true}
  ],
  "conflicts": ["Meeting A overlaps Meeting B"],
  "linear": [
    {"id": "IT-1234", "title": "Fix bug", "status": "In Progress", "due": "2026-07-18"}
  ],
  "notion": [
    {"title": "IT Team Meeting Agenda"}
  ],
  "slack": [
    {"channel": "helpdesk", "user": "Jane", "text": "Short summary of the message"}
  ],
  "errors": []
}
```

- Times are 12-hour with AM/PM, Pacific time
- `attendees` is first names only, excludes yourself
- `conflicts` covers overlaps and back-to-back meetings (< 5 min gap)
- `errors` is non-fatal — one source failing doesn't block the others

## Customizing

- **Styling**: `services/html_report.py` — single self-contained HTML string
  with inline CSS (dark/light via `prefers-color-scheme`), no build step
- **Notification text**: `DailyBriefing.swift`'s `sendNotification()` builds
  the summary line. Edit and rebuild with `swiftc`
- **Lookback/lookahead windows**: 7 days for Linear/Slack, 24h for Notion —
  defined in `main.py` and `services/*.py`

## Troubleshooting

- **No notification appears**: run the `.app` binary from terminal to see
  stderr. Re-signing resets the permission grant
- **`Notification app not found`**: build step was skipped
- **Notion returns nothing via API**: the integration hasn't been shared with
  any pages — share your workspace with it
- **Calendar returns no events**: check that GAM is authenticated
  (`~/bin/gam7/gam info domain`). Recurring events need `singleevents` flag
  (already set in `services/calendar.py`)
- **Errors in `errors[]`**: non-fatal by design; check the message for
  expired tokens or API changes
