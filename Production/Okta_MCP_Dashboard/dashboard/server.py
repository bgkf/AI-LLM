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

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

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
# OAuth config helpers
# ---------------------------------------------------------------------------

_ENV_KEYS = ("OKTA_ORG_URL", "OKTA_CLIENT_ID", "OKTA_SCOPES")


def set_okta_config(org_url: str, client_id: str, scopes: str) -> None:
    """Persist OAuth config to .env and os.environ."""
    for key, val in (("OKTA_ORG_URL", org_url), ("OKTA_CLIENT_ID", client_id), ("OKTA_SCOPES", scopes)):
        os.environ[key] = val
    env_path = REPO_ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updates = {"OKTA_ORG_URL": org_url, "OKTA_CLIENT_ID": client_id, "OKTA_SCOPES": scopes}
    new_lines = []
    written = set()
    for line in lines:
        key = line.split("=", 1)[0] if "=" in line else ""
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            written.add(key)
        else:
            new_lines.append(line)
    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
    env_path.write_text("\n".join(new_lines) + "\n")
    log.info("Okta OAuth config written to .env")


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
    log.info("Starting apfel — system prompt: %s", SYSTEM_PROMPT_PATH)
    apfel_proc = subprocess.Popen(
        [
            "apfel", "--serve",
            "--port", str(APFEL_PORT),
            "--cors",
            "--debug",
            "--context-strategy", "newest-first",
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
# Tool execution via official okta-mcp-server
# ---------------------------------------------------------------------------

def _mcp_server_cmd() -> str:
    venv_bin = REPO_ROOT / "venv" / "bin" / "okta-mcp-server"
    return str(venv_bin) if venv_bin.exists() else "okta-mcp-server"


def execute_tool_via_mcp(tool_name: str, tool_args: dict):
    """Execute a tool via okta-mcp-server subprocess using the MCP protocol."""
    import asyncio
    import json as _json
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_params = StdioServerParameters(
        command=_mcp_server_cmd(),
        env={
            "OKTA_ORG_URL":    os.getenv("OKTA_ORG_URL", ""),
            "OKTA_CLIENT_ID":  os.getenv("OKTA_CLIENT_ID", ""),
            "OKTA_SCOPES":     os.getenv("OKTA_SCOPES", ""),
            "HOME":            os.environ.get("HOME", ""),
            "PATH":            os.environ.get("PATH", ""),
        }
    )

    async def _run():
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, tool_args)
                if result.content and hasattr(result.content[0], "text"):
                    raw = result.content[0].text
                    log.debug("MCP raw response (%s): %.800s", tool_name, raw)
                    try:
                        return _json.loads(raw)
                    except (_json.JSONDecodeError, TypeError):
                        return raw
                return []

    return asyncio.run(_run())


def _normalize_result(result) -> list:
    """Unwrap paginated response dicts and flatten (profile, id) tuple items."""
    if isinstance(result, dict):
        if "error" in result:
            raise ValueError(result["error"])
        if "items" in result:
            result = result["items"]
        elif "policies" in result:
            result = result["policies"]
        else:
            return [result]

    if not isinstance(result, list):
        return []

    normalized = []
    for item in result:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            obj, item_id = item
            if isinstance(obj, dict):
                row = dict(obj)
                if "id" not in row:
                    row["id"] = item_id
                normalized.append(row)
            else:
                normalized.append({"value": str(obj), "id": item_id})
        elif isinstance(item, dict):
            normalized.append(item)
        elif item is not None:
            normalized.append({"value": item})
    return normalized


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
    # get_logs — failed logins (checked before generic events)
    # ----------------------------------------------------------------
    failed_login_phrases = (
        synonyms.get("tool_search_events", {}).get("failed_login", [])
        if synonyms else
        ["failed login", "failed logins", "login failure", "authentication failed"]
    )
    if _matches(p, failed_login_phrases):
        return "get_logs", {
            "filter": 'eventType eq "user.session.start" and outcome.result eq "FAILURE"',
            "limit": limit,
        }

    # ----------------------------------------------------------------
    # get_logs — MFA / suspicious activity
    # ----------------------------------------------------------------
    mfa_phrases = (
        synonyms.get("tool_search_events", {}).get("mfa_failure", [])
        if synonyms else
        ["mfa", "suspicious", "challenge", "multi-factor", "2fa"]
    )
    if _matches(p, mfa_phrases):
        return "get_logs", {
            "filter": 'outcome.result eq "FAILURE"',
            "limit": limit,
        }

    # ----------------------------------------------------------------
    # get_logs — audit logs / general events
    # ----------------------------------------------------------------
    audit_phrases = (
        synonyms.get("tool_get_audit_logs", [])
        if synonyms else
        ["audit", "log", "event", "history", "activity"]
    )
    if _matches(p, audit_phrases):
        return "get_logs", {"limit": limit}

    # ----------------------------------------------------------------
    # list_policies
    # ----------------------------------------------------------------
    policy_synonyms = synonyms.get("tool_get_policy", {}) if synonyms else {}

    sign_on_phrases    = policy_synonyms.get("OKTA_SIGN_ON",        ["sign on policy", "sign-on policy", "login policy", "authentication policy"])
    mfa_enroll_phrases = policy_synonyms.get("MFA_ENROLL",          ["mfa enroll", "mfa enrollment", "mfa policy"])
    profile_phrases    = policy_synonyms.get("PROFILE_ENROLLMENT",  ["profile enrollment", "profile policy"])
    password_phrases   = policy_synonyms.get("PASSWORD",            ["password policy", "password policies", "password rule",
                                                                      "password requirement", "policies of type password",
                                                                      "policy of type password"])

    if _matches(p, sign_on_phrases):
        return "list_policies", {"type": "OKTA_SIGN_ON", "limit": limit}
    if _matches(p, mfa_enroll_phrases):
        return "list_policies", {"type": "MFA_ENROLL", "limit": limit}
    if _matches(p, profile_phrases):
        return "list_policies", {"type": "PROFILE_ENROLLMENT", "limit": limit}
    if _matches(p, password_phrases):
        return "list_policies", {"type": "PASSWORD", "limit": limit}

    # ----------------------------------------------------------------
    # list_applications — after policy block to avoid "active" false-positives
    # ----------------------------------------------------------------
    app_phrases = (
        synonyms.get("tool_list_apps", [])
        if synonyms else
        ["app", "application", "assignment", "saml", "sso"]
    )
    if _matches(p, app_phrases):
        args: dict = {"limit": limit}
        if "active" in p:
            args["filter"] = 'status eq "ACTIVE"'
        elif "inactive" in p:
            args["filter"] = 'status eq "INACTIVE"'
        return "list_applications", args

    # ----------------------------------------------------------------
    # list_groups (returns group members via two-step in /query handler)
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
        return "list_groups", {"q": group_name, "limit": limit}

    # ----------------------------------------------------------------
    # list_users — status matching from synonyms
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
            return "list_users", {"search": f'status eq "{status_val}"', "limit": limit}

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

@app.route("/get-config", methods=["GET"])
def get_config():
    """Return current OAuth config values from env (for pre-filling the modal)."""
    default_scopes = "okta.users.read okta.groups.read okta.apps.read okta.policies.read okta.logs.read"
    return jsonify({
        "org_url":   os.getenv("OKTA_ORG_URL", "").strip(),
        "client_id": os.getenv("OKTA_CLIENT_ID", "").strip(),
        "scopes":    os.getenv("OKTA_SCOPES", default_scopes).strip(),
    })


@app.route("/set-config", methods=["POST"])
def set_config_endpoint():
    body       = request.get_json(silent=True) or {}
    org_url    = (body.get("org_url") or "").strip()
    client_id  = (body.get("client_id") or "").strip()
    scopes     = (body.get("scopes") or "").strip()
    if not org_url or not client_id:
        log.warning("set-config called with missing org_url or client_id")
        return jsonify({"status": "error", "message": "org_url and client_id are required"}), 400
    if not scopes:
        scopes = "okta.users.read okta.groups.read okta.apps.read okta.policies.read okta.logs.read"
    set_okta_config(org_url, client_id, scopes)
    log.info("Okta OAuth config saved")
    return jsonify({"status": "ok"})


@app.route("/server-status", methods=["GET"])
def server_status():
    proc_alive = apfel_proc is not None and apfel_proc.poll() is None
    return jsonify({"apfel": proc_alive})


@app.route("/api-status", methods=["GET"])
def api_status():
    """Lightweight config check — no Okta API call. Returns whether credentials are configured."""
    org_url   = os.getenv("OKTA_ORG_URL", "").strip()
    client_id = os.getenv("OKTA_CLIENT_ID", "").strip()
    configured = bool(org_url and client_id)
    return jsonify({"configured": configured, "org_url": org_url})


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
                    "\"Find failed logins\", \"List apps\", \"Password policies\", "
                    "or \"Show members of the [group name] group\"."
                )
            })

        log.info("Selected tool: %s with args: %s", tool_name, tool_args)

        # Group queries require two steps: find group ID, then list members
        if tool_name == "list_groups":
            groups_raw = execute_tool_via_mcp("list_groups", {
                "q": tool_args.get("q", ""),
                "limit": 5,
            })
            groups_result = _normalize_result(groups_raw)
            if not groups_result:
                return jsonify({
                    "status": "ok",
                    "content": _json.dumps({"tool_called": "list_groups", "result_count": 0, "data": []}),
                })
            group_id = (groups_result[0].get("id") or groups_result[0].get("groupId", ""))
            if not group_id:
                return jsonify({
                    "status": "ok",
                    "content": _json.dumps({"tool_called": "list_groups", "result_count": 0, "data": []}),
                })
            raw = execute_tool_via_mcp("list_group_users", {
                "group_id": group_id,
                "limit": tool_args.get("limit", 50),
            })
        else:
            raw = execute_tool_via_mcp(tool_name, tool_args)

        result = _normalize_result(raw)
        log.info("Tool result count: %s", len(result))

        return jsonify({
            "status": "ok",
            "content": _json.dumps({
                "tool_called": tool_name,
                "result_count": len(result),
                "data": result,
            })
        })

    except Exception as e:
        err_str = str(e)
        if "401" in err_str or "Unauthorized" in err_str:
            log.error("Query error: 401 Unauthorized — clearing cached token")
            try:
                import keyring as _kr
                _kr.delete_password("OktaAuthManager", "api_token")
                _kr.delete_password("OktaAuthManager", "refresh_token")
            except Exception:
                pass
            return jsonify({
                "status": "ok",
                "content": (
                    "CLARIFY: OAuth token expired. The cached token has been cleared. "
                    "Run okta-mcp-server in a terminal to re-authenticate, then retry your query."
                )
            })
        if "403" in err_str or "Forbidden" in err_str:
            log.error("Query error: 403 Forbidden")
            return jsonify({
                "status": "ok",
                "content": (
                    "CLARIFY: 403 Forbidden — the OAuth app lacks permission for this resource. "
                    "Verify the app's scopes include the required okta.* scopes and that the "
                    "app has been granted admin consent in Okta."
                )
            })
        if "429" in err_str:
            log.error("Query error: 429 Too Many Requests")
            return jsonify({
                "status": "ok",
                "content": "CLARIFY: 429 Too Many Requests — Okta rate limit hit. Wait a moment and try again.",
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