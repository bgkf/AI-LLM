import { query } from "@anthropic-ai/claude-agent-sdk";
import type { CommentContext } from "../types";

const COMMENT_AGENT_PROMPT = `
You write Linear issue comments for MDM remediation outcomes at COMPANY.
You receive a JSON object describing what happened and must output the comment text only.
No preamble. No markdown fences. Output the comment and nothing else.

Rules:
- Include only fields directly relevant to the closing reason.
- Match the case format exactly:
  Case A (self-resolved via blank push): ✅ Self-resolved — blank push restored communication.
  Case C (remediation taken, uncertain): 🔧 Remediation taken — awaiting confirmation.
  Case D (escalation needed): ⚠️ Escalation needed.
- Pending policies: list each as "Policy Name — URL" on its own line.
- Dates: format as YYYY-MM-DD.
- Be concise. One comment, posted once.
`;

export async function composeComment(context: CommentContext): Promise<string> {
  let comment = "";

  for await (const message of query({
    prompt: JSON.stringify(context, null, 2),
    options: {
      allowedTools: [],
      systemPrompt: COMMENT_AGENT_PROMPT,
      model: "claude-haiku-4-5-20251001",
      maxTurns: 1,
    },
  })) {
    if ("result" in message) comment = message.result as string;
  }

  if (!comment) throw new Error("Comment agent returned no result");
  return comment.trim();
}
