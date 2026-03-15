import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
config = json.loads((ROOT / "config.json").read_text())
