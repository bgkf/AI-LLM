# Okta Intelligence Dashboard

A local macOS dashboard that combines **apfel** (Apple's on-device LLM via FoundationModels) with an **Okta MCP server** to give your IT team a natural language interface for querying Okta data. All inference runs on-device. No external API keys required for the LLM.

---

## Overview

The dashboard has three layers:

```
Presentation layer   →   Intelligence layer   →   Data layer
(dashboard UI)           (apfel --serve)           (Okta MCP server + Okta API)
```

- **Presentation** — plain HTML + vanilla JS served by a local Python/Flask server
- **Intelligence** — apfel runs on-device, consumes the system prompt, and calls MCP tools
- **Data** — a FastMCP server wraps the Okta REST API with per-tool response trimming

Query routing is handled deterministically in `server.py` using a keyword/synonym matcher loaded from `intelligence/query-synonyms.json`. The model is used for the health indicator only — it never processes query results.

Data flows entirely in memory. Nothing is written to disk at runtime except logs and the session token written to `.env`. Closing the tab or quitting the server clears all results.

---

## Runtime requirements

| Requirement | Notes |
|---|---|
| macOS 26 (Tahoe) or later | Apple Intelligence required |
| Apple Silicon | Neural Engine used by apfel |
| Apple Intelligence enabled | System Settings → Apple Intelligence |
| `apfel` in `PATH` | Deployed via MDM — verify with `apfel --model-info` |
| Python 3.10+ | Required for FastMCP; managed via Jamf at `/usr/local/bin/python3` |

---

## Prerequisites

Before running the dashboard, confirm apfel is available:

```bash
apfel --model-info
```

If the command is not found, contact your IT administrator — apfel is deployed via MDM.

---

## Install

### MDM deployment (Jamf)

The package includes a `postinstall` script that runs automatically after the files land on the target machine. It handles four things in order:

1. Removes the macOS quarantine attribute from `apfel`
2. Creates the project-local `venv/` using `/usr/local/bin/python3`
3. Installs all Python dependencies from `requirements.txt` into the venv
4. Generates `data/okta-mcp-server/start.sh` with the correct user-specific venv path

The script writes to `launch.log` at the repo root throughout, so any failure during deployment is captured there.

> **Dependency order:** apfel must be present at `/usr/local/bin/apfel` before the postinstall runs. Set the dashboard package to depend on the apfel package in Jamf so the install order is guaranteed.

After deployment, edit `.env` at the install path to set `OKTA_DOMAIN` and optionally `OKTA_API_TOKEN`, or instruct team members to use the **Set Token** button at runtime.

---

### Manual install (development)

#### 1. Clone the repository

```bash
git clone <repo-url>
cd okta-intelligence-dashboard
```

#### 2. Create the project-local virtual environment

All Python dependencies are installed into `venv/` at the repo root and never touch system or user site-packages.

```bash
/usr/local/bin/python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

#### 3. Generate the MCP start script

```bash
INSTALL_DIR=$(pwd)
cat > data/okta-mcp-server/start.sh << EOF
#!/bin/bash
exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/data/okta-mcp-server/server.py"
EOF
chmod +x data/okta-mcp-server/start.sh
```

#### 4. Configure your environment

Open `.env` at the repo root and set:

```
OKTA_DOMAIN=your-domain.okta.com
OKTA_API_TOKEN=your-token-here
```

`OKTA_API_TOKEN` is optional — it can also be set at runtime via the **Set Token** button in the dashboard. `OKTA_DOMAIN` is required.

> **Security note:** `.env` is listed in `.gitignore` and will never be committed. The API token is held in memory during a session and written to `.env` when set via the modal so the MCP subprocess can read it.

#### 5. Start the dashboard

```bash
venv/bin/python dashboard/server.py
```

The server starts on `http://localhost:8080` and opens in your default browser automatically. apfel launches as a subprocess and is terminated when the server exits.

---

## Setting your Okta API token at runtime

If `OKTA_API_TOKEN` is not set in `.env`, the **API** health indicator will show amber and the **Set Token** button in the header will pulse. Click it, paste your token, and click **Save for session**. The token is held in memory and written to `.env` so it persists for the life of the server process.

If `OKTA_API_TOKEN` is already set in `.env`, the dashboard reads it on startup and the API indicator goes green automatically.

---

## File tree

```
okta-intelligence-dashboard/
│
├── .env                              # OKTA_DOMAIN + OKTA_API_TOKEN — never committed
├── .gitignore                        # .env, venv/, start.sh
├── requirements.txt                  # fastmcp, httpx, python-dotenv, flask
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
│                                     # /set-token, /quit, /restart, /server-status,
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
        ├── server.py                 # FastMCP entry point — registers all tools
        ├── auth.py                   # Loads OKTA_DOMAIN + OKTA_API_TOKEN from .env
        │                             # Also exposes get_gov_base_url() and
        │                             # get_gov_v2_base_url() for governance tools
        ├── trimmer.py                # Per-tool field trimming + queried-field extractor
        ├── pagination.py             # Okta Link-header cursor pagination
        ├── start.sh                  # Generated by postinstall — venv python launcher
        └── tools/
            ├── __init__.py
            │
            │   ── core tools ──
            ├── list_users.py         # Trim: displayName, email, status, lastLogin + queried field
            ├── get_group.py          # Trim: same as list_users; auto-switches to skinny_users
            │                         # endpoint for groups with 100+ members
            ├── get_audit_logs.py     # No trim — full event
            ├── search_events.py      # No trim — full event
            ├── list_apps.py          # Trim: label, status, signOnMode, assignedUserCount
            │                         # get_app_users() uses skinny_users endpoint
            │
            │   ── device tools ──
            ├── list_devices.py       # Trim: displayName, platform, model, status, lastUpdated
            ├── get_device_users.py   # Trim: displayName, email, status, managementStatus
            │
            │   ── identity & access tools ──
            ├── list_iam_roles.py     # Trim: label, type, status, description
            │                         # Also exposes list_iam_resource_sets()
            ├── list_oauth_clients.py # Trim: client_name, application_type, grant_types
            ├── list_sessions.py      # Trim: status, createdAt, expiresAt, mfaActive
            ├── get_user_factors.py   # Trim: factorType, provider, status, credentialId
            │
            │   ── governance tools (requires Okta Identity Governance license) ──
            ├── get_entitlements.py   # Trim: name, type, resource, status
            │                         # Also exposes list_grants() filtered by principal
            ├── get_principal_access.py  # Trim: resource, entitlement, grant status/dates
            │                            # Also exposes list_principal_entitlements()
            ├── get_entitlement_history.py  # Trim: action, principal, entitlement, timestamp
            └── get_access_reviews.py       # Trim: name, status, reviewer, campaign, dates
                                            # Also exposes get_access_review_detail()
                                            # Rate limit: 25/50 req/min — lowest in the org
```

---

## Dashboard UI

### Header

```
[ Okta Intelligence ]        [ ● Server  ● API ]  [ Set Token ]  [ Restart ]  [ Quit ]
```

The two health indicators are event-driven — they run on page load, after a restart, and after a failed query. They do not poll on a timer.

| Indicator | Green | Amber | Red |
|---|---|---|---|
| Server | apfel running + MCP connected | Restarting | apfel down or unreachable |
| API | Token valid + Okta reachable | No token set | 401 or unreachable |

Hovering either indicator shows the last check result and timestamp.

### Query panel

- Free-text input — natural language questions about your Okta environment
- Result limit selector (50 / 100 / 200 / 500)
- Time range picker (24h / 7d / 30d / Custom)
- Template chips for the most common queries

### Query routing

Queries are routed to tools by `select_tool()` in `dashboard/server.py`, which loads phrase lists from `intelligence/query-synonyms.json`. The model is not involved in routing or result formatting. The synonym file is loaded fresh on every query — changes take effect immediately without restarting the server.

| Keywords (examples) | Routes to |
|---|---|
| `failed login`, `authentication failed`, `invalid credentials` | `tool_search_events` (FAILURE) |
| `mfa`, `suspicious`, `challenge`, `push denied` | `tool_search_events` (FAILURE) |
| `audit`, `log`, `event`, `activity`, `history` | `tool_get_audit_logs` |
| `password policy`, `sign on policy`, `mfa policy` | `tool_unavailable` — see note below |
| `app`, `application`, `sso`, `saml`, `assignment` | `tool_list_apps` |
| `who is on device`, `device users`, `users on device` | `tool_get_device_users` |
| `device`, `devices`, `laptop`, `managed device` | `tool_list_devices` |
| `iam`, `admin role`, `who has admin`, `privileged access` | `tool_list_iam_roles` |
| `oauth`, `oauth client`, `oidc`, `api client` | `tool_list_oauth_clients` |
| `session`, `sessions`, `still signed in`, `logged in` | `tool_get_user_sessions` |
| `mfa factors`, `mfa enrolled`, `authenticator`, `two factor` | `tool_get_user_factors` |
| `entitlement history`, `access history`, `when was access granted` | `tool_get_entitlement_history` |
| `principal access`, `what can user access`, `over-provisioned` | `tool_get_principal_access` |
| `entitlement`, `entitlements`, `grants`, `active grants` | `tool_list_entitlements` |
| `access review`, `certification campaign`, `pending reviews` | `tool_list_access_reviews` |
| `group`, `team`, `members of` | `tool_get_group` |
| `active`, `locked`, `deprovisioned`, `suspended`, `terminated` | `tool_list_users` |

> **Policy queries** — `/api/v1/policies` is not in the permitted API list for this token. Any query matching policy phrases returns a clear error message in the clarify panel rather than executing. No API call is made.

To add new phrases, edit `intelligence/query-synonyms.json` — no code changes needed.

### Result panel

- Detects result type (users, log events, apps, devices, etc.) and renders the appropriate table
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
| `POST` | `/set-token` | Store Okta API token in memory and write to `.env` |
| `GET` | `/server-status` | Returns `{"apfel": true/false}` |
| `POST` | `/query` | Route prompt to tool via synonym matcher, execute, return JSON |
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

To add a new phrase for devices:

```json
"tool_list_devices": [
  "device", "devices", "managed device", "laptop",
  "your new phrase here"
]
```

Save the file — changes are picked up on the next query without restarting the server. Keys beginning with `_` are treated as comments and ignored by the loader.

---

## Governance tools

The following tools use the `/governance/api/v1/*` and `/governance/api/v2/*` endpoints and require the **Okta Identity Governance** license. They will return a 404 if the feature is not enabled on your org.

| Tool | Endpoint | Rate limit |
|---|---|---|
| `list_entitlements`, `list_grants` | `/governance/api/v1/entitlements`, `/grants` | 50/100 req/min |
| `get_principal_access`, `list_principal_entitlements` | `/governance/api/v1/principal-access` | 50/100 req/min |
| `get_entitlement_history` | `/governance/api/v1/principal-entitlements/history` | 50/100 req/min |
| `list_access_reviews`, `get_access_review_detail` | `/governance/api/v2/security-access-reviews` | 25/50 req/min |

To verify your org has the license before building:

```bash
curl -s -H "Authorization: SSWS YOUR_TOKEN" \
  "https://YOUR_DOMAIN/governance/api/v1/entitlements?limit=1" \
  | python3 -m json.tool
```

A `404` with `"errorCode": "E0000022"` means the feature is not licensed. A `200` or empty array means you are good.

---

## Rate limits

| Tool / endpoint | Limit |
|---|---|
| `list_devices` | 50/100 req/min |
| `list_oauth_clients` | 50/100 req/min |
| All `/governance/api/v1/*` tools | 50/100 req/min |
| `list_access_reviews` | 25/50 req/min — lowest in the org |
| `list_iam_roles` | 800/1,600 req/min |
| `list_users`, `get_group`, `list_apps` | 300–500/600–1,000 req/min |

`list_access_reviews` defaults to `limit=25` to respect the floor. Do not raise this without confirming your org's burst capacity.

---

## Restart behaviour

The Restart button stops apfel, clears all `__pycache__` and `.pyc` files, re-runs `pip install -r requirements.txt` into the venv, and starts apfel fresh. The session Okta API token is preserved across restart.

---

## Transit security

| Leg | Encrypted | Notes |
|---|---|---|
| Dashboard → server.py | No (HTTP localhost) | Loopback only — never leaves the machine |
| server.py → apfel | No (HTTP localhost) | Loopback only — never leaves the machine |
| apfel → Okta MCP server | No (stdio) | Local subprocess — no network hop |
| Okta MCP server → Okta API | Yes (HTTPS) | Enforced by Okta |
| server.py → Okta Workflows | Yes (HTTPS) | `https://` required — validated before send |

---

## Logging

All server lifecycle events are written to `launch.log` at the repo root. This includes startup, apfel process events (PID, start, stop, kill), token changes, tool selection and execution, restart sequences, workflow sends, and any errors. The `postinstall` script also appends to the same file during MDM deployment.

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
No token is set. Click Set Token in the header and paste your Okta API token.

**API indicator is red**
The token may be invalid or expired, or Okta is unreachable. Click Set Token to re-enter it.

**Query returns wrong results or wrong tool**
The prompt didn't match any synonym phrases. Check `intelligence/query-synonyms.json` and add the phrase to the appropriate tool. The `launch.log` shows `Selected tool:` for every query so you can see exactly what was matched.

**Policy queries return an error message**
`/api/v1/policies` is not in the permitted API list for this token. This is expected behaviour — the error is shown in the clarify panel and no API call is made.

**Governance tools return 404**
The Okta Identity Governance license is not active on this org. See the Governance tools section above for how to verify.

**`apfel: command not found`**
apfel is deployed via MDM. Contact your IT administrator to confirm it has been pushed to your machine.

**`OKTA_DOMAIN is not set` error in logs**
Add `OKTA_DOMAIN=your-domain.okta.com` to the `.env` file at the repo root.

**`ModuleNotFoundError: No module named 'flask'`**
Running with the system Python instead of the venv. Use `venv/bin/python dashboard/server.py`.

**`ModuleNotFoundError: No module named 'list_users'` (or any tool)**
The `tools/` directory is not on `sys.path`. This is resolved in the current `server.py` — ensure you are running the latest version.

**`fastmcp` not found during postinstall**
Python version is 3.9.x. The postinstall is pointing at the wrong interpreter. The `PYTHON` variable in `postinstall` must be `/usr/local/bin/python3` (3.10+), not `/usr/bin/python3`.

**Post-install failed during MDM deployment**
Check `launch.log` at the install path — the script logs each step and captures the failure. Common causes: apfel not yet deployed (dependency order issue in Jamf), or insufficient permissions on the install directory.
