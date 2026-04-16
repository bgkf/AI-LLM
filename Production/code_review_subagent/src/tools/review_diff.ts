import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { execSync } from "child_process";
import * as path from "path";
import { z } from "zod";
import { CHARACTER_LIMIT } from "../constants.js";
import { runCodeReview } from "../services/anthropic.js";
import { formatReviewInline, writeReviewFile } from "../services/formatter.js";

const ReviewDiffInputSchema = z
  .object({
    diff: z
      .string()
      .optional()
      .describe(
        "Raw git diff string to review. If omitted, Claude Code will auto-capture staged changes via `git diff --cached`."
      ),
    base_ref: z
      .string()
      .optional()
      .describe(
        "Git ref to diff against (e.g. 'main', 'HEAD~1'). Used when diff is not provided directly."
      ),
    output_path: z
      .string()
      .default("review.md")
      .describe("Path where the full review.md report will be written (default: review.md)"),
    working_dir: z
      .string()
      .optional()
      .describe(
        "Working directory for the git command. Defaults to the process current working directory."
      ),
  })
  .strict();

function captureDiff(baseRef?: string, workingDir?: string): string {
  const cwd = workingDir ? path.resolve(workingDir) : process.cwd();

  if (baseRef) {
    return execSync(`git diff ${baseRef}`, { cwd, encoding: "utf-8" });
  }

  // Try staged first, fall back to unstaged
  let diff = execSync("git diff --cached", { cwd, encoding: "utf-8" });
  if (!diff.trim()) {
    diff = execSync("git diff", { cwd, encoding: "utf-8" });
  }
  return diff;
}

export function registerReviewDiffTool(server: McpServer): void {
  server.registerTool(
    "review_diff",
    {
      title: "Review Git Diff",
      description: `Review a git diff (staged changes, unstaged changes, or a diff against a base ref).

If no diff string is provided, automatically captures the current git diff:
  1. First tries staged changes (git diff --cached)
  2. Falls back to unstaged changes (git diff)
  3. Or diffs against a base_ref if provided

Returns:
- An inline summary with verdict and top issues printed to Claude Code
- A full detailed review written to a review.md file

The review covers: security vulnerabilities, logic bugs, code style, performance issues, test coverage gaps, and comment quality.

Args:
  - diff (string, optional): Raw git diff text. If omitted, auto-captured.
  - base_ref (string, optional): Git ref to diff against, e.g. "main" or "HEAD~1"
  - output_path (string): Where to write review.md (default: "review.md")
  - working_dir (string, optional): Directory to run git commands in

Returns:
  Inline markdown summary with verdict, issue counts, top issues, and highlights.
  Full report written to output_path.

Examples:
  - Use when: "Review my staged changes" -> (no args needed)
  - Use when: "Review changes vs main" -> base_ref="main"
  - Use when: "Review this diff" + paste diff -> diff="<diff text>"
  - Don't use when: Reviewing a complete file (use review_file instead)

Error handling:
  - Returns "Error: No diff found" if there are no changes to review
  - Returns "Error: Diff too large" if diff exceeds character limit`,
      inputSchema: ReviewDiffInputSchema,
      annotations: {
        readOnlyHint: false, // writes review.md
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ diff, base_ref, output_path, working_dir }) => {
      let diffContent = diff;

      // Auto-capture if not provided
      if (!diffContent) {
        try {
          diffContent = captureDiff(base_ref, working_dir);
        } catch (err) {
          return {
            content: [
              {
                type: "text",
                text: `Error: Failed to capture git diff. Make sure you're in a git repository.\n\nDetails: ${err instanceof Error ? err.message : String(err)}`,
              },
            ],
          };
        }
      }

      if (!diffContent.trim()) {
        return {
          content: [
            {
              type: "text",
              text: "Error: No diff found. There are no staged or unstaged changes to review.",
            },
          ],
        };
      }

      if (diffContent.length > CHARACTER_LIMIT * 4) {
        return {
          content: [
            {
              type: "text",
              text: `Error: Diff too large (${diffContent.length} characters). Maximum is ${CHARACTER_LIMIT * 4}. Consider reviewing individual files with review_file or splitting into smaller commits.`,
            },
          ],
        };
      }

      const result = await runCodeReview(diffContent, "diff");

      // Write full report
      writeReviewFile(result, output_path);

      // Return inline summary
      const inline = formatReviewInline(result);

      return {
        content: [{ type: "text", text: inline }],
        structuredContent: result,
      };
    }
  );
}
