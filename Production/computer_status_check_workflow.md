# Computer Status Check — Agent Workflow

> **Baseline rule:** All staleness thresholds are measured from the issue's `created_at` date, not today. A ticket that sat in the queue for a week does not accumulate extra staleness.

---

## Phase 1 — Issue Discovery

### Step 0 · Fetch qualifying issues from Linear
- Query the project **🪨 Jamf Change Log** for all non-archived issues in **Todo** status.
- Filter to issues where the title starts with `acme-` **and** contains `Computer Status Check`.
- For each qualifying issue, fetch the **full description** and the issue's **`created_at`** timestamp.
- Parse the following fields from the description:
  - Line 1: Jamf URL, Task creation date
  - Line 2: Computer name
  - Line 3: Serial number
  - Line 4: Last inventory update
  - Line 5: Last check-in
  - Line 6: Jamf Protect last check-in
  - Line 7: Superman status
  - Line 8: Uptime (days)
  - Line 9: Failed commands
  - Line 10: Last completed command
  - Line 11: Number of computers for Jamf user
  - Line 12: Pending policies

---

## Phase 2 — Auto-Close Triage

> Evaluate each condition **in order**. Stop and close the issue at the first condition that is met. If no condition is met, proceed to Phase 3.

---

### Step 1 · Multiple computers check
**Condition:** `NUMBER_OF_COMPUTERS ≥ 2`

1. Call the Jamf MCP to list all devices enrolled under this Jamf username. Retrieve each device's last check-in date.
2. Evaluate the other device(s):

   **Sub-check A — other device recently active (last check-in < 7 days):**
   - The user likely switched to a new computer and the old one has not yet been returned.
   - Comment:
     ```
     ✅ 2 computers — {other_device_name} last checked in {date}. User likely on new device.
     ```
   - Ask approval → post comment + mark issue **Done**.
   - ✅ Stop here. Skip Steps 2–7.

   **Sub-check B — other device also stale (last check-in ≥ 7 days):**
   - Do NOT close the issue.
   - Note the multi-device finding and fall through to Step 2.
   - Include this finding in the Phase 3 diagnostics comment.

---

### Step 2 · Uptime-only check
**Condition:** `UPTIME ≥ 31 days` **AND** last check-in is within 7 days of `created_at` **AND** last inventory update is within 14 days of `created_at`

- Interpretation: MDM is communicating fine. The server can read uptime, which confirms check-in is working. The Mac simply hasn't rebooted. Superman will handle the reboot on its next cycle.
- **Do NOT call any Jamf diagnostics tools. Do NOT check OOO. Do NOT send a blank push.**
- Comment:
  ```
  ✅ Uptime ≥ 30 days — check-in and inventory are current. Superman is scheduled to handle the reboot.
  ```
- Ask approval → post comment + mark issue **Done**.
- ✅ Stop here. Skip Steps 3–7.

---

### Step 3 · Self-resolved check (live Jamf data)
**Condition:** Current last check-in **and** current last inventory update are both < 1 day old (per live Jamf data, not the description)

1. Call Jamf MCP: `get_computer(serial_number)` to retrieve live device state.
2. Compare the live last check-in and last inventory update against today's date.
3. If **both** are < 1 day old:
   - Device has self-resolved since the task was created.
   - Comment:
     ```
     ✅ Self-resolved — device is now communicating.
     - Last check-in: {date}
     - Last inventory update: {date}
     ```
   - Ask approval → post comment + mark issue **Done**.
   - ✅ Stop here. Skip Steps 4–7.
4. If either is still stale, fall through to Phase 3.

---

## Phase 3 — Full MDM Investigation

> Reaches here only if Steps 1–3 did not close the issue. A real MDM communication failure exists and requires investigation.

---

### Step 4 · Check user availability (OOO)
*Automated — check all sources before concluding OOO status.*

1. Get the user's email from Jamf: `get_user_email(serial_number)`.
   - **Do not derive the email from the computer name.** Emails do not follow a predictable pattern. Always use the Jamf-sourced email.
2. Use **GAM** to check the user's Google Calendar for OOO events today and the next 14 days. Note any OOO event title, start date, and end date.
3. Check **Slack** for an OOO status emoji or text, and any returning date.
4. If calendar and Slack show no OOO, call `check_okta_activity(email)` as a secondary signal:
   - Last Okta sign-in < 7 days → user is likely active.
   - No Okta activity in 14 days → note as "no Okta activity since MM/DD" and treat as a possible OOO signal.
   - If `fastpass_macos_signin = true` → note the Mac FastPass sign-in date.

**If user IS OOO:**
- Determine return date using this priority order:
  1. Slack returning date
  2. Vacation responder end date
  3. First calendar OOO event end date
  4. Unknown
- Build updated title:
  - Return date known: `[Back YYYY-MM-DD] original-title`
  - Return date unknown: `[OOO] original-title`
  - Do NOT modify the title if it already starts with `[Back` or `[OOO]`.
- Ask approval → call `update_linear_issue(issue_id, title=new_title, due_date=return_date)`.
- Leave the issue **open**.
- ✅ Skip Steps 5–7. Proceed to Step 8 (summary).

**If user is NOT OOO:** Proceed to Step 5.

---

### Step 5 · Gather Jamf diagnostics
*Automated — collect all context before taking any action.*

1. Call `get_computer(serial_number)`. Note:
   - Most recent completed command + date
   - Jamf Protect last check-in date
   - MDM profile expiration date
   - Count of pending and failed MDM commands
2. Call `check_macos_update(jamf_id)`. Flag if an OS update is available. This is a human-action recommendation — not automated.
3. If `PENDING_POLICIES` is non-empty, resolve each policy ID to its name and Jamf URL:
   `https://acme.jamfcloud.com/policies.html?id=<POLICY_ID>&o=r`
4. Determine the active failure mode(s) using the `created_at` baseline:
   - `INVENTORY` — if last inventory update > 14 days from `created_at`
   - `CHECKIN` — if last check-in > 7 days from `created_at`

---

### Step 6 · Remediate MDM communication
*Requires approval before each sub-step. Take steps in order — stop when communication is restored.*

**6a. Cancel failed and pending MDM commands**
- Ask approval → cancel all pending and failed commands via Jamf MCP.
- Note the count of cancelled commands for the comment.

**6b. Send blank push**
- Ask approval → call `send_blank_push(jamf_id)`.
- Wait ~2 minutes and re-check live check-in status.
- If communication is restored → self-resolved (proceed to Step 7, Case A).

**6c. Pending policies blocking inventory (if applicable)**
- If pending policies are listed, flag each one by name and URL.
- Recommend excluding the computer from each blocking policy scope.
- This is a **human action** — the agent cannot modify policy scope remotely.

**6d. Redeploy Jamf management framework (last resort)**
- Only if blank push did not restore communication.
- Ask approval → call `redeploy_jamf_framework(jamf_id)`.

---

### Step 7 · Post comment and apply final action
*The comment should only report what is directly relevant to the reason the issue is being closed or left open. Do not include fields that were not part of the closing reason. Compose the comment before asking for approval to post it. Post exactly once per run.*

**After determining the outcome, apply the first matching case:**

---

**Case A — Self-resolved (blank push restored communication)**
- Condition: blank push in Step 6b confirmed communication is restored.
- Comment:
  ```
  ✅ Self-resolved — blank push restored communication.
  - Last check-in: {date}
  - Last inventory update: {date}
  - Actions taken: cancelled {N} pending/failed commands, sent blank push
  ```
- Ask approval → post comment + mark issue **Done**.

---

**Case B — User is OOO (caught late, during Step 7)**
- Condition: OOO confirmed but not caught in Step 4 (handle here as a fallback).
- Update title and due date as described in Step 4. Leave issue **open**. No comment needed beyond the title update.

---

**Case C — Remediation taken, outcome uncertain**
- Condition: user is not OOO, at least one remediation action was taken, cannot immediately confirm resolution.
- Comment:
  ```
  🔧 Remediation taken — awaiting confirmation.
  - Actions taken: {list actions taken, e.g. cancelled N commands, sent blank push, redeployed framework}
  - Pending policies flagged: {list policy names + URLs, or "None"}
  - Next step: Verify inventory updated in Jamf in ~15 min; close if resolved.
  ```
- Leave issue **open**.

---

**Case D — Escalation needed**
- Condition: remediation steps exhausted without resolution, or issue requires physical access or user interaction.
- Comment:
  ```
  ⚠️ Escalation needed.
  - Actions taken: {list actions taken}
  - Next step: {specific next step from Guru card, e.g. "Run sudo jamf recon -verbose locally", "Restart required"}
  ```
- Leave issue **open**.

---

## Phase 4 — Run Summary

### Step 8 · Output run summary

After processing all qualifying issues, output a summary table:

| Identifier | Title | Branch | Reason | Final Status | Link |
|------------|-------|--------|--------|--------------|------|
| ... | ... | ... | ... | Done / Open / Skipped | ... |

Separate into four groups:
1. **Closed** — issues marked Done this run.
2. **OOO — left open** — issues where title was updated with `[Back]` or `[OOO]`.
3. **Left open — pending verification** — remediation taken, awaiting confirmation.
4. **Skipped** — operator declined all actions, or no qualifying conditions matched.
