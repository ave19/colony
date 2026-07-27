"""Tech / materials graph (milestone A subset + visible later paths)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Recipe:
    id: str
    name: str
    inputs: Dict[str, float]  # resource -> tonnes (or units)
    outputs: Dict[str, float]
    power_mw: float
    months: float  # base time for one batch at 1× scale
    building: Optional[str] = None  # required building type on site
    description: str = ""


@dataclass
class BuildingType:
    id: str
    name: str
    build_cost: Dict[str, float]
    description: str
    provides: List[str] = field(default_factory=list)  # recipe ids or tags


# Resources display names
RESOURCE_NAMES = {
    "Fe": "Iron",
    "Al": "Aluminum",
    "Si": "Silicon",
    "H2O": "Water",
    "CH4": "Methane",
    "O2": "Oxygen",
    "steel": "Steel",
    "panel": "Solar panel",
    "chip": "Computer chip",
    "chem_prop": "Chemical propellant",
    "wafer": "Silicon wafer",
    "al_plate": "Aluminum plate",
    "U": "Fissile",
    "Xe": "Xenon",
    "Ar": "Argon",
    "MAG": "Magnet feedstock",
    "He": "Cryogen",
    "magnet": "Superconducting magnet",
    "fusion_fuel": "Fusion fuel",
    "radiator": "Radiator",
    "food": "Food",
    "N": "Nitrogen",
}


BUILDINGS = {
    "extractor": BuildingType(
        "extractor",
        "Extractor",
        {"steel": 20, "chip": 2},
        "Mines local deposits.",
        ["mine"],
    ),
    "refinery": BuildingType(
        "refinery",
        "Iron refinery",
        {"steel": 40, "chip": 4},
        "Turns Fe ore into steel. Power hungry.",
        ["refine_fe"],
    ),
    "chem_plant": BuildingType(
        "chem_plant",
        "Chem plant",
        {"steel": 30, "chip": 3},
        "Electrolysis and propellant blending.",
        ["electrolysis", "blend_prop"],
    ),
    "scoop": BuildingType(
        "scoop",
        "Atmosphere scoop",
        {"steel": 25, "al_plate": 10, "chip": 3},
        "Harvests CH4 (and similar) from thick atmospheres.",
        ["scoop_ch4"],
    ),
    "solar_farm": BuildingType(
        "solar_farm",
        "Solar farm",
        {"panel": 50, "steel": 10, "chip": 2},
        "Local power from starlight.",
        ["power_solar"],
    ),
    "habitat": BuildingType(
        "habitat",
        "Underground habitat",
        {"steel": 80, "chip": 5, "H2O": 20},
        "Pressurized living volume.",
        ["hab"],
    ),
    "fab": BuildingType(
        "fab",
        "Fabricator",
        {"steel": 35, "chip": 8},
        "Parts and panels from feedstock.",
        ["make_panel", "make_wafer"],
    ),
    "refuel_depot": BuildingType(
        "refuel_depot",
        "Refueling depot",
        {"steel": 40, "chip": 3, "chem_prop": 35, "Al": 12},
        "Stores propellant and refills unit Δv budgets. Seed stock of chem_prop on deploy.",
        ["refuel"],
    ),
}


RECIPES = {
    "refine_fe": Recipe(
        "refine_fe",
        "Refine iron → steel",
        {"Fe": 1.2},
        {"steel": 1.0},
        power_mw=5.0,
        months=0.05,
        building="refinery",
        description="Smelt and roll structural steel.",
    ),
    "electrolysis": Recipe(
        "electrolysis",
        "Electrolyze water",
        {"H2O": 1.0},
        {"O2": 0.89, "H2": 0.11},
        power_mw=8.0,
        months=0.02,
        building="chem_plant",
    ),
    "blend_prop": Recipe(
        "blend_prop",
        "Blend CH4/O2 propellant",
        {"CH4": 0.4, "O2": 0.6},
        {"chem_prop": 1.0},
        power_mw=1.0,
        months=0.01,
        building="chem_plant",
    ),
    "scoop_ch4": Recipe(
        "scoop_ch4",
        "Scoop atmospheric methane",
        {},
        {"CH4": 10.0},
        power_mw=3.0,
        months=0.1,
        building="scoop",
        description="Requires CH4-bearing atmosphere on the body.",
    ),
    "make_wafer": Recipe(
        "make_wafer",
        "Silicon wafers",
        {"Si": 1.0},
        {"wafer": 0.8},
        power_mw=4.0,
        months=0.08,
        building="fab",
    ),
    "make_panel": Recipe(
        "make_panel",
        "Solar panels",
        {"wafer": 0.5, "al_plate": 0.2, "chip": 0.05},
        {"panel": 1.0},
        power_mw=2.0,
        months=0.1,
        building="fab",
    ),
    "ark_steel": Recipe(
        "ark_steel",
        "Ark foundry (trickle steel)",
        {"Fe": 1.2},
        {"steel": 1.0},
        power_mw=2.0,
        months=0.2,
        building=None,
        description="Colony ship tiny foundry — slow.",
    ),
    "ark_chip": Recipe(
        "ark_chip",
        "Ark chip line (trickle)",
        {"Si": 0.5, "Al": 0.1},
        {"chip": 1.0},
        power_mw=3.0,
        months=0.5,
        building=None,
        description="Colony ship tiny chip fab — very slow.",
    ),
    "ark_panel": Recipe(
        "ark_panel",
        "Ark panel line",
        {"Si": 0.4, "Al": 0.3, "chip": 0.1},
        {"panel": 1.0},
        power_mw=2.0,
        months=0.3,
        building=None,
    ),
    "ark_prop": Recipe(
        "ark_prop",
        "Ark chem prop from stocks",
        {"CH4": 0.4, "O2": 0.6},
        {"chem_prop": 1.0},
        power_mw=1.0,
        months=0.05,
        building=None,
    ),
}


# Base plan templates: goal options → bill of materials / buildings
POWER_OPTIONS = {
    "solar": {
        "name": "Solar",
        "buildings": ["solar_farm"],
        "materials": {"panel": 50, "steel": 15, "chip": 4},
        "description": "Depends on star type and distance. Weak at red dwarfs / outer system.",
    },
    "chemical": {
        "name": "Chemical genset",
        "buildings": [],
        "materials": {"steel": 20, "chem_prop": 40, "chip": 2},
        "description": "Bootstrap power. Burns propellant — not sustainable long-term.",
    },
    "fusion": {
        "name": "Fusion (path visible)",
        "buildings": [],
        "materials": {"magnet": 40, "He": 20, "fusion_fuel": 10, "radiator": 80, "steel": 200, "chip": 50},
        "description": "You can see the whole path. Magnets, cryogen, fuel, radiators — years of industry.",
    },
}

HAB_OPTIONS = {
    "underground": {
        "name": "Underground habitat",
        "buildings": ["habitat", "extractor", "refinery"],
        "materials": {"steel": 120, "chip": 10, "H2O": 30},
        "description": "Mine volume, refine iron for structure, seal habitat.",
    },
    "surface": {
        "name": "Surface habitat",
        "buildings": ["habitat", "solar_farm"],
        "materials": {"steel": 100, "panel": 30, "chip": 8, "H2O": 25},
        "description": "Faster to place; more radiation / weather exposure.",
    },
}


def expand_base_plan(power_id: str, hab_id: str) -> dict:
    """Expand goal options into aggregated materials and buildings."""
    power = POWER_OPTIONS[power_id]
    hab = HAB_OPTIONS[hab_id]
    materials: Dict[str, float] = {}
    for src in (power, hab):
        for k, v in src["materials"].items():
            materials[k] = materials.get(k, 0.0) + v
    buildings = list(dict.fromkeys(power["buildings"] + hab["buildings"]))
    return {
        "power": power,
        "hab": hab,
        "buildings": buildings,
        "materials": materials,
        "notes": [
            power["description"],
            hab["description"],
            "Contracts will request ore vs refined goods based on what you already operate.",
        ],
    }


# Units the ark can fabricate after arrival (materials + time — not pre-packed).
# dv_capacity_m_s: onboard Δv budget for units that burn propellant from tanks
# (survey probes are ion / high-Isp with a fixed tank — not free infinite moves).
UNIT_BUILDS = {
    "survey": {
        "id": "survey",
        "name": "Survey satellite",
        "kind": "survey",
        "cost": {"steel": 8.0, "chip": 4.0, "panel": 2.0, "Al": 3.0},
        "months": 1.5,
        "capabilities": ["survey"],
        "dv_capacity_m_s": 12000.0,
        "description": "Remote sensors for extraction sites. Fixed ion propellant budget — return to ark or a depot to refuel.",
    },
    "miner": {
        "id": "miner",
        "name": "Mining bot",
        "kind": "miner",
        "cost": {"steel": 15.0, "chip": 3.0, "panel": 1.0},
        "months": 2.0,
        "capabilities": ["mine"],
        "dv_capacity_m_s": 6000.0,
        "description": "Surface/asteroid extractor. Needs a surveyed mine site before it can dig.",
    },
    "hauler": {
        "id": "hauler",
        "name": "Hauler",
        "kind": "hauler",
        "cost": {"steel": 25.0, "chip": 2.0, "chem_prop": 10.0, "Al": 5.0},
        "months": 2.5,
        "capabilities": ["haul"],
        "dv_capacity_m_s": 8000.0,
        "description": "Chemical tug for orbital cargo. Burns cargo chem_prop on hauls; tanks still matter for station moves.",
    },
}

# Site structures the ark fabricates then deploys to a body (not fleet units).
STRUCTURE_BUILDS = {
    "refuel_depot": {
        "id": "refuel_depot",
        "name": "Refueling depot",
        "kind": "structure",
        "building": "refuel_depot",
        "cost": {"steel": 40.0, "chip": 3.0, "chem_prop": 35.0, "Al": 12.0},
        "months": 3.0,
        "description": "Propellant store on a body. Units that dock here refill Δv (uses depot chem_prop stock).",
    },
}


def tech_book_summary() -> dict:
    return {
        "resources": RESOURCE_NAMES,
        "unit_builds": UNIT_BUILDS,
        "structure_builds": STRUCTURE_BUILDS,
        "buildings": {k: {"name": v.name, "cost": v.build_cost, "description": v.description} for k, v in BUILDINGS.items()},
        "recipes": {
            k: {
                "name": v.name,
                "inputs": v.inputs,
                "outputs": v.outputs,
                "power_mw": v.power_mw,
                "months": v.months,
                "building": v.building,
                "description": v.description,
            }
            for k, v in RECIPES.items()
        },
        "power_options": POWER_OPTIONS,
        "hab_options": HAB_OPTIONS,
    }
