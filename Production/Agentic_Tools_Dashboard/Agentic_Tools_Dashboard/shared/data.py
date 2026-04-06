"""Data loading and querying utilities for Agentic Tools."""

import json
import os
from pathlib import Path
from typing import Optional

from shared.config import CONFIG


def _get_latest_json_file() -> Path:
    """Return the path to the most recently modified JSON file in data_dir."""
    data_dir = Path(CONFIG["data_dir"])
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    json_files = list(data_dir.glob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No JSON files found in {data_dir}")

    return max(json_files, key=os.path.getmtime)


def load_raw_data() -> list[dict]:
    """Load and return the raw device records from the latest JSON file."""
    path = _get_latest_json_file()
    with open(path, "r") as f:
        return json.load(f)


def get_all_devices(
    serial_number: Optional[str] = None,
    hostname: Optional[str] = None,
    tool: Optional[str] = None,
) -> list[dict]:
    """
    Return all device records, optionally filtered.

    Args:
        serial_number: Filter by exact or partial serial number match.
        hostname: Filter by exact or partial hostname match.
        tool: Filter to devices that have this tool installed.
    """
    records = load_raw_data()

    if serial_number:
        records = [
            r for r in records
            if serial_number.lower() in r["device"]["serial_number"].lower()
        ]

    if hostname:
        records = [
            r for r in records
            if hostname.lower() in r["device"]["hostname"].lower()
        ]

    if tool:
        records = [
            r for r in records
            if tool.lower() in r["tools"]
            and r["tools"][tool.lower()].get("installed", False)
        ]

    return records


def get_tool_overview() -> list[dict]:
    """
    Return an overview of every tool with:
      - computer_count: how many devices have it installed
      - unique_connections: list of unique connection/extension names
    """
    records = load_raw_data()
    tool_names = CONFIG["tools"]
    overview = []

    for tool_name in tool_names:
        installed_devices = []
        connection_counts: dict[str, int] = {}

        for record in records:
            tool_data = record["tools"].get(tool_name, {})
            if not tool_data.get("installed", False):
                continue

            installed_devices.append(record["device"]["serial_number"])

            for conn in tool_data.get("connections", []):
                name = conn.get("name", "").strip()
                if name:
                    connection_counts[name] = connection_counts.get(name, 0) + 1

            # Raycast: count extensions_installed as a summary stat
            if tool_name == "raycast" and tool_data.get("extensions_installed", 0) > 0:
                ext_label = "Extensions (Raycast)"
                connection_counts[ext_label] = connection_counts.get(ext_label, 0) + tool_data["extensions_installed"]

        overview.append({
            "tool": tool_name,
            "computer_count": len(installed_devices),
            "unique_connections": [
                {"name": k, "computer_count": v}
                for k, v in sorted(connection_counts.items())
            ],
        })

    return overview


def get_tool_detail(tool_name: str) -> dict:
    """
    Return detailed info for a single tool including per-device breakdown.
    """
    records = load_raw_data()
    tool_name = tool_name.lower()

    devices = []
    connection_counts: dict[str, int] = {}

    for record in records:
        tool_data = record["tools"].get(tool_name, {})
        if not tool_data.get("installed", False):
            continue

        connections = [c.get("name", "") for c in tool_data.get("connections", []) if c.get("name")]
        devices.append({
            "hostname": record["device"]["hostname"],
            "serial_number": record["device"]["serial_number"],
            "current_user": record["device"]["current_user"],
            "version": tool_data.get("version"),
            "connections": connections,
        })

        for conn_name in connections:
            connection_counts[conn_name] = connection_counts.get(conn_name, 0) + 1

    return {
        "tool": tool_name,
        "computer_count": len(devices),
        "connections_summary": [
            {"name": k, "computer_count": v}
            for k, v in sorted(connection_counts.items())
        ],
        "devices": devices,
    }


def get_all_connections(
    name: Optional[str] = None,
    tool: Optional[str] = None,
) -> list[dict]:
    """
    Return a flat list of all unique connections/extensions across all tools.

    Args:
        name: Filter by connection name (partial match).
        tool: Filter by tool name.
    """
    records = load_raw_data()
    # { (tool, connection_name) -> set of serial_numbers }
    seen: dict[tuple, set] = {}

    for record in records:
        sn = record["device"]["serial_number"]
        for tool_name, tool_data in record["tools"].items():
            if not tool_data.get("installed", False):
                continue
            for conn in tool_data.get("connections", []):
                conn_name = conn.get("name", "").strip()
                if not conn_name:
                    continue
                key = (tool_name, conn_name)
                seen.setdefault(key, set()).add(sn)

    results = [
        {
            "tool": t,
            "connection_name": c,
            "computer_count": len(sns),
        }
        for (t, c), sns in seen.items()
    ]

    if name:
        results = [r for r in results if name.lower() in r["connection_name"].lower()]
    if tool:
        results = [r for r in results if tool.lower() == r["tool"].lower()]

    return sorted(results, key=lambda r: (-r["computer_count"], r["tool"], r["connection_name"]))
