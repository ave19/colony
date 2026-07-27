# Colony — Tech & materials book (v1)

Playable industrial graph for ~**2200** (optimistic: practical fusion, serious ISRU, high‑Isp electric).  
Everything is **known** on arrival. Nothing is “unlocked.” Only **mass, power, parts, labor, time, and location** decide what completes.

Related: [PLAYABLE_LADDER.md](./PLAYABLE_LADDER.md) · GitHub A10 (#12)

---

## 1. Design rules

| Rule | Meaning |
|------|---------|
| No research tree | Full know-how from day 0 |
| Visible paths | You can always see fusion, shipyard, colony ship — and every missing leg |
| Physics + logistics only | Rates, prerequisites as **objects/products**, not fog |
| Contracts are contextual | Ore vs refined vs finished depends on local plants |
| Inefficient ≠ illegal | Bad siting is slow, not unplayable |
| Banished soul | Needs create work; assign labor; watch the graph run |
| Ark is bootstrap, not god | Slow basic production; cannot spew megastructures from the craft queue alone |
| No hard wipe | Ark sustains ~10k people indefinitely; setbacks, not game over |
| Win is demographic + industrial | Outbound ships need **~10k founders** each; ship **rate** is the score |

### Arrival state

- You **are** a colony ship another system built (replay loop).
- **~10k people** aboard; closed life support already proven over centuries.
- **Xe (ion propellant) spent** on capture / stop-in-orbit.
- Seed stocks, e.g. order-of **~1000 t iron-class metals** plus thinner amounts of other atoms — enough for hundreds of small builds, not infinite spam.
- Tiny onboard fabs (foundry, chip line, chem, machine shop) at **very low rate**.

### Outbound colony ship (endgame unit)

Minimum meaningful export:

- **~10k founders** (minimum breeding / society size)
- Fusion power + large ion drive farm + **full Xe (or Ar) load** for the voyage
- Radiators, magnets, structure, ECLSS, amenities mass
- Seed industry kit (bots, sats, small fabs, seed stocks) for the *next* system
- Built in an **orbital shipyard** large enough to assemble it
- Emigration: willing fraction of population only when a ship is **ready**; if 10k is most of your pop, you get one ship and then a long recovery

---

## 2. Skinny atom set

### Bulk (almost every system has some path)

| ID | Name | Role |
|----|------|------|
| `Fe` | Iron | Structure, machines, steel |
| `Ni` | Nickel | Asteroid flavor; steel alloys (can soft-merge with Fe early) |
| `Al` | Aluminum | Light structure; wiring substitute for Cu (worse mass/losses) |
| `Si` | Silicon | Glass, solar, chip feedstock |
| `C` | Carbon | Organics, composites, CH₄ chemistry |
| `H` | Hydrogen | Water, propellant chemistry, fusion fuel leg |
| `O` | Oxygen | Water, oxidizer, life support |
| `N` | Nitrogen | Air, fertilizer — easy to forget, shapes some systems |

### Strategic (shape the run)

| ID | Name | Role |
|----|------|------|
| `Cu` | Copper | Good electrical path |
| `U` | Fissile | Fission power (abstracted; not full actinide chemistry) |
| `Xe` | Xenon | Preferred ion propellant |
| `Ar` | Argon | Dirtier/cheaper ion gas; worse performance than Xe |
| `Li` | Lithium | Batteries / light electrochem |
| `MAG` | Magnet feedstock | One bag for Nb/REE/superconductor alloy path |
| `He` | Cryogen (helium-class) | Magnet / fusion support |

### Named compounds / goods (UI language)

| ID | Name | Notes |
|----|------|-------|
| `H2O` | Water | Ice, oceans, electrolysis feedstock |
| `CH4` | Methane | Atmosphere scoop (Titan-like) or synth |
| `O2` | Oxygen | Oxidizer + breathing |
| `H2` | Hydrogen | High-performance chem propellant leg |
| `steel` | Steel | Structural bulk from Fe (+ power) |
| `al_plate` | Aluminum plate | Light structure |
| `wafer` | Silicon wafer | Toward panels/chips |
| `panel` | Solar panel | Power, star- and distance-limited |
| `chip` | Computer chip | Guidance, fabs, automation |
| `magnet` | Superconducting magnet assembly | Fusion + advanced electric |
| `radiator` | Radiator segment | Waste heat; mass sinks for nuclear/electric |
| `pressure_vessel` | Pressure vessel / tank | Hab, propellant, process |
| `fertilizer` | Fertilizer | Farms (N + other bulk) |
| `air_mix` | Breathable air | N₂ + O₂ (+ scrubbing) |
| `food` | Food | Farms + stores |
| `chem_prop` | Chemical propellant pack | e.g. CH₄/O₂ or H₂/O₂ blend as cargo |
| `ion_prop` | Ion propellant | Xe or Ar loaded for electric drives |
| `fusion_fuel` | Fusion fuel | Abstracted D/T or D–³He path for v1 |

---

## 3. Power

All known. Materials and siting decide feasibility.

| Source | Needs (skinny) | Notes |
|--------|----------------|-------|
| **Chemical** | Fuel + oxidizer or burnable + air; genset parts | Bootstrap; dirty; easy |
| **Solar** | `panel`s | Scales with **stellar luminosity × distance**; weak at M-dwarfs / outer system |
| **Fission** | `U`, structure, `radiator`s, plant parts | Dark-side baseload |
| **Fusion** | `magnet`s, `He` cryogen, `fusion_fuel`, plant, large `radiator`s | Visible path; heavy prerequisites |

**Waste heat** is first-class: nuclear and high-power electric want **radiator mass**.

---

## 4. Propulsion & mobility

| Mode | Consumes | Role |
|------|----------|------|
| Chemical rocket | `chem_prop` (CH₄/O₂ or H₂/O₂) | Landers, tugs, propulsive landing |
| Ion / electric | `ion_prop` (Xe preferred, Ar OK) + **large continuous power** | Efficient hauls; colony-ship main drive |
| Surface vehicles | power and/or chemical | Base local transport |
| Ocean vessels | hull + power | Ocean worlds / seas |
| Aircraft | atmosphere + power/chem | Only if air density allows |

Transfer planning offers **physics-derived options** (e.g. low propellant / long time vs high propellant / shorter time).  
Δv to **orbit** and **escape** is real. Gravity wells are not free.

---

## 5. Manufacturing DAG

```text
Environment (ore, ice, atmosphere, ocean)
  → Extract / scoop / electrolyze
  → Refine (power + plant)
  → Stockpile (form depends on local industry)
  → Fabricate parts
  → Assemble modules / vehicles / plants
  → Large assemblies need real berths, power, cranes (shipyard objects)
```

### Core processes (v1)

| Process | Inputs (skinny) | Outputs |
|---------|-----------------|---------|
| Mine / extract | deposit access, power, bots/people | ore (Fe, Al, Si, U, Li, MAG, …) |
| Atmosphere scoop | body atmosphere, power, scoop plant | e.g. `CH4` |
| Ice/water handle | ice/ocean access, power | `H2O` |
| Electrolysis | `H2O`, power | `H2`, `O2` |
| Methane/ox blend | `CH4`, `O2` | `chem_prop` |
| Foundry / refine Fe | Fe ore, power | `steel` / refined Fe |
| Refine Al | Al ore, power | `al_plate` / refined Al |
| Si path | Si feedstock, power | `wafer` |
| Panel line | `wafer`, parts, power | `panel` |
| Chip fab | `wafer`, power, time, fab building | `chip` |
| Magnet line | `MAG`, `He`, power, fab | `magnet` |
| Radiator line | metal plate, power | `radiator` |
| Chem plant | C/H/O/N as needed, power | air, fertilizer precursors, propellant legs |
| Fabricator | plate/bar + `chip` (light) + power | engines, bots, frames, plant kits |
| Bot factory | parts, power, labor | mining bots, haul drones, etc. |
| Farm | water, fertilizer, power, labor, habitat volume | `food` |
| ECLSS | power, spare parts, volatiles | sustained air/water loop |
| Shipyard berth | huge steel/Al, power, cranes, orbital site | capacity to assemble colony ships |
| Colony ship integrate | berth + fusion + ion farm + prop load + ECLSS + 10k people + seed | outbound ship |

### Substitutes (examples)

| Preferred | Substitute | Penalty |
|-----------|------------|---------|
| `Cu` wiring | `Al` wiring | More mass, higher losses |
| `Xe` ion prop | `Ar` | Worse Isp / more prop mass for same Δv |
| `Al` structure | `steel` | Heavier vehicle → more Δv/propellant |
| Ground chip fab | Ark / space tiny fab | Rate and maybe yield; huge ground fabs need settlement industry |

### Contract forms (contextual)

If the need is “iron for project X”:

- Local **refinery** → contracts for **ore** (+ power/labor implied by plant)
- No refinery → contracts for **refined metal**
- No mine but fab → import finished **parts**

Same pattern for Li, CH₄, chips, magnets, etc.

**Example:** Titan-like moon has free-ish atmospheric `CH4` via scoop, but chemical rockets also need `O2` — ice electrolysis, import, or another body. Lift still costs **Δv**.

---

## 6. Labor (Banished-like)

| Pool | Needs | Notes |
|------|-------|-------|
| **People** | air, water, food, habitat, amenities (bowling alleys, etc.) | Natural growth; required for “win” / outbound founders |
| **Robots** | power, propulsion/mobility, maintenance parts | Can build more robots; no food |

Work assignment is **agnostic**: either pool can staff an operation if present.  
Population growth is **natural** (not “move ark A into ship B and done”).  
Theme: humanity settles the stars; robots amplify industry.

---

## 7. World → deposits (formation priors)

Generator maps features from science-ish parameters (star type, distance, mass, gravity, volatiles budget) — not pure loot tables.

Examples:

| Prior | Likely feature |
|-------|----------------|
| Cold + high water | Surface ice; possible subsurface ocean |
| Past snow line | Volatile-rich small bodies |
| Differentiated / metallic asteroids | Fe/Ni |
| Thick reducing atmosphere | CH₄ / organics scoop targets |
| M-dwarf + close orbit | Weak or harsh solar power story |
| Trace atmosphere / no N source | Nitrogen crisis for big open-air biomes |

**Scan** turns priors into measured grades and mineable sites.  
Approach over years: large planets known early; deposits not free.

---

## 8. Colony Director (later, milestone C)

- Suggests **goals** from known state + this graph  
- Goals → needs → contracts (same pipeline as humans)  
- Optional auto mode uses **only legal actions** (no free mass/energy)

---

## 9. Milestone A implementation cut

### Build for real in A

- Atoms/goods: `Fe`, `Al`, `Si`, `H2O`, `CH4`, `O2`, `steel`, `panel`, `chip`, `chem_prop` (thin set OK)
- Power: chemical + solar
- Propulsion: chemical hauls/landers; Δv orbit/escape; transfer options
- Processes: mine, scoop or ice, refine Fe, fabricator basics, tiny ark fabs
- Actors: ark, scan sats, mining bots, haulers
- Goals → needs → contracts for one base plan
- Labor pools stub OK (even if simplified numbers)

### Present in data, not required to finish A

- Fission, fusion, magnets, He, Xe/Ar full loop
- Ocean/air craft
- Full colony-ship BOM and shipyard
- Emigration fraction / 10k outbound (can stub UI)

### Explicit non-goals for v1 fidelity

- Full rare-earth chemistry
- Real semiconductor dopant lists
- True n-body or full thermo sim
- Stoichiometry textbook precision (planning-visible medium depth only)

---

## 10. Open balance knobs (not design forks)

- Exact tonnes for seed stocks  
- Exact emigration fraction  
- Panel output vs star tables  
- Chip fab rates (ark vs ground)  
- Magnet / fusion mass budgets  

Tune in playtests; keep the graph shape stable.

---

## 11. One-page “Apollo skinny” checklist

To reproduce industrial civilization in a new system:

1. Power (chem → solar → nuclear as materials allow)  
2. Propellant loop (water/CH₄/O₂ and/or ion gas + power)  
3. Metals (Fe/Al) + foundry  
4. Silicon → panels/chips  
5. Habitats + food + N for people growth  
6. Bots to multiply labor  
7. Magnets + cryogen + fusion fuel → fusion  
8. Big ion + Xe/Ar load  
9. Orbital shipyard  
10. 10k people to spare + outfit → **next colony ship**

That is the game.
