#!/usr/bin/env python3
"""
deepseacli.py — Command line interface for the Deep Sea Creature Database.

Usage:
  python cli/deepseacli.py creature list
  python cli/deepseacli.py creature get "Goblin Shark"
  python cli/deepseacli.py creature search --zone "Bathyal Zone" --bioluminescent
  python cli/deepseacli.py creature foodweb "Anglerfish"
  python cli/deepseacli.py expedition list
  python cli/deepseacli.py expedition get "HMS Challenger"
  python cli/deepseacli.py specimens "Vampire Squid"
  python cli/deepseacli.py export creatures --format csv
  python cli/deepseacli.py export expeditions --format json
  python cli/deepseacli.py chain "Goblin Shark"
  python cli/deepseacli.py info
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from shared.config import config

API = f"http://localhost:{config['api_port']}"

# ── ANSI colours ──────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
CYAN  = "\033[96m"
BLUE  = "\033[94m"
AMBER = "\033[93m"
GREEN = "\033[92m"
PINK  = "\033[95m"
RED   = "\033[91m"
WHITE = "\033[97m"


def col(text, colour):
    return f"{colour}{text}{RESET}"


def header(text):
    width = 60
    print()
    print(col("─" * width, DIM))
    print(col(f"  {text}", BOLD + CYAN))
    print(col("─" * width, DIM))


def kv(key, value, key_colour=DIM, val_colour=WHITE):
    print(f"  {col(key + ':', key_colour):<28} {col(str(value), val_colour)}")


def section(text):
    print()
    print(col(f"  {text}", AMBER))
    print(col("  " + "·" * len(text), DIM))


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def get(path):
    url = f"{API}{path}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError:
        print(col(f"\n  ✗ Cannot connect to API at {API}", RED))
        print(col("    Is the FastAPI server running?", DIM))
        print(col("    uv run uvicorn api.main:app --reload --port 8000\n", DIM))
        sys.exit(1)


def timed_get(path, label=None):
    """Fetch with timing. Returns (data, elapsed_ms). Prints request line if label given."""
    url = f"{API}{path}"
    if label:
        print(f"  {col('→', CYAN)} {col(label, DIM)}", end="", flush=True)
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
        elapsed = int((time.time() - t0) * 1000)
        if label:
            print(f"  {col('✓', GREEN)} {col(str(elapsed) + 'ms', DIM)}")
        return data, elapsed
    except urllib.error.URLError:
        if label:
            print(f"  {col('✗ failed', RED)}")
        sys.exit(1)


def find_creature(name):
    creatures = get("/creatures")
    return next((c for c in creatures if name.lower() in c["name"].lower()), None)


def find_expedition(name):
    expeditions = get("/expeditions")
    return next((e for e in expeditions if name.lower() in e["name"].lower()), None)


# ── Output helpers ────────────────────────────────────────────────────────────

def print_json(data):
    print(json.dumps(data, indent=2))


def flatten(data):
    flat = {}
    for k, v in data.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                flat[f"{k}_{kk}"] = vv
        elif isinstance(v, list):
            flat[k] = "; ".join(str(i) for i in v)
        else:
            flat[k] = v
    return flat


def to_csv(rows):
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_creature_list(args):
    creatures = get("/creatures")
    header(f"Creatures  ({len(creatures)} total)")
    print(f"\n  {col('ID', DIM):<8} {col('Name', BOLD):<28} {col('Zone', DIM):<20} {col('Depth (m)', DIM):<18} {col('Bio', DIM)}")
    print(col("  " + "─" * 78, DIM))
    for cr in creatures:
        bio   = col("✦", AMBER) if cr["bioluminescent"] else col("·", DIM)
        depth = f"{cr['depth_min']}–{cr['depth_max']}"
        print(f"  {col(str(cr['id']), DIM):<16} {col(cr['name'], WHITE):<36} {col(cr['habitat_zone'], BLUE):<28} {col(depth, CYAN):<26} {bio}")
    print()


def cmd_creature_get(args):
    if not args.name:
        print(col("  ✗ Provide a creature name: creature get \"Goblin Shark\"", RED))
        sys.exit(1)
    cr = find_creature(args.name)
    if not cr:
        print(col(f"\n  ✗ No creature found matching '{args.name}'", RED))
        sys.exit(1)

    data = get(f"/creatures/{cr['id']}")

    if args.output == "json":
        print_json(data)
        return

    header(data["name"])
    print()
    kv("Scientific name", data["scientific_name"])
    kv("Habitat zone",    data["habitat_zone"],    val_colour=CYAN)
    kv("Depth range",     f"{data['depth_min']}–{data['depth_max']} m")
    kv("Size",            f"{data['size_cm']} cm")
    kv("Bioluminescent",  col("Yes ✦", AMBER) if data["bioluminescent"] else col("No", DIM))
    kv("Discovery year",  data["discovery_year"])
    print()
    print(f"  {col(data['description'], DIM)}")

    if data.get("expedition"):
        exp = data["expedition"]
        section("Discovery Expedition")
        kv("Name",        exp["name"])
        kv("Vessel",      exp["vessel"])
        kv("Institution", exp["institution"])
        kv("Years",       exp["years"])
        kv("Region",      exp["region"])
        kv("Scientist",   exp["lead_scientist"])

    if data.get("zone"):
        z = data["zone"]
        section("Habitat Zone")
        kv("Also known as", z["aka"])
        kv("Depth range",   f"{z['depth_min_m']}–{z['depth_max_m']} m")
        kv("Temperature",   f"{z['temperature_c']} °C")
        kv("Pressure",      f"{z['pressure_atm']} atm")
        kv("Light",         z["light"])
        kv("Oxygen",        f"{z['oxygen_ml_per_l']} ml/L")

    if data.get("specimens"):
        section(f"Specimen Holdings  ({len(data['specimens'])} records)")
        for s in data["specimens"]:
            cond_col = {"live": GREEN, "preserved": BLUE, "skeleton": PINK}.get(s["condition"], WHITE)
            display  = col("  on display", AMBER) if s["on_display"] else ""
            print(f"    {col(s['institution'], WHITE)}, {col(s['city'], DIM)}")
            print(f"    {col(s['condition'], cond_col)}  acq. {col(str(s['acquisition_year']), DIM)}{display}")
            print()
    print()


def cmd_creature_search(args):
    params = []
    if args.zone:
        params.append(f"habitat_zone={urllib.parse.quote(args.zone)}")
    if args.bioluminescent:
        params.append("bioluminescent=true")
    if args.not_bioluminescent:
        params.append("bioluminescent=false")

    query    = "?" + "&".join(params) if params else ""
    creatures = get(f"/creatures{query}")

    filters = []
    if args.zone:               filters.append(f"zone={args.zone}")
    if args.bioluminescent:     filters.append("bioluminescent=yes")
    if args.not_bioluminescent: filters.append("bioluminescent=no")
    label = "  ·  ".join(filters) if filters else "no filters"

    header(f"Search  [{label}]  ({len(creatures)} found)")
    if not creatures:
        print(col("\n  No creatures match those filters.\n", DIM))
        return
    print(f"\n  {col('Name', BOLD):<28} {col('Zone', DIM):<20} {col('Depth (m)', DIM):<18} {col('Bio', DIM)}")
    print(col("  " + "─" * 68, DIM))
    for cr in creatures:
        bio   = col("✦", AMBER) if cr["bioluminescent"] else col("·", DIM)
        depth = f"{cr['depth_min']}–{cr['depth_max']}"
        print(f"  {col(cr['name'], WHITE):<36} {col(cr['habitat_zone'], BLUE):<28} {col(depth, CYAN):<26} {bio}")
    print()


def cmd_creature_foodweb(args):
    if not args.name:
        print(col("  ✗ Provide a creature name: creature foodweb \"Anglerfish\"", RED))
        sys.exit(1)
    cr = find_creature(args.name)
    if not cr:
        print(col(f"\n  ✗ No creature found matching '{args.name}'", RED))
        sys.exit(1)

    data = get(f"/creatures/{cr['id']}/food-web")

    if args.output == "json":
        print_json(data)
        return

    header(f"Food Web  —  {data['name']}")

    if data.get("preys_on"):
        section(f"Preys on  ({len(data['preys_on'])})")
        for p in data["preys_on"]:
            print(f"    {col(p['name'], WHITE)}")
            print(f"    {col(p.get('relationship_notes', ''), DIM)}")
            print()
    else:
        print(col("\n  No prey recorded.", DIM))

    if data.get("preyed_on_by"):
        section(f"Preyed on by  ({len(data['preyed_on_by'])})")
        for p in data["preyed_on_by"]:
            print(f"    {col(p['name'], WHITE)}")
            print(f"    {col(p.get('relationship_notes', ''), DIM)}")
            print()
    else:
        print(col("\n  No predators recorded.", DIM))
    print()


def cmd_expedition_list(args):
    expeditions = get("/expeditions")
    creatures   = get("/creatures")

    counts = {}
    for cr in creatures:
        eid = cr["expedition_id"]
        counts[eid] = counts.get(eid, 0) + 1

    header(f"Expeditions  ({len(expeditions)} total)")
    print(f"\n  {col('Name', BOLD):<38} {col('Years', DIM):<14} {col('Region', DIM):<22} {col('Finds', DIM)}")
    print(col("  " + "─" * 80, DIM))
    for exp in sorted(expeditions, key=lambda e: e["years"]):
        n = counts.get(exp["id"], 0)
        print(f"  {col(exp['name'], WHITE):<46} {col(exp['years'], CYAN):<22} {col(exp['region'], BLUE):<30} {col(str(n), AMBER)}")
    print()


def cmd_expedition_get(args):
    if not args.name:
        print(col("  ✗ Provide a name: expedition get \"Valdivia\"", RED))
        sys.exit(1)
    exp = find_expedition(args.name)
    if not exp:
        print(col(f"\n  ✗ No expedition found matching '{args.name}'", RED))
        sys.exit(1)

    data = get(f"/expeditions/{exp['id']}")

    if args.output == "json":
        print_json(data)
        return

    header(data["name"])
    print()
    kv("Vessel",         data["vessel"])
    kv("Institution",    data["institution"])
    kv("Years",          data["years"])
    kv("Region",         data["region"])
    kv("Lead scientist", data["lead_scientist"])
    kv("Max depth",      f"{data['depth_record_m']:,} m")
    print()
    print(f"  {col(data['description'], DIM)}")

    if data.get("creatures"):
        section(f"Creatures Discovered  ({len(data['creatures'])})")
        for cr in data["creatures"]:
            bio = col(" ✦", AMBER) if cr["bioluminescent"] else ""
            print(f"    {col(cr['name'], WHITE)}{bio}  {col(cr['habitat_zone'], BLUE)}")
    print()


def cmd_specimens(args):
    if not args.name:
        print(col("  ✗ Provide a creature name: specimens \"Firefly Squid\"", RED))
        sys.exit(1)
    cr = find_creature(args.name)
    if not cr:
        print(col(f"\n  ✗ No creature found matching '{args.name}'", RED))
        sys.exit(1)

    specimens = get(f"/creatures/{cr['id']}/specimens")

    if args.output == "json":
        print_json(specimens)
        return

    header(f"Specimens  —  {cr['name']}  ({len(specimens)} records)")
    if not specimens:
        print(col("\n  No specimen records found.\n", DIM))
        return
    print()
    for s in specimens:
        cond_col = {"live": GREEN, "preserved": BLUE, "skeleton": PINK}.get(s["condition"], WHITE)
        display  = col("  on display", AMBER) if s["on_display"] else ""
        print(f"  {col(s['institution'], WHITE)}")
        print(f"  {col(s['city'] + ', ' + s['country'], DIM)}  ·  {col(s['condition'], cond_col)}  ·  acq. {col(str(s['acquisition_year']), DIM)}{display}")
        print()
    print()


def cmd_export(args):
    resource = args.resource
    fmt      = args.format

    if resource == "creatures":
        raw = get("/creatures")
        data = [get(f"/creatures/{cr['id']}") for cr in raw]
    elif resource == "expeditions":
        raw = get("/expeditions")
        data = [get(f"/expeditions/{exp['id']}") for exp in raw]
    else:
        print(col(f"  ✗ Unknown resource '{resource}'. Use: creatures, expeditions", RED))
        sys.exit(1)

    if fmt == "json":
        print_json(data)
    elif fmt == "csv":
        print(to_csv([flatten(d) for d in data]), end="")


def cmd_chain(args):
    if not args.name:
        print(col("  ✗ Provide a creature name: chain \"Goblin Shark\"", RED))
        sys.exit(1)

    print()
    print(col(f"  API Chain Demo  —  {args.name}", BOLD + CYAN))
    print(col("  " + "─" * 56, DIM))
    print()

    creatures, t1 = timed_get("/creatures", "GET /creatures")
    cr = next((c for c in creatures if args.name.lower() in c["name"].lower()), None)
    if not cr:
        print(col(f"\n  ✗ No creature found matching '{args.name}'", RED))
        sys.exit(1)

    cid = cr["id"]
    eid = cr["expedition_id"]
    print(col(f"    matched: {cr['name']}  (id={cid}, expedition_id={eid})", DIM))
    print()

    detail,     t2 = timed_get(f"/creatures/{cid}",          f"GET /creatures/{cid}             (creature + zone + specimens joined)")
    foodweb,    t3 = timed_get(f"/creatures/{cid}/food-web",  f"GET /creatures/{cid}/food-web    (predator/prey chain)")
    expedition, t4 = timed_get(f"/expeditions/{eid}",         f"GET /expeditions/{eid}            (expedition + creatures joined)")

    total = t1 + t2 + t3 + t4
    print()
    print(col(f"  4 requests completed in {total}ms total", GREEN))
    print()

    section("Assembled Profile")
    kv("Name",         detail["name"])
    kv("Zone",         detail["habitat_zone"])
    kv("Depth",        f"{detail['depth_min']}–{detail['depth_max']} m")
    kv("Expedition",   expedition["name"])
    kv("Scientist",    expedition["lead_scientist"])
    kv("Specimens",    len(detail.get("specimens", [])))
    kv("Preys on",     ", ".join(p["name"] for p in foodweb.get("preys_on", [])) or "none recorded")
    kv("Preyed on by", ", ".join(p["name"] for p in foodweb.get("preyed_on_by", [])) or "none recorded")
    print()


def cmd_info(args):
    header("Deep Sea Database — Project Info")
    print()
    kv("API base URL",      API)
    kv("llama-server URL",  config["llama_server_url"])
    kv("Allowed dir",       config["allowed_dir"])
    kv("Data dir",          config["data_dir"])
    print()
    print(f"  {col('Checking API status...', DIM)}", end="", flush=True)
    try:
        stats = get("/stats")
        print(col("  ✓ online", GREEN))
        print()
        kv("Creatures",    stats["total"])
        kv("Expeditions",  stats["total_expeditions"])
        kv("Specimens",    stats["total_specimens"])
        kv("Institutions", stats["total_institutions"])
        kv("Countries",    stats["total_countries"])
        kv("Bioluminescent", f"{stats['bioluminescent_count']} ({stats['bioluminescent_pct']}%)")
        print()
        section("Zone Breakdown")
        for zone, count in stats["zones"].items():
            bar = col("█" * count, CYAN)
            print(f"    {col(zone, WHITE):<22} {bar}  {col(str(count), DIM)}")
    except SystemExit:
        pass
    print()


# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="deepseacli",
        description="Deep Sea Creature Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python cli/deepseacli.py creature list
  python cli/deepseacli.py creature get "Goblin Shark"
  python cli/deepseacli.py creature search --zone "Bathyal Zone" --bioluminescent
  python cli/deepseacli.py creature foodweb "Anglerfish"
  python cli/deepseacli.py expedition list
  python cli/deepseacli.py expedition get "Valdivia"
  python cli/deepseacli.py specimens "Firefly Squid"
  python cli/deepseacli.py export creatures --format csv > creatures.csv
  python cli/deepseacli.py export expeditions --format json
  python cli/deepseacli.py chain "Goblin Shark"
  python cli/deepseacli.py info
        """
    )

    sub = parser.add_subparsers(dest="command")

    # creature
    creature_p   = sub.add_parser("creature", help="Creature commands")
    creature_sub = creature_p.add_subparsers(dest="subcommand")

    creature_sub.add_parser("list", help="List all creatures")

    cget = creature_sub.add_parser("get", help="Get full creature detail")
    cget.add_argument("name", nargs="?")
    cget.add_argument("--output", choices=["table", "json"], default="table")

    csearch = creature_sub.add_parser("search", help="Filter creatures")
    csearch.add_argument("--zone")
    csearch.add_argument("--bioluminescent", action="store_true")
    csearch.add_argument("--not-bioluminescent", action="store_true", dest="not_bioluminescent")
    csearch.add_argument("--output", choices=["table", "json"], default="table")

    cfw = creature_sub.add_parser("foodweb", help="Show predator/prey relationships")
    cfw.add_argument("name", nargs="?")
    cfw.add_argument("--output", choices=["table", "json"], default="table")

    # expedition
    exp_p   = sub.add_parser("expedition", help="Expedition commands")
    exp_sub = exp_p.add_subparsers(dest="subcommand")

    exp_sub.add_parser("list", help="List all expeditions")

    eget = exp_sub.add_parser("get", help="Get full expedition detail")
    eget.add_argument("name", nargs="?")
    eget.add_argument("--output", choices=["table", "json"], default="table")

    # specimens
    spec_p = sub.add_parser("specimens", help="Specimen holdings for a creature")
    spec_p.add_argument("name", nargs="?")
    spec_p.add_argument("--output", choices=["table", "json"], default="table")

    # export
    export_p = sub.add_parser("export", help="Export data as JSON or CSV")
    export_p.add_argument("resource", choices=["creatures", "expeditions"])
    export_p.add_argument("--format", choices=["json", "csv"], default="json")

    # chain
    chain_p = sub.add_parser("chain", help="Live API chain demo for a creature")
    chain_p.add_argument("name", nargs="?")

    # info
    sub.add_parser("info", help="Project info and API status")

    return parser


def main():
    parser = build_parser()
    args   = parser.parse_args()

    dispatch = {
        "creature":   lambda: (
            cmd_creature_list(args)    if args.subcommand == "list"    else
            cmd_creature_get(args)     if args.subcommand == "get"     else
            cmd_creature_search(args)  if args.subcommand == "search"  else
            cmd_creature_foodweb(args) if args.subcommand == "foodweb" else
            creature_p.print_help()
        ),
        "expedition": lambda: (
            cmd_expedition_list(args) if args.subcommand == "list" else
            cmd_expedition_get(args)  if args.subcommand == "get"  else
            parser.parse_args(["expedition", "--help"])
        ),
        "specimens":  lambda: cmd_specimens(args),
        "export":     lambda: cmd_export(args),
        "chain":      lambda: cmd_chain(args),
        "info":       lambda: cmd_info(args),
    }

    if args.command in dispatch:
        dispatch[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
