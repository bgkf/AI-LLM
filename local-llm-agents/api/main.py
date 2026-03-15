import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from shared.config import config

app = FastAPI(title="Deep Sea Creature Database")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = Path(config["data_dir"]) / "creatures.json"


def load_creatures():
    with open(DATA_FILE) as f:
        return json.load(f)


@app.get("/creatures")
def get_creatures(
    bioluminescent: Optional[bool] = Query(default=None),
    habitat_zone: Optional[str] = Query(default=None),
):
    creatures = load_creatures()
    if bioluminescent is not None:
        creatures = [c for c in creatures if c["bioluminescent"] == bioluminescent]
    if habitat_zone:
        creatures = [c for c in creatures if c["habitat_zone"].lower() == habitat_zone.lower()]
    return creatures


@app.get("/creatures/{creature_id}")
def get_creature(creature_id: int):
    creatures = load_creatures()
    for c in creatures:
        if c["id"] == creature_id:
            return c
    return {"error": "Creature not found"}


@app.get("/stats")
def get_stats():
    creatures = load_creatures()
    total = len(creatures)
    bioluminescent_count = sum(1 for c in creatures if c["bioluminescent"])
    zones = {}
    for c in creatures:
        zones[c["habitat_zone"]] = zones.get(c["habitat_zone"], 0) + 1
    return {
        "total": total,
        "bioluminescent_count": bioluminescent_count,
        "bioluminescent_pct": round(bioluminescent_count / total * 100),
        "zones": zones,
    }
