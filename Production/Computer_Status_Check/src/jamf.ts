import { daysBetween, parseDate } from "./dates";
import type { ParsedIssue, DiagnosticsResult } from "./types";

function getConfig() {
  const url = process.env.JAMF_URL;
  const clientId = process.env.JAMF_CLIENT_ID;
  const clientSecret = process.env.JAMF_CLIENT_SECRET;
  if (!url || !clientId || !clientSecret) {
    throw new Error("JAMF_URL, JAMF_CLIENT_ID, and JAMF_CLIENT_SECRET must be set in .env");
  }
  return { url: url.replace(/\/$/, ""), clientId, clientSecret };
}

let cachedToken: { token: string; expiresAt: number } | null = null;

async function getAuthToken(): Promise<string> {
  if (cachedToken && Date.now() < cachedToken.expiresAt - 30_000) {
    return cachedToken.token;
  }
  const { url, clientId, clientSecret } = getConfig();
  const res = await fetch(`${url}/api/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `client_id=${encodeURIComponent(clientId)}&client_secret=${encodeURIComponent(clientSecret)}&grant_type=client_credentials`,
  });
  if (!res.ok) throw new Error(`Jamf auth failed ${res.status}: ${await res.text()}`);
  const json = (await res.json()) as { access_token: string; expires_in: number };
  cachedToken = {
    token: json.access_token,
    expiresAt: Date.now() + json.expires_in * 1000,
  };
  return cachedToken.token;
}

async function jamfApi(path: string, options: RequestInit = {}): Promise<unknown> {
  const { url } = getConfig();
  const token = await getAuthToken();
  const res = await fetch(`${url}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...((options.headers as Record<string, string>) ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Jamf API ${options.method ?? "GET"} ${path} → ${res.status}: ${body}`);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

// --- Read operations ---

interface InventoryResponse {
  totalCount: number;
  results: Array<{
    id: string;
    general: {
      lastContactTime: string;
      reportDate: string;
      managementId: string;
    };
    userAndLocation?: {
      email: string;
    };
  }>;
}

export async function getComputersInventory(
  filter: string,
  sections: string[]
): Promise<InventoryResponse> {
  const sectionParams = sections.map((s) => `section=${s}`).join("&");
  const path = `/api/v1/computers-inventory?${sectionParams}&filter=${encodeURIComponent(filter)}&page-size=1`;
  return (await jamfApi(path)) as InventoryResponse;
}

interface DeviceDetail {
  pendingCommandCount: number;
  failedCommandCount: number;
  pendingPolicyNames?: Record<string, string>;
}

export async function getComputerDetail(jamfId: number): Promise<DeviceDetail> {
  const data = (await jamfApi(`/api/v1/computers-inventory-detail/${jamfId}`)) as Record<string, unknown>;

  const mgmt = (data.management as Record<string, unknown>) ?? {};
  const commands = (mgmt.managementCommands as Record<string, unknown>) ?? {};

  return {
    pendingCommandCount: (commands.pendingCount as number) ?? 0,
    failedCommandCount: (commands.failedCount as number) ?? 0,
    pendingPolicyNames: (data.pendingPolicyNames as Record<string, string>) ?? undefined,
  };
}

interface UserDevice {
  serialNumber: string;
  name: string;
  lastCheckin: Date;
}

export async function listDevicesForUser(serialNumber: string): Promise<UserDevice[]> {
  const anchor = await getComputersInventory(
    `hardware.serialNumber==${serialNumber}`,
    ["USER_AND_LOCATION"]
  );
  if (anchor.totalCount === 0) return [];
  const email = anchor.results[0].userAndLocation?.email;
  if (!email) return [];

  const allDevices = (await jamfApi(
    `/api/v1/computers-inventory?section=GENERAL&section=HARDWARE&filter=${encodeURIComponent(`userAndLocation.email==${email}`)}&page-size=50`
  )) as InventoryResponse;

  return allDevices.results.map((r) => ({
    serialNumber: (r as Record<string, unknown> as { hardware?: { serialNumber?: string } }).hardware?.serialNumber ?? "",
    name: ((r as Record<string, unknown>).general as Record<string, unknown>)?.name as string ?? "",
    lastCheckin: new Date(r.general.lastContactTime),
  }));
}

// --- Diagnostics ---

export async function gatherDiagnostics(issue: ParsedIssue): Promise<DiagnosticsResult> {
  const inventory = await getComputersInventory(
    `hardware.serialNumber==${issue.fields.serialNumber}`,
    ["GENERAL", "USER_AND_LOCATION"]
  );

  if (inventory.totalCount === 0) {
    throw new Error(`No device found for serial ${issue.fields.serialNumber}`);
  }

  const result = inventory.results[0];
  const jamfId = parseInt(result.id, 10);
  const email = result.userAndLocation?.email;
  if (!email) {
    throw new Error(`No email in USER_AND_LOCATION for serial ${issue.fields.serialNumber}`);
  }

  const deviceDetail = await getComputerDetail(jamfId);

  const pendingPoliciesResolved = issue.fields.pendingPolicies.map((id) => ({
    id,
    name: deviceDetail.pendingPolicyNames?.[id] ?? `Policy ${id}`,
    url: `${getConfig().url}/policies.html?id=${id}&o=r`,
  }));

  const activeFailureModes: Array<"INVENTORY" | "CHECKIN"> = [];
  if (daysBetween(parseDate(issue.fields.lastInventoryUpdate), issue.createdAt) > 14)
    activeFailureModes.push("INVENTORY");
  if (daysBetween(parseDate(issue.fields.lastCheckin), issue.createdAt) > 7)
    activeFailureModes.push("CHECKIN");

  return {
    email,
    jamfId,
    managementId: result.general.managementId,
    liveLastCheckin: new Date(result.general.lastContactTime),
    liveLastInventory: new Date(result.general.reportDate),
    pendingCommandCount: deviceDetail.pendingCommandCount,
    failedCommandCount: deviceDetail.failedCommandCount,
    pendingPoliciesResolved,
    activeFailureModes,
  };
}

// --- MDM operations ---

export async function flushFailedCommands(jamfId: number): Promise<void> {
  await jamfApi(`/JSSResource/commandflush/computers/id/${jamfId}/status/Failed`, {
    method: "DELETE",
  });
}

export async function cancelPendingCommands(jamfId: number): Promise<number> {
  await jamfApi(`/JSSResource/commandflush/computers/id/${jamfId}/status/Pending`, {
    method: "DELETE",
  });
  return 0; // classic API does not return a count
}

export async function sendBlankPush(managementId: string): Promise<void> {
  await jamfApi("/api/preview/mdm/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      clientData: [{ managementId }],
      commandData: { commandType: "BLANK_PUSH" },
    }),
  });
}

export async function redeployFramework(jamfId: number): Promise<void> {
  await jamfApi(`/api/v1/jamf-management-framework/redeploy/${jamfId}`, {
    method: "POST",
  });
}

// --- Re-check after blank push ---

export async function recheckDevice(jamfId: number): Promise<{ lastCheckin: Date; lastInventory: Date }> {
  const data = await getComputersInventory(`id==${jamfId}`, ["GENERAL"]);
  const general = data.results[0]?.general;
  if (!general) throw new Error(`Device ${jamfId} not found on re-check`);
  return {
    lastCheckin: new Date(general.lastContactTime),
    lastInventory: new Date(general.reportDate),
  };
}
