import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import * as fs from "fs";
import * as path from "path";
import { z } from "zod";
import { CHARACTER_LIMIT } from "../constants.js";
import { runCodeReview } from "../services/anthropic.js";
import { formatReviewInline, writeReviewFile } from "../services/formatter.js";

const ReviewFileInputSchema = z
  .object({
    file_path: z
      .string()
      .min(1, "file_path is required")
      .describe("Absolute or relative path to the source file to review"),
    output_path: z
      .string()
      .default("review.md")
      .describe(
        "Path where the full review.md report will be written (default: review.md in current directory)"
      ),
  })
  .strict();

export function registerReviewFileTool(server: McpServer): void {
  server.registerTool(
    "review_file",
    {
      title: "Review Source File",
      description: `Review a complete source code file and return a structured code review.

Reads the file at the given path, sends it to Claude for analysis, and returns:
- An inline summary with verdict and top issues printed to Claude Code
- A full detailed review written to a \`review.md\` file

The review covers: security vulnerabilities, logic bugs, code style, performance issues, test coverage gaps, and comment quality.

Args:
  - file_path (string): Absolute or relative path to the source file
  - output_path (string): Where to write review.md (default: "review.md")

Returns:
  Inline markdown summary with verdict (APPROVE | REQUEST_CHANGES | NEEDS_DISCUSSION),
  issue counts by severity, top critical/high issues, and positive highlights.
  Full report written to output_path.

Examples:
  - Use when: "Review src/auth.ts" -> file_path="src/auth.ts"
  - Use when: "Check this file for security issues" -> file_path="<path>"
  - Don't use when: You only have a diff (use review_diff instead)

Error handling:
  - Returns "Error: File not found" if path does not exist
  - Returns "Error: File too large" if file exceeds 100,000 characters`,
      inputSchema: ReviewFileInputSchema,
      annotations: {
        readOnlyHint: false, // writes review.md
        destructiveHint: false,
        idempotentHint: true,
        openWorldHint: false,
      },
    },
    async ({ file_path, output_path }) => {
      // Resolve path
      const resolved = path.resolve(file_path);

      if (!fs.existsSync(resolved)) {
        return {
          content: [
            {
              type: "text",
              text: `Error: File not found at path: ${resolved}`,
            },
          ],
        };
      }

      const code = fs.readFileSync(resolved, "utf-8");

      if (code.length > CHARACTER_LIMIT * 4) {
        return {
          content: [
            {
              type: "text",
              text: `Error: File too large (${code.length} characters). Maximum supported size is ${CHARACTER_LIMIT * 4} characters. Consider reviewing specific sections or using review_diff instead.`,
            },
          ],
        };
      }

      const result = await runCodeReview(code, "file", file_path);

      // Write full report to file
      writeReviewFile(result, output_path, file_path);

      // Return inline summary
      const inline = formatReviewInline(result, file_path);

      return {
        content: [{ type: "text", text: inline }],
        structuredContent: result,
      };
    }
  );
}
