"""
tools/jamf_tools.py
--------------------
LangChain tools for interacting with the Jamf Pro API.
All write actions (send_blank_push, run_jamf_policy, redeploy_jamf_framework)
check the DRY_RUN env var and no-op if set to 'true'.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

JAMF_URL = os.environ.get("JAMF_URL", "https://acme.jamfcloud.com")
JAMF_CLIENT_ID = os.environ.get("JAMF_CLIENT_ID", "")
JAMF_CLIENT_SECRET = os.environ.get("JAMF_CLIENT_SECRET", "")
OKTA_REDEPLOY_WORKFLOW_URL = os.environ.get("OKTA_REDEPLOY_WORKFLOW_URL", "")
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() == "true"


# ── Auth ──────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_jamf_token() -> str:
    """Obtain a short-lived Jamf Pro API bearer token via OAuth2 client credentials."""
    resp = httpx.post(
        f"{JAMF_URL}/api/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": JAMF_CLIENT_ID,
            "client_secret": JAMF_CLIENT_SECRET,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _jamf_headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_jamf_token()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _jamf_get(path: str, **kwargs) -> dict:
    resp = httpx.get(f"{JAMF_URL}{path}", headers=_jamf_headers(), timeout=15, **kwargs)
    resp.raise_for_status()
    return resp.json()


def _jamf_post(path: str, json: dict | None = None, **kwargs) -> dict:
    resp = httpx.post(
        f"{JAMF_URL}{path}",
        headers=_jamf_headers(),
        json=json,
        timeout=15,
        **kwargs,
    )
    resp.raise_for_status()
    return resp.json() if resp.content else {}


# ── Tools ─────────────────────────────────────────────────────────────────────

@tool
def get_jamf_computer(serial_number: str) -> dict:
    """
    Fetch a computer's Jamf Pro inventory record by serial number.

    Returns a dict with:
      jamf_id, computer_name, serial_number,
      last_inventory_update, last_check_in,
      mdm_profile_expiry, os_version,
      pending_commands (list), failed_commands (list),
      management_id, jamf_url

    Args:
        serial_number: The device serial number (e.g. 'K56FLQ04VV').
    """
    try:
        result = _jamf_get(
            "/api/v1/computers-preview",
            params={"filter": f"hardware.serialNumber=={serial_number}"},
        )
        computers = result.get("results", [])
        if not computers:
            return {"error": f"No computer found with serial {serial_number}"}

        computer = computers[0]
        jamf_id = computer["id"]

        detail = _jamf_get(f"/api/v1/computers/{jamf_id}/details")
        mgmt = detail.get("general", {})
        hw = detail.get("hardware", {})

        commands = _jamf_get(f"/api/v1/computers/{jamf_id}/management/commands")

        return {
            "jamf_id": jamf_id,
            "computer_name": mgmt.get("name", ""),
            "serial_number": serial_number,
            "jamf_url": f"{JAMF_URL}/computers.html?id={jamf_id}&o=r",
            "management_id": mgmt.get("managementId", ""),
            "last_inventory_update": mgmt.get("lastInventoryUpdate"),
            "last_check_in": mgmt.get("lastContactTime"),
            "mdm_profile_expiry": mgmt.get("mdmProfileExpiration"),
            "os_version": hw.get("osVersion", ""),
            "pending_commands": commands.get("pending", []),
            "failed_commands": commands.get("failed", []),
        }
    except Exception as e:
        logger.error("get_jamf_computer failed for %s: %s", serial_number, e)
        return {"error": str(e)}


@tool
def get_user_email(serial_number: str) -> dict:
    """
    Look up the assigned user's email address from Jamf Pro for a given device.

    Queries the computer record to find the Jamf username, then resolves the
    user record to get the authoritative email address. This email should be
    used for all downstream lookups (GAM, Slack, Okta) instead of deriving
    the email from the computer name.

    Args:
        serial_number: The device serial number (e.g. 'HM96TH7NYK').

    Returns:
        A dict with:
          email (str): The user's email from Jamf.
          full_name (str): The user's full name.
          jamf_username (str): The Jamf username.
          position (str): The user's job title.
          error (str | None): Set if lookup failed.
    """
    try:
        # Step 1: Find the computer by serial to get the Jamf username
        result = _jamf_get(
            "/api/v1/computers-preview",
            params={"filter": f"hardware.serialNumber=={serial_number}"},
        )
        computers = result.get("results", [])
        if not computers:
            return {"error": f"No computer found with serial {serial_number}"}

        computer = computers[0]
        jamf_id = computer["id"]

        # Step 2: Get the userAndLocation section from the computer inventory
        detail = _jamf_get(f"/JSSResource/computers/id/{jamf_id}")
        user_location = detail.get("computer", {}).get("location", {})
        email = user_location.get("email_address", "").strip()
        username = user_location.get("username", "").strip()
        full_name = (
            f"{user_location.get('real_name', '')}".strip()
            or user_location.get("realname", "").strip()
        )
        position = user_location.get("position", "").strip()

        # Step 3: If no email in location, fall back to Jamf user record lookup
        if not email and username:
            user_data = _jamf_get(f"/JSSResource/users/name/{username}")
            user = user_data.get("user", {})
            email = user.get("email_address", "") or user.get("email", "")
            full_name = full_name or user.get("full_name", "")
            position = position or user.get("position", "")

        if not email:
            return {
                "error": f"No email found in Jamf for serial {serial_number} (username: {username})",
                "jamf_username": username,
            }

        return {
            "email": email,
            "full_name": full_name,
            "jamf_username": username,
            "position": position,
            "error": None,
        }
    except Exception as e:
        logger.error("get_user_email failed for %s: %s", serial_number, e)
        return {"error": str(e)}


@tool
def check_other_devices(jamf_username: str) -> list[dict]:
    """
    List all Jamf-enrolled devices for a Jamf user account.

    Used in BRANCH 1 of the triage hierarchy: when NUMBER_OF_COMPUTERS > 1,
    check whether the other device has a recent check-in (< 7 days ago),
    which indicates a device swap rather than an MDM communication failure.

    Args:
        jamf_username: The Jamf username (typically firstname.lastname).

    Returns:
        A list of dicts: [{computer_name, serial, last_checkin, jamf_url}, ...]
    """
    try:
        data = _jamf_get(f"/JSSResource/users/name/{jamf_username}")
        user = data.get("user", {})
        computers = user.get("links", {}).get("computers", [])
        results = []
        for comp in computers:
            cid = comp.get("id")
            detail = _jamf_get(f"/api/v1/computers/{cid}/details")
            general = detail.get("general", {})
            results.append({
                "computer_name": general.get("name", ""),
                "serial": detail.get("hardware", {}).get("serialNumber", ""),
                "last_checkin": general.get("lastContactTime", ""),
                "jamf_url": f"{JAMF_URL}/computers.html?id={cid}&o=r",
            })
        return results
    except Exception as e:
        logger.error("check_other_devices failed for %s: %s", jamf_username, e)
        return [{"error": str(e)}]


@tool
def check_macos_update(jamf_id: int) -> dict:
    """
    Check whether a macOS software update is available for the device.

    Only relevant in BRANCH 2 (check-in or inventory failure). An available
    OS update is surfaced as a potential contributing cause of MDM communication
    failure and flagged as a human-action recommendation. The agent does not
    trigger updates remotely.

    Why an OS update may resolve MDM issues:
      - macOS security updates sometimes patch MDM/APNS communication bugs
      - Very old OS versions may have APNS certificate compatibility issues
      - A pending update prompt can interfere with background Jamf check-ins

    Args:
        jamf_id: The Jamf Pro computer record ID (integer).

    Returns:
        A dict with:
          update_available (bool)
          current_version (str)
          latest_available_version (str | None)
          notes (str)
    """
    try:
        data = _jamf_get(f"/api/v1/computers/{jamf_id}/details")
        sw = data.get("softwareUpdates", {})
        available_updates = sw.get("availableUpdates", [])
        current_version = data.get("hardware", {}).get("osVersion", "unknown")

        if not available_updates:
            return {
                "update_available": False,
                "current_version": current_version,
                "latest_available_version": None,
                "notes": f"No macOS updates available. Current: {current_version}",
            }

        # Find the most recent macOS update in the list
        macos_updates = [
            u for u in available_updates
            if "macos" in u.get("name", "").lower() or u.get("productKey", "").startswith("MSU")
        ]
        latest = macos_updates[0] if macos_updates else available_updates[0]
        latest_version = latest.get("version", latest.get("name", "unknown"))

        return {
            "update_available": True,
            "current_version": current_version,
            "latest_available_version": latest_version,
            "notes": (
                f"macOS update available: {current_version} → {latest_version}. "
                "An OS update may resolve MDM communication issues. "
                "Recommend: scope to macOS update policy or direct user to System Settings."
            ),
        }
    except Exception as e:
        logger.error("check_macos_update failed for jamf_id %s: %s", jamf_id, e)
        return {"error": str(e)}


@tool
def resolve_pending_policies(policy_ids: list[int]) -> list[dict]:
    """
    For each Jamf policy ID, fetch the policy name and scope from Jamf Pro API.

    Returns a list of dicts with:
      id, name, jamf_url, enabled, scope_all_computers

    Args:
        policy_ids: List of integer policy IDs from the issue description's
                    PENDING POLICIES field.
    """
    results = []
    for pid in policy_ids:
        try:
            data = _jamf_get(f"/JSSResource/policies/id/{pid}")
            policy = data.get("policy", {})
            general = policy.get("general", {})
            scope = policy.get("scope", {})
            results.append({
                "id": pid,
                "name": general.get("name", f"Policy {pid}"),
                "jamf_url": f"{JAMF_URL}/policies.html?id={pid}&o=r",
                "enabled": general.get("enabled", False),
                "scope_all_computers": scope.get("all_computers", False),
                "category": general.get("category", {}).get("name", ""),
            })
        except Exception as e:
            results.append({
                "id": pid,
                "error": str(e),
                "jamf_url": f"{JAMF_URL}/policies.html?id={pid}&o=r",
            })
    return results


@tool
def send_blank_push(jamf_id: int) -> dict:
    """
    Send an MDM blank push to a device to test whether management commands
    are working.

    REQUIRES HUMAN APPROVAL — present an explicit approval prompt before
    calling this tool. Wait for 'yes' before proceeding.

    Example approval prompt:
        "I'm about to send a blank push to {computer_name} (Jamf ID {jamf_id}).
         This tests whether MDM commands are working.
         Type 'yes' to proceed or 'no' to skip."

    In DRY_RUN mode, this is a no-op.

    Args:
        jamf_id: The Jamf Pro computer record ID (integer).
    """
    if DRY_RUN:
        return {"dry_run": True, "message": "Blank push skipped (DRY_RUN=true)"}
    try:
        _jamf_post(f"/JSSResource/computercommands/command/BlankPush/id/{jamf_id}")
        return {"success": True, "message": "Blank push sent"}
    except Exception as e:
        logger.error("send_blank_push failed for jamf_id %s: %s", jamf_id, e)
        return {"success": False, "error": str(e)}


@tool
def run_jamf_policy(jamf_id: int, policy_id: int) -> dict:
    """
    Scope a specific computer into a Jamf policy and trigger execution.

    Used for Superman-related remediation policies:
      - 735: super log last 100 entries (diagnostic)
      - 653: Superman Reset
      - 457: Uninstall Superman
      - 1222: Install Superman 5.0.0

    REQUIRES HUMAN APPROVAL — present an explicit approval prompt before
    calling this tool. Name the policy and state what it will do.

    Example approval prompt:
        "I'm about to run policy {policy_id} ({policy_name}) on {computer_name}
         (Jamf ID {jamf_id}). This will {description_of_action}.
         Type 'yes' to proceed or 'no' to skip."

    In DRY_RUN mode, this is a no-op.

    Args:
        jamf_id: The Jamf Pro computer record ID.
        policy_id: The Jamf policy ID to run.
    """
    if DRY_RUN:
        return {
            "dry_run": True,
            "message": f"Policy {policy_id} on device {jamf_id} skipped (DRY_RUN=true)",
        }
    try:
        _jamf_post(
            f"/JSSResource/computercommands/command/RunScript/id/{jamf_id}",
            json={"policyId": policy_id},
        )
        return {
            "success": True,
            "message": f"Policy {policy_id} queued on device {jamf_id}",
            "jamf_url": f"{JAMF_URL}/policies.html?id={policy_id}&o=r",
        }
    except Exception as e:
        logger.error("run_jamf_policy failed (policy=%s, device=%s): %s", policy_id, jamf_id, e)
        return {"success": False, "error": str(e)}


@tool
def redeploy_jamf_framework(jamf_id: int) -> dict:
    """
    Trigger the Jamf Management Framework redeployment for a device via Okta Workflows.

    This is equivalent to running:
        sudo profiles renew -type enrollment
    on the device, and will redeploy the MDM enrollment profile.

    REQUIRES HUMAN APPROVAL — present an explicit approval prompt before
    calling this tool.

    Example approval prompt:
        "I'm about to trigger a Jamf framework redeploy on {computer_name}
         (Jamf ID {jamf_id}). This will re-enroll the MDM profile without
         requiring physical access. Type 'yes' to proceed or 'no' to skip."

    In DRY_RUN mode, this is a no-op.

    Args:
        jamf_id: The Jamf Pro computer record ID.
    """
    if DRY_RUN:
        return {
            "dry_run": True,
            "message": f"Framework redeploy for device {jamf_id} skipped (DRY_RUN=true)",
        }
    if not OKTA_REDEPLOY_WORKFLOW_URL:
        return {"error": "OKTA_REDEPLOY_WORKFLOW_URL not configured"}
    try:
        resp = httpx.post(
            OKTA_REDEPLOY_WORKFLOW_URL,
            json={"jamf_id": jamf_id},
            timeout=15,
        )
        resp.raise_for_status()
        return {"success": True, "message": "Jamf Framework redeploy triggered via Okta"}
    except Exception as e:
        logger.error("redeploy_jamf_framework failed for jamf_id %s: %s", jamf_id, e)
        return {"success": False, "error": str(e)}
