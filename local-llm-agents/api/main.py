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

DATA_DIR = Path(config["data_dir"])


def load(filename):
    with open(DATA_DIR / filename) as f:
        return json.load(f)


# ── Creatures ────────────────────────────────────────────────────────────────

@app.get("/creatures")
def get_creatures(
    bioluminescent: Optional[bool] = Query(default=None),
    habitat_zone: Optional[str] = Query(default=None),
    expedition_id: Optional[int] = Query(default=None),
):
    creatures = load("creatures.json")
    if bioluminescent is not None:
        creatures = [c for c in creatures if c["bioluminescent"] == bioluminescent]
    if habitat_zone:
        creatures = [c for c in creatures if c["habitat_zone"].lower() == habitat_zone.lower()]
    if expedition_id is not None:
        creatures = [c for c in creatures if c["expedition_id"] == expedition_id]
    return creatures


@app.get("/creatures/{creature_id}")
def get_creature(creature_id: int):
    """Creature with expedition, zone, and specimens joined in — three chained lookups."""
    creatures   = load("creatures.json")
    expeditions = load("expeditions.json")
    zones       = load("zones.json")
    specimens   = load("specimens.json")

    creature = next((c for c in creatures if c["id"] == creature_id), None)
    if not creature:
        raise HTTPException(status_code=404, detail="Creature not found")

    expedition = next((e for e in expeditions if e["id"] == creature["expedition_id"]), None)
    zone       = next((z for z in zones if z["name"] == creature["habitat_zone"]), None)
    specs      = [s for s in specimens if s["creature_id"] == creature_id]

    return {**creature, "expedition": expedition, "zone": zone, "specimens": specs}


@app.get("/creatures/{creature_id}/food-web")
def get_food_web(creature_id: int):
    """Creature with its predators and prey resolved — chains through relationships."""
    creatures     = load("creatures.json")
    relationships = load("relationships.json")

    creature = next((c for c in creatures if c["id"] == creature_id), None)
    if not creature:
        raise HTTPException(status_code=404, detail="Creature not found")

    prey_ids     = [r["prey_id"]     for r in relationships if r["predator_id"] == creature_id]
    predator_ids = [r["predator_id"] for r in relationships if r["prey_id"]     == creature_id]

    def enrich(ids, role_key):
        results = []
        for cid in ids:
            related = next((c for c in creatures if c["id"] == cid), None)
            if related:
                rel = next(
                    (r for r in relationships
                     if (role_key == "prey"     and r["predator_id"] == creature_id and r["prey_id"]     == cid) or
                        (role_key == "predator" and r["prey_id"]     == creature_id and r["predator_id"] == cid)),
                    None
                )
                results.append({**related, "relationship_notes": rel["notes"] if rel else ""})
        return results

    return {
        **creature,
        "preys_on":    enrich(prey_ids,     "prey"),
        "preyed_on_by": enrich(predator_ids, "predator"),
    }


@app.get("/creatures/{creature_id}/specimens")
def get_creature_specimens(creature_id: int):
    specimens = load("specimens.json")
    return [s for s in specimens if s["creature_id"] == creature_id]


# ── Expeditions ───────────────────────────────────────────────────────────────

@app.get("/expeditions")
def get_expeditions():
    return load("expeditions.json")


@app.get("/expeditions/{expedition_id}")
def get_expedition(expedition_id: int):
    """Expedition with all discovered creatures joined in."""
    expeditions = load("expeditions.json")
    creatures   = load("creatures.json")

    expedition = next((e for e in expeditions if e["id"] == expedition_id), None)
    if not expedition:
        raise HTTPException(status_code=404, detail="Expedition not found")

    discovered = [c for c in creatures if c["expedition_id"] == expedition_id]
    return {**expedition, "creatures": discovered}


# ── Zones ─────────────────────────────────────────────────────────────────────

@app.get("/zones")
def get_zones():
    return load("zones.json")


@app.get("/zones/{zone_name}")
def get_zone(zone_name: str):
    """Zone with all resident creatures joined in."""
    zones     = load("zones.json")
    creatures = load("creatures.json")

    zone = next((z for z in zones if z["name"].lower() == zone_name.lower()), None)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")

    residents = [c for c in creatures if c["habitat_zone"].lower() == zone_name.lower()]
    return {**zone, "creatures": residents}


# ── Specimens ─────────────────────────────────────────────────────────────────

@app.get("/specimens")
def get_specimens(
    creature_id: Optional[int] = Query(default=None),
    institution: Optional[str] = Query(default=None),
    condition: Optional[str]   = Query(default=None),
    on_display: Optional[bool] = Query(default=None),
):
    specimens = load("specimens.json")
    if creature_id is not None:
        specimens = [s for s in specimens if s["creature_id"] == creature_id]
    if institution:
        specimens = [s for s in specimens if institution.lower() in s["institution"].lower()]
    if condition:
        specimens = [s for s in specimens if s["condition"] == condition]
    if on_display is not None:
        specimens = [s for s in specimens if s["on_display"] == on_display]
    return specimens


@app.get("/specimens/{specimen_id}")
def get_specimen(specimen_id: int):
    """Specimen with its creature joined in."""
    specimens = load("specimens.json")
    creatures = load("creatures.json")

    specimen = next((s for s in specimens if s["id"] == specimen_id), None)
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found")

    creature = next((c for c in creatures if c["id"] == specimen["creature_id"]), None)
    return {**specimen, "creature": creature}


# ── Stats ─────────────────────────────────────────────────────────────────────

@app.get("/stats")
def get_stats():
    creatures   = load("creatures.json")
    expeditions = load("expeditions.json")
    specimens   = load("specimens.json")
    zones       = load("zones.json")

    total = len(creatures)
    bioluminescent_count = sum(1 for c in creatures if c["bioluminescent"])
    zones_count = {}
    for c in creatures:
        zones_count[c["habitat_zone"]] = zones_count.get(c["habitat_zone"], 0) + 1

    institutions = set(s["institution"] for s in specimens)
    countries    = set(s["country"]     for s in specimens)

    return {
        "total":                total,
        "bioluminescent_count": bioluminescent_count,
        "bioluminescent_pct":   round(bioluminescent_count / total * 100),
        "zones":                zones_count,
        "total_expeditions":    len(expeditions),
        "total_specimens":      len(specimens),
        "total_institutions":   len(institutions),
        "total_countries":      len(countries),
    }
