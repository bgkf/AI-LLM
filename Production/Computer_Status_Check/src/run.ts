import * as dotenv from "dotenv";
dotenv.config();

import { fetchQualifyingIssues, fetchIssueByIdentifier, postComment, markDone, updateIssue } from "./linear";
import { gatherDiagnostics } from "./jamf";
import { evaluateMultiComputer, evaluateUptime, evaluateSelfResolved } from "./triage";
import { detectOOO } from "./agents/oooAgent";
import {
  runRemediation,
  composeAndPostComment,
  StopRunError,
} from "./remediation";
import { buildSummaryTable } from "./summary";
import { createApprovalFn, parseBatchArgs } from "./approval";
import { fmtDate } from "./dates";
import type { ParsedIssue, IssueSummaryRow, IssueOutcome } from "./types";

const OKTA_API_TOKEN = process.env.OKTA_API_TOKEN;
if (!OKTA_API_TOKEN) throw new Error("OKTA_API_TOKEN is not set. Add it to .env");

async function processIssue(
  issue: ParsedIssue,
  approval: ReturnType<typeof createApprovalFn>
): Promise<IssueSummaryRow> {
  const buildRow = (outcome: IssueOutcome): IssueSummaryRow => ({
    issueId: issue.issueId,
    title: issue.title,
    outcome,
    linearUrl: `https://linear.app/issue/${issue.issueId}`,
  });

  // --- Phase 2: Triage (parallel) ---
  const [multiResult, uptimeResult, selfResolvedResult] = await Promise.all([
    evaluateMultiComputer(issue),
    Promise.resolve(evaluateUptime(issue)),
    evaluateSelfResolved(issue),
  ]);

  for (const result of [multiResult, uptimeResult, selfResolvedResult]) {
    if (result.detail) console.log(`  Triage step ${result.step}: ${result.detail}`);
    if (result.close) {
      console.log(`  ✓ Triage close: ${result.reason}`);
      const decision = await approval(
        `Post comment and mark Done: ${result.comment}`,
        "post-comment"
      );
      if (decision === "stop") throw new StopRunError();
      if (decision === "proceed") {
        await postComment(issue.linearId, result.comment!);
        await markDone(issue.linearId, issue.teamId);
      }
      return buildRow({
        kind: "closed-triage",
        step: result.step,
        comment: result.comment!,
      });
    }
  }

  console.log("  Triage: no close condition met → investigation");

  // --- Phase 3: Investigation ---
  // Diagnostics first — anchor call gives us email + jamfId
  const diagnostics = await gatherDiagnostics(issue);
  console.log(`  Diagnostics: email=${diagnostics.email}, jamfId=${diagnostics.jamfId}`);

  // OOO detection
  const oooResult = await detectOOO(issue, diagnostics.email, OKTA_API_TOKEN!);
  const oooSourceLabel = oooResult.returnDateSource
    ? ({ vacation_responder: "GAM vacation responder", calendar: "GAM calendar", slack: "Slack" } as const)[oooResult.returnDateSource]
    : null;
  const oooDetailStr = [
    oooSourceLabel,
    oooResult.sourceDetail,
  ].filter(Boolean).join(": ");
  console.log(
    `  OOO: isOOO=${oooResult.isOOO}` +
    (oooResult.returnDate ? `, returns ${fmtDate(oooResult.returnDate)}` : "") +
    (oooDetailStr ? ` [${oooDetailStr}]` : "")
  );

  // OOO branch
  if (oooResult.isOOO) {
    let newTitle = issue.title;
    if (oooResult.suggestedTitlePrefix) {
      newTitle = `${oooResult.suggestedTitlePrefix} ${issue.title}`;
    }
    const dueStr = oooResult.returnDate ? fmtDate(oooResult.returnDate) : undefined;

    const decision = await approval(
      `Update title to: "${newTitle}"${dueStr ? ` and set due date to ${dueStr}` : ""}`,
      "update-title"
    );
    if (decision === "stop") throw new StopRunError();
    if (decision === "proceed") {
      await updateIssue(issue.linearId, {
        title: newTitle,
        dueDate: dueStr,
      });
    }
    return buildRow({
      kind: "ooo-open",
      titleUpdated: newTitle,
      dueDate: oooResult.returnDate,
    });
  }

  // --- Remediation (Steps 6a–6d) ---
  console.log("  Starting remediation...");
  const remediationResult = await runRemediation(issue, diagnostics, approval);

  // --- Step 7: Comment composition ---
  const { comment, outcomeCase } = await composeAndPostComment(
    issue,
    remediationResult,
    diagnostics,
    approval
  );

  if (outcomeCase === "A") {
    return buildRow({
      kind: "self-resolved",
      remediation: remediationResult,
      comment,
    });
  } else if (outcomeCase === "D") {
    return buildRow({
      kind: "escalation",
      remediation: remediationResult,
      comment,
    });
  } else {
    return buildRow({
      kind: "remediation-taken",
      remediation: remediationResult,
      comment,
    });
  }
}

function parseIssueArg(args: string[]): string | undefined {
  const idx = args.indexOf("--issue");
  if (idx === -1) return undefined;
  const value = args[idx + 1];
  if (!value || value.startsWith("--")) {
    throw new Error("--issue requires a Linear identifier (e.g., --issue IT-123)");
  }
  return value;
}

async function main() {
  const batchConfig = parseBatchArgs(process.argv);
  const approval = createApprovalFn(batchConfig);
  const singleIssueId = parseIssueArg(process.argv);

  // Phase 1 — fetch issues
  let issues: ParsedIssue[];
  if (singleIssueId) {
    console.log(`Fetching single issue: ${singleIssueId}`);
    const issue = await fetchIssueByIdentifier(singleIssueId);
    issues = [issue];
  } else {
    console.log("Fetching qualifying issues from Linear...");
    issues = await fetchQualifyingIssues();
  }

  if (issues.length === 0) {
    console.log("No qualifying issues found.");
    return;
  }
  console.log(`Found ${issues.length} qualifying issue(s). Processing sequentially.\n`);

  const summaryRows: IssueSummaryRow[] = [];

  for (const issue of issues) {
    console.log(`\n── ${issue.issueId}: ${issue.title}`);
    try {
      const row = await processIssue(issue, approval);
      summaryRows.push(row);
    } catch (err) {
      if (err instanceof StopRunError) {
        console.log("\nRun stopped by operator.");
        break;
      }
      console.error(`  Error processing ${issue.issueId}:`, err);
      summaryRows.push({
        issueId: issue.issueId,
        title: issue.title,
        outcome: { kind: "skipped", reason: String(err) },
        linearUrl: `https://linear.app/issue/${issue.issueId}`,
      });
    }
  }

  // Phase 4 — run summary
  console.log("\n" + buildSummaryTable(summaryRows));
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
