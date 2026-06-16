import type { IssueSummaryRow, IssueOutcome, PlanRow } from "./types";

function outcomeLabel(o: IssueOutcome): string {
  switch (o.kind) {
    case "closed-triage":
      return `Closed (triage step ${o.step})`;
    case "closed-okta":
      return `Closed (Okta Staged)`;
    case "ooo-open":
      return `OOO — title → "${o.titleUpdated}"`;
    case "self-resolved":
      return "Self-resolved";
    case "remediation-taken":
      return "Remediation taken";
    case "escalation":
      return "Escalation needed";
    case "skipped":
      return `Skipped: ${o.reason}`;
  }
}

function outcomeBucket(o: IssueOutcome): string {
  switch (o.kind) {
    case "closed-triage":
    case "closed-okta":
    case "self-resolved":
      return "closed";
    case "ooo-open":
      return "ooo-open";
    case "remediation-taken":
    case "escalation":
      return "pending";
    case "skipped":
      return "skipped";
  }
}

export function buildSummaryTable(rows: IssueSummaryRow[]): string {
  if (rows.length === 0) return "No issues processed.";

  const buckets: Record<string, IssueSummaryRow[]> = {
    closed: [],
    "ooo-open": [],
    pending: [],
    skipped: [],
  };

  for (const row of rows) {
    const bucket = outcomeBucket(row.outcome);
    buckets[bucket].push(row);
  }

  const lines: string[] = ["═══ Run Summary ═══", ""];

  const sections: Array<[string, string]> = [
    ["closed", "Closed"],
    ["ooo-open", "OOO (left open)"],
    ["pending", "Pending / Escalation"],
    ["skipped", "Skipped"],
  ];

  for (const [key, label] of sections) {
    const items = buckets[key];
    if (items.length === 0) continue;
    lines.push(`── ${label} (${items.length}) ──`);
    for (const row of items) {
      lines.push(`  ${row.issueId}  ${row.title}`);
      lines.push(`    → ${outcomeLabel(row.outcome)}`);
    }
    lines.push("");
  }

  lines.push(`Total: ${rows.length} issue(s) processed.`);
  return lines.join("\n");
}

function renderPlanRow(row: PlanRow): string[] {
  const lines: string[] = [];
  const a = row.plannedAction;

  if (a.kind === "close-triage") {
    lines.push(`  ${row.issueId}  ${row.title}`);
    if (a.detail)  lines.push(`    ${a.detail}`);
    if (a.comment) lines.push(`    Comment: ${a.comment}`);
  } else if (a.kind === "close-okta") {
    lines.push(`  ${row.issueId}  ${row.title}`);
    lines.push(`    Okta status: ${a.oktaStatus}`);
    lines.push(`    Comment: ${a.comment}`);
  } else if (a.kind === "ooo") {
    lines.push(`  ${row.issueId}  ${row.title}`);
    if (a.sourceDetail) lines.push(`    Source: ${a.sourceDetail}`);
    lines.push(`    New title: "${a.newTitle}"${a.newDueDate ? ` | Due: ${a.newDueDate}` : ""}`);
  } else if (a.kind === "remediate") {
    lines.push(`  ${row.issueId}  ${row.title}  (${a.email})`);
    if (a.triageDetail) lines.push(`    ${a.triageDetail}`);
    const oktaParts = [
      a.oktaStatus ? `status=${a.oktaStatus}` : null,
      a.oktaLastSignin ? `lastSignin=${a.oktaLastSignin}` : "lastSignin=never",
    ].filter(Boolean);
    lines.push(`    Okta: ${oktaParts.join(", ")}`);
    const steps: string[] = [];
    if (a.failedCommands > 0) steps.push(`flush ${a.failedCommands} failed`);
    if (a.pendingCommands > 0) steps.push(`cancel ${a.pendingCommands} pending`);
    steps.push("blank push");
    if (a.activeFailureModes.length > 0) steps.push(`[modes: ${a.activeFailureModes.join(", ")}]`);
    lines.push(`    Likely: ${steps.join(" → ")}`);
  } else if (a.kind === "error") {
    lines.push(`  ${row.issueId}  ${row.title}`);
    lines.push(`    ${a.reason}`);
  }

  return lines;
}

export function buildPlanTable(rows: PlanRow[]): string {
  if (rows.length === 0) return "No qualifying issues found.";

  const groups: Record<PlanRow["plannedAction"]["kind"], PlanRow[]> = {
    "close-triage": [],
    "close-okta": [],
    ooo: [],
    remediate: [],
    error: [],
  };
  for (const row of rows) groups[row.plannedAction.kind].push(row);

  const lines: string[] = [`═══ Plan — ${rows.length} issue(s) ═══`, ""];

  const sections: Array<[PlanRow["plannedAction"]["kind"], string]> = [
    ["close-triage", "CLOSE"],
    ["close-okta",   "CLOSE (Staged Okta account)"],
    ["ooo",          "OOO"],
    ["remediate",    "REMEDIATE"],
    ["error",        "ERROR"],
  ];

  for (const [kind, label] of sections) {
    const group = groups[kind];
    if (group.length === 0) continue;
    lines.push(`── ${label} (${group.length}) ──`);
    for (const row of group) lines.push(...renderPlanRow(row));
    lines.push("");
  }

  lines.push(`Total: ${rows.length} issue(s)`);
  return lines.join("\n");
}
