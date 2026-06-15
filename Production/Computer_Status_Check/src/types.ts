export interface ParsedIssue {
  linearId: string;
  issueId: string;
  title: string;
  createdAt: Date;
  teamId: string;
  fields: {
    jamfUrl: string;
    taskCreationDate: string;
    computerName: string;
    serialNumber: string;
    lastInventoryUpdate: string;
    lastCheckin: string;
    protectLastCheckin: string;
    supermanStatus: string;
    uptimeDays: number;
    failedCommands: number;
    lastCompletedCommand: string;
    numberOfComputers: number;
    pendingPolicies: string[];
  };
}

export interface TriageResult {
  step: 1 | 2 | 3;
  close: boolean;
  reason: string;
  comment?: string;
  detail?: string;
  data?: Record<string, unknown>;
}

export interface DiagnosticsResult {
  email: string;
  jamfId: number;
  managementId: string;
  liveLastCheckin: Date;
  liveLastInventory: Date;
  pendingCommandCount: number;
  failedCommandCount: number;
  pendingPoliciesResolved: Array<{ id: string; name: string; url: string }>;
  activeFailureModes: Array<"INVENTORY" | "CHECKIN">;
}

export interface OOOResult {
  email: string;
  isOOO: boolean;
  returnDate: Date | null;
  returnDateSource: "slack" | "vacation_responder" | "calendar" | null;
  sourceDetail: string | null;
  suggestedTitlePrefix: string | null;
}

export interface RemediationResult {
  failedCommandsFlushed: number;
  commandsCancelled: number;
  blankPushSent: boolean;
  blankPushRestoredCommunication: boolean;
  frameworkRedeployed: boolean;
}

export type IssueOutcome =
  | { kind: "closed-triage"; step: 1 | 2 | 3; comment: string }
  | { kind: "ooo-open"; titleUpdated: string; dueDate: Date | null }
  | { kind: "self-resolved"; remediation: RemediationResult; comment: string }
  | { kind: "remediation-taken"; remediation: RemediationResult; comment: string }
  | { kind: "escalation"; remediation: RemediationResult; comment: string }
  | { kind: "skipped"; reason: string };

export interface IssueSummaryRow {
  issueId: string;
  title: string;
  outcome: IssueOutcome;
  linearUrl: string;
}

export interface CommentContext {
  outcomeCase: "A" | "C" | "D";
  actionsTaken: string[];
  pendingPolicies: Array<{ name: string; url: string }>;
  liveCheckin?: string;
  liveInventory?: string;
}
