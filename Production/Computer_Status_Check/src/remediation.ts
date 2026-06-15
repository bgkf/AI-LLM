import { daysBetween, fmtDate, sleep } from "./dates";
import * as jamf from "./jamf";
import * as linear from "./linear";
import type {
  ParsedIssue,
  DiagnosticsResult,
  RemediationResult,
  CommentContext,
} from "./types";
import type { ApprovalFn } from "./approval";
import { composeComment } from "./agents/commentAgent";

export async function runRemediation(
  issue: ParsedIssue,
  diagnostics: DiagnosticsResult,
  approval: ApprovalFn
): Promise<RemediationResult> {
  const result: RemediationResult = {
    failedCommandsFlushed: 0,
    commandsCancelled: 0,
    blankPushSent: false,
    blankPushRestoredCommunication: false,
    frameworkRedeployed: false,
  };

  // 6a — flush failed commands
  if (diagnostics.failedCommandCount > 0) {
    const decision = await approval(
      `Clear ${diagnostics.failedCommandCount} failed MDM commands on ${issue.fields.computerName}?`,
      "flush-commands"
    );
    if (decision === "stop") throw new StopRunError();
    if (decision === "proceed") {
      await jamf.flushFailedCommands(diagnostics.jamfId);
      result.failedCommandsFlushed = diagnostics.failedCommandCount;
      await linear.postComment(
        issue.linearId,
        `${diagnostics.failedCommandCount} failed command${diagnostics.failedCommandCount === 1 ? "" : "s"} cleared`
      );
    }
  }

  // 6b — cancel pending commands
  if (diagnostics.pendingCommandCount > 0) {
    const decision = await approval(
      `Cancel ${diagnostics.pendingCommandCount} pending MDM commands on ${issue.fields.computerName}?`,
      "cancel-commands"
    );
    if (decision === "stop") throw new StopRunError();
    if (decision === "proceed") {
      result.commandsCancelled = await jamf.cancelPendingCommands(diagnostics.jamfId);
    }
  }

  // 6c — blank push
  const blankPushDecision = await approval(
    `Send blank push to ${issue.fields.computerName}? ` +
      `(live checkin: ${fmtDate(diagnostics.liveLastCheckin)}, live inventory: ${fmtDate(diagnostics.liveLastInventory)})`,
    "blank-push"
  );
  if (blankPushDecision === "stop") throw new StopRunError();
  if (blankPushDecision === "proceed") {
    await jamf.sendBlankPush(diagnostics.managementId);
    result.blankPushSent = true;

    console.log("  Waiting 2 minutes for device to respond...");
    await sleep(2 * 60 * 1000);

    const live = await jamf.recheckDevice(diagnostics.jamfId);
    result.blankPushRestoredCommunication =
      daysBetween(live.lastCheckin, new Date()) < 1 &&
      daysBetween(live.lastInventory, new Date()) < 1;

    if (result.blankPushRestoredCommunication) return result;
  }

  // 6d — redeploy framework (last resort)
  const redeployDecision = await approval(
    `Redeploy Jamf management framework on ${issue.fields.computerName}? (last resort)`,
    "redeploy-framework"
  );
  if (redeployDecision === "stop") throw new StopRunError();
  if (redeployDecision === "proceed") {
    await jamf.redeployFramework(diagnostics.jamfId);
    result.frameworkRedeployed = true;
  }

  return result;
}

export function determineOutcomeCase(
  result: RemediationResult
): "A" | "C" | "D" {
  if (result.blankPushRestoredCommunication) return "A";
  if (result.frameworkRedeployed) return "D";
  return "C";
}

export function buildCommentContext(
  result: RemediationResult,
  diagnostics: DiagnosticsResult,
  outcomeCase: "A" | "C" | "D"
): CommentContext {
  const actionsTaken: string[] = [];
  if (result.failedCommandsFlushed > 0)
    actionsTaken.push(`Cleared ${result.failedCommandsFlushed} failed commands`);
  if (result.commandsCancelled > 0)
    actionsTaken.push(`Cancelled ${result.commandsCancelled} pending commands`);
  if (result.blankPushSent) actionsTaken.push("Sent blank push");
  if (result.frameworkRedeployed)
    actionsTaken.push("Redeployed management framework");

  const ctx: CommentContext = {
    outcomeCase,
    actionsTaken,
    pendingPolicies: diagnostics.pendingPoliciesResolved.map((p) => ({
      name: p.name,
      url: p.url,
    })),
  };

  if (outcomeCase === "A") {
    ctx.liveCheckin = fmtDate(diagnostics.liveLastCheckin);
    ctx.liveInventory = fmtDate(diagnostics.liveLastInventory);
  }

  return ctx;
}

export async function composeAndPostComment(
  issue: ParsedIssue,
  result: RemediationResult,
  diagnostics: DiagnosticsResult,
  approval: ApprovalFn
): Promise<{ comment: string; outcomeCase: "A" | "C" | "D" }> {
  const outcomeCase = determineOutcomeCase(result);
  const context = buildCommentContext(result, diagnostics, outcomeCase);

  const comment = await composeComment(context);
  console.log(`\n  Draft comment:\n  ${comment.replace(/\n/g, "\n  ")}\n`);

  const decision = await approval("Post this comment to Linear?", "post-comment");
  if (decision === "stop") throw new StopRunError();
  if (decision === "proceed") {
    await linear.postComment(issue.linearId, comment);

    const finalStatus =
      outcomeCase === "A" ? "Done" : outcomeCase === "D" ? "Todo" : "In Progress";
    await linear.setStatus(issue.linearId, issue.teamId, finalStatus);
  }

  return { comment, outcomeCase };
}

export class StopRunError extends Error {
  constructor() {
    super("Run stopped by operator");
    this.name = "StopRunError";
  }
}
