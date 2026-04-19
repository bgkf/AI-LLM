"""
data/okta-mcp-server/auth.py

Okta API authentication helpers.
OKTA_DOMAIN and OKTA_API_TOKEN are both loaded from the .env file.
OKTA_API_TOKEN can also be set at runtime via the dashboard's Set Token modal,
which posts to server.py — that module-level value is passed into tool calls.
"""

import os
import pathlib
from dotenv import load_dotenv

ENV_PATH = pathlib.Path(__file__).parent.parent.parent / ".env"

OKTA_DOMAIN: str = os.environ.get("OKTA_DOMAIN", "").strip().rstrip("/")


def get_base_url() -> str:
    if not OKTA_DOMAIN:
        raise RuntimeError("OKTA_DOMAIN is not set. Add it to your .env file.")
    return f"https://{OKTA_DOMAIN}/api/v1"


def get_gov_base_url() -> str:
    """
    Return the base URL for Okta Identity Governance API endpoints.
    Governance uses a different path prefix to the standard /api/v1 base.
    Requires Okta Identity Governance license — endpoints return 404 if not licensed.
    """
    if not API_DOMAIN:
        raise RuntimeError("OKTA_DOMAIN is not set.")
    return f"https://{API_DOMAIN}/governance/api/v1"


def get_gov_v2_base_url() -> str:
    """
    Return the base URL for Okta Identity Governance v2 API endpoints.
    Used by security access review tools.
    """
    if not API_DOMAIN:
        raise RuntimeError("OKTA_DOMAIN is not set.")
    return f"https://{API_DOMAIN}/governance/api/v2"


def get_token() -> str:
    load_dotenv(ENV_PATH, override=True)  # re-read on every call
    token = os.environ.get("OKTA_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("No Okta API token available. Use the Set Token modal.")
    return token


def get_headers() -> dict[str, str]:
    return {
        "Authorization": f"SSWS {get_token()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
