import Anthropic from "@anthropic-ai/sdk";
import { REVIEW_SYSTEM_PROMPT } from "../constants.js";
import { ReviewResult } from "../types.js";

const client = new Anthropic();

export async function runCodeReview(
  code: string,
  mode: "file" | "diff",
  filePath?: string
): Promise<ReviewResult> {
  const contextLabel = filePath ? `File: ${filePath}` : "Code snippet";
  const modeLabel = mode === "diff" ? "git diff" : "full file";

  const userMessage = `Please review the following ${modeLabel}.

${contextLabel}

\`\`\`
${code}
\`\`\`

Return ONLY the JSON review object described in your instructions. No markdown, no extra text.`;

  const response = await client.messages.create({
    model: "claude-opus-4-5",
    max_tokens: 4096,
    system: REVIEW_SYSTEM_PROMPT,
    messages: [{ role: "user", content: userMessage }],
  });

  const text = response.content
    .filter((block) => block.type === "text")
    .map((block) => (block as { type: "text"; text: string }).text)
    .join("");

  // Strip any accidental markdown fences
  const clean = text.replace(/^```(?:json)?\n?/m, "").replace(/\n?```$/m, "").trim();

  try {
    return JSON.parse(clean) as ReviewResult;
  } catch {
    throw new Error(`Failed to parse review response as JSON.\n\nRaw response:\n${text}`);
  }
}
