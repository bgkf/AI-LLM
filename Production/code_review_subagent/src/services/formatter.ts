import * as fs from "fs";
import * as path from "path";
import { ReviewResult, Severity } from "../types.js";

const SEVERITY_EMOJI: Record<Severity, string> = {
  CRITICAL: "🔴",
  HIGH: "🟠",
  MEDIUM: "🟡",
  LOW: "🔵",
  INFO: "⚪",
};

const VERDICT_EMOJI: Record<string, string> = {
  APPROVE: "✅",
  REQUEST_CHANGES: "❌",
  NEEDS_DISCUSSION: "💬",
};

export function formatReviewAsMarkdown(result: ReviewResult, filePath?: string): string {
  const lines: string[] = [];
  const ts = new Date().toISOString();

  lines.push(`# Code Review Report`);
  if (filePath) lines.push(`**File:** \`${filePath}\``);
  lines.push(`**Reviewed:** ${ts}`);
  lines.push(`**Language:** ${result.review_metadata.language}`);
  lines.push(`**Mode:** ${result.review_metadata.review_mode}`);
  lines.push(`**Lines reviewed:** ${result.review_metadata.lines_reviewed}`);
  lines.push("");

  // Verdict
  const verdictEmoji = VERDICT_EMOJI[result.verdict] ?? "❓";
  lines.push(`## ${verdictEmoji} Verdict: ${result.verdict}`);
  lines.push("");
  lines.push(result.summary);
  lines.push("");

  // Stats
  lines.push("## 📊 Issue Summary");
  lines.push("");
  lines.push(`| Severity | Count |`);
  lines.push(`|----------|-------|`);
  lines.push(`| 🔴 Critical | ${result.stats.critical} |`);
  lines.push(`| 🟠 High | ${result.stats.high} |`);
  lines.push(`| 🟡 Medium | ${result.stats.medium} |`);
  lines.push(`| 🔵 Low | ${result.stats.low} |`);
  lines.push(`| ⚪ Info | ${result.stats.info} |`);
  lines.push(`| **Total** | **${result.stats.total_issues}** |`);
  lines.push("");

  // Positive highlights
  if (result.positive_highlights.length > 0) {
    lines.push("## 👍 What's Done Well");
    lines.push("");
    for (const highlight of result.positive_highlights) {
      lines.push(`- ${highlight}`);
    }
    lines.push("");
  }

  // Issues grouped by severity
  const severityOrder: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
  const grouped = new Map<Severity, typeof result.issues>();
  for (const sev of severityOrder) grouped.set(sev, []);
  for (const issue of result.issues) {
    grouped.get(issue.severity)?.push(issue);
  }

  lines.push("## 🔍 Issues");
  lines.push("");

  for (const sev of severityOrder) {
    const issues = grouped.get(sev) ?? [];
    if (issues.length === 0) continue;

    lines.push(`### ${SEVERITY_EMOJI[sev]} ${sev} (${issues.length})`);
    lines.push("");

    for (const issue of issues) {
      const lineRef = issue.line != null ? ` — Line ${issue.line}` : "";
      lines.push(`#### \`${issue.id}\` ${issue.title}${lineRef}`);
      lines.push(`**Category:** ${issue.category}`);
      lines.push("");
      lines.push(issue.description);
      lines.push("");
      lines.push(`**💡 Suggestion:** ${issue.suggestion}`);
      if (issue.code_example) {
        lines.push("");
        lines.push("```");
        lines.push(issue.code_example);
        lines.push("```");
      }
      lines.push("");
    }
  }

  return lines.join("\n");
}

export function formatReviewInline(result: ReviewResult, filePath?: string): string {
  const lines: string[] = [];
  const verdictEmoji = VERDICT_EMOJI[result.verdict] ?? "❓";
  const label = filePath ? ` for \`${filePath}\`` : "";

  lines.push(`${verdictEmoji} **Code Review${label}: ${result.verdict}**`);
  lines.push("");
  lines.push(result.summary);
  lines.push("");
  lines.push(
    `**Issues:** 🔴 ${result.stats.critical} critical · 🟠 ${result.stats.high} high · 🟡 ${result.stats.medium} medium · 🔵 ${result.stats.low} low · ⚪ ${result.stats.info} info`
  );

  if (result.stats.total_issues > 0) {
    lines.push("");
    const topIssues = result.issues
      .filter((i) => i.severity === "CRITICAL" || i.severity === "HIGH")
      .slice(0, 5);

    if (topIssues.length > 0) {
      lines.push("**Top issues to address:**");
      for (const issue of topIssues) {
        const lineRef = issue.line != null ? ` (line ${issue.line})` : "";
        lines.push(
          `${SEVERITY_EMOJI[issue.severity]} **${issue.title}**${lineRef} — ${issue.suggestion}`
        );
      }
    }
  }

  if (result.positive_highlights.length > 0) {
    lines.push("");
    lines.push(`**👍 Highlights:** ${result.positive_highlights.slice(0, 2).join("; ")}`);
  }

  lines.push("");
  lines.push("_Full report written to `review.md`_");

  return lines.join("\n");
}

export function writeReviewFile(
  result: ReviewResult,
  outputPath: string,
  filePath?: string
): void {
  const markdown = formatReviewAsMarkdown(result, filePath);
  const dir = path.dirname(outputPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  fs.writeFileSync(outputPath, markdown, "utf-8");
}
