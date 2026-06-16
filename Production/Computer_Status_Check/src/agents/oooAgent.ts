import { query } from "@anthropic-ai/claude-agent-sdk";
import type { ParsedIssue, OOOResult } from "../types";

const OOO_AGENT_PROMPT = `
You are an OOO detection agent. Your job is to determine if a COMPANY employee is
currently out of office, and if so, when they return.

You have access to four data sources. Check them in this order:
1. GAM vacation responder — most reliable signal
2. GAM calendar OOO events — check for "OOO", "Out of Office", "Vacation", "PTO"
3. Slack status — check for OOO emoji or text, return date
   Call slack_search_users with the user's email to get their Slack user ID.
   Then call slack_read_user_profile with that user ID.
   Check profile.status_text for: "OOO", "Out of Office", "Vacation", "PTO", or a return date.
   Check profile.status_emoji for travel/vacation emoji: :palm_tree: :airplane: :beach_with_umbrella: :desert_island:
   Parse return date from status_text if present (e.g. "OOO until June 20").
4. Okta — ALWAYS check, regardless of other signals (account status is required)
   The token is provided to you as OKTA_API_TOKEN in this prompt. Fetch via Bash:
   curl -s -H "Authorization: SSWS {OKTA_API_TOKEN}" -H "Accept: application/json" \\
     "https://COMPANY.okta.com/api/v1/users?q={email}&limit=1"
   Read response[0].lastLogin (ISO 8601 timestamp, or null if never logged in).
   Read response[0].status (STAGED | PROVISIONED | ACTIVE | RECOVERY | PASSWORD_EXPIRED | LOCKED_OUT | DEPROVISIONED).

IMPORTANT:
- GAM is aliased to /Users/USERNAME/bin/gam7/gam
- Compute RFC 3339 timestamps for YESTERDAY and 14_DAYS_FROM_TODAY at runtime
- Never derive the user email from the computer name — it is given to you directly
- The Okta token is provided in this prompt — use it verbatim in the curl Authorization header
- If signals conflict, weight them: vacation_responder > calendar > slack > okta
- Okta inactivity alone is not OOO — it is a weak signal, note it but don't close on it
- Always populate oktaStatus and oktaLastSignin even when isOOO is false

Return ONLY a JSON object — no preamble, no markdown fences:
{
  "isOOO": boolean,
  "returnDate": "YYYY-MM-DD" | null,
  "returnDateSource": "vacation_responder" | "calendar" | "slack" | null,
  "sourceDetail": "exact text or description of the confirming signal, e.g. 'Slack status: :pto: Vacationing - Back on Mon 6/15' or 'GAM vacation responder active until 2026-06-20'" | null,
  "oktaStatus": "STAGED" | "PROVISIONED" | "ACTIVE" | "RECOVERY" | "PASSWORD_EXPIRED" | "LOCKED_OUT" | "DEPROVISIONED" | null,
  "oktaLastSignin": "YYYY-MM-DD" | null,
  "evidence": {
    "vacationResponderActive": boolean,
    "calendarOOOFound": boolean,
    "slackOOOFound": boolean,
    "oktaActive": boolean | null
  },
  "suggestedTitlePrefix": "[Back YYYY-MM-DD]" | "[OOO]" | null
}

Set suggestedTitlePrefix to null if the issue title already starts with "[Back" or "[OOO]".
`;

export async function detectOOO(
  issue: ParsedIssue,
  email: string,
  oktaToken: string
): Promise<OOOResult> {
  let resultJson: string | undefined;

  const prompt = [
    `Check OOO status for user email: ${email}`,
    `Issue: ${issue.issueId} — ${issue.title}`,
    `OKTA_API_TOKEN: ${oktaToken}`,
  ].join("\n");

  for await (const message of query({
    prompt,
    options: {
      allowedTools: ["Bash", "slack_search_users", "slack_read_user_profile"],
      systemPrompt: OOO_AGENT_PROMPT,
      maxTurns: 15,
    },
  })) {
    if ("result" in message) resultJson = message.result as string;
  }

  if (!resultJson) throw new Error("OOO agent returned no result");

  const jsonMatch = resultJson.match(/\{[\s\S]*\}/);
  if (!jsonMatch) throw new Error(`OOO agent returned non-JSON: ${resultJson.slice(0, 200)}`);
  const parsed = JSON.parse(jsonMatch[0]);

  return {
    email,
    isOOO: parsed.isOOO,
    returnDate: parsed.returnDate ? new Date(parsed.returnDate) : null,
    returnDateSource: parsed.returnDateSource,
    sourceDetail: parsed.sourceDetail ?? null,
    suggestedTitlePrefix: parsed.suggestedTitlePrefix,
    oktaStatus: parsed.oktaStatus ?? null,
    oktaLastSignin: parsed.oktaLastSignin ?? null,
  };
}
