"""
async_agent.py — demonstrates two async API call patterns:

Pattern 1 — Concurrent startup fetch:
  All 5 data files are fetched simultaneously with asyncio.gather on startup.
  Questions are answered from the combined in-memory dataset.

Pattern 2 — Fan-out per creature:
  Given a creature name, concurrently fetch its zone detail, expedition detail,
  specimen records, and food-web from 4 simultaneous API requests, then
  assemble a complete profile and pass it to the LLM to reason about.
"""

import asyncio
import json
from typing import Union
import aiohttp
from openai import OpenAI
from shared.config import config

API_BASE = f"http://localhost:{config['api_port']}"
LLM_BASE = f"{config['llama_server_url']}/v1"

client = OpenAI(base_url=LLM_BASE, api_key="none")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

async def fetch(session: aiohttp.ClientSession, url: str) -> Union[dict, list]:
    async with session.get(url) as resp:
        resp.raise_for_status()
        return await resp.json()


# ── Pattern 1: Concurrent startup fetch ──────────────────────────────────────

async def load_all_data() -> dict:
    """Fetch all 5 endpoints simultaneously and return as a combined dict."""
    print("  [async] Fetching all data sources concurrently...")
    async with aiohttp.ClientSession() as session:
        creatures, expeditions, zones, specimens, stats = await asyncio.gather(
            fetch(session, f"{API_BASE}/creatures"),
            fetch(session, f"{API_BASE}/expeditions"),
            fetch(session, f"{API_BASE}/zones"),
            fetch(session, f"{API_BASE}/specimens"),
            fetch(session, f"{API_BASE}/stats"),
        )
    print("  [async] All data loaded.\n")
    return {
        "creatures":   creatures,
        "expeditions": expeditions,
        "zones":       zones,
        "specimens":   specimens,
        "stats":       stats,
    }


def answer_from_data(data: dict, question: str) -> str:
    """Pass the full combined dataset to the LLM and ask the question."""
    summary = json.dumps(data, indent=2)
    response = client.chat.completions.create(
        model="local",
        messages=[
            {
                "role": "system",
                "content": (
                    "/no-think\n"
                    "You are a marine biology research assistant. "
                    "Answer questions using only the data provided. Be concise and precise."
                ),
            },
            {
                "role": "user",
                "content": f"Here is the complete database:\n\n{summary}\n\nQuestion: {question}",
            },
        ],
    )
    return response.choices[0].message.content


# ── Pattern 2: Fan-out per creature ──────────────────────────────────────────

async def fetch_creature_profile(creature_id: int) -> dict:
    """
    Given a creature id, concurrently fetch:
      - full creature detail (with expedition + zone + specimens joined)
      - food-web (predators and prey)
    Two simultaneous requests assembling a complete profile.
    """
    print(f"  [async] Fan-out: fetching creature profile + food-web concurrently for id {creature_id}...")
    async with aiohttp.ClientSession() as session:
        detail, food_web = await asyncio.gather(
            fetch(session, f"{API_BASE}/creatures/{creature_id}"),
            fetch(session, f"{API_BASE}/creatures/{creature_id}/food-web"),
        )
    print("  [async] Profile assembled.\n")
    return {
        "detail":   detail,
        "food_web": food_web,
    }


def answer_from_profile(profile: dict, question: str) -> str:
    """Pass the creature profile to the LLM and ask the question."""
    summary = json.dumps(profile, indent=2)
    response = client.chat.completions.create(
        model="local",
        messages=[
            {
                "role": "system",
                "content": (
                    "/no-think\n"
                    "You are a marine biology research assistant. "
                    "Answer questions using only the data provided. Be concise and precise."
                ),
            },
            {
                "role": "user",
                "content": f"Here is a complete creature profile:\n\n{summary}\n\nQuestion: {question}",
            },
        ],
    )
    return response.choices[0].message.content


def find_creature_id(creatures: list, name: str) -> Union[int, None]:
    name_lower = name.lower()
    for c in creatures:
        if name_lower in c["name"].lower():
            return c["id"]
    return None


# ── Main interactive loop ─────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  Async Deep Sea Agent")
    print("=" * 60)
    print()

    # Pattern 1: load all data upfront concurrently
    print("Pattern 1 — Loading all data sources concurrently on startup:")
    data = await load_all_data()

    print("Ready. Ask questions about the full database, or type:")
    print("  profile <creature name>  — switch to Pattern 2 fan-out mode")
    print("  exit                     — quit\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "exit":
            break

        if user_input.lower().startswith("profile "):
            # Pattern 2: fan-out for a specific creature
            name = user_input[8:].strip()
            creature_id = find_creature_id(data["creatures"], name)
            if not creature_id:
                print(f"\nAgent: No creature found matching '{name}'. Try another name.\n")
                continue
            print(f"\nPattern 2 — Fan-out: assembling full profile for '{name}':")
            profile = await fetch_creature_profile(creature_id)
            question = f"Give me a complete summary of the {name}: its biology, where it lives, which expedition found it, its food web, and where specimens are held."
            result = answer_from_profile(profile, question)
        else:
            # Pattern 1: answer from preloaded data
            result = answer_from_data(data, user_input)

        print(f"\nAgent: {result}\n")


if __name__ == "__main__":
    asyncio.run(main())
