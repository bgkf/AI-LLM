import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { registerReviewDiffTool } from "./tools/review_diff.js";
import { registerReviewFileTool } from "./tools/review_file.js";

const server = new McpServer({
  name: "code-review-mcp-server",
  version: "1.0.0",
});

// Register all tools
registerReviewFileTool(server);
registerReviewDiffTool(server);

async function runStdio(): Promise<void> {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("Code Review MCP server running on stdio");
}

runStdio().catch((error) => {
  console.error("Server error:", error);
  process.exit(1);
});
