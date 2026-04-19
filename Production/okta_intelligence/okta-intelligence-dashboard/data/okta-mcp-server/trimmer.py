"""
data/okta-mcp-server/trimmer.py

Shared field-trimming logic for Okta API responses.
Each tool specifies which fields to keep; the trimmer strips everything else.
The queried-field extractor appends any filter field to the keep-list.
"""

import re
from typing import Any


# ---------------------------------------------------------------------------
# Base keep-lists per tool
# ---------------------------------------------------------------------------

KEEP_FIELDS: dict[str, list[str]] = {
    "list_users":                  ["displayName", "email", "status", "lastLogin"],
    "get_group":                   ["displayName", "email", "status", "lastLogin"],
    "list_apps":                   ["label", "status", "signOnMode", "assignedUserCount"],
    "get_policy":                  ["name", "status", "type", "conditions", "rules"],
    "list_devices":                ["id", "status", "profile.displayName", "profile.platform", "profile.manufacturer", "profile.model", "profile.osVersion", "profile.serialNumber", "lastUpdated"],
    "get_device_users":            ["id", "profile.displayName", "profile.email", "profile.login", "status", "managementStatus", "screenLockType"],
    "list_iam_roles":              ["id", "label", "type", "status", "description", "created", "lastUpdated"],
    "list_iam_resource_sets":      ["id", "label", "description", "created", "lastUpdated"],
    "list_oauth_clients":          ["client_id", "client_name", "client_uri", "application_type", "grant_types", "redirect_uris", "response_types", "token_endpoint_auth_method", "created_at"],
    "get_user_sessions":           ["id", "status", "createdAt", "expiresAt", "lastPasswordVerification", "lastFactorVerification", "amr", "idp.type", "mfaActive"],
    "get_user_factors":            ["id", "factorType", "provider", "status", "created", "lastUpdated", "profile.credentialId", "profile.deviceType", "profile.name", "vendorName"],
    "list_entitlements":           ["id", "name", "description", "status", "resource.id", "resource.name", "resource.type", "created", "lastUpdated"],
    "list_grants":                 ["id", "status", "principal.id", "principal.displayName", "principal.type", "entitlement.id", "entitlement.name", "resource.name", "created", "expiresAt"],
    "get_principal_access":        ["resource.id", "resource.name", "resource.type", "entitlement.id", "entitlement.name", "grant.status", "grant.created", "grant.expiresAt"],
    "list_principal_entitlements": ["entitlement.id", "entitlement.name", "entitlement.status", "resource.name", "grant.status", "grant.created"],
    "get_entitlement_history":     ["id", "action", "principal.id", "principal.displayName", "entitlement.id", "entitlement.name", "resource.name", "actor.displayName", "timestamp"],
    "list_access_reviews":         ["id", "name", "status", "reviewer.displayName", "reviewer.email", "campaign.name", "created", "dueDate", "completedDate"],
    "get_access_review_detail":    ["id", "status", "principal.displayName", "principal.email", "resource.name", "resource.type", "decision", "reviewer.displayName", "anomalyCount", "lastUpdated"],
    "get_group_skinny":            ["id", "profile.displayName", "profile.email", "profile.login", "status"],
    "get_app_users_skinny":        ["id", "profile.displayName", "profile.email", "profile.login", "status"],
}

# Audit log tools — never trimmed
UNTRIMMED_TOOLS = {"get_audit_logs", "search_events"}


# ---------------------------------------------------------------------------
# Queried-field extractor
# ---------------------------------------------------------------------------

def extract_queried_fields(filter_str: str | None, search_str: str | None) -> list[str]:
    """
    Pull field names from Okta filter/search expressions so they can be
    added to the keep-list.

    Examples:
      filter=profile.countryCode eq "CA"  →  ["countryCode"]
      search=profile.department eq "Eng"  →  ["department"]
    """
    fields: list[str] = []
    combined = " ".join(filter(None, [filter_str, search_str]))
    if not combined:
        return fields

    # Match profile.fieldName or top-level fieldName before comparison operators
    pattern = re.compile(r'(?:profile\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s+(?:eq|ne|gt|lt|ge|le|sw|co|pr)', re.I)
    for match in pattern.finditer(combined):
        field = match.group(1)
        if field not in fields:
            fields.append(field)

    return fields


# ---------------------------------------------------------------------------
# Trim a single user/member record
# ---------------------------------------------------------------------------

def trim_user(record: dict[str, Any], extra_fields: list[str] | None = None) -> dict[str, Any]:
    keep = {"displayName", "email", "status", "lastLogin"} | set(extra_fields or [])
    profile = record.get("profile", {})

    result: dict[str, Any] = {}

    # Flatten common profile fields into the top level
    for field in keep:
        if field in record:
            result[field] = record[field]
        elif field in profile:
            result[field] = profile[field]

    # Ensure displayName and email always resolve
    if "displayName" not in result:
        result["displayName"] = profile.get("displayName") or profile.get("login") or "—"
    if "email" not in result:
        result["email"] = profile.get("email") or profile.get("login") or "—"
    if "status" not in result:
        result["status"] = record.get("status", "—")
    if "lastLogin" not in result:
        result["lastLogin"] = record.get("lastLogin")

    return result


# ---------------------------------------------------------------------------
# Trim an app record
# ---------------------------------------------------------------------------

def trim_app(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "label":             record.get("label", "—"),
        "status":            record.get("status", "—"),
        "signOnMode":        record.get("signOnMode", "—"),
        "assignedUserCount": record.get("assignedUserCount"),
    }


# ---------------------------------------------------------------------------
# Trim a policy record
# ---------------------------------------------------------------------------

def trim_policy(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "name":       record.get("name", "—"),
        "status":     record.get("status", "—"),
        "type":       record.get("type", "—"),
        "conditions": record.get("conditions"),
        "rules":      record.get("rules"),
    }


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def trim_records(
    tool_name: str,
    records: list[dict[str, Any]],
    filter_str: str | None = None,
    search_str: str | None = None,
) -> list[dict[str, Any]]:
    """Apply the appropriate trimmer for the given tool."""
    if tool_name in UNTRIMMED_TOOLS:
        return records

    extra = extract_queried_fields(filter_str, search_str)

    if tool_name in ("list_users", "get_group"):
        return [trim_user(r, extra) for r in records]
    elif tool_name == "list_apps":
        return [trim_app(r) for r in records]
    elif tool_name == "get_policy":
        return [trim_policy(r) for r in records]
    else:
        return records
