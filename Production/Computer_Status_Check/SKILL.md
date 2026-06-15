---
name: computer-status-check
description: Run the Computer Status Check workflow — triage, investigate, and remediate Jamf MDM issues from Linear. Use when the user says "run computer status check", "check computer status", "run CSC", "process Jamf issues", or "check IT-123".
argument-hint: [issue-identifier]
allowed-tools: [Bash, Read]
---

# Computer Status Check

Run the Computer Status Check workflow against qualifying Linear issues in the 🪨 Jamf Change Log project.

## Arguments

$ARGUMENTS

## Instructions

1. Change to the project directory

2. Ensure dependencies are installed. If `node_modules` does not exist, run:
   ```
   npm install
   ```

3. Ensure `.env` exists with the required credentials (`OKTA_API_TOKEN`, `LINEAR_API_KEY`, `JAMF_URL`, `JAMF_CLIENT_ID`, `JAMF_CLIENT_SECRET`). If missing, tell the user which variables are needed and stop.

4. Build the run command based on arguments:

   - **No arguments** — process all qualifying issues:
     ```
     npx ts-node src/run.ts
     ```

   - **Single issue identifier** (e.g., `IT-123`) — process only that issue:
     ```
     npx ts-node src/run.ts --issue <identifier>
     ```

   - If the user says "batch" or "auto-approve", add `--batch`:
     ```
     npx ts-node src/run.ts --batch
     npx ts-node src/run.ts --issue IT-123 --batch
     ```

5. Run the command and stream output to the user. The process is interactive — it will prompt for approval at each remediation step unless `--batch` is used.

6. When the run completes, summarize the results shown in the summary table.

## Example Usage

```
/computer-status-check
/computer-status-check IT-123
/computer-status-check IT-123 batch
```
