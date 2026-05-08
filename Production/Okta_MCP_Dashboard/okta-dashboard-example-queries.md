# Okta Intelligence Dashboard — Example Queries

Example queries for each of the tools powered by the official Okta MCP server. Type these directly into the dashboard query input.

---

## Users (`list_users`)

1. `List all active users`
2. `Show all locked out users`
3. `List users with status DEPROVISIONED`
4. `Find all suspended users`
5. `Show users with expired passwords`

---

## Groups (`list_groups` → `list_group_users`)

1. `List members of the Engineering group`
2. `Show all users in the IT Admins group`
3. `List members of the Sales team group`
4. `Who is in the Contractors group`
5. `Show users in the Finance group`

---

## System logs (`get_logs`)

1. `Get audit logs from the last 24 hours`
2. `Show all failed login events from the last 7 days`
3. `Find all failed logins today`
4. `Search for MFA challenge failures`
5. `Show suspicious authentication events this week`

---

## Applications (`list_applications`)

1. `List all active apps`
2. `Show all inactive applications`
3. `List all applications`
4. `Show active apps`
5. `List all SAML applications`

---

## Policies (`list_policies`)

1. `Show all password policies`
2. `Get all sign on policies`
3. `List MFA enrollment policies`
4. `Show profile enrollment policies`
5. `Get all active password policies`

---

## Notes on query wording

The `select_tool()` keyword matcher in `dashboard/server.py` maps natural language phrases to the correct tool. Wording matters:

| Keywords | Routes to |
|---|---|
| `active`, `locked`, `deprovisioned`, `suspended`, `password expired` | `list_users` |
| `group`, `team`, `members of` | `list_groups` → `list_group_users` |
| `audit`, `log`, `event`, `failed login`, `mfa`, `suspicious` | `get_logs` |
| `app`, `application`, `assignment`, `saml`, `sso` | `list_applications` |
| `password policy`, `sign on policy`, `mfa policy`, `profile enrollment` | `list_policies` |

To add new query patterns, edit `intelligence/query-synonyms.json` — no code changes needed.
