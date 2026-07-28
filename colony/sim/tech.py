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
    "log": "Timber log",
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
        "Local power from starlight. Output falls with distance² and weak stars.",
        ["power_solar"],
    ),
    "chem_genset": BuildingType(
        "chem_genset",
        "Chemical genset",
        {"steel": 25, "chip": 2, "chem_prop": 15},
        "Bootstrap baseload power. Burns chem_prop while loads run.",
        ["power_chem"],
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
    "mass_driver": BuildingType(
        "mass_driver",
        "Mass driver (railgun)",
        {"steel": 90, "chip": 8, "Al": 40, "panel": 20},
        "Electromagnetic launcher for light worlds. Needs continuous site power "
        "(≥18 MW) — pair with a solar farm or chem genset. Shoots cargo without chemical ascent.",
        ["mass_launch"],
    ),
    "l1_magnetic_shield": BuildingType(
        "l1_magnetic_shield",
        "L1 magnetic shield",
        {"steel": 120, "chip": 25, "MAG": 15, "panel": 40, "Al": 30},
        "Station-kept artificial magnetosphere at the sunward Lagrange point. "
        "Stands in for a missing planetary dynamo so air and settlers can survive solar wind.",
        ["shield"],
    ),
    "habitat_module": BuildingType(
        "habitat_module",
        "Habitation module",
        {"steel": 50, "chip": 6, "H2O": 15, "panel": 8, "log": 25},
        "Pressurized living volume. Timber framing + steel pressure shell. Required for off-ark growth.",
        ["hab"],
    ),
    "launch_pad": BuildingType(
        "launch_pad",
        "Launch pad",
        {"steel": 65, "chip": 4, "Al": 20, "log": 10},
        "Chemical launch facility for surface-to-orbit rockets (heavy-world lift path).",
        ["launch"],
    ),
    "rocket_fab": BuildingType(
        "rocket_fab",
        "Rocket fab",
        {"steel": 55, "chip": 12, "Al": 25},
        "Assembles chemical landers / boosters from steel, Al, and chips.",
        ["rocket_build"],
    ),
    "fuel_fab": BuildingType(
        "fuel_fab",
        "Fuel plant",
        {"steel": 40, "chip": 5, "panel": 10},
        "Makes chem_prop from CH₄ + O₂ (or electrolysis path). Feeds launch pads and gensets.",
        ["fuel"],
    ),
    "recovery_pad": BuildingType(
        "recovery_pad",
        "Rocket recovery pad",
        {"steel": 45, "chip": 3, "Al": 15},
        "Landing / catch pad for reusable boosters — cuts rocket attrition.",
        ["recovery"],
    ),
    "extractor": BuildingType(
        "extractor",
        "Extractor",
        {"steel": 20, "chip": 2},
        "Continuous mine on known deposits (needs power).",
        ["mine"],
    ),
}

# Continuous power draw while the rail is armed / launching.
MASS_DRIVER_POWER_MW = 18.0


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
    "constructor": {
        "id": "constructor",
        "name": "Construction bot",
        "kind": "constructor",
        "cost": {"steel": 18.0, "chip": 5.0, "panel": 2.0, "Al": 6.0},
        "months": 2.2,
        "capabilities": ["build"],
        "dv_capacity_m_s": 5500.0,
        "description": "Assembles site structures from local stockpiles (or ark stores when at home). "
        "Also harvests timber logs on suitable worlds for framing habitats and pads.",
    },
}

# Site structures the ark fabricates then deploys to a body (not fleet units).
STRUCTURE_BUILDS = {
    "solar_farm": {
        "id": "solar_farm",
        "name": "Solar farm",
        "kind": "structure",
        "building": "solar_farm",
        "cost": {"panel": 50.0, "steel": 10.0, "chip": 2.0},
        "months": 2.0,
        "description": "Site power from starlight. Weaker on outer orbits / dim stars. Required (or genset) to run a mass driver.",
    },
    "chem_genset": {
        "id": "chem_genset",
        "name": "Chemical genset",
        "kind": "structure",
        "building": "chem_genset",
        "cost": {"steel": 25.0, "chip": 2.0, "chem_prop": 15.0},
        "months": 1.5,
        "description": "Bootstrap baseload. Burns chem_prop when loads (e.g. mass driver) fire.",
    },
    "refuel_depot": {
        "id": "refuel_depot",
        "name": "Refueling depot",
        "kind": "structure",
        "building": "refuel_depot",
        "cost": {"steel": 40.0, "chip": 3.0, "chem_prop": 35.0, "Al": 12.0},
        "months": 3.0,
        "description": "Propellant store on a body. Units that dock here refill Δv (uses depot chem_prop stock).",
    },
    "mass_driver": {
        "id": "mass_driver",
        "name": "Mass driver (railgun)",
        "kind": "structure",
        "building": "mass_driver",
        "cost": {"steel": 90.0, "chip": 8.0, "Al": 40.0, "panel": 20.0},
        "months": 4.0,
        "description": "Railgun for light wells. Requires ≥18 MW site power (solar farm and/or chem genset). "
        "Shoots ore without chemical ascent; assists bots leaving the body. Not for deep wells.",
    },
    "l1_magnetic_shield": {
        "id": "l1_magnetic_shield",
        "name": "L1 magnetic shield",
        "kind": "structure",
        "building": "l1_magnetic_shield",
        "cost": {"steel": 120.0, "chip": 25.0, "MAG": 15.0, "panel": 40.0, "Al": 30.0},
        "months": 6.0,
        "description": "Artificial magnetosphere station at the sunward Lagrange point of a body. "
        "Required for open-air terraforming when the world has no native magnetic field "
        "(deflects solar wind / cosmic radiation). Deploy against the target planet/moon.",
    },
    "habitat_module": {
        "id": "habitat_module",
        "name": "Habitation module",
        "kind": "structure",
        "building": "habitat_module",
        "cost": {"steel": 50.0, "chip": 6.0, "H2O": 15.0, "panel": 8.0, "log": 25.0},
        "months": 3.0,
        "description": "Pressurized living volume. Needs timber logs + steel. Construction bots assemble on site; ark can prefab kits.",
    },
    "launch_pad": {
        "id": "launch_pad",
        "name": "Launch pad",
        "kind": "structure",
        "building": "launch_pad",
        "cost": {"steel": 65.0, "chip": 4.0, "Al": 20.0, "log": 10.0},
        "months": 3.5,
        "description": "Chemical rocket launch facility — heavy-world path when mass drivers cannot work. Uses timber formwork.",
    },
    "rocket_fab": {
        "id": "rocket_fab",
        "name": "Rocket fab",
        "kind": "structure",
        "building": "rocket_fab",
        "cost": {"steel": 55.0, "chip": 12.0, "Al": 25.0},
        "months": 4.0,
        "description": "Builds landers / boosters for the chemical lift chain.",
    },
    "fuel_fab": {
        "id": "fuel_fab",
        "name": "Fuel plant",
        "kind": "structure",
        "building": "fuel_fab",
        "cost": {"steel": 40.0, "chip": 5.0, "panel": 10.0},
        "months": 2.5,
        "description": "Produces chem_prop from local CH₄/O₂ stocks. Pairs with launch pads and gensets.",
    },
    "recovery_pad": {
        "id": "recovery_pad",
        "name": "Rocket recovery pad",
        "kind": "structure",
        "building": "recovery_pad",
        "cost": {"steel": 45.0, "chip": 3.0, "Al": 15.0},
        "months": 2.5,
        "description": "Recovery/landing zone for reusable rockets — closes the chemical flight loop.",
    },
    "extractor": {
        "id": "extractor",
        "name": "Extractor",
        "kind": "structure",
        "building": "extractor",
        "cost": {"steel": 20.0, "chip": 2.0},
        "months": 2.0,
        "description": "Continuous automated mining on known deposits (needs site power).",
    },
}

# Surface-to-orbit Δv above this: mass driver is not practical (game threshold).
MASS_DRIVER_MAX_SURFACE_DV_M_S = 2800.0


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
