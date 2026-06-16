# Computer Status Check

Automated triage and remediation for Jamf MDM issues tracked in Linear. Built on the Claude Agent SDK — TypeScript owns the state machine, Claude handles the two judgment calls (OOO detection and comment composition).

## How it works

1. **Issue Discovery** — Fetches all `Todo` issues in the Linear project "🪨 Jamf Change Log" whose title starts with `COMPANY-` and contains `Computer Status Check`.

2. **Triage** (Steps 1–3, parallel) — Three pure checks run concurrently:
   - **Multi-computer** — If the user has 2+ devices and another is active, close.
   - **Uptime-only** — If uptime ≥ 31 days with fresh check-in/inventory, close (Superman handles the reboot).
   - **Self-resolved** — If the device is now communicating (check-in + inventory < 1 day old), close.

3. **Investigation** (Steps 4–5) — If triage didn't close the issue:
   - **Jamf diagnostics** — Resolves email, Jamf ID, live check-in dates, MDM command queue, and pending policies.
   - **OOO detection** (Claude agent) — Checks GAM vacation responder, Google Calendar, Slack status, and Okta last sign-in. Prefixes the issue title with `[OOO]` or `[Back YYYY-MM-DD]` and stops.

4. **Remediation** (Steps 6a–6d, sequential with approval gates):
   - 6a: Flush failed MDM commands
   - 6b: Cancel pending MDM commands
   - 6c: Send blank push → wait 2 min → re-check
   - 6d: Redeploy Jamf management framework (last resort)

5. **Comment composition** (Claude agent) — Generates a case-matched Linear comment (Case A: self-resolved, Case C: remediation taken, Case D: escalation needed).

6. **Summary** — Prints a table grouping issues by outcome: closed, OOO, pending, skipped.

## Setup

### Prerequisites

- Node.js 18+
- Claude Code with the Claude Agent SDK
- MCP servers connected: Linear, Jamf, Slack (for OOO detection)
- GAM installed at `/Users/USERNAME/bin/gam7/gam`

### Environment variables

Copy `.env.example` to `.env` and fill in:

```
OKTA_API_TOKEN=       # Okta API token — OOO agent checks last sign-in
LINEAR_API_KEY=       # Linear API key — issue reads and writes
JAMF_URL=             # Jamf Pro URL (e.g., https://COMPANY.jamfcloud.com)
JAMF_CLIENT_ID=       # Jamf Pro API client ID — MDM commands
JAMF_CLIENT_SECRET=   # Jamf Pro API client secret
```

### Install

```bash
cd ~/projects/computer_status_check
npm install
```

## Usage

### Preview what will happen (no writes)

```bash
npx ts-node src/run.ts --plan
npx ts-node src/run.ts --plan --issue IT-123
```

Runs all read-only phases (triage, diagnostics, OOO detection) and prints a plan table showing the intended action for each issue — close, OOO, or remediate — with the evidence behind each decision. Nothing is written to Linear or Jamf. Use this to review before executing.

Example output:
```
═══ Plan — 3 issue(s) ═══

IT-6393  COMPANY-ISSUE-NAME
  → CLOSE     step 2
               uptime=32d (✓ need≥31) | checkin=2026-06-15 0.1d (✓) | inventory=2026-06-15 0.1d (✓)
               Comment: ✅ Uptime ≥ 30 days — check-in and inventory are current...

IT-6401  COMPANY-ISSUE-NAME
  → OOO       Slack: :pto: Vacationing - Back on Mon 6/20
               New title: "[Back 2026-06-20] COMPANY-ISSUE-NAME Computer Status Check" | Due: 2026-06-20

IT-6405  COMPANY-ISSUE-NAME
  → REMEDIATE  john.doe@COMPANY.com
               live checkin=2026-06-07 (196h ago ✗) | live inventory=2026-06-07 (197h ago ✗)
               Queue: 2 failed, 3 pending
               Likely: flush 2 failed → cancel 3 pending → blank push

To execute with interactive approval:
  ! npx ts-node src/run.ts
  ! npx ts-node src/run.ts --issue IT-123
```

### Execute with interactive approval

Run from the Claude Code prompt using `!` so you can approve each action as it appears:

```
! npx ts-node src/run.ts
! npx ts-node src/run.ts --issue IT-123
```

### Process all qualifying issues (non-interactive)

```bash
npx ts-node src/run.ts
```

### Process a single issue

```bash
npx ts-node src/run.ts --issue IT-123
```

### Batch mode (auto-approve all actions)

```bash
npx ts-node src/run.ts --batch
npx ts-node src/run.ts --issue IT-123 --batch
```

### Selective auto-approve

```bash
npx ts-node src/run.ts --batch post-comment,mark-done,blank-push
```

### Claude Code skill

If the skill is installed, invoke from any Claude Code session:

```
/computer-status-check
/computer-status-check IT-123
/computer-status-check IT-123 batch
```

## Architecture

```
src/
├── run.ts                  Entry point — env validation, issue loop, summary
├── linear.ts               Linear GraphQL API — fetch, comment, update
├── jamf.ts                 Jamf Pro REST API — inventory reads, MDM commands
├── triage.ts               Steps 1–3: multi-computer, uptime, self-resolved
├── remediation.ts          Steps 6a–6d with approval gates + comment orchestration
├── agents/
│   ├── oooAgent.ts         Claude query() — OOO detection across 4 sources
│   └── commentAgent.ts     Claude query() — case-matched comment generation
├── approval.ts             Interactive + batch-mode approval gates
├── summary.ts              Run summary table builder
├── dates.ts                Date utilities: daysBetween, parseDate, fmtDate
└── types.ts                All interfaces — ParsedIssue, DiagnosticsResult, etc.
```

**Design principle:** Claude is used in exactly two places — OOO detection (ambiguous multi-signal judgment) and comment composition (prose generation). Everything else is deterministic TypeScript: date math, triage conditions, API calls, sequencing, approval gates.

## Key constraints

- `createdAt` is the staleness baseline for triage, never `new Date()`.
- The anchor Jamf call is `getComputersInventory` with `GENERAL` + `USER_AND_LOCATION` sections — yields email, jamfId, lastContactTime, and reportDate in one request.
- Subagents never take side-effecting actions. All writes go through TypeScript approval gates.
- Step 2 (uptime) makes zero external calls.
- "Stop the run" exits cleanly with whatever summary has been accumulated.
