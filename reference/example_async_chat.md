```
============================================================
  Async Deep Sea Agent
============================================================

Pattern 1 — Loading all data sources concurrently on startup:
  [async] Fetching all data sources concurrently...
  [async] All data loaded.

Ready. Ask questions about the full database, or type:
  profile <creature name>  — switch to Pattern 2 fan-out mode
  exit                     — quit

You: Tell me about the Stoplight Loosejaw. Include predator and prey relationships, discovery data and collection information.  
Agent: The Stoplight Loosejaw (*Malacosteus niger*) is a deep-sea fish found in the Midnight Zone (1000-4000m depth). It's the only known fish capable of producing and seeing red bioluminescent light, giving it a secret searchlight invisible to prey. Its jawbones are unconnected to its skull, allowing it to open its mouth impossibly wide.

Discovery data:
- Discovered in 1841
- First specimen collected during the HMS Challenger Expedition (1872-1876)
- Named by Charles Wyville Thomson

Collection information:
- Specimens held at Natural History Museum (London) - acquired in 1845
- Specimens held at Muséum National d'Histoire Naturelle (Paris) - acquired in 1856
- Specimens held at Scripps Institution of Oceanography (La Jolla) - acquired in 1961

The Stoplight Loosejaw's prey includes small fish and crustaceans, while its primary predator is likely larger deep-sea sharks and fish that have adapted to the extreme depths where it lives.

This species demonstrates a unique evolutionary adaptation for deep-sea predation through its red bioluminescence and specialized jaw structure.

You: What other creatures are found in the same zone as the Stoplight Loosejaw that were discovered on different expiditions?

Agent: Looking at the data:

1. The Stoplight Loosejaw (creature_id 12) is in the Midnight Zone and was discovered on expedition 1.

2. In the Midnight Zone, there are 4 creatures total:
   - Vampire Squid (expedition 3)
   - Anglerfish (expedition 1) 
   - Siphonophore (expedition 2)
   - Stoplight Loosejaw (expedition 1)

3. Excluding the Stoplight Loosejaw itself, the other creatures in the Midnight Zone were discovered on expeditions 2 and 3.

Therefore, the creatures found in the same zone as the Stoplight Loosejaw that were discovered on different expeditions are:
- Vampire Squid (discovered on expedition 3)
- Siphonophore (discovered on expedition 2)

You: 

```

```
============================================================
  Async Deep Sea Agent
============================================================

Pattern 1 — Loading all data sources concurrently on startup:
  [async] Fetching all data sources concurrently...
  [async] All data loaded.

Ready. Ask questions about the full database, or type:
  profile <creature name>  — switch to Pattern 2 fan-out mode
  exit                     — quit

You: profile goblin shark

Pattern 2 — Fan-out: assembling full profile for 'goblin shark':
  [async] Fan-out: fetching creature profile + food-web concurrently for id 10...
  [async] Profile assembled.


Agent: The Goblin Shark (*Mitsukurina owstoni*) is a deep-sea predator living in the Bathyal Zone (Continental Slope Zone) at depths of 270-1300 meters. It has an elongated snout packed with electroreceptors and a unique jaw-slingshot mechanism for capturing prey.

Found during the Albatross Pacific Expedition (1891-1905) aboard the USFC Albatross, led by Alexander Agassiz, this species was first scientifically documented in 1898. The expedition was the first dedicated oceanographic survey vessel and collected thousands of deep-sea specimens.

In its food web, the goblin shark preys on Sea Pigs (*Scotoplanes globosa*) and Giant Isopods (*Bathynomus giganteus*), both found in deep-sea environments. It is not preyed upon by other species.

Specimens are held at:
- Tokyo Sea Life Park (Japan) - preserved specimen acquired in 2004
- Smithsonian Institution (USA) - preserved specimen acquired in 1902  
- Natural History Museum (UK) - skeleton specimen acquired in 1900

You: profile Anglerfish

Pattern 2 — Fan-out: assembling full profile for 'Anglerfish':
  [async] Fan-out: fetching creature profile + food-web concurrently for id 2...
  [async] Profile assembled.


Agent: **Anglerfish Summary**

**Biology**: The Anglerfish (*Melanocetus johnsonii*) is a deep-sea predator with a bioluminescent lure on a stalk extending from the female's head. Males are tiny parasites that permanently fuse to females, sharing their bloodstream.

**Habitat**: Lives in the Midnight Zone (Bathypelagic Zone) at depths of 200-2000 meters, where temperatures are near freezing and pressure is crushing. This zone receives no sunlight, with food scarce and marine snow as primary sustenance.

**Discovery**: First documented during the HMS Challenger Expedition (1872-1876), the first true oceanographic expedition that sailed 68,890 nautical miles and established modern marine biology foundations.

**Food Web**: 
- Preys on Firefly Squid and Barreleye Fish
- Firefly Squid: Ambushed by anglerfish lures in overlapping depth ranges (200-400m)
- Barreleye Fish: Consumed when they stray into deeper waters during vertical migrations

**Specimens**: 
1. Monterey Bay Aquarium (Monterey, USA) - live specimen acquired in 1998
2. Smithsonian Institution (Washington D.C., USA) - preserved specimen acquired in 1945
3. Museum Victoria (Melbourne, Australia) - preserved specimen acquired in 1987

You: 
```
