import type { IssueSummaryRow, IssueOutcome } from "./types";

function outcomeLabel(o: IssueOutcome): string {
  switch (o.kind) {
    case "closed-triage":
      return `Closed (triage step ${o.step})`;
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
