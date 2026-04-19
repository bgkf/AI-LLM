"""
dashboard/server.py

Local HTTP server for the Okta Intelligence Dashboard.
Manages the apfel process lifecycle and exposes endpoints for the dashboard UI.
"""

import atexit
import json
import logging
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import threading

from flask import Flask, jsonify, request, send_from_directory
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DASHBOARD_DIR  = pathlib.Path(__file__).parent
REPO_ROOT      = DASHBOARD_DIR.parent
VENV_PYTHON    = REPO_ROOT / "venv" / "bin" / "python"
LOG_PATH       = REPO_ROOT / "launch.log"
SYNONYMS_PATH  = REPO_ROOT / "intelligence" / "query-synonyms.json"

CONFIG_PATH = REPO_ROOT / "intelligence" / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

SYSTEM_PROMPT_PATH = REPO_ROOT / CONFIG["system_prompt_path"]
MCP_SERVER_PATH    = REPO_ROOT / CONFIG["mcp_server_path"]
PORT               = CONFIG.get("port", 8080)
APFEL_PORT         = CONFIG.get("apfel_port", 11434)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

load_dotenv(REPO_ROOT / ".env")

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_session_token: str | None = None
_token_lock = threading.Lock()


def get_token() -> str | None:
    with _token_lock:
        return _session_token


def set_token(token: str) -> None:
    global _session_token
    with _token_lock:
        _session_token = token
        os.environ["OKTA_API_TOKEN"] = token
        # Write to .env so the MCP subprocess can read it on next tool call
        env_path = REPO_ROOT / ".env"
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        new_lines = []
        token_written = False
        for line in lines:
            if line.startswith("OKTA_API_TOKEN="):
                new_lines.append(f"OKTA_API_TOKEN={token}")
                token_written = True
            else:
                new_lines.append(line)
        if not token_written:
            new_lines.append(f"OKTA_API_TOKEN={token}")
        env_path.write_text("\n".join(new_lines) + "\n")
        log.info("Okta API token written to .env for MCP subprocess")


# ---------------------------------------------------------------------------
# venv helpers
# ---------------------------------------------------------------------------

SYSTEM_PYTHON = "/usr/local/bin/python3"


def get_python() -> str:
    """Return the venv interpreter if present, otherwise fall back to system python3."""
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else SYSTEM_PYTHON


# ---------------------------------------------------------------------------
# apfel lifecycle
# ---------------------------------------------------------------------------

apfel_proc: subprocess.Popen | None = None

def start_apfel() -> None:
    global apfel_proc
    log.info("Starting apfel — system prompt: %s, MCP server: %s", SYSTEM_PROMPT_PATH, MCP_SERVER_PATH)
    apfel_proc = subprocess.Popen(
        [
            "apfel", "--serve",
            "--port", str(APFEL_PORT),
            "--cors",
            "--debug",
            "--context-strategy", "newest-first",
            "--mcp", str(MCP_SERVER_PATH),
            "--system-file", str(SYSTEM_PROMPT_PATH),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    log.info("apfel started — PID %s", apfel_proc.pid)

    def _pipe_apfel_logs(proc):
        for line in proc.stdout:
            log.info("[apfel] %s", line.decode("utf-8", errors="replace").rstrip())

    threading.Thread(target=_pipe_apfel_logs, args=(apfel_proc,), daemon=True).start()
    atexit.register(stop_apfel)


def stop_apfel() -> None:
    global apfel_proc
    if apfel_proc and apfel_proc.poll() is None:
        log.info("Stopping apfel — PID %s", apfel_proc.pid)
        apfel_proc.terminate()
        try:
            apfel_proc.wait(timeout=5)
            log.info("apfel stopped cleanly")
        except subprocess.TimeoutExpired:
            apfel_proc.kill()
            log.warning("apfel did not stop within 5s — killed")
    apfel_proc = None


def clear_pycache() -> None:
    log.info("Clearing __pycache__ and .pyc files")
    for cache_dir in REPO_ROOT.rglob("__pycache__"):
        shutil.rmtree(cache_dir, ignore_errors=True)
    for pyc_file in REPO_ROOT.rglob("*.pyc"):
        pyc_file.unlink(missing_ok=True)


signal.signal(signal.SIGTERM, lambda *_: stop_apfel())


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def execute_tool_sync(tool_name: str, tool_args: dict):
    """Execute an MCP tool directly by importing and calling it."""
    import asyncio
    mcp_dir   = MCP_SERVER_PATH.parent
    tools_dir = mcp_dir / "tools"
    for p in (str(mcp_dir), str(tools_dir)):
        if p not in sys.path:
            sys.path.insert(0, p)

    async def _run():
        if tool_name == "tool_list_users":
            from tools.list_users import list_users
            return await list_users(**tool_args)
        elif tool_name == "tool_get_group":
            from tools.get_group import get_group
            return await get_group(**tool_args)
        elif tool_name == "tool_get_audit_logs":
            from tools.get_audit_logs import get_audit_logs
            return await get_audit_logs(**tool_args)
        elif tool_name == "tool_search_events":
            from tools.search_events import search_events
            return await search_events(**tool_args)
        elif tool_name == "tool_list_apps":
            from tools.list_apps import list_apps
            return await list_apps(**tool_args)
        elif tool_name == "tool_list_devices":
            from tools.list_devices import list_devices
            return await list_devices(**tool_args)
        elif tool_name == "tool_get_device_users":
            from tools.get_device_users import get_device_users
            return await get_device_users(**tool_args)
        elif tool_name == "tool_list_iam_roles":
            from tools.list_iam_roles import list_iam_roles
            return await list_iam_roles(**tool_args)
        elif tool_name == "tool_list_oauth_clients":
            from tools.list_oauth_clients import list_oauth_clients
            return await list_oauth_clients(**tool_args)
        elif tool_name == "tool_get_user_sessions":
            from tools.list_sessions import get_user_sessions
            return await get_user_sessions(**tool_args)
        elif tool_name == "tool_get_user_factors":
            from tools.get_user_factors import get_user_factors
            return await get_user_factors(**tool_args)
        elif tool_name == "tool_list_entitlements":
            from tools.get_entitlements import list_entitlements
            return await list_entitlements(**tool_args)
        elif tool_name == "tool_list_grants":
            from tools.get_entitlements import list_grants
            return await list_grants(**tool_args)
        elif tool_name == "tool_get_principal_access":
            from tools.get_principal_access import get_principal_access
            return await get_principal_access(**tool_args)
        elif tool_name == "tool_get_entitlement_history":
            from tools.get_entitlement_history import get_entitlement_history
            return await get_entitlement_history(**tool_args)
        elif tool_name == "tool_list_access_reviews":
            from tools.get_access_reviews import list_access_reviews
            return await list_access_reviews(**tool_args)
        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Synonym loader
# ---------------------------------------------------------------------------

def _load_synonyms() -> dict:
    """Load query-synonyms.json, stripping comment keys. Returns empty dict on failure."""
    try:
        with open(SYNONYMS_PATH) as f:
            raw = json.load(f)
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except Exception as e:
        log.warning("Could not load query-synonyms.json: %s — falling back to built-in matcher", e)
        return {}


def _matches(p: str, phrases) -> bool:
    """Return True if any phrase in the list appears in the prompt string p."""
    if isinstance(phrases, str):
        return phrases in p
    return any(phrase in p for phrase in phrases)


def _extract_okta_id(prompt: str) -> str | None:
    """
    Extract a bare Okta object ID from the prompt.
    Okta IDs are alphanumeric ~20 chars, always starting with 00.
    Example: 00u1ab2cd3EFGhijKL4x5
    """
    match = re.search(r'\b(00[a-zA-Z0-9]{18,20})\b', prompt)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Tool selection
# ---------------------------------------------------------------------------

def select_tool(prompt: str) -> tuple[str, dict]:
    """
    Map a natural language prompt to a tool name and arguments.
    Loads phrase → intent mappings from intelligence/query-synonyms.json.
    Falls back to built-in keyword matching if the file is unavailable.
    Returns ("no_match", {}) when nothing matches — caller should prompt
    the user to rephrase.
    """
    p = prompt.lower()

    limit_match = re.search(r'\[limit=(\d+)\]', prompt)
    limit = int(limit_match.group(1)) if limit_match else 50

    synonyms = _load_synonyms()

    # ----------------------------------------------------------------
    # tool_search_events — failed logins (checked before generic events)
    # ----------------------------------------------------------------
    failed_login_phrases = (
        synonyms.get("tool_search_events", {}).get("failed_login", [])
        if synonyms else
        ["failed login", "failed logins", "login failure", "authentication failed"]
    )
    if _matches(p, failed_login_phrases):
        return "tool_search_events", {
            "event_type": "user.session.start",
            "outcome": "FAILURE",
            "limit": limit,
        }

    # ----------------------------------------------------------------
    # tool_search_events — MFA / suspicious activity
    # ----------------------------------------------------------------
    mfa_phrases = (
        synonyms.get("tool_search_events", {}).get("mfa_failure", [])
        if synonyms else
        ["mfa", "suspicious", "challenge", "multi-factor", "2fa"]
    )
    if _matches(p, mfa_phrases):
        return "tool_search_events", {"outcome": "FAILURE", "limit": limit}

    # ----------------------------------------------------------------
    # tool_get_audit_logs
    # ----------------------------------------------------------------
    audit_phrases = (
        synonyms.get("tool_get_audit_logs", [])
        if synonyms else
        ["audit", "log", "event", "history", "activity"]
    )
    if _matches(p, audit_phrases):
        return "tool_get_audit_logs", {"limit": limit}

    # ----------------------------------------------------------------
    # tool_get_policy — not available: /api/v1/policies is not in the
    # permitted API list for this token. Intercept all policy phrases
    # and return a clear error before they fall through to other tools.
    # ----------------------------------------------------------------
    policy_synonyms = synonyms.get("tool_get_policy", {}) if synonyms else {}

    sign_on_phrases    = policy_synonyms.get("OKTA_SIGN_ON",        ["sign on policy", "sign-on policy", "login policy", "authentication policy"])
    mfa_enroll_phrases = policy_synonyms.get("MFA_ENROLL",          ["mfa enroll", "mfa enrollment", "mfa policy"])
    profile_phrases    = policy_synonyms.get("PROFILE_ENROLLMENT",  ["profile enrollment", "profile policy"])
    password_phrases   = policy_synonyms.get("PASSWORD",            ["password policy", "password policies", "password rule",
                                                                      "password requirement", "policies of type password",
                                                                      "policy of type password"])

    if (_matches(p, sign_on_phrases) or _matches(p, mfa_enroll_phrases)
            or _matches(p, profile_phrases) or _matches(p, password_phrases)):
        return "tool_unavailable", {
            "message": (
                "Policy queries are not available — /api/v1/policies is not "
                "permitted for this API token. Contact your Okta administrator "
                "if you need policy access."
            )
        }

    # ----------------------------------------------------------------
    # tool_list_apps — after policy block to avoid "active" false-positives
    # ----------------------------------------------------------------
    app_phrases = (
        synonyms.get("tool_list_apps", [])
        if synonyms else
        ["app", "application", "assignment", "saml", "sso"]
    )
    if _matches(p, app_phrases):
        app_status = "ACTIVE" if "active" in p else None
        args: dict = {"limit": limit}
        if app_status:
            args["status"] = app_status
        return "tool_list_apps", args

    # ----------------------------------------------------------------
    # tool_get_device_users — more specific, check before tool_list_devices
    # ----------------------------------------------------------------
    device_user_phrases = (
        synonyms.get("tool_get_device_users", [])
        if synonyms else
        ["who is on device", "who was on device", "device users", "users on device",
         "signed into device", "logged into device", "who used this device"]
    )
    if _matches(p, device_user_phrases):
        okta_id = _extract_okta_id(prompt)
        if okta_id:
            return "tool_get_device_users", {"device_id": okta_id}
        return "tool_get_device_users", {}

    # ----------------------------------------------------------------
    # tool_list_devices
    # ----------------------------------------------------------------
    device_phrases = (
        synonyms.get("tool_list_devices", [])
        if synonyms else
        ["device", "devices", "managed device", "laptop", "macbook",
         "computer", "enrolled device", "device inventory", "hardware"]
    )
    if _matches(p, device_phrases):
        status = None
        if "inactive" in p:
            status = "INACTIVE"
        elif "active" in p:
            status = "ACTIVE"
        args: dict = {"limit": limit}
        if status:
            args["status"] = status
        return "tool_list_devices", args

    # ----------------------------------------------------------------
    # tool_list_iam_roles
    # ----------------------------------------------------------------
    iam_phrases = (
        synonyms.get("tool_list_iam_roles", [])
        if synonyms else
        ["iam", "admin role", "admin roles", "who has admin", "admin access",
         "administrator", "resource set", "scoped admin", "super admin",
         "org admin", "privileged access"]
    )
    if _matches(p, iam_phrases):
        return "tool_list_iam_roles", {"limit": limit}

    # ----------------------------------------------------------------
    # tool_list_oauth_clients
    # ----------------------------------------------------------------
    oauth_phrases = (
        synonyms.get("tool_list_oauth_clients", [])
        if synonyms else
        ["oauth", "oauth client", "oidc", "api client", "registered app",
         "client credentials", "service account app", "connected app", "api access"]
    )
    if _matches(p, oauth_phrases):
        return "tool_list_oauth_clients", {"limit": limit}

    # ----------------------------------------------------------------
    # tool_get_user_sessions
    # ----------------------------------------------------------------
    session_phrases = (
        synonyms.get("tool_get_user_sessions", [])
        if synonyms else
        ["session", "sessions", "active session", "signed in", "logged in",
         "currently logged in", "still signed in", "open sessions"]
    )
    if _matches(p, session_phrases):
        okta_id = _extract_okta_id(prompt)
        if okta_id:
            return "tool_get_user_sessions", {"user_id": okta_id}
        return "tool_get_user_sessions", {}

    # ----------------------------------------------------------------
    # tool_get_user_factors
    # ----------------------------------------------------------------
    factor_phrases = (
        synonyms.get("tool_get_user_factors", [])
        if synonyms else
        ["mfa factors", "enrolled factors", "user factors", "authenticator",
         "has mfa", "mfa enrolled", "mfa setup", "mfa configured",
         "two factor", "push enrolled", "totp enrolled", "webauthn"]
    )
    if _matches(p, factor_phrases):
        okta_id = _extract_okta_id(prompt)
        if okta_id:
            return "tool_get_user_factors", {"user_id": okta_id}
        return "tool_get_user_factors", {}

    # ----------------------------------------------------------------
    # tool_get_entitlement_history — more specific, check before tool_list_entitlements
    # ----------------------------------------------------------------
    ent_history_phrases = (
        synonyms.get("tool_get_entitlement_history", [])
        if synonyms else
        ["entitlement history", "access history", "when did user get access",
         "when was access granted", "when was access revoked", "access changes",
         "entitlement changes", "provisioning history", "access audit trail"]
    )
    if _matches(p, ent_history_phrases):
        okta_id = _extract_okta_id(prompt)
        args: dict = {"limit": limit}
        if okta_id:
            args["principal_id"] = okta_id
        return "tool_get_entitlement_history", args

    # ----------------------------------------------------------------
    # tool_get_principal_access — more specific, check before tool_list_entitlements
    # ----------------------------------------------------------------
    principal_phrases = (
        synonyms.get("tool_get_principal_access", [])
        if synonyms else
        ["principal access", "what can user access", "what does user have access to",
         "user resources", "access for user", "resources for principal",
         "over-provisioned", "overprivileged", "excessive access"]
    )
    if _matches(p, principal_phrases):
        okta_id = _extract_okta_id(prompt)
        args: dict = {"limit": limit}
        if okta_id:
            args["principal_id"] = okta_id
        return "tool_get_principal_access", args

    # ----------------------------------------------------------------
    # tool_list_entitlements
    # ----------------------------------------------------------------
    entitlement_phrases = (
        synonyms.get("tool_list_entitlements", [])
        if synonyms else
        ["entitlement", "entitlements", "grants", "active grants", "list grants",
         "what entitlements exist", "available entitlements"]
    )
    if _matches(p, entitlement_phrases):
        return "tool_list_entitlements", {"limit": limit}

    # ----------------------------------------------------------------
    # tool_list_access_reviews
    # ----------------------------------------------------------------
    review_phrases = (
        synonyms.get("tool_list_access_reviews", [])
        if synonyms else
        ["access review", "access reviews", "security access review",
         "certification campaign", "in flight reviews", "pending reviews",
         "open reviews", "completed reviews", "governance review",
         "access certification"]
    )
    if _matches(p, review_phrases):
        return "tool_list_access_reviews", {"limit": min(limit, 25)}

    # ----------------------------------------------------------------
    # tool_get_group
    # ----------------------------------------------------------------
    group_phrases = (
        synonyms.get("tool_get_group", [])
        if synonyms else
        ["group", "groups", "team", "members of"]
    )
    if _matches(p, group_phrases):
        name_match = re.search(
            r'(?:group|team)[s]?\s+(?:called|named|for)?\s*["\']?([a-zA-Z0-9 _-]+)["\']?', p
        )
        group_name = name_match.group(1).strip() if name_match else prompt
        return "tool_get_group", {"group_name": group_name, "limit": limit}

    # ----------------------------------------------------------------
    # tool_list_users — status matching from synonyms
    # ----------------------------------------------------------------
    user_synonyms = synonyms.get("tool_list_users", {}) if synonyms else {}

    status_map = {
        "LOCKED_OUT":       user_synonyms.get("LOCKED_OUT",       ["locked", "locked out", "account locked"]),
        "DEPROVISIONED":    user_synonyms.get("DEPROVISIONED",    ["deprovisioned", "offboarded", "terminated"]),
        "SUSPENDED":        user_synonyms.get("SUSPENDED",        ["suspended", "disabled"]),
        "PASSWORD_EXPIRED": user_synonyms.get("PASSWORD_EXPIRED", ["password expired", "expired password"]),
        "ACTIVE":           user_synonyms.get("ACTIVE",           ["active"]),
    }

    for status_val, phrases in status_map.items():
        if _matches(p, phrases):
            return "tool_list_users", {"status": status_val, "limit": limit}

    # ----------------------------------------------------------------
    # Nothing matched — signal caller to prompt for a rephrase
    # ----------------------------------------------------------------
    return "no_match", {}


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=str(DASHBOARD_DIR))


# Serve dashboard static files
@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route("/set-token", methods=["POST"])
def set_token_endpoint():
    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    if not token:
        log.warning("set-token called with empty token")
        return jsonify({"status": "error", "message": "No token supplied"}), 400
    set_token(token)
    log.info("Okta API token set for session")
    return jsonify({"status": "ok"})


@app.route("/server-status", methods=["GET"])
def server_status():
    proc_alive = apfel_proc is not None and apfel_proc.poll() is None
    return jsonify({"apfel": proc_alive})


@app.route("/query", methods=["POST"])
def query():
    import json as _json

    body   = request.get_json(silent=True) or {}
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return jsonify({"status": "error", "message": "No prompt supplied"}), 400

    try:
        tool_name, tool_args = select_tool(prompt)

        if tool_name == "no_match":
            log.info("No tool matched prompt — returning rephrase request")
            return jsonify({
                "status": "ok",
                "content": (
                    "CLARIFY: I wasn't sure what to look up. Try rephrasing — for example: "
                    "\"List active users\", \"Show locked out users\", \"Get audit logs\", "
                    "\"Find failed logins\", \"List apps\", "
                    "or \"Show members of the [group name] group\"."
                )
            })

        if tool_name == "tool_unavailable":
            msg = tool_args.get("message", "That query is not available for this API token.")
            log.info("Unavailable tool requested: %s", msg)
            return jsonify({"status": "ok", "content": f"CLARIFY: {msg}"})

        log.info("Selected tool: %s with args: %s", tool_name, tool_args)

        result = execute_tool_sync(tool_name, tool_args)
        log.info("Tool result count: %s", len(result) if isinstance(result, list) else "N/A")

        return jsonify({
            "status": "ok",
            "content": _json.dumps({
                "tool_called": tool_name,
                "result_count": len(result) if isinstance(result, list) else 0,
                "data": result,
            })
        })

    except Exception as e:
        # Surface 403 explicitly — usually an API token permissions issue
        if hasattr(e, "response") and e.response is not None:
            status_code = e.response.status_code
            if status_code == 403:
                log.error("Query error: 403 Forbidden — %s", e.response.url)
                return jsonify({
                    "status": "ok",
                    "content": (
                        f"CLARIFY: 403 Forbidden — the API token doesn't have permission to access this resource. "
                        f"URL: {e.response.url}\n"
                        f"The token needs at minimum the Read-only Admin role in Okta. "
                        f"Contact your Okta administrator to update the token's permissions."
                    )
                })
            elif status_code == 401:
                log.error("Query error: 401 Unauthorized — token invalid or expired")
                return jsonify({
                    "status": "ok",
                    "content": (
                        f"CLARIFY: 401 Unauthorized — the API token is invalid or expired. "
                        f"URL: {e.response.url}\n"
                        f"Use Set Token to re-enter it."
                    )
                })
            elif status_code == 429:
                log.error("Query error: 429 Too Many Requests")
                return jsonify({
                    "status": "ok",
                    "content": (
                        f"CLARIFY: 429 Too Many Requests — Okta rate limit hit. "
                        f"URL: {e.response.url}\n"
                        f"Wait a moment and try again."
                    )
                })

        log.error("Query error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/restart", methods=["POST"])
def restart():
    log.info("Restart requested")
    stop_apfel()
    clear_pycache()
    log.info("Re-installing dependencies into venv")
    subprocess.check_call(
        [get_python(), "-m", "pip", "install", "-r", str(REPO_ROOT / "requirements.txt"), "--quiet"]
    )
    start_apfel()
    log.info("Restart complete")
    return jsonify({"status": "restarting"})


@app.route("/send-to-workflow", methods=["POST"])
def send_to_workflow():
    import httpx

    body       = request.get_json(silent=True) or {}
    invoke_url = (body.get("invoke_url") or "").strip()
    payload    = body.get("payload")

    if not invoke_url.startswith("https://"):
        return jsonify({"status": "error", "message": "Invoke URL must use HTTPS"}), 400

    if not payload:
        return jsonify({"status": "error", "message": "No payload supplied"}), 400

    log.info("Sending workflow payload to %s", invoke_url)
    try:
        resp = httpx.post(
            invoke_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "OktaIntelligenceDashboard/1.0",
            },
            timeout=10,
            follow_redirects=False,
        )
        log.info("Workflow response: HTTP %s", resp.status_code)
        return jsonify({"status": "ok", "http_code": resp.status_code})
    except httpx.TimeoutException:
        log.error("Workflow request timed out (10s) — URL: %s", invoke_url)
        return jsonify({"status": "error", "message": "Request timed out (10s)"}), 504
    except httpx.RequestError as e:
        log.error("Workflow request error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 502


@app.route("/quit", methods=["POST"])
def quit_server():
    log.info("Quit requested — shutting down")
    stop_apfel()

    def _shutdown():
        import time, os
        time.sleep(0.3)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"status": "ok"})


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("=== Okta Intelligence Dashboard starting ===")
    log.info("Repo root: %s", REPO_ROOT)
    log.info("Python interpreter: %s", get_python())
    log.info("Dashboard port: %s  |  apfel port: %s", PORT, APFEL_PORT)
    start_apfel()
    import webbrowser
    threading.Timer(0.8, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)