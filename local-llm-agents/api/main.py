import json
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shared.config import config

app = FastAPI(title="Deep Sea Creature Database")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CREATURES_FILE = Path(config["data_dir"]) / "creatures.json"
EXPEDITIONS_FILE = Path(config["data_dir"]) / "expeditions.json"


def load_creatures():
    with open(CREATURES_FILE) as f:
        return json.load(f)


def load_expeditions():
    with open(EXPEDITIONS_FILE) as f:
        return json.load(f)


# --- Creatures ---

@app.get("/creatures")
def get_creatures(
    bioluminescent: Optional[bool] = Query(default=None),
    habitat_zone: Optional[str] = Query(default=None),
    expedition_id: Optional[int] = Query(default=None),
):
    creatures = load_creatures()
    if bioluminescent is not None:
        creatures = [c for c in creatures if c["bioluminescent"] == bioluminescent]
    if habitat_zone:
        creatures = [c for c in creatures if c["habitat_zone"].lower() == habitat_zone.lower()]
    if expedition_id is not None:
        creatures = [c for c in creatures if c["expedition_id"] == expedition_id]
    return creatures


@app.get("/creatures/{creature_id}")
def get_creature(creature_id: int):
    """Returns a creature with its full expedition data joined in."""
    creatures = load_creatures()
    expeditions = load_expeditions()

    creature = next((c for c in creatures if c["id"] == creature_id), None)
    if not creature:
        raise HTTPException(status_code=404, detail="Creature not found")

    # chain: join expedition data onto the creature
    expedition = next((e for e in expeditions if e["id"] == creature["expedition_id"]), None)
    return {**creature, "expedition": expedition}


# --- Expeditions ---

@app.get("/expeditions")
def get_expeditions():
    return load_expeditions()


@app.get("/expeditions/{expedition_id}")
def get_expedition(expedition_id: int):
    """Returns an expedition with its full list of discovered creatures joined in."""
    expeditions = load_expeditions()
    creatures = load_creatures()

    expedition = next((e for e in expeditions if e["id"] == expedition_id), None)
    if not expedition:
        raise HTTPException(status_code=404, detail="Expedition not found")

    # chain: join all creatures that belong to this expedition
    discovered = [c for c in creatures if c["expedition_id"] == expedition_id]
    return {**expedition, "creatures": discovered}


# --- Stats ---

@app.get("/stats")
def get_stats():
    creatures = load_creatures()
    expeditions = load_expeditions()
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
        "total_expeditions": len(expeditions),
    }
