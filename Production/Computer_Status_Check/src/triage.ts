import { daysBetween, parseDate, fmtDate } from "./dates";
import * as jamf from "./jamf";
import type { ParsedIssue, TriageResult } from "./types";

export async function evaluateMultiComputer(issue: ParsedIssue): Promise<TriageResult> {
  if (issue.fields.numberOfComputers < 2) {
    return { step: 1, close: false, reason: "single-device", detail: "1 computer for user — skip multi-device check" };
  }

  const otherDevices = await jamf.listDevicesForUser(issue.fields.serialNumber);
  const other = otherDevices.find(
    (d) => d.serialNumber !== issue.fields.serialNumber
  );
  if (!other) {
    return {
      step: 1,
      close: false,
      reason: "no-other-device",
      detail: `${issue.fields.numberOfComputers} computers listed but no other device found in Jamf`,
    };
  }

  const otherAgeDays = daysBetween(other.lastCheckin, new Date());
  const otherActive = otherAgeDays < 7;
  if (otherActive) {
    return {
      step: 1,
      close: true,
      reason: "other-device-active",
      comment: `✅ 2 computers — ${other.name} last checked in ${fmtDate(other.lastCheckin)}. User likely on new device.`,
      detail: `2 computers — ${other.name} last checkin ${fmtDate(other.lastCheckin)} (${otherAgeDays.toFixed(1)}d ago) → active`,
      data: { otherDeviceName: other.name, otherLastCheckin: other.lastCheckin.toISOString() },
    };
  }

  return {
    step: 1,
    close: false,
    reason: "both-devices-stale",
    detail: `2 computers — ${other.name} last checkin ${fmtDate(other.lastCheckin)} (${otherAgeDays.toFixed(1)}d ago) → both stale`,
    data: { other },
  };
}

// createdAt is the staleness baseline, never new Date()
export function evaluateUptime(issue: ParsedIssue): TriageResult {
  const baseline = issue.createdAt;
  const uptimeDays = issue.fields.uptimeDays;
  const uptimeOk = uptimeDays >= 31;

  const checkinDays = daysBetween(parseDate(issue.fields.lastCheckin), baseline);
  const checkinOk = checkinDays <= 7;

  const inventoryDays = daysBetween(parseDate(issue.fields.lastInventoryUpdate), baseline);
  const inventoryOk = inventoryDays <= 14;

  const checkinDate = issue.fields.lastCheckin.slice(0, 10);
  const inventoryDate = issue.fields.lastInventoryUpdate.slice(0, 10);
  const detail =
    `uptime=${uptimeDays}d (${uptimeOk ? "✓" : "✗"} need≥31) | ` +
    `checkin=${checkinDate} ${checkinDays.toFixed(1)}d before issue (${checkinOk ? "✓" : "✗"} need≤7) | ` +
    `inventory=${inventoryDate} ${inventoryDays.toFixed(1)}d before issue (${inventoryOk ? "✓" : "✗"} need≤14)`;

  if (uptimeOk && checkinOk && inventoryOk) {
    return {
      step: 2,
      close: true,
      reason: "uptime-only",
      comment:
        "✅ Uptime ≥ 30 days — check-in and inventory are current. Superman is scheduled to handle the reboot.",
      detail,
    };
  }
  return { step: 2, close: false, reason: "uptime-conditions-not-met", detail };
}

export async function evaluateSelfResolved(issue: ParsedIssue): Promise<TriageResult> {
  const inventory = await jamf.getComputersInventory(
    `hardware.serialNumber==${issue.fields.serialNumber}`,
    ["GENERAL"]
  );

  if (inventory.totalCount === 0) {
    return { step: 3, close: false, reason: "device-not-found", detail: "device not found in Jamf inventory" };
  }

  const general = inventory.results[0].general;
  const liveCheckin = new Date(general.lastContactTime);
  const liveInventory = new Date(general.reportDate);
  const checkinDaysAgo = daysBetween(liveCheckin, new Date());
  const inventoryDaysAgo = daysBetween(liveInventory, new Date());
  const checkinFresh = checkinDaysAgo < 1;
  const inventoryFresh = inventoryDaysAgo < 1;

  const detail =
    `live checkin=${fmtDate(liveCheckin)} (${checkinFresh ? "fresh ✓" : `${checkinDaysAgo.toFixed(1)}d ago ✗`}) | ` +
    `live inventory=${fmtDate(liveInventory)} (${inventoryFresh ? "fresh ✓" : `${inventoryDaysAgo.toFixed(1)}d ago ✗`})`;

  if (checkinFresh && inventoryFresh) {
    return {
      step: 3,
      close: true,
      reason: "self-resolved",
      comment: [
        "✅ Self-resolved — device is now communicating.",
        `- Last check-in: ${fmtDate(liveCheckin)}`,
        `- Last inventory update: ${fmtDate(liveInventory)}`,
      ].join("\n"),
      detail,
      data: {
        liveLastCheckin: liveCheckin.toISOString(),
        liveLastInventory: liveInventory.toISOString(),
      },
    };
  }

  return {
    step: 3,
    close: false,
    reason: "still-stale",
    detail,
    data: {
      liveLastCheckin: liveCheckin.toISOString(),
      liveLastInventory: liveInventory.toISOString(),
    },
  };
}
