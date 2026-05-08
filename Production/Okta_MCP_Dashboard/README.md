# Okta Intelligence Dashboard

A local macOS dashboard that combines **apfel** (Apple's on-device LLM via FoundationModels) with the **official Okta MCP server** to give your IT team a natural language interface for querying Okta data. All inference runs on-device. No external API keys required for the LLM.

---

## Overview

The dashboard has three layers:

```
Presentation layer   →   Intelligence layer   →   Data layer
(dashboard UI)           (apfel --serve)           (okta-mcp-server + Okta API)
```

- **Presentation** — plain HTML + vanilla JS served by a local Python/Flask server
- **Intelligence** — apfel runs on-device, consumes the system prompt, and calls MCP tools
- **Data** — the official [`okta-mcp-server`](https://github.com/okta/okta-mcp-server) package handles Okta API calls via OAuth 2.0

Query routing is handled deterministically in `server.py` using a keyword/synonym matcher loaded from `intelligence/query-synonyms.json`. The model is not involved in routing or result formatting. The synonym file is loaded fresh on every query — changes take effect immediately without restarting the server.

Data flows entirely in memory. Nothing is written to disk at runtime except logs. Closing the tab or quitting the server clears all results.

---

## Runtime requirements

| Requirement | Notes |
|---|---|
| macOS 26 (Tahoe) or later | Apple Intelligence required |
| Apple Silicon | Neural Engine used by apfel |
| Apple Intelligence enabled | System Settings → Apple Intelligence |
| `apfel` in `PATH` | Deployed via MDM — verify with `apfel --model-info` |
| Python 3.10+ | Managed via Jamf at `/usr/local/bin/python3` |
| Okta API Services app | OAuth 2.0 client — see Authentication below |

---

## Authentication

The dashboard uses the official Okta MCP server, which authenticates via **OAuth 2.0 Device Authorization Grant**. This replaces the old SSWS API token approach.

### One-time setup

1. In your Okta Admin Console, create an **API Services** application
2. Note the **Client ID**
3. Grant the app the following scopes: `okta.users.read`, `okta.groups.read`, `okta.apps.read`, `okta.policies.read`, `okta.logs.read`
4. Set `OKTA_CLIENT_ID` in `.env` (or via the **Configure Okta OAuth** button in the dashboard)

### First-run browser auth

The first time the server makes an Okta API call, `okta-mcp-server` initiates the Device Auth Grant flow — it prints a verification URL and user code. Open that URL in your browser, enter the code, and approve access. The token is cached in the OS keyring and reused for all subsequent runs.

To trigger auth manually before using the dashboard:

```bash
venv/bin/okta-mcp-server
```

Follow the prompt, then Ctrl-C once authenticated. The dashboard will use the cached token from that point on.

### Token storage

The OAuth token is stored in the macOS **Keychain** via the `keyring` library — not in a file, cookie, or environment variable. It persists across reboots and process restarts. You can inspect or delete it in **Keychain Access.app** by searching for `OktaAuthManager`.

| Keychain entry | Key |
|---|---|
| `OktaAuthManager` | `api_token` |
| `OktaAuthManager` | `refresh_token` (when present) |

When a query returns a 401, the dashboard automatically deletes the cached token from the keychain. The next query will trigger a fresh Device Auth Grant flow.

---

## Install

### MDM deployment (Jamf)

The package includes a `postinstall` script that runs automatically after the files land on the target machine. It handles four things in order:

1. Removes the macOS quarantine attribute from `apfel`
2. Creates the project-local `venv/` using `/usr/local/bin/python3`
3. Installs all Python dependencies from `requirements.txt` into the venv (includes `okta-mcp-server`)
4. Generates `data/okta-mcp-server/start.sh` pointing to `venv/bin/okta-mcp-server`

The script writes to `launch.log` at the repo root throughout, so any failure during deployment is captured there.

> **Dependency order:** apfel must be present at `/usr/local/bin/apfel` before the postinstall runs. Set the dashboard package to depend on the apfel package in Jamf so the install order is guaranteed.

After deployment, edit `.env` at the install path to set `OKTA_ORG_URL`, `OKTA_CLIENT_ID`, and optionally `OKTA_SCOPES`. Users must complete the first-run browser auth step before the dashboard can reach Okta.

---

### Manual install (development)

#### 1. Clone the repository

```bash
git clone <repo-url>
cd okta-intelligence-dashboard
```

#### 2. Create the project-local virtual environment

```bash
/usr/local/bin/python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

#### 3. Generate the MCP start script

```bash
INSTALL_DIR=$(pwd)
cat > data/okta-mcp-server/start.sh << EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/okta-mcp-server"
EOF
chmod +x data/okta-mcp-server/start.sh
```

#### 4. Configure your environment

Open `.env` at the repo root and set:

```
OKTA_ORG_URL=https://your-domain.okta.com
OKTA_CLIENT_ID=0oa…
OKTA_SCOPES=okta.users.read okta.groups.read okta.apps.read okta.policies.read okta.logs.read
```

#### 5. Complete first-run authentication

```bash
venv/bin/okta-mcp-server
```

Follow the Device Auth Grant prompt in your browser, then Ctrl-C. The token is cached in the OS keyring.

#### 6. Start the dashboard

```bash
venv/bin/python dashboard/server.py
```

The server starts on `http://localhost:8080` and opens in your default browser automatically. apfel launches as a subprocess and is terminated when the server exits.

---

## Configuring OAuth credentials at runtime

Click **Configure Okta OAuth** in the dashboard header to open the config modal. Enter your Org URL, Client ID, and Scopes, then click **Save**. Values are written to `.env` immediately. If this is the first time credentials are being set, run `venv/bin/okta-mcp-server` in a terminal to complete browser authentication before making queries.

---

## File tree

```
okta-intelligence-dashboard/
│
├── .env                              # OKTA_ORG_URL, OKTA_CLIENT_ID, OKTA_SCOPES — never committed
├── .gitignore                        # .env, venv/, start.sh
├── requirements.txt                  # mcp, httpx, python-dotenv, flask, okta-mcp-server (GitHub)
├── postinstall                       # MDM post-install script — venv setup + quarantine removal
├── launch.log                        # Created at runtime — server lifecycle + install events
├── venv/                             # Project-local venv — not committed
│
├── dashboard/
│   ├── icon.png                      # Optional — shown in header if present
│   ├── index.html                    # Full dashboard UI
│   ├── app.js                        # apfel client, health checks, export,
│   │                                 # workflow modal, row selection, table rendering
│   ├── style.css                     # System dark/light theme, all component styles
│   └── server.py                     # Flask server — apfel lifecycle, query routing,
│                                     # /set-config, /quit, /restart, /server-status,
│                                     # /query, /send-to-workflow
│                                     # Logs to launch.log via Python logging
│
├── intelligence/
│   ├── system-prompt.txt             # Loaded by apfel at startup
│   ├── config.json                   # Port, apfel port, token budget, result limits,
│   │                                 # paths to system prompt and MCP server
│   └── query-synonyms.json           # Natural language → tool intent mapping table.
│                                     # Edit this file to add query phrases without
│                                     # touching Python code. Loaded fresh on every query.
│
└── data/
    └── okta-mcp-server/
        └── start.sh                  # Generated by postinstall — launches okta-mcp-server
```

---

## Dashboard UI

### Header

```
[ Okta Intelligence ]        [ ● Server  ● API ]  [ Configure Okta OAuth ]  [ Restart ]  [ Quit ]
```

The two health indicators are event-driven — they run on page load, after a restart, and after a failed query. They do not poll on a timer.

| Indicator | Green | Amber | Red |
|---|---|---|---|
| Server | apfel running + MCP connected | Restarting | apfel down or unreachable |
| API | OAuth token valid + Okta reachable | Credentials not configured | 401 or unreachable |

Hovering either indicator shows the last check result and timestamp.

### Query panel

- Free-text input — natural language questions about your Okta environment
- Result limit selector (50 / 100 / 200 / 500)
- Time range picker (24h / 7d / 30d / Custom)
- Template chips for the most common queries

### Query routing

Queries are routed to tools by `select_tool()` in `dashboard/server.py`, which loads phrase lists from `intelligence/query-synonyms.json`. The model is not involved in routing or result formatting.

| Keywords (examples) | Routes to |
|---|---|
| `failed login`, `authentication failed`, `invalid credentials` | `get_logs` (failure filter) |
| `mfa`, `suspicious`, `challenge`, `push denied` | `get_logs` (failure filter) |
| `audit`, `log`, `event`, `activity`, `history` | `get_logs` |
| `sign on policy`, `authentication policy` | `list_policies` (OKTA_SIGN_ON) |
| `mfa enroll`, `mfa enrollment`, `mfa policy` | `list_policies` (MFA_ENROLL) |
| `profile enrollment`, `profile policy` | `list_policies` (PROFILE_ENROLLMENT) |
| `password policy`, `password policies`, `password rule` | `list_policies` (PASSWORD) |
| `app`, `application`, `sso`, `saml`, `assignment` | `list_applications` |
| `group`, `team`, `members of` | `list_groups` → `list_group_users` (two-step) |
| `active`, `locked`, `deprovisioned`, `suspended`, `terminated` | `list_users` |

To add new phrases, edit `intelligence/query-synonyms.json` — no code changes needed.

### Result panel

- Detects result type (users, log events, apps, policies, etc.) and renders the appropriate table
- Log events show four summary columns with expandable full-event rows (click any row)
- All columns are client-side sortable
- Checkbox column with Select All for row selection
- Export and Workflow buttons appear whenever a result set is present

### Export

Both exports run entirely in the browser — no server involvement.

- **↓ JSON** — exports the `data` array as a formatted `.json` file
- **↓ CSV** — flattens records to CSV; nested objects are JSON-stringified into their cell

### Send to Okta Workflow

Clicking **→ Workflow** opens a modal where you supply an Okta Workflows invoke URL. The HTTP request is proxied through `server.py` (using `httpx`) to avoid CORS issues. The invoke URL is remembered for the session. No retry logic — resend manually if needed.

---

## Server endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/set-config` | Write `OKTA_ORG_URL`, `OKTA_CLIENT_ID`, `OKTA_SCOPES` to `.env` |
| `GET` | `/server-status` | Returns `{"apfel": true/false}` |
| `POST` | `/query` | Route prompt to tool via synonym matcher, execute via MCP, return JSON |
| `POST` | `/restart` | Stop apfel, clear pycache, re-install deps, restart apfel |
| `POST` | `/send-to-workflow` | Proxy payload to an Okta Workflows invoke URL |
| `POST` | `/quit` | Stop apfel and exit the server |

---

## Query templates

| Button | Query sent to server |
|---|---|
| All active users | `List all users with status ACTIVE` |
| Locked out users | `List all users with status LOCKED_OUT` |
| Deprovisioned this month | `List users deprovisioned in the last 30 days` |
| Failed logins today | `Get all failed login events from the last 24 hours` |
| Suspicious MFA events | `Search for MFA challenge failures in the last 7 days` |
| App access report | `List all active app assignments` |

---

## Adding query synonyms

Open `intelligence/query-synonyms.json`. The file structure maps tool names to phrase lists. For tools that support subtypes (users), phrases are grouped by subtype key.

To add a new phrase for locked-out users:

```json
"tool_list_users": {
  "LOCKED_OUT": [
    "locked", "locked out", "account locked",
    "your new phrase here"
  ]
}
```

To add a new phrase that routes to audit logs:

```json
"tool_get_audit_logs": [
  "audit", "log", "event", "activity",
  "your new phrase here"
]
```

Save the file — changes are picked up on the next query without restarting the server. Keys beginning with `_` are treated as comments and ignored by the loader.

---

## Restart behaviour

The Restart button stops apfel, clears all `__pycache__` and `.pyc` files, re-runs `pip install -r requirements.txt` into the venv, and starts apfel fresh. OAuth credentials in `.env` are preserved across restart.

---

## Transit security

| Leg | Encrypted | Notes |
|---|---|---|
| Dashboard → server.py | No (HTTP localhost) | Loopback only — never leaves the machine |
| server.py → apfel | No (HTTP localhost) | Loopback only — never leaves the machine |
| apfel → okta-mcp-server | No (stdio) | Local subprocess — no network hop |
| okta-mcp-server → Okta API | Yes (HTTPS) | Enforced by Okta |
| server.py → Okta Workflows | Yes (HTTPS) | `https://` required — validated before send |

---

## Logging

All server lifecycle events are written to `launch.log` at the repo root. This includes startup, apfel process events (PID, start, stop, kill), OAuth config changes, tool selection and execution, restart sequences, workflow sends, and any errors. The `postinstall` script also appends to the same file during MDM deployment.

To tail the log while the server is running:

```bash
tail -f launch.log
```

---

## Troubleshooting

**Check the log first**
Most issues are explained in `launch.log`. Open it or tail it before investigating further.

**Server indicator is red on load**
apfel may still be starting. Wait a few seconds and click Restart. Verify apfel is in PATH: `which apfel`.

**API indicator is amber**
OAuth credentials are not configured. Click **Configure Okta OAuth** in the header and enter your Org URL and Client ID.

**API indicator is red**
The OAuth token may be invalid or expired, or Okta is unreachable. Run `venv/bin/okta-mcp-server` in a terminal to re-authenticate.

**Query returns wrong results or wrong tool**
The prompt didn't match any synonym phrases. Check `intelligence/query-synonyms.json` and add the phrase to the appropriate tool. The `launch.log` shows `Selected tool:` for every query so you can see exactly what was matched.

**First query hangs for a long time**
The Device Auth Grant flow may be waiting for browser approval. Check the terminal where the server is running (or `launch.log`) for a verification URL. Open it in your browser and approve access.

**`401 Unauthorized` in query results**
OAuth token has expired. Run `venv/bin/okta-mcp-server` in a terminal to re-authenticate.

**`403 Forbidden` in query results**
The OAuth app is missing a required scope. Verify the app in Okta Admin Console has all five `okta.*.read` scopes and that admin consent has been granted.

**`apfel: command not found`**
apfel is deployed via MDM. Contact your IT administrator to confirm it has been pushed to your machine.

**`ModuleNotFoundError: No module named 'flask'`**
Running with the system Python instead of the venv. Use `venv/bin/python dashboard/server.py`.

**`okta-mcp-server: command not found`**
The venv is missing the package. Run `venv/bin/pip install -r requirements.txt` from the repo root. Note: `okta-mcp-server` is not on PyPI and is installed directly from GitHub — ensure the machine has internet access and `git` is available during install.

**Post-install failed during MDM deployment**
Check `launch.log` at the install path — the script logs each step and captures the failure. Common causes: apfel not yet deployed (dependency order issue in Jamf), or insufficient permissions on the install directory.
