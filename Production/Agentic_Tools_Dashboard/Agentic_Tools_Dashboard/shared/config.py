"""Centralised configuration loader."""

import json
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _ROOT / "config.json"


def load_config() -> dict:
    """Load and return the project config.json."""
    with open(_CONFIG_PATH, "r") as f:
        return json.load(f)


CONFIG = load_config()
