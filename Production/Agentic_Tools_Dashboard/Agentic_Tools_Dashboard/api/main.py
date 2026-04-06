"""Agentic Tools Dashboard — FastAPI backend.

Serves:
  - Static dashboard at GET /
  - Data API at GET /api/...
"""

import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shared.config import CONFIG
from shared.data import (
    get_all_connections,
    get_all_devices,
    get_tool_detail,
    get_tool_overview,
    load_raw_data,
)

app = FastAPI(
    title="Agentic Tools Dashboard API",
    description="Query agentic tool adoption across Wellthy devices.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Serve the dashboard static files
_DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
if _DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    """Serve the main dashboard HTML."""
    index = _DASHBOARD_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return FileResponse(str(index))


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/data", summary="Raw device records")
def raw_data():
    """Return the full raw JSON dataset from the latest Agentic Tools file."""
    try:
        return load_raw_data()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/tools", summary="Tool overview")
def tools_overview():
    """
    Return an overview of every tool:
    - how many computers it is installed on
    - total unique connections/extensions used with it
    """
    try:
        return get_tool_overview()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/tools/{tool_name}", summary="Tool detail")
def tool_detail(tool_name: str):
    """
    Return detailed info for a single tool including a per-device breakdown
    and a summary of connections/extensions with computer counts.
    """
    known_tools = CONFIG["tools"]
    if tool_name.lower() not in known_tools:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown tool '{tool_name}'. Known tools: {known_tools}",
        )
    try:
        return get_tool_detail(tool_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/devices", summary="Device list")
def devices(
    serial_number: Optional[str] = Query(None, description="Filter by serial number (partial match)"),
    hostname: Optional[str] = Query(None, description="Filter by computer name (partial match)"),
    tool: Optional[str] = Query(None, description="Filter to devices with this tool installed"),
):
    """
    Return all device records. Supports optional filtering by:
    - `serial_number` — partial match on serial number
    - `hostname` — partial match on computer name
    - `tool` — only devices with this tool installed
    """
    try:
        return get_all_devices(serial_number=serial_number, hostname=hostname, tool=tool)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/connections", summary="Connections & extensions list")
def connections(
    name: Optional[str] = Query(None, description="Filter by connection name (partial match)"),
    tool: Optional[str] = Query(None, description="Filter by tool name"),
):
    """
    Return all unique connections/extensions across all tools and devices.
    Supports optional filtering by:
    - `name` — partial match on connection name
    - `tool` — only connections for this tool
    """
    try:
        return get_all_connections(name=name, tool=tool)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=CONFIG["api"]["host"],
        port=CONFIG["api"]["port"],
        reload=True,
    )
