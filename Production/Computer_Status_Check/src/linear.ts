import type { ParsedIssue } from "./types";

const LINEAR_API_URL = "https://api.linear.app/graphql";

function getApiKey(): string {
  const key = process.env.LINEAR_API_KEY;
  if (!key) throw new Error("LINEAR_API_KEY is not set. Add it to .env");
  return key;
}

async function gql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const res = await fetch(LINEAR_API_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: getApiKey(),
    },
    body: JSON.stringify({ query, variables }),
  });
  if (!res.ok) throw new Error(`Linear API ${res.status}: ${await res.text()}`);
  const json = (await res.json()) as { data?: T; errors?: Array<{ message: string }> };
  if (json.errors?.length) throw new Error(`Linear GraphQL: ${json.errors[0].message}`);
  return json.data!;
}

const LIST_ISSUES_QUERY = `
  query($after: String) {
    issues(
      filter: {
        project: { name: { eq: "🪨 Jamf Change Log" } }
        state: { name: { eq: "Todo" } }
      }
      first: 100
      after: $after
    ) {
      nodes {
        id
        identifier
        title
        description
        createdAt
        team { id }
        url
      }
      pageInfo { hasNextPage endCursor }
    }
  }
`;

interface LinearIssueNode {
  id: string;
  identifier: string;
  title: string;
  description: string | null;
  createdAt: string;
  team: { id: string };
  url: string;
}

interface ListIssuesResponse {
  issues: {
    nodes: LinearIssueNode[];
    pageInfo: { hasNextPage: boolean; endCursor: string | null };
  };
}

export async function fetchQualifyingIssues(): Promise<ParsedIssue[]> {
  const allNodes: LinearIssueNode[] = [];
  let after: string | null = null;

  do {
    const data: ListIssuesResponse = await gql<ListIssuesResponse>(LIST_ISSUES_QUERY, { after });
    allNodes.push(...data.issues.nodes);
    after = data.issues.pageInfo.hasNextPage ? data.issues.pageInfo.endCursor : null;
  } while (after);

  return allNodes
    .filter(
      (n) =>
        n.title.startsWith("COMPANY-") && n.title.includes("Computer Status Check")
    )
    .map((n) => ({
      linearId: n.id,
      issueId: n.identifier,
      title: n.title,
      createdAt: new Date(n.createdAt),
      teamId: n.team.id,
      fields: parseDescriptionFields(n.description ?? ""),
    }));
}

function normalizeDateString(s: string): string {
  if (!s) return s;
  // "2026-06-05 14:06 pm EDT" → "2026-06-05T14:06:00"
  const m = s.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{1,2}:\d{2})(?:\s+(?:am|pm))?(?:\s+\w+)?$/i);
  if (m) return `${m[1]}T${m[2]}:00`;
  return s;
}

function parseDescriptionFields(description: string): ParsedIssue["fields"] {
  const lines = description.split("\n").filter((l) => l.trim());
  const map = new Map<string, string>();

  for (const line of lines) {
    // New format: " 1. LABEL:: value" or "10. LABEL:: value"
    const newMatch = line.match(/^\s*\d+\.\s+(.+?)::\s*(.*)$/);
    if (newMatch) {
      map.set(newMatch[1].trim().toUpperCase(), newMatch[2].trim());
      continue;
    }
    // Old format: "Label: value"
    const oldMatch = line.match(/^([A-Za-z][A-Za-z 0-9\-]+?):\s*(.*)$/);
    if (oldMatch) {
      map.set(oldMatch[1].trim().toUpperCase(), oldMatch[2].trim());
    }
  }

  const get = (newLabel: string, oldLabel?: string): string =>
    map.get(newLabel.toUpperCase()) ?? (oldLabel ? map.get(oldLabel.toUpperCase()) ?? "" : "");

  // COMPUTER NAME may be a markdown link: [name](<url>)
  const rawComputerName = get("COMPUTER NAME", "Computer Name");
  const computerName = rawComputerName.replace(/^\[(.+?)\]\(.*?\)$/, "$1");

  // Extract Jamf URL from COMPUTER NAME link if present, else fall back to old field
  const jamfUrlMatch = rawComputerName.match(/\(<?(https?:\/\/[^>)]+)>?\)/);
  const jamfUrl = jamfUrlMatch ? jamfUrlMatch[1] : get("Jamf URL");

  // UPTIME: "0 days" → 0
  const uptimeRaw = get("UPTIME", "Uptime Days");
  const uptimeDays = parseInt(uptimeRaw, 10) || 0;

  // PENDING POLICIES: semicolon-separated in new format, comma-separated in old
  const pendingRaw = get("PENDING POLICIES", "Pending Policies");
  const pendingPolicies = pendingRaw
    ? pendingRaw.split(/[;,]/).map((s) => s.trim()).filter(Boolean)
    : [];

  return {
    jamfUrl,
    taskCreationDate: get("Task Creation Date"),
    computerName,
    serialNumber: get("SERIAL NUMBER", "Serial Number"),
    lastInventoryUpdate: normalizeDateString(get("LAST INVENTORY UPDATE", "Last Inventory Update")),
    lastCheckin: normalizeDateString(get("LAST CHECKIN", "Last Check-in")),
    protectLastCheckin: normalizeDateString(get("JAMF PROTECT LAST CHECK-IN", "Protect Last Check-in")),
    supermanStatus: get("SUPER STATUS", "Superman Status"),
    uptimeDays,
    failedCommands: parseInt(get("FAILED COMMANDS", "Failed Commands"), 10) || 0,
    lastCompletedCommand: normalizeDateString(get("MOST RECENT COMPLETED COMMAND", "Last Completed Command")),
    numberOfComputers: parseInt(get("NUMBER OF COMPUTERS FOR JAMF USER", "Number of Computers"), 10) || 1,
    pendingPolicies,
  };
}

const GET_ISSUE_QUERY = `
  query($identifier: String!) {
    issueVcsBranchSearch(branchName: $identifier) {
      id
      identifier
      title
      description
      createdAt
      team { id }
      url
    }
  }
`;

const GET_ISSUE_BY_ID_QUERY = `
  query($id: String!) {
    issue(id: $id) {
      id
      identifier
      title
      description
      createdAt
      team { id }
      url
    }
  }
`;

export async function fetchIssueByIdentifier(identifier: string): Promise<ParsedIssue> {
  // Linear's GraphQL uses the `issue` query with the identifier directly
  const data = await gql<{ issue: LinearIssueNode }>(
    `query($id: String!) {
      issue(id: $id) {
        id
        identifier
        title
        description
        createdAt
        team { id }
        url
      }
    }`,
    { id: identifier }
  );

  const n = data.issue;
  if (!n) throw new Error(`Issue "${identifier}" not found`);

  return {
    linearId: n.id,
    issueId: n.identifier,
    title: n.title,
    createdAt: new Date(n.createdAt),
    teamId: n.team.id,
    fields: parseDescriptionFields(n.description ?? ""),
  };
}

export async function postComment(issueId: string, body: string): Promise<void> {
  await gql(
    `mutation($issueId: String!, $body: String!) {
      commentCreate(input: { issueId: $issueId, body: $body }) {
        success
      }
    }`,
    { issueId, body }
  );
}

export async function updateIssue(
  linearId: string,
  updates: { title?: string; dueDate?: string; stateId?: string }
): Promise<void> {
  const input: Record<string, unknown> = {};
  if (updates.title !== undefined) input.title = updates.title;
  if (updates.dueDate !== undefined) input.dueDate = updates.dueDate;
  if (updates.stateId !== undefined) input.stateId = updates.stateId;

  await gql(
    `mutation($id: String!, $input: IssueUpdateInput!) {
      issueUpdate(id: $id, input: $input) {
        success
      }
    }`,
    { id: linearId, input }
  );
}

async function resolveStateId(teamId: string, stateName: string): Promise<string> {
  const data = await gql<{
    workflowStates: { nodes: Array<{ id: string; name: string }> };
  }>(
    `query($teamId: ID!) {
      workflowStates(filter: { team: { id: { eq: $teamId } } }) {
        nodes { id name }
      }
    }`,
    { teamId }
  );
  const state = data.workflowStates.nodes.find((s) => s.name === stateName);
  if (!state) throw new Error(`State "${stateName}" not found for team ${teamId}`);
  return state.id;
}

export async function markDone(linearId: string, teamId: string): Promise<void> {
  const stateId = await resolveStateId(teamId, "Done");
  await updateIssue(linearId, { stateId });
}

export async function setStatus(
  linearId: string,
  teamId: string,
  statusName: string
): Promise<void> {
  const stateId = await resolveStateId(teamId, statusName);
  await updateIssue(linearId, { stateId });
}
