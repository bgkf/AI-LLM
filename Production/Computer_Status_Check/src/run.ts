import * as dotenv from "dotenv";
dotenv.config();

import { fetchQualifyingIssues, fetchIssueByIdentifier, postComment, markDone, updateIssue } from "./linear";
import { gatherDiagnostics } from "./jamf";
import { getOktaUser, isOktaError } from "./okta";
import { evaluateMultiComputer, evaluateUptime, evaluateSelfResolved } from "./triage";
import { detectOOO } from "./agents/oooAgent";
import {
  runRemediation,
  composeAndPostComment,
  StopRunError,
} from "./remediation";
import { buildSummaryTable, buildPlanTable } from "./summary";
import { createApprovalFn, parseBatchArgs } from "./approval";
import { fmtDate } from "./dates";
import type { ParsedIssue, IssueSummaryRow, IssueOutcome, PlanRow } from "./types";

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

  // Okta status — direct call, authoritative for account status checks
  const oktaRaw = await getOktaUser(diagnostics.email, OKTA_API_TOKEN!);
  const oktaStatus = isOktaError(oktaRaw) ? null : (oktaRaw?.status ?? null);
  const oktaLastSignin = isOktaError(oktaRaw) ? null : (oktaRaw?.lastLogin?.slice(0, 10) ?? null);
  if (isOktaError(oktaRaw)) {
    console.log(`  Okta: ⚠ ${oktaRaw.error}`);
  } else {
    console.log(
      `  Okta: status=${oktaStatus ?? "not found"}` +
      (oktaLastSignin ? `, lastSignin=${oktaLastSignin}` : ", lastSignin=never")
    );
  }

  // Okta STAGED — device is between setup and in use, no remediation needed
  if (oktaStatus === "STAGED") {
    const comment = "✅ Okta account is Staged — device is between setup and in use. No remediation needed.";
    const decision = await approval(`Post comment and mark Done: ${comment}`, "post-comment");
    if (decision === "stop") throw new StopRunError();
    if (decision === "proceed") {
      await postComment(issue.linearId, comment);
      await markDone(issue.linearId, issue.teamId);
    }
    return buildRow({ kind: "closed-okta", comment });
  }

  // OOO detection
  const oooResult = await detectOOO(issue, diagnostics.email, OKTA_API_TOKEN!);
  const oooSourceLabel = oooResult.returnDateSource
    ? ({ vacation_responder: "GAM vacation responder", calendar: "GAM calendar", slack: "Slack" } as const)[oooResult.returnDateSource]
    : null;
  const oooDetailStr = [oooSourceLabel, oooResult.sourceDetail].filter(Boolean).join(": ");
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

function parsePlanArg(args: string[]): boolean {
  return args.includes("--plan");
}

async function planIssue(issue: ParsedIssue): Promise<PlanRow> {
  const buildRow = (plannedAction: PlanRow["plannedAction"]): PlanRow => ({
    issueId: issue.issueId,
    title: issue.title,
    linearUrl: `https://linear.app/issue/${issue.issueId}`,
    plannedAction,
  });

  const [multiResult, uptimeResult, selfResolvedResult] = await Promise.all([
    evaluateMultiComputer(issue),
    Promise.resolve(evaluateUptime(issue)),
    evaluateSelfResolved(issue),
  ]);

  for (const result of [multiResult, uptimeResult, selfResolvedResult]) {
    if (result.close) {
      return buildRow({
        kind: "close-triage",
        step: result.step,
        detail: result.detail ?? "",
        comment: result.comment ?? "",
      });
    }
  }

  try {
    const diagnostics = await gatherDiagnostics(issue);

    // Okta status — direct call, authoritative for account status checks
    const oktaRaw = await getOktaUser(diagnostics.email, OKTA_API_TOKEN!);
    const oktaStatus = isOktaError(oktaRaw) ? `⚠ ${oktaRaw.error}` : (oktaRaw?.status ?? "not found");
    const oktaLastSignin = isOktaError(oktaRaw) ? null : (oktaRaw?.lastLogin?.slice(0, 10) ?? null);

    if (!isOktaError(oktaRaw) && oktaRaw?.status === "STAGED") {
      return buildRow({
        kind: "close-okta",
        oktaStatus,
        comment: "✅ Okta account is Staged — device is between setup and in use. No remediation needed.",
      });
    }

    const oooResult = await detectOOO(issue, diagnostics.email, OKTA_API_TOKEN!);

    if (oooResult.isOOO) {
      const newTitle = oooResult.suggestedTitlePrefix
        ? `${oooResult.suggestedTitlePrefix} ${issue.title}`
        : issue.title;
      return buildRow({
        kind: "ooo",
        sourceDetail: oooResult.sourceDetail,
        newTitle,
        newDueDate: oooResult.returnDate ? fmtDate(oooResult.returnDate) : undefined,
      });
    }

    const triageDetail = [multiResult, uptimeResult, selfResolvedResult]
      .map(r => r.detail)
      .filter(Boolean)
      .join(" | ");

    return buildRow({
      kind: "remediate",
      triageDetail,
      email: diagnostics.email,
      failedCommands: diagnostics.failedCommandCount,
      pendingCommands: diagnostics.pendingCommandCount,
      activeFailureModes: diagnostics.activeFailureModes,
      oktaStatus,
      oktaLastSignin,
    });
  } catch (err) {
    return buildRow({ kind: "error", reason: String(err) });
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
  const isPlan = parsePlanArg(process.argv);
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

  // ── Plan mode: read-only preview, no writes ──
  if (isPlan) {
    console.log(`Found ${issues.length} qualifying issue(s). Building plan (read-only)...\n`);
    const planRows: PlanRow[] = [];
    for (const issue of issues) {
      process.stdout.write(`  Planning ${issue.issueId}...`);
      try {
        const row = await planIssue(issue);
        planRows.push(row);
        console.log(" done");
      } catch (err) {
        console.log(` error: ${err}`);
        planRows.push({
          issueId: issue.issueId,
          title: issue.title,
          linearUrl: `https://linear.app/issue/${issue.issueId}`,
          plannedAction: { kind: "error", reason: String(err) },
        });
      }
    }
    console.log("\n" + buildPlanTable(planRows));
    return;
  }

  // ── Normal mode: interactive run with approval gates ──
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
