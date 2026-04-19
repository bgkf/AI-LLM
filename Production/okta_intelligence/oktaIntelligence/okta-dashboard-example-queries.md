# Okta Intelligence Dashboard — Example Queries

Five example queries for each of the six MCP tools. Type these directly into the dashboard query input.

---

## tool_list_users

1. `List all users with status ACTIVE`
2. `Show all locked out users`
3. `List users with status DEPROVISIONED`
4. `Find all suspended users`
5. `Show users with expired passwords`

---

## tool_get_group

1. `List members of the Engineering group`
2. `Show all users in the IT Admins group`
3. `List members of the Sales team group`
4. `Who is in the Contractors group`
5. `Show users in the Finance group`

---

## tool_get_audit_logs

1. `Get audit logs from the last 24 hours`
2. `Show all audit log events from the last 7 days`
3. `Get audit logs for the last 30 days`
4. `Show recent system log events`
5. `List all audit events from today`

---

## tool_search_events

1. `Search for MFA challenge failures in the last 7 days`
2. `Find all failed login events from the last 24 hours`
3. `Show suspicious authentication events this week`
4. `Search for failed MFA attempts in the last 30 days`
5. `Find all login failures from the last 24 hours`

---

## tool_list_apps

1. `List all active app assignments`
2. `Show all inactive applications`
3. `List all applications`
4. `Show active apps assigned to users`
5. `List all SAML applications`

---

## tool_get_policy

1. `Get all active policies of type PASSWORD`
2. `Show all sign on policies`
3. `List MFA enrollment policies`
4. `Get all active access policies`
5. `Show all password policies`

---

## Notes on query wording

The `select_tool()` keyword matcher in `dashboard/server.py` maps natural language phrases to the correct tool. Wording matters:

| Keywords | Routes to |
|---|---|
| `active`, `locked`, `deprovisioned`, `suspended`, `password expired` | `tool_list_users` |
| `group`, `members of` | `tool_get_group` |
| `audit`, `log`, `event` | `tool_get_audit_logs` |
| `mfa`, `suspicious`, `challenge`, `failed login` | `tool_search_events` |
| `app`, `application`, `assignment` | `tool_list_apps` |
| `policy`, `policies` | `tool_get_policy` |

To add new query patterns, add keyword branches to `select_tool()` in `dashboard/server.py`.
