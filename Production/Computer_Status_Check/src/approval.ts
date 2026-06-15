import * as readline from "readline";

export type ApprovalAction =
  | "post-comment"
  | "mark-done"
  | "update-title"
  | "cancel-commands"
  | "flush-commands"
  | "blank-push"
  | "redeploy-framework";

export interface BatchModeConfig {
  autoApprove: ApprovalAction[];
}

export type ApprovalFn = (
  description: string,
  action?: ApprovalAction
) => Promise<"proceed" | "skip" | "stop">;

export function createApprovalFn(batchConfig?: BatchModeConfig): ApprovalFn {
  return async (description: string, action?: ApprovalAction) => {
    if (batchConfig && action && batchConfig.autoApprove.includes(action)) {
      console.log(`  [auto-approved] ${description}`);
      return "proceed";
    }
    return promptUser(description);
  };
}

function promptUser(description: string): Promise<"proceed" | "skip" | "stop"> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(`  ⟩ ${description}\n    [Y]es / [S]kip / [Q]uit: `, (answer) => {
      rl.close();
      const a = answer.trim().toLowerCase();
      if (a === "q" || a === "quit" || a === "stop") resolve("stop");
      else if (a === "s" || a === "skip" || a === "n" || a === "no") resolve("skip");
      else resolve("proceed");
    });
  });
}

export function parseBatchArgs(args: string[]): BatchModeConfig | undefined {
  const idx = args.indexOf("--batch");
  if (idx === -1) return undefined;
  const spec = args[idx + 1];
  if (!spec) {
    return {
      autoApprove: [
        "post-comment",
        "mark-done",
        "update-title",
        "cancel-commands",
        "flush-commands",
        "blank-push",
      ],
    };
  }
  const actions = spec.split(",").map((s) => s.trim()) as ApprovalAction[];
  return { autoApprove: actions };
}
