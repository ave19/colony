"""Game state: colony room, contracts, production, hauls."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import (
    ARK_POPULATION,
    DAYS_PER_MONTH,
    G,
    SECONDS_PER_DAY,
    SEED_FE_TONNES,
)
from .orbits import period_seconds, transfer_options
from .system_gen import StarSystem, build_survey_archive, generate_system
from .tech import (
    BUILDINGS,
    HAB_OPTIONS,
    MASS_DRIVER_MAX_SURFACE_DV_M_S,
    MASS_DRIVER_POWER_MW,
    POWER_OPTIONS,
    RECIPES,
    RESOURCE_NAMES,
    STRUCTURE_BUILDS,
    UNIT_BUILDS,
    expand_base_plan,
    tech_book_summary,
)
from .orbits import dv_surface_to_orbit
from .constants import AU_M


def _id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Contract:
    id: str
    project_id: str
    title: str
    resource: str
    amount_t: float
    delivered_t: float = 0.0
    status: str = "open"  # open, filled, cancelled
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "resource": self.resource,
            "resource_name": RESOURCE_NAMES.get(self.resource, self.resource),
            "amount_t": round(self.amount_t, 2),
            "delivered_t": round(self.delivered_t, 2),
            "remaining_t": round(max(0.0, self.amount_t - self.delivered_t), 2),
            "status": self.status,
            "note": self.note,
        }


@dataclass
class Project:
    id: str
    name: str
    body_id: str
    power_id: str
    hab_id: str
    materials: Dict[str, float]
    buildings: List[str]
    status: str = "active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "body_id": self.body_id,
            "power_id": self.power_id,
            "hab_id": self.hab_id,
            "materials": self.materials,
            "buildings": self.buildings,
            "status": self.status,
        }


@dataclass
class Haul:
    id: str
    origin_id: str
    dest_id: str
    resource: str
    amount_t: float
    option_name: str
    propellant_t: float
    months_total: float
    months_left: float
    dv_m_s: float
    status: str = "in_flight"  # in_flight, arrived
    unit_id: str = ""  # hauler carrying this cargo
    contract_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "origin_id": self.origin_id,
            "dest_id": self.dest_id,
            "resource": self.resource,
            "amount_t": round(self.amount_t, 2),
            "option_name": self.option_name,
            "propellant_t": round(self.propellant_t, 2),
            "months_total": round(self.months_total, 2),
            "months_left": round(self.months_left, 2),
            "dv_m_s": round(self.dv_m_s, 1),
            "status": self.status,
            "unit_id": self.unit_id,
            "contract_id": self.contract_id,
        }


@dataclass
class Site:
    body_id: str
    buildings: List[str] = field(default_factory=list)
    stockpile: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"body_id": self.body_id, "buildings": self.buildings, "stockpile": {k: round(v, 2) for k, v in self.stockpile.items()}}


# Capability tags a unit can apply to a target body
CAP_SURVEY = "survey"
CAP_MINE = "mine"
CAP_HAUL = "haul"
CAP_BUILD = "build"  # ark / construction focus
CAP_COMMAND = "command"


@dataclass
class FleetUnit:
    id: str
    name: str
    kind: str  # ark | survey | miner | hauler
    location_id: str  # body id, or "ark" while docked at the colony ship
    status: str = "idle"  # idle | en_route | working
    order: str = ""
    target_id: str = ""
    search_resource: str = ""  # directed survey: "Fe", "H2O", …
    months_left: float = 0.0
    months_total: float = 0.0  # for transit progress on map
    transit_from_id: str = ""  # where this hop started (map path)
    capabilities: List[str] = field(default_factory=list)
    # Fixed propellant budget (m/s). 0 capacity = unlimited (ark command node).
    dv_capacity_m_s: float = 0.0
    dv_remaining_m_s: float = 0.0

    def to_dict(self) -> dict:
        progress = None
        if self.status == "en_route" and self.months_total > 1e-9:
            progress = round(
                max(0.0, min(1.0, 1.0 - self.months_left / self.months_total)), 3
            )
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "location_id": self.location_id,
            "status": self.status,
            "order": self.order,
            "target_id": self.target_id,
            "search_resource": self.search_resource,
            "months_left": round(self.months_left, 2),
            "months_total": round(self.months_total, 2),
            "transit_from_id": self.transit_from_id,
            "transit_progress": progress,
            "capabilities": self.capabilities,
            "dv_capacity_m_s": round(self.dv_capacity_m_s, 1),
            "dv_remaining_m_s": round(self.dv_remaining_m_s, 1),
            "dv_fraction": (
                round(self.dv_remaining_m_s / self.dv_capacity_m_s, 3)
                if self.dv_capacity_m_s > 0
                else None
            ),
        }


@dataclass
class BuildJob:
    """Ark fabrication job — materials already reserved from stock."""
    id: str
    unit_kind: str  # survey|miner|hauler|structure kinds
    name: str
    months_total: float
    months_left: float
    capabilities: List[str] = field(default_factory=list)
    status: str = "building"  # building | complete
    # Structure deploy target (body id); empty for fleet units
    deploy_body_id: str = ""
    building_id: str = ""  # BUILDINGS key for structures
    dv_capacity_m_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "unit_kind": self.unit_kind,
            "name": self.name,
            "months_total": round(self.months_total, 2),
            "months_left": round(self.months_left, 2),
            "capabilities": self.capabilities,
            "status": self.status,
            "deploy_body_id": self.deploy_body_id,
            "building_id": self.building_id,
        }


class Game:
    """Single colony room — continuous going-concern simulation."""

    def __init__(self, universe_seed: int = 20260727) -> None:
        self.phase = "menu"  # menu | transit | system
        self.system: Optional[StarSystem] = None
        # Pre-existing remote dossiers (not generated by a player "scan" click)
        self.survey_archive: List[dict] = build_survey_archive(8, universe_seed=universe_seed)
        self.catalog: List[dict] = []  # currently viewed archive slice
        self.archive_opened: bool = False
        self.sim_time_s: float = 0.0
        self.wall_anchor: float = time.time()
        self.last_wall: float = self.wall_anchor
        self.events: List[dict] = []
        self.projects: Dict[str, Project] = {}
        self.contracts: Dict[str, Contract] = {}
        self.hauls: Dict[str, Haul] = {}
        self.sites: Dict[str, Site] = {}
        self.fleet: Dict[str, FleetUnit] = {}
        self.build_queue: List[BuildJob] = []
        self._unit_seq: Dict[str, int] = {"survey": 0, "miner": 0, "hauler": 0}
        # Ark inventory (materials / seed stock — specialized gear is built later)
        self.ark_stock: Dict[str, float] = {
            "Fe": SEED_FE_TONNES,
            "Al": 200.0,
            "Si": 150.0,
            "H2O": 500.0,
            "CH4": 80.0,
            "O2": 120.0,
            "steel": 100.0,
            "chip": 40.0,
            "panel": 20.0,
            "chem_prop": 60.0,
            "Xe": 0.0,  # spent on arrival
        }
        self.population = ARK_POPULATION
        self.selected_seed: Optional[int] = None
        self.transit_months_left: float = 0.0
        self.message: str = (
            "Open the survey archive to review remote dossiers, then commit a destination."
        )
        self.scanned: set[str] = set()
        self.auto_warp_votes = 0
        self.home_body_id: str = ""
        # Ark-level continuous scan goals (system-wide), e.g. "habitable", "Fe", "asteroids"
        self.ark_scan_goals: List[str] = []
        # Per-body habitability intel 0..3 (ark / broad survey)
        self.hab_intel: Dict[str, int] = {}
        self.hab_seek_months: Dict[str, float] = {}

    # --- time ---
    def catch_up(self) -> float:
        """Advance sim from wall clock. Returns months advanced."""
        now = time.time()
        dt = max(0.0, now - self.last_wall)
        self.last_wall = now
        if self.phase == "menu":
            return 0.0
        # Real time 1:1 — one Earth second of wall clock = one second of sim time.
        # Logistics (transit months, fab jobs, survey campaigns) use the event queue / Warp.
        game_dt_s = dt
        return self.advance(game_dt_s)

    def advance(self, game_dt_s: float) -> float:
        if game_dt_s <= 0:
            return 0.0
        self.sim_time_s += game_dt_s
        months = game_dt_s / (SECONDS_PER_DAY * DAYS_PER_MONTH)

        if self.phase == "transit":
            self.transit_months_left = max(0.0, self.transit_months_left - months)
            if self.transit_months_left <= 0:
                self._arrive()
            return months

        if self.phase != "system":
            return months

        for h in list(self.hauls.values()):
            if h.status != "in_flight":
                continue
            h.months_left -= months
            if h.months_left <= 0:
                self._complete_haul(h)

        for u in list(self.fleet.values()):
            # Haulers on cargo runs are driven by Haul.months_left / _complete_haul
            if u.order == "haul" and u.status == "en_route":
                continue
            if u.status == "en_route" and u.months_left > 0:
                u.months_left -= months
                if u.months_left <= 0:
                    self._complete_unit_order(u)
            elif u.status == "working" and u.order == "survey":
                # Continuous survey: learn more the longer you sit
                self._tick_survey(u, months)
            elif u.status == "working" and u.order == "mine" and u.months_left > 0:
                u.months_left -= months
                if u.months_left <= 0:
                    self._complete_unit_order(u)

        self._tick_builds(months)
        self._tick_ark_scan_goals(months)
        # Ark trickle fabs (slow basics) + site industry
        self._ark_tick(months)
        self._site_tick(months)
        self._tick_population(months)
        return months

    # --- Ark system-wide scan goals -----------------------------------------
    ARK_SCAN_GOAL_SPECS = {
        "habitable": {
            "id": "habitable",
            "label": "Find terraform / habitability targets",
            "description": "Scan for surface g, atmosphere, water, active core & magnetic field. "
            "No magnetosphere ⇒ need an artificial L1 radiation shield.",
        },
        "Fe": {
            "id": "Fe",
            "label": "Find iron sources",
            "description": "System-wide search for Fe-bearing worlds and asteroids.",
            "resource": "Fe",
        },
        "H2O": {
            "id": "H2O",
            "label": "Find water / ice sources",
            "description": "Look for ice moons, outer belts, hydrated rock.",
            "resource": "H2O",
        },
        "asteroids": {
            "id": "asteroids",
            "label": "Survey asteroid belt",
            "description": "Catalog belt objects and their accessible materials.",
        },
        "CH4": {
            "id": "CH4",
            "label": "Find methane / organics",
            "description": "Giants, icy moons, and carbonaceous rocks.",
            "resource": "CH4",
        },
    }

    def set_ark_scan_goal(self, goal_id: str, enabled: bool = True) -> dict:
        """Toggle a continuous ark scan goal (system-wide)."""
        self.catch_up()
        if self.phase != "system":
            raise ValueError("only after arrival")
        if goal_id not in self.ARK_SCAN_GOAL_SPECS:
            raise ValueError(f"unknown scan goal {goal_id}")
        if enabled:
            if goal_id not in self.ark_scan_goals:
                self.ark_scan_goals.append(goal_id)
                self._log(
                    "scan",
                    f"Ark scan goal set: {self.ARK_SCAN_GOAL_SPECS[goal_id]['label']}",
                )
        else:
            if goal_id in self.ark_scan_goals:
                self.ark_scan_goals.remove(goal_id)
                self._log("scan", f"Ark scan goal cleared: {goal_id}")
        return self.snapshot()

    def _tick_ark_scan_goals(self, months: float) -> None:
        """Ark remote sensing — slower than a probe on-station, covers the system."""
        if not self.system or not self.ark_scan_goals or months <= 0:
            return
        # Remote rate: fraction of an on-site probe
        rate = months * 0.35
        for goal_id in list(self.ark_scan_goals):
            spec = self.ARK_SCAN_GOAL_SPECS.get(goal_id)
            if not spec:
                continue
            if goal_id == "habitable":
                self._ark_seek_habitable(rate)
            elif goal_id == "asteroids":
                self._ark_seek_asteroids(rate)
            elif spec.get("resource"):
                self._ark_seek_resource(spec["resource"], rate)

    def _ark_seek_habitable(self, months: float) -> None:
        """Progressive terraform survey: g → atmosphere → water → core/magnetosphere."""
        assert self.system
        from .system_gen import _habitable_zone
        from .constants import AU_M

        lum = float(self.system.star.get("lum") or 1.0)
        hz_in, hz_out = _habitable_zone(lum)
        # Rocky planets first (true surface targets), then large moons near HZ planets
        candidates = [
            b
            for b in self.system.bodies
            if b.kind == "planet" and b.planet_class == "rocky"
        ]
        candidates.sort(
            key=lambda b: abs((b.semi_major_m / AU_M) - 0.5 * (hz_in + hz_out))
        )
        # Append interesting moons of HZ-region planets
        for p in list(candidates):
            for m in self.system.bodies:
                if m.kind == "moon" and m.parent_id == p.id and m.mass_kg > 5e21:
                    if m not in candidates:
                        candidates.append(m)

        for b in candidates:
            if self.hab_intel.get(b.id, 0) >= 5:
                continue
            self.hab_seek_months[b.id] = self.hab_seek_months.get(b.id, 0.0) + months
            notes = self._advance_terraform_intel(b, remote=True)
            if notes:
                for n in notes:
                    self._log("scan", f"Ark (terraform survey) {b.name}: {n}")
            break  # focus one body at a time

    def _advance_terraform_intel(self, body, *, remote: bool = True) -> List[str]:
        """
        Reveal terraform factors by seek months.
        Levels:
          1 insolation / HZ
          2 surface g
          3 atmosphere
          4 water
          5 core + magnetosphere + infrastructure needs
        On-station probes advance ~2.5× faster than remote ark sensing.
        """
        from .system_gen import _habitable_zone
        from .constants import AU_M
        from .orbits import surface_gravity

        assert self.system
        sm = self.hab_seek_months.get(body.id, 0.0)
        # thresholds (months of *seek* time)
        if remote:
            levels = [(0.7, 1), (1.6, 2), (2.8, 3), (4.0, 4), (5.5, 5)]
        else:
            levels = [(0.3, 1), (0.7, 2), (1.2, 3), (1.8, 4), (2.5, 5)]
        old = self.hab_intel.get(body.id, 0)
        new = old
        for t, lv in levels:
            if sm >= t:
                new = max(new, lv)
        if new <= old:
            return []
        self.hab_intel[body.id] = new

        lum = float(self.system.star.get("lum") or 1.0)
        hz_in, hz_out = _habitable_zone(lum)
        if body.kind == "moon" and body.parent_id:
            parent = self.system.body_by_id(body.parent_id)
            a_au = (parent.semi_major_m / AU_M) if parent else 0.0
        else:
            a_au = body.semi_major_m / AU_M
        in_hz = hz_in <= a_au <= hz_out if a_au > 0 else False
        g_e = surface_gravity(body.mass_kg, body.radius_m) / 9.81
        notes: List[str] = []
        for lv in range(old + 1, new + 1):
            if lv == 1:
                notes.append(
                    f"insolation: a≈{a_au:.2f} AU · "
                    f"{'in optimistic HZ' if in_hz else 'outside temperate band'}"
                )
            elif lv == 2:
                if g_e < 0.35:
                    g_note = "low-g (light; easy lift, hard to hold air long-term)"
                elif g_e <= 1.2:
                    g_note = "comfortable surface g for settlement"
                else:
                    g_note = "high-g (costly surface ops / lift)"
                notes.append(f"surface gravity ≈ {g_e:.2f} g — {g_note}")
            elif lv == 3:
                ac = body.atmosphere_class or ("substantial" if body.has_atmosphere else "none")
                notes.append(
                    f"atmosphere: {ac}"
                    + (f" ({body.atmosphere_note})" if body.atmosphere_note else "")
                )
            elif lv == 4:
                wc = body.water_class or "none"
                notes.append(f"water inventory: {wc.replace('_', ' ')}")
            elif lv == 5:
                core = "active core (dynamo possible)" if body.has_active_core else "dead/cold core"
                if body.has_magnetosphere:
                    mag = "native magnetosphere — natural radiation shield"
                    need = "no artificial L1 shield required for cosmic/solar wind"
                else:
                    mag = "no planetary magnetic field"
                    need = (
                        "terraform needs an artificial magnetosphere — "
                        "e.g. a magnetic shield station at the sunward Lagrange point (L1)"
                    )
                notes.append(f"interior: {core}; {mag}")
                notes.append(f"infrastructure: {need}")
                score = self._terraform_score(body, in_hz, g_e)
                notes.append(f"terraform viability sketch: {score}/10")
        return notes

    def _terraform_score(self, body, in_hz: bool, g_e: float) -> int:
        """Rough 0–10 playable score once fully surveyed."""
        score = 0
        if body.planet_class == "rocky" or body.kind == "moon":
            score += 2
        if in_hz:
            score += 2
        if 0.4 <= g_e <= 1.3:
            score += 2
        elif 0.25 <= g_e < 0.4 or 1.3 < g_e <= 1.6:
            score += 1
        ac = body.atmosphere_class
        if ac == "substantial":
            score += 2
        elif ac == "thin":
            score += 1
        wc = body.water_class
        if wc == "surface_potential":
            score += 2
        elif wc in ("subsurface", "ice"):
            score += 1
        if body.has_magnetosphere:
            score += 2
        elif body.has_active_core:
            score += 1  # might restore dynamo someday — still need shield for now
        return min(10, score)

    def terraform_dossier(self, body_id: str) -> dict:
        """
        Habitability / terraform report for UI.

        Physics we always know (mass → g, orbit → insolation) is never fogged.
        Atmosphere, water, core, and magnetosphere need progressive survey (levels 3–5).
        Always includes a path checklist: what is ok / bad / unknown / build-required.
        """
        from .system_gen import _habitable_zone
        from .constants import AU_M
        from .orbits import surface_gravity

        if not self.system:
            return {"body_id": body_id, "level": 0, "factors": [], "path": []}
        body = self.system.body_by_id(body_id)
        if not body:
            return {"body_id": body_id, "level": 0, "factors": [], "path": []}
        level = self.hab_intel.get(body_id, 0)
        lum = float(self.system.star.get("lum") or 1.0)
        hz_in, hz_out = _habitable_zone(lum)
        if body.kind == "moon" and body.parent_id:
            parent = self.system.body_by_id(body.parent_id)
            a_au = (parent.semi_major_m / AU_M) if parent else None
        else:
            a_au = body.semi_major_m / AU_M if body.kind != "moon" else None
        in_hz = bool(a_au is not None and hz_in <= a_au <= hz_out)
        g_e = surface_gravity(body.mass_kg, body.radius_m) / 9.81
        if g_e < 0.35:
            g_class = "low"
        elif g_e <= 1.2:
            g_class = "comfortable"
        else:
            g_class = "high"

        surface_ok = body.planet_class in ("rocky", "moon") or body.kind == "moon"
        is_giant = body.planet_class in ("gas_giant", "ice_giant")
        is_rock = body.kind == "asteroid"

        d: Dict[str, Any] = {
            "body_id": body_id,
            "name": body.name,
            "kind": body.kind,
            "planet_class": body.planet_class,
            "level": level,
            "level_max": 5,
            "survey_complete": level >= 5,
            # Always-known physics
            "semi_major_au": round(a_au, 3) if a_au is not None else None,
            "in_hz": in_hz,
            "insolation_note": (
                "in optimistic habitable zone"
                if in_hz
                else "outside temperate insolation band"
            ),
            "surface_g": round(g_e, 3),
            "g_class": g_class,
            "surface_settlement_possible": surface_ok and not is_giant,
        }

        # Survey-revealed (only when earned)
        if level >= 3:
            d["atmosphere_class"] = body.atmosphere_class
            d["atmosphere_note"] = body.atmosphere_note
            d["has_atmosphere"] = body.has_atmosphere
        if level >= 4:
            d["water_class"] = body.water_class
        if level >= 5:
            d["has_active_core"] = body.has_active_core
            d["has_magnetosphere"] = body.has_magnetosphere
            d["needs_l1_magnetic_shield"] = (
                not body.has_magnetosphere and surface_ok and not is_rock
            )
            d["terraform_score"] = self._terraform_score(body, in_hz, g_e)
            d["l1_shield_online"] = self._has_building(body_id, "l1_magnetic_shield")
            if d["needs_l1_magnetic_shield"]:
                d["shield_note"] = (
                    "No native magnetosphere — build an L1 magnetic shield "
                    "(ark fab → deploy on this body) before open-air settlement."
                )
            else:
                d["shield_note"] = "Native magnetosphere provides radiation shielding."

        # --- Factor checklist (always, with known/unknown) ---------------------
        factors: List[dict] = []

        if is_giant:
            factors.append(
                {
                    "id": "surface",
                    "label": "Solid surface",
                    "known": True,
                    "status": "no",
                    "value": "gas/ice giant — no surface colony",
                    "fix": "Cannot terraform as a surface world. Moons may be targets.",
                }
            )
        elif is_rock:
            factors.append(
                {
                    "id": "surface",
                    "label": "Settlement type",
                    "known": True,
                    "status": "hard",
                    "value": "asteroid — stations / caves, not open-air planet",
                    "fix": "Habitable only as pressurized habitats, not planetary terraforming.",
                }
            )
        else:
            factors.append(
                {
                    "id": "surface",
                    "label": "Solid surface",
                    "known": True,
                    "status": "ok",
                    "value": "rocky surface available",
                    "fix": "Can host surface bases.",
                }
            )

        # Gravity — always known
        if g_class == "comfortable":
            g_status, g_fix = "ok", "Fine for long-term settlement."
        elif g_class == "low":
            g_status, g_fix = (
                "hard",
                "Easy launch, hard to hold thick air / bone health — habitats help.",
            )
        else:
            g_status, g_fix = "hard", "High-g ops costly; lift and construction harder."
        factors.append(
            {
                "id": "gravity",
                "label": "Surface gravity",
                "known": True,
                "status": g_status,
                "value": f"{g_e:.2f} g ({g_class})",
                "fix": g_fix,
            }
        )

        # Insolation — always known for planets/moons with a
        if a_au is None:
            factors.append(
                {
                    "id": "insolation",
                    "label": "Starlight / climate band",
                    "known": False,
                    "status": "unknown",
                    "value": "—",
                    "fix": "Need orbital context.",
                }
            )
        elif in_hz:
            factors.append(
                {
                    "id": "insolation",
                    "label": "Starlight / climate band",
                    "known": True,
                    "status": "ok",
                    "value": f"~{a_au:.2f} AU · optimistic HZ",
                    "fix": "Temperate insolation possible with right atmosphere.",
                }
            )
        else:
            factors.append(
                {
                    "id": "insolation",
                    "label": "Starlight / climate band",
                    "known": True,
                    "status": "hard",
                    "value": f"~{a_au:.2f} AU · outside optimistic HZ",
                    "fix": "Too hot or cold for open-air Earth-like climate without heavy engineering "
                    "(domes, heat, or reflective systems).",
                }
            )

        # Atmosphere
        if level < 3:
            factors.append(
                {
                    "id": "atmosphere",
                    "label": "Atmosphere",
                    "known": False,
                    "status": "unknown",
                    "value": "not surveyed",
                    "fix": "Send a survey probe or enable ark terraform scan.",
                }
            )
        else:
            ac = body.atmosphere_class or "none"
            if ac == "substantial":
                st, fix = "ok", "Thick air present — still check composition / pressure."
            elif ac == "thin":
                st, fix = (
                    "hard",
                    "Thin air — import volatiles, pressure habitats, or thicken over centuries.",
                )
            elif ac == "giant_envelope":
                st, fix = "no", "Not a surface atmosphere we can settle."
            else:
                st, fix = (
                    "hard",
                    "Airless — sealed habitats required; import N₂/O₂ for any open air.",
                )
            factors.append(
                {
                    "id": "atmosphere",
                    "label": "Atmosphere",
                    "known": True,
                    "status": st,
                    "value": ac + (f" · {body.atmosphere_note}" if body.atmosphere_note else ""),
                    "fix": fix,
                }
            )

        # Water
        if level < 4:
            factors.append(
                {
                    "id": "water",
                    "label": "Water / ice",
                    "known": False,
                    "status": "unknown",
                    "value": "not surveyed",
                    "fix": "Directed H₂O search or continue terraform survey.",
                }
            )
        else:
            wc = body.water_class or "none"
            if wc == "surface_potential":
                st, fix = "ok", "Water inventory supports life-support / climate work."
            elif wc in ("subsurface", "ice"):
                st, fix = (
                    "hard",
                    "Ice/subsurface water — mine and melt; not free oceans.",
                )
            else:
                st, fix = "hard", "Dry — import ice from outer system or moons."
            factors.append(
                {
                    "id": "water",
                    "label": "Water / ice",
                    "known": True,
                    "status": st,
                    "value": wc.replace("_", " "),
                    "fix": fix,
                }
            )

        # Magnetosphere / radiation
        if level < 5:
            factors.append(
                {
                    "id": "magnetosphere",
                    "label": "Magnetic field / radiation",
                    "known": False,
                    "status": "unknown",
                    "value": "not surveyed",
                    "fix": "Need core/dynamo assessment. If no field → L1 magnetic shield.",
                }
            )
        else:
            if body.has_magnetosphere:
                factors.append(
                    {
                        "id": "magnetosphere",
                        "label": "Magnetic field / radiation",
                        "known": True,
                        "status": "ok",
                        "value": "native magnetosphere"
                        + (" · active core" if body.has_active_core else ""),
                        "fix": "Natural solar-wind protection.",
                    }
                )
            else:
                shield_on = self._has_building(body_id, "l1_magnetic_shield")
                factors.append(
                    {
                        "id": "magnetosphere",
                        "label": "Magnetic field / radiation",
                        "known": True,
                        "status": "ok" if shield_on else "need_build",
                        "value": (
                            "no native field · L1 shield ONLINE"
                            if shield_on
                            else "no native field · L1 shield REQUIRED"
                        ),
                        "fix": (
                            "Artificial magnetosphere is active."
                            if shield_on
                            else "Build L1 magnetic shield (ark fabrication bay → deploy on this body)."
                        ),
                    }
                )
            factors.append(
                {
                    "id": "core",
                    "label": "Planetary core",
                    "known": True,
                    "status": "ok" if body.has_active_core else "hard",
                    "value": "active dynamo possible" if body.has_active_core else "cold / dead core",
                    "fix": (
                        "May sustain or rebuild a field over geologic time."
                        if body.has_active_core
                        else "No natural field recovery — artificial shield is the path."
                    ),
                }
            )

        d["factors"] = factors

        # Path summary
        path: List[str] = []
        if is_giant:
            path.append("Not a terraform surface target. Survey its moons instead.")
        elif is_rock:
            path.append("Build pressurized habitats (not open-air terraforming).")
        else:
            if level < 5:
                path.append(
                    f"Survey incomplete ({level}/5). Enable ark “terraform targets” scan "
                    "or park a survey sat here and warp."
                )
            for f in factors:
                if f["status"] == "need_build":
                    path.append(f["fix"])
                elif f["status"] == "hard" and f["known"]:
                    path.append(f"{f['label']}: {f['fix']}")
                elif f["status"] == "no":
                    path.append(f["fix"])
            if level >= 5 and all(
                f["status"] in ("ok", "hard") for f in factors if f["id"] != "surface"
            ):
                if any(f["status"] == "need_build" for f in factors):
                    path.append("After L1 shield: sealed bases → expand life support → optional climate work.")
                elif not path:
                    path.append(
                        "Strong candidate: bases first, then industry, then optional open-air climate work."
                    )

        # One-line verdict
        if is_giant:
            verdict = "Not habitable (no solid surface)."
            verdict_status = "no"
        elif is_rock:
            verdict = "Habitable only as habitats / stations — not a planet to terraform."
            verdict_status = "hard"
        elif level < 3:
            verdict = (
                f"Unknown habitability — physics: {g_e:.2f} g, "
                f"{'in' if in_hz else 'outside'} optimistic HZ. Survey for air, water, magnetic field."
            )
            verdict_status = "unknown"
        elif level < 5:
            verdict = (
                f"Partial survey ({level}/5). Gravity and climate band known; "
                "still scanning atmosphere/water/magnetosphere."
            )
            verdict_status = "unknown"
        else:
            score = d.get("terraform_score", 0)
            if d.get("needs_l1_magnetic_shield") and not d.get("l1_shield_online"):
                verdict = (
                    f"Not open-air ready (score {score}/10). "
                    "Missing magnetic field — build L1 shield first."
                )
                verdict_status = "need_build"
            elif score >= 7:
                verdict = f"Strong terraform / settlement candidate (score {score}/10)."
                verdict_status = "ok"
            elif score >= 4:
                verdict = f"Marginal candidate (score {score}/10) — expect heavy engineering."
                verdict_status = "hard"
            else:
                verdict = f"Poor open-air candidate (score {score}/10) — sealed bases only."
                verdict_status = "hard"

        d["path"] = path
        d["verdict"] = verdict
        d["verdict_status"] = verdict_status
        d["how_to_survey"] = (
            "Ark console → Survey priorities → “Find terraform / habitability targets”, "
            "or Tasks tab → survey probe → Scan / broad survey on this body, then Warp."
        )
        return d

    def _ark_seek_asteroids(self, months: float) -> None:
        assert self.system
        rocks = [b for b in self.system.bodies if b.kind == "asteroid"]
        rocks.sort(key=lambda b: b.survey_months)
        for b in rocks:
            if b.survey_months >= 4.0 and b.mine_sites:
                continue
            notes = b.apply_survey_time(months * 0.8, focus_resource=None)
            self.scanned.add(b.id)
            if notes:
                self._log("scan", f"Ark (belt survey) {b.name}: " + "; ".join(notes))
            break

    def _ark_seek_resource(self, resource: str, months: float) -> None:
        assert self.system
        # Prefer bodies that can host this resource and lack a site yet
        cands = []
        for b in self.system.bodies:
            if any(s.resource == resource for s in b.mine_sites):
                continue
            if resource in b.seek_exhausted:
                continue
            from .system_gen import _searchable_resources

            if resource not in _searchable_resources(b) and not any(
                d.resource == resource for d in b.deposits
            ):
                continue
            cands.append(b)
        # Prefer closer to home for remote sensing narrative
        home = self.home_body_id
        def key(b):
            return (b.seek_months.get(resource, 0.0), abs(hash(b.id) % 100))

        cands.sort(key=key)
        if not cands:
            return
        b = cands[0]
        notes = b.apply_survey_time(months, focus_resource=resource)
        self.scanned.add(b.id)
        if notes:
            self._log(
                "scan",
                f"Ark seeking {RESOURCE_NAMES.get(resource, resource)} @ {b.name}: "
                + "; ".join(notes),
            )

    def body_tree(self) -> List[dict]:
        """Hierarchical body list for UI: planets with nested moons, then belt."""
        if not self.system:
            return []
        from .constants import AU_M
        from .system_gen import _habitable_zone

        lum = float(self.system.star.get("lum") or 1.0)
        hz_in, hz_out = _habitable_zone(lum)
        planets = sorted(
            [b for b in self.system.bodies if b.kind == "planet"],
            key=lambda b: b.semi_major_m,
        )
        asteroids = sorted(
            [b for b in self.system.bodies if b.kind == "asteroid"],
            key=lambda b: b.semi_major_m,
        )
        tree = []
        for p in planets:
            a_au = p.semi_major_m / AU_M
            moons = sorted(
                [m for m in self.system.bodies if m.kind == "moon" and m.parent_id == p.id],
                key=lambda m: m.semi_major_m,
            )
            tree.append(
                {
                    "id": p.id,
                    "name": p.name,
                    "kind": "planet",
                    "planet_class": p.planet_class,
                    "semi_major_au": round(a_au, 3),
                    "in_hz": hz_in <= a_au <= hz_out and p.planet_class == "rocky",
                    "hab_intel": self.hab_intel.get(p.id, 0),
                    "moon_count": len(moons),
                    "moons": [
                        {
                            "id": m.id,
                            "name": m.name,
                            "kind": "moon",
                            "moon_a_over_R": round(m.semi_major_m / p.radius_m, 2),
                            "period_days": round(
                                period_seconds(m.semi_major_m, G * p.mass_kg) / 86400.0, 2
                            ),
                        }
                        for m in moons
                    ],
                }
            )
        if asteroids:
            tree.append(
                {
                    "id": "_belt",
                    "name": "Asteroid belt",
                    "kind": "belt_group",
                    "planet_class": "asteroid",
                    "semi_major_au": None,
                    "moons": [],
                    "asteroids": [
                        {
                            "id": a.id,
                            "name": a.name,
                            "kind": "asteroid",
                            "semi_major_au": round(a.semi_major_m / AU_M, 3),
                            "density_hint": a.density_hint,
                        }
                        for a in asteroids
                    ],
                }
            )
        return tree

    def _tick_builds(self, months: float) -> None:
        # Single bay: only the head job advances.
        for job in list(self.build_queue):
            if job.status != "building":
                continue
            job.months_left -= months
            if job.months_left <= 0:
                job.months_left = 0.0
                job.status = "complete"
                self._finish_build(job)
            break
        self.build_queue = [j for j in self.build_queue if j.status == "building"]

    def _finish_build(self, job: BuildJob) -> None:
        home = self.home_body_id or (
            self.sites.get("ark_orbit").body_id if self.sites.get("ark_orbit") else "p0"
        )
        # Structure deploy
        if job.building_id:
            body_id = job.deploy_body_id or home
            site = self.sites.setdefault(body_id, Site(body_id=body_id))
            if job.building_id not in site.buildings:
                site.buildings.append(job.building_id)
            # Seed propellant stock for depots
            if job.building_id == "refuel_depot":
                site.stockpile["chem_prop"] = site.stockpile.get("chem_prop", 0.0) + 25.0
            body = self.system.body_by_id(body_id) if self.system else None
            where = body.name if body else body_id
            extra = ""
            if job.building_id == "refuel_depot":
                extra = " Units can refuel Δv here."
            elif job.building_id == "mass_driver":
                extra = (
                    f" Needs ≥{MASS_DRIVER_POWER_MW:.0f} MW site power to fire "
                    "(solar farm / chem genset)."
                )
            elif job.building_id == "solar_farm":
                extra = " Feeding local power bus."
            elif job.building_id == "chem_genset":
                extra = " Baseload available while chem_prop lasts."
            elif job.building_id == "l1_magnetic_shield":
                extra = (
                    " Artificial magnetosphere online at sunward L1 — "
                    "radiation shield for open-air settlement."
                )
            self._log("build", f"Deployed {job.name} at {where}.{extra}")
            return

        self._unit_seq[job.unit_kind] = self._unit_seq.get(job.unit_kind, 0) + 1
        n = self._unit_seq[job.unit_kind]
        uid = f"{job.unit_kind[0:2]}{n}"
        name = f"{job.name} {n}"
        cap = float(job.dv_capacity_m_s or 0.0)
        # Craft leave the fabrication bay *on the ark* — not already on the planet.
        # They must transit (and burn Δv) to any body, including the home world.
        self.fleet[uid] = FleetUnit(
            id=uid,
            name=name,
            kind=job.unit_kind,
            location_id="ark",
            capabilities=list(job.capabilities),
            dv_capacity_m_s=cap,
            dv_remaining_m_s=cap,  # full tanks on launch from ark
        )
        self._log(
            "build",
            f"Fabrication complete: {name} docked at ark"
            + (f" (Δv {cap:.0f} m/s tanks full). Transit required to any body." if cap > 0 else "."),
        )

    def rename_unit(self, unit_id: str, name: str) -> dict:
        """Player-facing rename for probes, bots, haulers, or the ark."""
        self.catch_up()
        u = self.fleet.get(unit_id)
        if not u:
            raise ValueError("unknown unit")
        cleaned = " ".join((name or "").strip().split())
        if not cleaned:
            raise ValueError("name cannot be empty")
        if len(cleaned) > 40:
            raise ValueError("name too long (max 40 characters)")
        # Soft uniqueness: allow duplicates but warn in log if clash
        clash = next(
            (x for x in self.fleet.values() if x.id != unit_id and x.name == cleaned),
            None,
        )
        old = u.name
        u.name = cleaned
        if clash:
            self._log("order", f"Renamed {old} → {cleaned} (note: also used by {clash.id}).")
        else:
            self._log("order", f"Renamed {old} → {cleaned}.")
        return self.snapshot()

    def queue_build(self, unit_kind: str, deploy_body_id: str = "") -> dict:
        """Authorize ark to build a unit or structure from seed materials + time.

        The fabrication bay runs **one job at a time** — no parallel queue.
        """
        self.catch_up()
        if self.phase != "system":
            raise ValueError("can only build after arrival")
        if not any(u.kind == "ark" for u in self.fleet.values()):
            raise ValueError("no ark")
        active = [j for j in self.build_queue if j.status == "building"]
        if active:
            job = active[0]
            raise ValueError(
                f"fabrication bay busy: {job.name} "
                f"({job.months_left:.1f} mo left) — warp or wait until complete"
            )

        unit_spec = UNIT_BUILDS.get(unit_kind)
        struct_spec = STRUCTURE_BUILDS.get(unit_kind)
        if unit_spec:
            spec = unit_spec
            is_structure = False
        elif struct_spec:
            spec = struct_spec
            is_structure = True
        else:
            raise ValueError(f"unknown build type {unit_kind}")

        if is_structure:
            body_id = deploy_body_id or self.home_body_id
            if not body_id or not self.system or not self.system.body_by_id(body_id):
                raise ValueError("pick a body to deploy the structure on")
            body = self.system.body_by_id(body_id)
            # One of each structure type per body
            site = self.sites.get(body_id)
            if site and spec.get("building") in site.buildings:
                raise ValueError("that body already has this structure")
            # Mass drivers only on light gravity wells
            if spec.get("building") == "mass_driver":
                if not self.body_allows_mass_driver(body):
                    dv = dv_surface_to_orbit(body.mass_kg, body.radius_m)
                    raise ValueError(
                        f"{body.name} well is too deep for a mass driver "
                        f"(surface→orbit ~{dv:.0f} m/s; need ≤{MASS_DRIVER_MAX_SURFACE_DV_M_S:.0f} "
                        f"or an asteroid/moon-class light body)"
                    )
            # L1 shield: only for rocky worlds / large moons without native field (or always allow as overkill)
            if spec.get("building") == "l1_magnetic_shield":
                if body.planet_class in ("gas_giant", "ice_giant", "asteroid"):
                    raise ValueError(
                        f"L1 magnetic shield is for rocky worlds/moons — not {body.planet_class}"
                    )
                # Prefer after survey knows they need it, but allow early build
                if body.has_magnetosphere:
                    # still allow deploy (redundant) but warn via log after
                    pass

        for res, need in spec["cost"].items():
            have = self.ark_stock.get(res, 0.0)
            if have + 1e-9 < need:
                raise ValueError(f"need {need} t {res}, ark has {have:.1f}")
        for res, need in spec["cost"].items():
            self.ark_stock[res] = self.ark_stock.get(res, 0.0) - need

        job = BuildJob(
            id=_id(),
            unit_kind=spec["kind"],
            name=spec["name"],
            months_total=float(spec["months"]),
            months_left=float(spec["months"]),
            capabilities=list(spec.get("capabilities") or []),
            deploy_body_id=deploy_body_id or (self.home_body_id if is_structure else ""),
            building_id=spec.get("building") or "",
            dv_capacity_m_s=float(spec.get("dv_capacity_m_s") or 0.0),
        )
        self.build_queue.append(job)
        where = ""
        if is_structure and self.system:
            b = self.system.body_by_id(job.deploy_body_id)
            where = f" → {b.name}" if b else f" → {job.deploy_body_id}"
        self._log(
            "build",
            f"Authorized build: {spec['name']}{where} "
            f"({spec['months']} mo, materials reserved).",
        )
        return self.snapshot()

    # Auto-warp without confirm for short logistics (fab jobs, local hops).
    # Multi-month / multi-year jumps (transit, outer system) need force=True.
    SAFE_WARP_MONTHS = 3.0  # ~3 months
    # Survey discovery slices — short checkpoints so warp feels responsive
    SURVEY_WARP_SLICE_MONTHS = 0.5  # half a month per survey/ark-scan warp

    def event_queue(self) -> List[dict]:
        """Upcoming scheduled work, shortest first — the event queue."""
        items: List[dict] = []
        if self.phase == "transit" and self.transit_months_left > 0:
            items.append(
                {
                    "kind": "transit",
                    "label": "Arrive in system (end of transit)",
                    "months": self.transit_months_left,
                }
            )
        for h in self.hauls.values():
            if h.status == "in_flight" and h.months_left > 0:
                res_name = RESOURCE_NAMES.get(h.resource, h.resource)
                dest = self._location_label(h.dest_id)
                unit = self.fleet.get(h.unit_id)
                who = f"{unit.name}: " if unit else ""
                items.append(
                    {
                        "kind": "haul",
                        "label": f"{who}{h.amount_t:.0f} t {res_name} → {dest} ({h.option_name})",
                        "months": h.months_left,
                        "unit_id": h.unit_id,
                        "haul_id": h.id,
                    }
                )
        for job in self.build_queue:
            if job.status == "building" and job.months_left > 0:
                items.append(
                    {
                        "kind": "build",
                        "label": f"Finish building {job.name}",
                        "months": job.months_left,
                    }
                )
        for u in self.fleet.values():
            if u.status == "en_route" and u.months_left > 0:
                dest_id = u.target_id
                # Mine orders target a site id; resolve body for labeling
                dest_body = self.system.body_by_id(dest_id) if self.system else None
                if not dest_body and self.system and u.order == "mine":
                    site = self._find_mine_site(dest_id)
                    if site:
                        dest_body = self.system.body_by_id(site.body_id)
                dest_name = dest_body.name if dest_body else (dest_id or "destination")
                if u.order == "survey":
                    if u.search_resource:
                        mission = f"seek {RESOURCE_NAMES.get(u.search_resource, u.search_resource)}"
                    else:
                        mission = "broad survey"
                    label = f"{u.name} arrives at {dest_name} ({mission})"
                    kind = "survey_arrival"
                elif u.order == "mine":
                    label = f"{u.name} arrives at extraction site on {dest_name}"
                    kind = "mine_arrival"
                elif u.order == "return_ark":
                    label = f"{u.name} returns to ark (refuel)"
                    kind = "return_ark"
                elif u.order == "move":
                    label = f"{u.name} arrives at {dest_name}"
                    kind = "arrival"
                else:
                    label = f"{u.name} arrives at {dest_name}"
                    kind = "arrival"
                items.append(
                    {
                        "kind": kind,
                        "label": label,
                        "months": u.months_left,
                        "unit_id": u.id,
                        "body_id": dest_body.id if dest_body else dest_id,
                    }
                )
            elif u.status == "working" and u.order == "mine" and u.months_left > 0:
                items.append(
                    {
                        "kind": "mine",
                        "label": f"{u.name} finishes mining shift",
                        "months": u.months_left,
                        "unit_id": u.id,
                    }
                )
            elif u.status == "working" and u.order == "survey":
                res = u.search_resource or "broad survey"
                res_name = RESOURCE_NAMES.get(res, res) if u.search_resource else "broad survey"
                body = self.system.body_by_id(u.location_id) if self.system else None
                where = body.name if body else u.location_id
                items.append(
                    {
                        "kind": "survey",
                        "label": f"{u.name} survey checkpoint @ {where} ({res_name})",
                        "months": self.SURVEY_WARP_SLICE_MONTHS,
                        "unit_id": u.id,
                        "body_id": u.location_id,
                    }
                )
        # Ark continuous goals show as recurring checkpoints
        if self.phase == "system" and self.ark_scan_goals:
            for gid in self.ark_scan_goals:
                spec = self.ARK_SCAN_GOAL_SPECS.get(gid, {})
                items.append(
                    {
                        "kind": "ark_scan",
                        "label": f"Ark scan: {spec.get('label', gid)}",
                        "months": self.SURVEY_WARP_SLICE_MONTHS,
                        "goal_id": gid,
                    }
                )
        items.sort(key=lambda x: x["months"])
        for it in items:
            it["months"] = round(it["months"], 3)
            it["years"] = round(it["months"] / 12.0, 3)
            it["needs_confirm"] = it["months"] > self.SAFE_WARP_MONTHS + 1e-9
        return items

    def warp_to_next_event(self, force: bool = False) -> dict:
        """
        Advance to next queue event.
        Jumps longer than SAFE_WARP_MONTHS require force=True (UI confirms) so
        multi-year transit is not one accidental click. Idle warp skips *no* time.
        """
        self.catch_up()
        queue = self.event_queue()
        if not queue:
            return {
                "warped_months": 0.0,
                "reason": "idle",
                "message": "Nothing queued — authorize a build, order a unit, or set a scan goal first.",
                "next_event": None,
            }
        nxt = queue[0]
        m = float(nxt["months"])
        # Never "warp" a zero/negative residual (float dust)
        if m <= 1e-9:
            self.advance(SECONDS_PER_DAY * 0.01)
            return {
                "warped_months": 0.0,
                "reason": "next_event",
                "needs_confirm": False,
                "next_event": nxt,
                "message": f"Event due: {nxt['label']}",
            }
        if m > self.SAFE_WARP_MONTHS and not force:
            return {
                "warped_months": 0.0,
                "reason": "needs_confirm",
                "needs_confirm": True,
                "next_event": nxt,
                "message": (
                    f"Next: {nxt['label']} in {m:.2f} mo (~{m/12:.2f} y). "
                    f"Confirm long warp — time will not advance until you do."
                ),
            }
        # Nudge slightly past the event so floating-point cannot leave units stuck
        # at months_left ≈ 1e-15 still "en_route".
        dt_months = m + 1e-6
        self.advance(dt_months * SECONDS_PER_DAY * DAYS_PER_MONTH)
        self.auto_warp_votes += 1
        self._log("event", f"Warped {m:.2f} mo → {nxt['label']}")
        return {
            "warped_months": round(m, 4),
            "reason": "next_event",
            "needs_confirm": False,
            "next_event": nxt,
            "message": f"Warped {m:.2f} mo → {nxt['label']}",
        }

    def _log(self, kind: str, text: str) -> None:
        self.events.insert(
            0,
            {
                "id": _id(),
                "t_months": self.sim_time_s / (SECONDS_PER_DAY * DAYS_PER_MONTH),
                "kind": kind,
                "text": text,
            },
        )
        self.events = self.events[:100]
        self.message = text

    # --- menu / transit ---
    def open_survey_archive(self) -> List[dict]:
        """
        View pre-existing remote survey dossiers.
        Does not invent systems — archive was fixed when the room was created.
        """
        self.archive_opened = True
        self.catalog = list(self.survey_archive)
        self.message = (
            f"Survey archive open: {len(self.catalog)} remote dossiers on file "
            f"(colonial deep-space network)."
        )
        return self.catalog

    def refresh_catalog(self) -> List[dict]:
        """Legacy name — opens the going-concern survey archive."""
        return self.open_survey_archive()

    def select_star(self, seed: int) -> dict:
        # Must match a dossier (going concern), not an arbitrary invent
        dossier = next((d for d in self.survey_archive if d["seed"] == seed), None)
        if dossier is None:
            # Allow if archive not filtered yet but seed is in opened catalog
            dossier = next((d for d in self.catalog if d.get("seed") == seed), None)
        if dossier is None:
            raise ValueError("unknown dossier — open the survey archive and pick a star on file")
        self.selected_seed = seed
        self.system = generate_system(seed=seed)
        self.transit_months_left = 12.0 * (8.0 + self.system.difficulty)  # ~8–18 years
        self.phase = "transit"
        self.sim_time_s = 0.0
        self.last_wall = time.time()
        label = dossier.get("dossier_id") or seed
        self._log(
            "transit",
            f"Committed to dossier {label} ({self.system.star.get('name', seed)}). "
            f"Transit ~{self.transit_months_left/12:.1f} years. Xe reserved for capture.",
        )
        return self.snapshot()

    def _arrive(self) -> None:
        self.phase = "system"
        self.ark_stock["Xe"] = 0.0
        assert self.system
        home = next(
            (b for b in self.system.bodies if b.kind == "planet" and b.planet_class == "rocky"),
            next(b for b in self.system.bodies if b.kind == "planet"),
        )
        self.home_body_id = home.id
        self.sites["ark_orbit"] = Site(body_id=home.id, buildings=["ark"], stockpile={})
        self._spawn_arrival_ark(home.id)
        self._log(
            "arrival",
            f"Capture complete at {home.name}. Xe tanks dry. "
            f"Ark holds people and seed materials — authorize builds for survey craft and industry gear.",
        )

    def _spawn_arrival_ark(self, home_id: str) -> None:
        """Materials-only arrival: ark only, no pre-built specialized fleet."""
        self.fleet.clear()
        self.build_queue.clear()
        self.fleet["ark"] = FleetUnit(
            id="ark",
            name="Colony Ark",
            kind="ark",
            location_id="ark",  # ark is its own map node, parked at home_body
            capabilities=[CAP_COMMAND, CAP_BUILD, CAP_HAUL],
        )

    def body_allows_mass_driver(self, body) -> bool:
        """Railguns only work on light wells (asteroids, most moons, small rock worlds)."""
        if body is None:
            return False
        if body.kind == "asteroid":
            return True
        if body.kind == "moon":
            return (
                dv_surface_to_orbit(body.mass_kg, body.radius_m)
                <= MASS_DRIVER_MAX_SURFACE_DV_M_S * 1.15
            )
        if body.kind == "planet" and body.planet_class == "rocky":
            return (
                dv_surface_to_orbit(body.mass_kg, body.radius_m)
                <= MASS_DRIVER_MAX_SURFACE_DV_M_S
            )
        return False  # gas giants, ice giants, etc.

    def _has_building(self, body_id: str, building_id: str) -> bool:
        site = self.sites.get(body_id)
        return bool(site and building_id in site.buildings)

    def site_power_mw(self, body_id: str) -> float:
        """
        Available electrical power at a site (MW).
        Solar scales with stellar luminosity / a²; chem genset needs fuel in stockpile.
        """
        if not self.system:
            return 0.0
        site = self.sites.get(body_id)
        if not site:
            return 0.0
        body = self.system.body_by_id(body_id)
        if not body:
            return 0.0
        mw = 0.0
        if "ark" in site.buildings:
            mw += 80.0  # colony ship reactors
        if "solar_farm" in site.buildings:
            lum = float(self.system.star.get("lum") or 1.0)
            # Moons use parent heliocentric distance for insolation
            if body.kind == "moon" and body.parent_id:
                parent = self.system.body_by_id(body.parent_id)
                a_m = parent.semi_major_m if parent else body.semi_major_m
            else:
                a_m = body.semi_major_m
            a_au = max(a_m / AU_M, 0.05)
            insolation = lum / (a_au * a_au)
            # ~28 MW nameplate @ 1 AU Sol; outer / dim stars fall off hard
            mw += 28.0 * min(max(insolation, 0.0), 4.0)
        if "chem_genset" in site.buildings:
            # Rated 30 MW only while fuel remains
            if site.stockpile.get("chem_prop", 0.0) >= 0.25:
                mw += 30.0
        return mw

    def mass_driver_online(self, body_id: str) -> bool:
        """Mass driver present *and* site bus can supply its continuous draw."""
        if not self._has_building(body_id, "mass_driver"):
            return False
        return self.site_power_mw(body_id) + 1e-9 >= MASS_DRIVER_POWER_MW

    def _consume_mass_driver_power(self, body_id: str, amount_t: float) -> None:
        """
        Firing the rail draws the power bus. If chem genset is part of the supply
        and solar alone is insufficient, burn a little chem_prop.
        """
        site = self.sites.get(body_id)
        if not site:
            return
        solar_only = 0.0
        # Recompute solar+ark without genset
        body = self.system.body_by_id(body_id) if self.system else None
        if body and "ark" in site.buildings:
            solar_only += 80.0
        if body and "solar_farm" in site.buildings:
            lum = float(self.system.star.get("lum") or 1.0)
            if body.kind == "moon" and body.parent_id:
                parent = self.system.body_by_id(body.parent_id)
                a_m = parent.semi_major_m if parent else body.semi_major_m
            else:
                a_m = body.semi_major_m
            a_au = max(a_m / AU_M, 0.05)
            insolation = lum / (a_au * a_au)
            solar_only += 28.0 * min(max(insolation, 0.0), 4.0)
        if solar_only + 1e-9 >= MASS_DRIVER_POWER_MW:
            return  # pure electric shot
        if "chem_genset" in site.buildings:
            # ~0.08 t prop per tonne of payload (dirty bootstrap)
            burn = max(0.3, 0.08 * amount_t)
            have = site.stockpile.get("chem_prop", 0.0)
            if have + 1e-9 < burn:
                raise ValueError(
                    f"chem genset needs {burn:.2f} t chem_prop for this shot; have {have:.1f}"
                )
            site.stockpile["chem_prop"] = have - burn

    def _heliocentric_radius_m(self, body_id: str) -> float:
        """Orbital radius about the star for travel planning (moons use parent planet)."""
        assert self.system
        if body_id in ("ark", "ark_orbit"):
            site = self.sites.get("ark_orbit")
            body_id = site.body_id if site else next(b.id for b in self.system.bodies if b.kind == "planet")
        b = self.system.body_by_id(body_id)
        if not b:
            raise ValueError("unknown body")
        if b.kind == "moon" and b.parent_id:
            parent = self.system.body_by_id(b.parent_id)
            return parent.semi_major_m if parent else b.semi_major_m
        return b.semi_major_m

    def _is_ark_loc(self, location_id: str) -> bool:
        return location_id in ("ark", "ark_orbit")

    def _resolve_location_id(self, location_id: str) -> str:
        """
        Body id for *heliocentric* travel math.
        Note: "ark" is a real dock for fleet ops — use _is_ark_loc / _same_location
        for presence. This maps ark → home planet only for orbital radii.
        """
        if location_id in ("ark", "ark_orbit", "home", ""):
            return self.home_body_id or location_id
        return location_id

    def _same_location(self, a: str, b: str) -> bool:
        """True only if both docked at ark, or both on the same body (not ark≈planet)."""
        if self._is_ark_loc(a) and self._is_ark_loc(b):
            return True
        if self._is_ark_loc(a) or self._is_ark_loc(b):
            return False
        return self._resolve_location_id(a) == self._resolve_location_id(b)

    def _begin_transit(self, u: FleetUnit, dest_id: str, travel: float, order: str) -> None:
        """Mark unit en route; path drawn from transit_from → dest on the map."""
        u.transit_from_id = u.location_id
        u.target_id = dest_id
        u.order = order
        u.status = "en_route"
        u.months_total = max(travel, 0.05)
        u.months_left = u.months_total

    def _travel_dv_m_s(self, from_id: str, to_id: str, unit_kind: str = "survey") -> float:
        """
        Δv cost (m/s) for a unit hop. Survey probes are low-thrust ion → higher budget burn
        than pure chemical Hohmann. Local planet-system hops are cheaper.
        """
        from .orbits import hohmann_transfer

        assert self.system
        # Leaving / returning to the ark always costs a small orbital hop
        # (even when the destination is the home planet the ark is parked at).
        ark_leg = False
        if self._is_ark_loc(from_id) ^ self._is_ark_loc(to_id):
            ark_leg = True
        if self._same_location(from_id, to_id):
            return 0.0

        from_body = self._resolve_location_id(from_id)
        to_body = self._resolve_location_id(to_id)
        fb = self.system.body_by_id(from_body)
        tb = self.system.body_by_id(to_body)

        def planet_key(body_id: str, body) -> Optional[str]:
            if body is None:
                return body_id
            if body.kind == "moon":
                return body.parent_id
            return body.id

        # Ark ↔ home planet (or any body in home planet system after resolve)
        if ark_leg and from_body == to_body:
            # Separation burn / rendezvous from high ark orbit to LO
            return 220.0 if unit_kind == "survey" else 280.0

        if tb and fb and planet_key(from_body, fb) == planet_key(to_body, tb):
            # Local moon/planet rephasing
            base = 280.0
            if fb.kind == "moon" and tb.kind == "moon" and fb.id != tb.id:
                base = 420.0
            elif fb.kind != tb.kind:
                base = 350.0
            if ark_leg:
                base += 120.0
            # Powered mass driver: EM assist for bots/probes leaving surface
            if fb and not self._is_ark_loc(from_id) and self.mass_driver_online(from_body):
                base *= 0.25
            return base

        r1 = self._heliocentric_radius_m(from_body)
        r2 = self._heliocentric_radius_m(to_body)
        if abs(r1 - r2) / max(r1, r2) < 0.01:
            return 180.0 + (80.0 if ark_leg else 0.0)

        dv_h, _tof = hohmann_transfer(r1, r2, self.system.star_mu)
        # Playable budgets: high-Isp ion / efficient tugs use a fraction of chemical Hohmann
        # as "tank units" so outer system is expensive but not a single-hop brick wall.
        if unit_kind == "survey":
            cost = max(200.0, dv_h * 0.22)
        elif unit_kind == "miner":
            cost = max(250.0, dv_h * 0.28)
        else:
            cost = max(300.0, dv_h * 0.35)
        if ark_leg:
            cost += 100.0  # ark departure / capture
        # Powered rail launch shaves the surface-lift share of the budget
        if fb and not self._is_ark_loc(from_id) and self.mass_driver_online(from_body):
            assist = min(cost * 0.35, 800.0)
            cost = max(150.0, cost - assist)
        return cost

    def _travel_months(self, from_id: str, to_id: str, unit_kind: str = "hauler") -> float:
        """
        Cruise time from orbital mechanics (Hohmann between heliocentric radii).
        Survey sats are low-thrust → longer than a chemical hauler.
        Ark dock → home planet is a real hop (not free).
        """
        from .orbits import hohmann_transfer
        from .constants import DAYS_PER_MONTH, SECONDS_PER_DAY

        assert self.system
        if self._same_location(from_id, to_id):
            return 0.0

        ark_leg = self._is_ark_loc(from_id) ^ self._is_ark_loc(to_id)
        from_body = self._resolve_location_id(from_id)
        to_body = self._resolve_location_id(to_id)

        # Ark ↔ same planet: days–weeks to leave bay and enter survey/low orbit
        if ark_leg and from_body == to_body:
            return 0.55 if unit_kind == "survey" else 0.4

        fb = self.system.body_by_id(from_body)
        tb = self.system.body_by_id(to_body)

        # Local transfer: same planet system (planet ↔ its moon, or moon ↔ moon of same parent)
        def planet_key(body) -> Optional[str]:
            if body is None:
                return None
            if body.kind == "moon":
                return body.parent_id
            return body.id

        if tb and fb and planet_key(fb) == planet_key(tb):
            # Days–weeks to change moon orbits / lander loiter — not interplanetary
            local = 0.4 if unit_kind == "survey" else 0.25
            if fb.kind == "moon" and tb.kind == "moon" and fb.id != tb.id:
                local += 0.2
            if ark_leg:
                local += 0.2
            return local

        r1 = self._heliocentric_radius_m(from_body)
        r2 = self._heliocentric_radius_m(to_body)
        # Avoid identical radii numerical issue
        if abs(r1 - r2) / max(r1, r2) < 0.01:
            return 0.5 + (0.2 if ark_leg else 0.0)

        _dv, tof_s = hohmann_transfer(r1, r2, self.system.star_mu)
        months = tof_s / (SECONDS_PER_DAY * DAYS_PER_MONTH)

        # Hohmann is the *minimum-energy* coast. Add synodic-ish wait fudge for departure
        # window (player doesn't micro the date): ~10–20% of TOF, min 0.5 mo.
        window = max(0.5, 0.15 * months)

        # Low-thrust survey sats: longer than pure Hohmann chemical
        if unit_kind == "survey":
            months *= 1.65
            window *= 1.1
        elif unit_kind == "miner":
            months *= 1.25

        total = months + window
        if ark_leg:
            total += 0.15
        # Floor: even "nearby" neighbors take real time
        return max(0.75, total)

    def _spend_dv(self, u: FleetUnit, dv_cost: float, label: str) -> None:
        """Deduct Δv from unit tanks; raise if insufficient."""
        if u.dv_capacity_m_s <= 0:
            return  # unlimited (ark)
        if dv_cost <= 1e-6:
            return
        if u.dv_remaining_m_s + 1e-6 < dv_cost:
            raise ValueError(
                f"{u.name} needs {dv_cost:.0f} m/s Δv for {label}, "
                f"has {u.dv_remaining_m_s:.0f} m/s remaining — return to ark or a refuel depot"
            )
        u.dv_remaining_m_s = max(0.0, u.dv_remaining_m_s - dv_cost)

    def _can_refuel_at(self, location_id: str) -> tuple[bool, str]:
        """(ok, reason). Docked at ark, or site with refuel_depot."""
        if self._is_ark_loc(location_id) and any(
            u.kind == "ark" for u in self.fleet.values()
        ):
            return True, "ark"
        loc = self._resolve_location_id(location_id)
        # Also allow refuel at home planet if ark is parked there and unit is on that body
        if loc == self.home_body_id and any(u.kind == "ark" for u in self.fleet.values()):
            return True, "ark"
        site = self.sites.get(loc)
        if site and "refuel_depot" in site.buildings:
            return True, "depot"
        return False, ""

    def _refuel_unit(self, u: FleetUnit, source: str) -> float:
        """Fill tanks. Returns m/s restored. Depot spends chem_prop; ark is free refill."""
        if u.dv_capacity_m_s <= 0:
            return 0.0
        need = u.dv_capacity_m_s - u.dv_remaining_m_s
        if need <= 1e-6:
            return 0.0
        if source == "depot":
            site = self.sites.get(u.location_id)
            if not site or "refuel_depot" not in site.buildings:
                raise ValueError("no refuel depot here")
            # ~1 t chem_prop per 150 m/s restored (playable abstraction)
            prop_need = need / 150.0
            have = site.stockpile.get("chem_prop", 0.0)
            if have + 1e-9 < 0.5:
                raise ValueError("depot propellant empty — haul chem_prop here")
            fraction = min(1.0, have / max(prop_need, 1e-6))
            restored = need * fraction
            site.stockpile["chem_prop"] = have - prop_need * fraction
            u.dv_remaining_m_s = min(u.dv_capacity_m_s, u.dv_remaining_m_s + restored)
            return restored
        # ark: full free refill (seed industry / ship stores)
        u.dv_remaining_m_s = u.dv_capacity_m_s
        return need

    def estimate_order(self, unit_id: str, order: str, target_id: str = "") -> dict:
        """UI helper: how long / how much Δv will this order take?"""
        u = self.fleet.get(unit_id)
        if not u or not self.system:
            return {"months": 0, "travel_months": 0, "work_months": 0, "dv_m_s": 0}
        work = 0.0
        if order == "survey":
            work = 0.0
        elif order == "mine":
            work = 1.5
        elif order in ("move", "return_ark"):
            work = 0.0
        elif order == "idle":
            return {
                "months": 0,
                "travel_months": 0,
                "work_months": 0,
                "dv_m_s": 0,
                "dv_remaining_m_s": round(u.dv_remaining_m_s, 1),
                "dv_capacity_m_s": round(u.dv_capacity_m_s, 1),
            }
        elif order == "refuel":
            return {
                "months": 0.05,
                "travel_months": 0,
                "work_months": 0.05,
                "dv_m_s": 0,
                "dv_remaining_m_s": round(u.dv_remaining_m_s, 1),
                "dv_capacity_m_s": round(u.dv_capacity_m_s, 1),
                "note": "Refill tanks at ark or a refuel depot.",
            }

        dest_body = target_id
        if order == "return_ark":
            dest_body = self.home_body_id
        elif order == "mine" and self.system:
            site = self._find_mine_site(target_id)
            if site:
                dest_body = site.body_id
        travel = (
            self._travel_months(u.location_id, dest_body, u.kind) if dest_body else 0.0
        )
        dv = (
            self._travel_dv_m_s(u.location_id, dest_body, u.kind) if dest_body else 0.0
        )
        note = ""
        if order == "survey":
            note = "Then stays on station; detail improves over months until you recall it."
        if order == "return_ark":
            note = "Arriving at ark refills Δv tanks."
        can = u.dv_capacity_m_s <= 0 or u.dv_remaining_m_s + 1e-6 >= dv
        return {
            "months": round(travel + work, 2),
            "travel_months": round(travel, 2),
            "work_months": round(work, 2),
            "years": round((travel + work) / 12.0, 2),
            "dv_m_s": round(dv, 1),
            "dv_remaining_m_s": round(u.dv_remaining_m_s, 1),
            "dv_capacity_m_s": round(u.dv_capacity_m_s, 1),
            "dv_after_m_s": round(max(0.0, u.dv_remaining_m_s - dv), 1)
            if u.dv_capacity_m_s > 0
            else None,
            "can_afford_dv": can,
            "note": note,
        }

    def _find_mine_site(self, site_id: str):
        if not self.system:
            return None
        for b in self.system.bodies:
            for s in b.mine_sites:
                if s.id == site_id:
                    return s
        return None

    def _tick_survey(self, u: FleetUnit, months: float) -> None:
        assert self.system
        body = self.system.body_by_id(u.location_id)
        if not body:
            return
        focus = u.search_resource or None
        notes = body.apply_survey_time(months, focus_resource=focus)
        self.scanned.add(body.id)
        if notes:
            label = f"seeking {focus}" if focus else "broad survey"
            seek_t = body.seek_months.get(focus, body.survey_months) if focus else body.survey_months
            self._log(
                "scan",
                f"{u.name} @ {body.name} ({label}, {seek_t:.1f} mo): " + "; ".join(notes),
            )
        # On-station probes also deepen terraform dossiers (faster than remote ark)
        if body.planet_class in ("rocky", "moon") or (
            body.kind == "planet" and body.planet_class == "rocky"
        ):
            if self.hab_intel.get(body.id, 0) < 5:
                self.hab_seek_months[body.id] = (
                    self.hab_seek_months.get(body.id, 0.0) + months
                )
                tnotes = self._advance_terraform_intel(body, remote=False)
                for n in tnotes:
                    self._log("scan", f"{u.name} terraform intel @ {body.name}: {n}")

    def issue_order(
        self, unit_id: str, order: str, target_id: str = "", resource: str = ""
    ) -> dict:
        """
        Apply a unit's capability: survey | mine | move | return_ark | refuel | idle.
        Survey with resource="Fe" means "find sources of iron" on that body.
        Mine requires a found extraction site.
        Units with dv_capacity spend Δv on transit; return_ark / depot refuels.
        """
        self.catch_up()
        u = self.fleet.get(unit_id)
        if not u:
            raise ValueError("unknown unit")
        # Busy if en_route with time left, or mining shift, or surveying (must idle first)
        if u.status == "en_route" and u.months_left > 0:
            raise ValueError(f"{u.name} is en route")
        if u.status == "working" and u.order == "mine" and u.months_left > 0:
            raise ValueError(f"{u.name} is mining")
        if u.status == "working" and u.order == "survey" and order != "idle":
            raise ValueError(f"{u.name} is surveying — stand by (idle) to reassign")
        assert self.system

        if order == "idle":
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.search_resource = ""
            u.months_left = 0.0
            u.months_total = 0.0
            u.transit_from_id = ""
            self._log("order", f"{u.name}: standing by.")
            return self.snapshot()

        if order == "refuel":
            ok, source = self._can_refuel_at(u.location_id)
            if not ok:
                raise ValueError(
                    "not at ark or a refuel depot — return to ark or deploy a depot first"
                )
            if u.dv_capacity_m_s <= 0:
                raise ValueError("this unit has no Δv tanks")
            if u.dv_remaining_m_s >= u.dv_capacity_m_s - 1e-6:
                self._log("order", f"{u.name}: tanks already full.")
                return self.snapshot()
            restored = self._refuel_unit(u, source)
            self._log(
                "order",
                f"{u.name} refueled at {source}: +{restored:.0f} m/s Δv "
                f"({u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f}).",
            )
            return self.snapshot()

        if order == "return_ark":
            if self._is_ark_loc(u.location_id) and u.status == "idle":
                ok, source = self._can_refuel_at("ark")
                if ok and u.dv_capacity_m_s > 0:
                    restored = self._refuel_unit(u, source)
                    self._log(
                        "order",
                        f"{u.name} already at ark — tanks topped "
                        f"(+{restored:.0f} m/s, now {u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f}).",
                    )
                else:
                    self._log("order", f"{u.name} already at ark.")
                return self.snapshot()
            travel = self._travel_months(u.location_id, "ark", u.kind)
            dv = self._travel_dv_m_s(u.location_id, "ark", u.kind)
            self._spend_dv(u, dv, "return to ark")
            u.search_resource = ""
            self._begin_transit(u, "ark", max(0.4, travel), "return_ark")
            self._log(
                "order",
                f"{u.name} → return to ark: {u.months_left:.1f} mo, "
                f"burned {dv:.0f} m/s Δv (remaining {u.dv_remaining_m_s:.0f}). "
                f"Tanks will refill on arrival.",
            )
            return self.snapshot()

        if order == "survey":
            if CAP_SURVEY not in u.capabilities:
                raise ValueError("unit cannot survey")
            body = self.system.body_by_id(target_id)
            if not body:
                raise ValueError("pick a body to survey")
            res = (resource or "").strip()
            from .system_gen import _searchable_resources

            allowed = _searchable_resources(body)
            if res and res not in allowed:
                if not any(d.resource == res for d in body.deposits):
                    raise ValueError(f"not a useful search target here: {res}")
            u.search_resource = res
            goal = f"sources of {RESOURCE_NAMES.get(res, res)}" if res else "broad composition"
            # On the body already (not just docked at ark near it)
            if not self._is_ark_loc(u.location_id) and self._same_location(
                u.location_id, target_id
            ):
                u.location_id = target_id
                u.order = "survey"
                u.target_id = target_id
                u.status = "working"
                u.months_left = 0.0
                u.months_total = 0.0
                u.transit_from_id = ""
                self._log(
                    "order",
                    f"{u.name} begins search for {goal} on {body.name} "
                    f"(already on station — 0 m/s Δv). "
                    f"Tanks {u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f} m/s.",
                )
            else:
                travel = self._travel_months(u.location_id, target_id, u.kind)
                dv = self._travel_dv_m_s(u.location_id, target_id, u.kind)
                self._spend_dv(u, dv, f"transit to {body.name}")
                from_label = self._location_label(u.location_id)
                self._begin_transit(u, target_id, travel, "survey")
                self._log(
                    "order",
                    f"{u.name} leaves {from_label} → {body.name} for {goal}: "
                    f"{u.months_left:.2f} mo, burned {dv:.0f} m/s Δv "
                    f"(remaining {u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f}).",
                )
            return self.snapshot()

        if order == "mine":
            if CAP_MINE not in u.capabilities:
                raise ValueError("unit cannot mine")
            msite = self._find_mine_site(target_id)
            if not msite:
                raise ValueError(
                    "no mine site selected — survey until a suitable location is found, "
                    "then mine that site (not the whole world)"
                )
            body = self.system.body_by_id(msite.body_id)
            work = 1.5
            if not self._is_ark_loc(u.location_id) and self._same_location(
                u.location_id, msite.body_id
            ):
                u.location_id = msite.body_id
                u.order = "mine"
                u.target_id = msite.id
                u.status = "en_route"
                u.months_total = work
                u.months_left = work
                u.transit_from_id = msite.body_id
                self._log(
                    "order",
                    f"{u.name} starts mining shift at {msite.name} on "
                    f"{body.name if body else msite.body_id} "
                    f"({work:.1f} mo, already on body — 0 m/s Δv).",
                )
            else:
                travel = self._travel_months(u.location_id, msite.body_id, u.kind)
                dv = self._travel_dv_m_s(u.location_id, msite.body_id, u.kind)
                self._spend_dv(u, dv, f"transit to mine {msite.name}")
                from_label = self._location_label(u.location_id)
                self._begin_transit(u, msite.id, travel + work, "mine")
                self._log(
                    "order",
                    f"{u.name} leaves {from_label} → mine {msite.name} on "
                    f"{body.name if body else msite.body_id}: "
                    f"{travel:.1f} mo transit + {work:.1f} mo shift, "
                    f"burned {dv:.0f} m/s Δv (remaining {u.dv_remaining_m_s:.0f}).",
                )
            return self.snapshot()

        if order == "move":
            body = self.system.body_by_id(target_id)
            if not body:
                raise ValueError("pick a destination")
            if not self._is_ark_loc(u.location_id) and self._same_location(
                u.location_id, target_id
            ):
                u.location_id = target_id
                u.status = "idle"
                u.order = ""
                u.target_id = ""
                u.months_left = 0.0
                u.months_total = 0.0
                u.transit_from_id = ""
                self._log("order", f"{u.name} already at {body.name} — 0 m/s Δv.")
                return self.snapshot()
            travel = self._travel_months(u.location_id, target_id, u.kind)
            dv = self._travel_dv_m_s(u.location_id, target_id, u.kind)
            self._spend_dv(u, dv, f"move to {body.name}")
            from_label = self._location_label(u.location_id)
            self._begin_transit(u, target_id, max(0.75, travel), "move")
            self._log(
                "order",
                f"{u.name} leaves {from_label} → {body.name}: {u.months_left:.1f} mo, "
                f"burned {dv:.0f} m/s Δv "
                f"(remaining {u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f}).",
            )
            return self.snapshot()

        raise ValueError(f"unknown order {order}")

    def _complete_unit_order(self, u: FleetUnit) -> None:
        assert self.system
        if u.order == "return_ark":
            u.location_id = "ark"
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.months_left = 0.0
            u.months_total = 0.0
            u.transit_from_id = ""
            restored = 0.0
            if u.dv_capacity_m_s > 0:
                restored = self._refuel_unit(u, "ark")
            home = self.home_body_id
            body = self.system.body_by_id(home) if home else None
            self._log(
                "order",
                f"{u.name} docked at ark"
                + (f" (near {body.name})" if body else "")
                + f". Tanks refilled (+{restored:.0f} m/s → "
                f"{u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f}).",
            )
            return

        if u.order == "move":
            u.location_id = u.target_id
            u.status = "idle"
            u.order = ""
            body = self.system.body_by_id(u.location_id)
            self._log(
                "order",
                f"{u.name} arrived at {body.name if body else u.location_id} "
                f"(Δv {u.dv_remaining_m_s:.0f}/{u.dv_capacity_m_s:.0f} m/s).",
            )
            u.target_id = ""
            u.months_left = 0.0
            u.months_total = 0.0
            u.transit_from_id = ""
            return

        if u.order == "survey":
            u.location_id = u.target_id
            body = self.system.body_by_id(u.target_id)
            u.status = "working"
            u.months_left = 0.0
            u.months_total = 0.0
            u.transit_from_id = ""
            goal = (
                f"sources of {RESOURCE_NAMES.get(u.search_resource, u.search_resource)}"
                if u.search_resource
                else "broad composition"
            )
            self._log(
                "scan",
                f"{u.name} on station at {body.name if body else u.target_id}, "
                f"searching for {goal}. Recall with Stand by.",
            )
            if body:
                notes = body.apply_survey_time(0.25, focus_resource=u.search_resource or None)
                self.scanned.add(body.id)
                if notes:
                    self._log("scan", f"{u.name}: " + "; ".join(notes))
            return

        if u.order == "mine":
            msite = self._find_mine_site(u.target_id)
            if not msite:
                u.status = "idle"
                u.order = ""
                u.months_left = 0.0
                u.months_total = 0.0
                u.transit_from_id = ""
                self._log("mine", f"{u.name}: mine site gone.")
                return
            u.location_id = msite.body_id
            body = self.system.body_by_id(msite.body_id)
            site = self.sites.setdefault(msite.body_id, Site(body_id=msite.body_id))
            took = min(msite.amount_t, 50.0 * msite.grade)
            msite.amount_t -= took
            if body:
                for dep in body.deposits:
                    if dep.resource == msite.resource:
                        dep.amount_t = max(0.0, dep.amount_t - took)
            site.stockpile[msite.resource] = site.stockpile.get(msite.resource, 0.0) + took
            self._log(
                "mine",
                f"{u.name} extracted {took:.0f} t {msite.resource} at {msite.name} "
                f"({msite.region}). Site remaining ~{msite.amount_t:.0f} t.",
            )
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.months_left = 0.0
            u.months_total = 0.0
            u.transit_from_id = ""
            return

        u.status = "idle"
        u.months_left = 0.0
        u.months_total = 0.0
        u.transit_from_id = ""

    # --- scan / base plans ---
    def scan_body(self, body_id: str) -> dict:
        """Legacy helper: instant survey via first free survey sat, or error."""
        free = next((u for u in self.fleet.values() if CAP_SURVEY in u.capabilities and u.status == "idle"), None)
        if not free:
            raise ValueError("no idle survey unit — select a survey sat and order Survey")
        return self.issue_order(free.id, "survey", body_id)

    def plan_base(self, body_id: str, power_id: str, hab_id: str, name: str = "") -> dict:
        self.catch_up()
        assert self.system
        body = self.system.body_by_id(body_id)
        if not body:
            raise ValueError("unknown body")
        if power_id not in POWER_OPTIONS or hab_id not in HAB_OPTIONS:
            raise ValueError("bad options")
        plan = expand_base_plan(power_id, hab_id)
        pid = _id()
        project = Project(
            id=pid,
            name=name or f"Base on {body.name}",
            body_id=body_id,
            power_id=power_id,
            hab_id=hab_id,
            materials=dict(plan["materials"]),
            buildings=list(plan["buildings"]),
        )
        self.projects[pid] = project
        if body_id not in self.sites:
            self.sites[body_id] = Site(body_id=body_id)

        # Spawn contracts — contextual ore vs refined
        site = self.sites[body_id]
        has_refinery = "refinery" in site.buildings or "refinery" in project.buildings
        for res, amt in project.materials.items():
            if amt <= 0:
                continue
            note = ""
            req = res
            # If they need steel and will build refinery / have Fe deposit, prefer Fe ore contract too
            if res == "steel" and has_refinery:
                # split: contract steel from ark + Fe ore local
                self._add_contract(pid, f"Deliver steel (bootstrap)", "steel", amt * 0.35, "Ark or import refined steel to start.")
                self._add_contract(pid, f"Mine iron ore for refinery", "Fe", amt * 1.2, "Local ore once extractor is up; refinery converts to steel.")
                continue
            if res == "panel":
                note = "Ark can trickle panels, or fab locally once online."
            if res == "magnet" or res in ("He", "fusion_fuel", "radiator"):
                note = "Long path — visible, not blocked by research. Expect years."
            self._add_contract(pid, f"Supply {RESOURCE_NAMES.get(res, res)}", req, amt, note)

        # Building kits themselves
        for b in project.buildings:
            bt = BUILDINGS.get(b)
            if not bt:
                continue
            for res, amt in bt.build_cost.items():
                self._add_contract(pid, f"Build {bt.name}: {RESOURCE_NAMES.get(res, res)}", res, amt, f"Construction inputs for {bt.name}.")

        self._log("project", f"Project '{project.name}' created — contracts opened from needs.")
        return self.snapshot()

    def _add_contract(self, project_id: str, title: str, resource: str, amount: float, note: str) -> None:
        cid = _id()
        self.contracts[cid] = Contract(
            id=cid,
            project_id=project_id,
            title=title,
            resource=resource,
            amount_t=amount,
            note=note,
        )

    def deliver_from_ark(self, contract_id: str, amount_t: Optional[float] = None) -> dict:
        """Fill contract from ark stock (instant local orbital transfer abstraction for bootstrap)."""
        self.catch_up()
        c = self.contracts.get(contract_id)
        if not c or c.status != "open":
            raise ValueError("bad contract")
        need = c.amount_t - c.delivered_t
        have = self.ark_stock.get(c.resource, 0.0)
        give = min(need, have, amount_t if amount_t is not None else need)
        if give <= 0:
            raise ValueError(f"ark has no {c.resource}")
        self.ark_stock[c.resource] = have - give
        c.delivered_t += give
        # material goes to site stockpile
        proj = self.projects[c.project_id]
        site = self.sites.setdefault(proj.body_id, Site(body_id=proj.body_id))
        site.stockpile[c.resource] = site.stockpile.get(c.resource, 0.0) + give
        if c.delivered_t >= c.amount_t - 1e-6:
            c.status = "filled"
            c.delivered_t = c.amount_t
            self._try_complete_project(proj)
        self._log("deliver", f"Ark delivered {give:.1f} t {c.resource} toward '{c.title}'.")
        return self.snapshot()

    def _try_complete_project(self, proj: Project) -> None:
        related = [c for c in self.contracts.values() if c.project_id == proj.id]
        if related and all(c.status == "filled" for c in related):
            site = self.sites[proj.body_id]
            for b in proj.buildings:
                if b not in site.buildings:
                    site.buildings.append(b)
            proj.status = "complete"
            self._log("project", f"Project complete: {proj.name}. Buildings online: {', '.join(proj.buildings)}.")

    # --- hauls ---
    def haul_options(self, origin_id: str, dest_id: str) -> List[dict]:
        """
        Transfer menu: interplanetary Hohmann + surface legs.
        - Leaving a surface stockpile costs ascent Δv *unless* a mass driver is online
          (railguns replace chemical ascent on light bodies).
        - Arriving at a body costs a partial landing burn.
        """
        assert self.system
        o = self._radius_of(origin_id)
        d = self._radius_of(dest_id)
        extra = 0.0
        notes: List[str] = []

        origin_body = None
        if origin_id not in ("ark", "ark_orbit"):
            origin_body = self.system.body_by_id(origin_id)
        if origin_body and origin_body.kind in ("planet", "moon", "asteroid"):
            ascent = 0.45 * dv_surface_to_orbit(origin_body.mass_kg, origin_body.radius_m)
            if self.mass_driver_online(origin_id):
                notes.append(
                    f"mass driver ascent (rail + {self.site_power_mw(origin_id):.0f} MW — no chemical lift)"
                )
                # EM launch: negligible propellant; tiny residual for catch/rendezvous
                extra += min(80.0, ascent * 0.05)
            else:
                if self._has_building(origin_id, "mass_driver"):
                    notes.append(
                        f"mass driver unpowered ({self.site_power_mw(origin_id):.0f}/"
                        f"{MASS_DRIVER_POWER_MW:.0f} MW) — chemical ascent"
                    )
                notes.append(f"chemical ascent ~{ascent:.0f} m/s")
                extra += ascent

        dest = self.system.body_by_id(dest_id) if dest_id not in ("ark", "ark_orbit") else None
        if dest and dest.kind in ("planet", "moon", "asteroid"):
            # Landing / surface delivery leg (not full SSTO both ways)
            land = 0.35 * dv_surface_to_orbit(dest.mass_kg, dest.radius_m)
            extra += land
            notes.append(f"landing ~{land:.0f} m/s")

        # Avoid identical radii (same orbit) — tiny hop
        if abs(o - d) / max(o, d) < 0.02:
            o *= 0.98
        opts = transfer_options(
            o, d, self.system.star_mu, ship_dry_mass_t=8.0, extra_dv_m_s=extra, isp_s=340.0
        )
        out = []
        for x in opts:
            dopt = x.to_dict()
            if notes:
                dopt["description"] = (dopt.get("description") or "") + " · " + "; ".join(notes)
            dopt["mass_driver_ascent"] = self.mass_driver_online(origin_id) if origin_body else False
            dopt["site_power_mw"] = (
                round(self.site_power_mw(origin_id), 1) if origin_body else None
            )
            out.append(dopt)
        return out

    def mass_launch(
        self,
        origin_id: str,
        dest_id: str,
        resource: str,
        amount_t: float,
    ) -> dict:
        """
        Fire cargo off a mass-driver body without a hauler or chemical ascent.
        Requires site power ≥ MASS_DRIVER_POWER_MW. Packet coasts to dest.
        """
        self.catch_up()
        if self.phase != "system":
            raise ValueError("only after arrival")
        if origin_id in ("ark", "ark_orbit"):
            raise ValueError("mass driver is a surface launcher — pick a body origin")
        body = self.system.body_by_id(origin_id) if self.system else None
        if not body:
            raise ValueError("unknown origin body")
        if not self._has_building(origin_id, "mass_driver"):
            raise ValueError(f"no mass driver on {body.name} — build one first")
        if not self.body_allows_mass_driver(body):
            raise ValueError(f"{body.name} is too deep a well for mass-driver launch")
        power = self.site_power_mw(origin_id)
        if power + 1e-9 < MASS_DRIVER_POWER_MW:
            raise ValueError(
                f"mass driver needs ≥{MASS_DRIVER_POWER_MW:.0f} MW; "
                f"{body.name} bus has {power:.1f} MW — build a solar farm or chem genset"
            )
        if dest_id in ("ark_orbit",):
            dest_id = "ark"
        if origin_id == dest_id:
            raise ValueError("origin and destination must differ")

        stock = self._stock_for(origin_id)
        if stock.get(resource, 0.0) + 1e-9 < amount_t:
            raise ValueError(
                f"insufficient {RESOURCE_NAMES.get(resource, resource)} "
                f"(have {stock.get(resource, 0.0):.1f} t)"
            )
        # Fuel the shot if genset is carrying the bus
        self._consume_mass_driver_power(origin_id, amount_t)

        # Time of flight ≈ economy transfer (no rocket propellant)
        from .orbits import hohmann_transfer
        from .constants import DAYS_PER_MONTH, SECONDS_PER_DAY

        r1 = self._radius_of(origin_id)
        r2 = self._radius_of(dest_id)
        if abs(r1 - r2) / max(r1, r2) < 0.02:
            r1 *= 0.98
        _dv, tof_s = hohmann_transfer(r1, r2, self.system.star_mu)
        months = max(0.5, tof_s / (SECONDS_PER_DAY * DAYS_PER_MONTH))
        # Mass-driver packets are slightly slower (release windows / catch)
        months *= 1.1

        stock[resource] -= amount_t
        hid = _id()
        self.hauls[hid] = Haul(
            id=hid,
            origin_id=origin_id,
            dest_id=dest_id,
            resource=resource,
            amount_t=amount_t,
            option_name="Mass driver launch",
            propellant_t=0.0,
            months_total=months,
            months_left=months,
            dv_m_s=_dv,
            unit_id="",
            contract_id=None,
        )
        dest_label = self._location_label(dest_id)
        res_name = RESOURCE_NAMES.get(resource, resource)
        self._log(
            "haul",
            f"Mass driver @ {body.name} ({power:.0f} MW): shot {amount_t:.1f} t {res_name} "
            f"→ {dest_label} ({months:.1f} mo coast, electric launch).",
        )
        return self.snapshot()

    def _radius_of(self, body_id: str) -> float:
        assert self.system
        if body_id in ("ark", "ark_orbit"):
            site = self.sites.get("ark_orbit")
            body_id = site.body_id if site else next(
                (b.id for b in self.system.bodies if b.kind == "planet"),
                self.system.bodies[0].id,
            )
        b = self.system.body_by_id(body_id)
        if not b:
            raise ValueError("unknown body")
        if b.kind == "moon":
            parent = self.system.body_by_id(b.parent_id) if b.parent_id else None
            return parent.semi_major_m if parent else b.semi_major_m
        return b.semi_major_m

    def start_haul(
        self,
        origin_id: str,
        dest_id: str,
        resource: str,
        amount_t: float,
        option_index: int = 0,
        contract_id: Optional[str] = None,
        unit_id: str = "",
    ) -> dict:
        """
        Launch a physics transfer: cargo + chem_prop from origin stock.
        Prefer a free hauler (unit_id or first idle CAP_HAUL) — it rides the route.
        Transfer options: Economy / Expedited / Sprint (propellant vs months).
        """
        self.catch_up()
        if self.phase != "system":
            raise ValueError("only after arrival")
        if origin_id == dest_id or (
            origin_id in ("ark", "ark_orbit") and dest_id in ("ark", "ark_orbit")
        ):
            raise ValueError("origin and destination must differ")
        # Normalize ark aliases
        if origin_id == "ark_orbit":
            origin_id = "ark"
        if dest_id == "ark_orbit":
            dest_id = "ark"

        opts = self.haul_options(origin_id, dest_id)
        if not opts or option_index < 0 or option_index >= len(opts):
            raise ValueError("bad transfer option")
        opt = opts[option_index]

        # Resolve hauler: explicit unit, else first idle hauler, else ark if it has CAP_HAUL
        hauler: Optional[FleetUnit] = None
        if unit_id:
            hauler = self.fleet.get(unit_id)
            if not hauler:
                raise ValueError("unknown unit")
            if CAP_HAUL not in hauler.capabilities:
                raise ValueError(f"{hauler.name} cannot haul")
            if hauler.status != "idle" and not (
                hauler.kind == "ark" and hauler.status == "idle"
            ):
                if hauler.status != "idle":
                    raise ValueError(f"{hauler.name} is busy")
        else:
            hauler = next(
                (
                    u
                    for u in self.fleet.values()
                    if CAP_HAUL in u.capabilities
                    and u.status == "idle"
                    and u.kind == "hauler"
                ),
                None,
            )
            if not hauler:
                # Ark can bootstrap a single local-ish haul without a dedicated tug
                hauler = next(
                    (
                        u
                        for u in self.fleet.values()
                        if u.kind == "ark" and CAP_HAUL in u.capabilities
                    ),
                    None,
                )
        if not hauler:
            raise ValueError("no free hauler — authorize a Hauler build on the ark")

        stock = self._stock_for(origin_id)
        if stock.get(resource, 0.0) + 1e-9 < amount_t:
            raise ValueError(
                f"insufficient {RESOURCE_NAMES.get(resource, resource)} at origin "
                f"(have {stock.get(resource, 0.0):.1f} t)"
            )
        prop = float(opt["propellant_t"])
        # Propellant: prefer origin stock, else ark chem_prop for site→site hops
        prop_stock = stock
        if prop_stock.get("chem_prop", 0.0) + 1e-9 < prop:
            if origin_id not in ("ark", "ark_orbit") and self.ark_stock.get("chem_prop", 0.0) + 1e-9 >= prop:
                prop_stock = self.ark_stock
            else:
                have = stock.get("chem_prop", 0.0)
                raise ValueError(
                    f"need {prop:.1f} t chem_prop for {opt['name']}; have {have:.1f} t at origin"
                )

        stock[resource] = stock.get(resource, 0.0) - amount_t
        prop_stock["chem_prop"] = prop_stock.get("chem_prop", 0.0) - prop

        hid = _id()
        months = float(opt["months"])
        self.hauls[hid] = Haul(
            id=hid,
            origin_id=origin_id,
            dest_id=dest_id,
            resource=resource,
            amount_t=amount_t,
            option_name=opt["name"],
            propellant_t=prop,
            months_total=months,
            months_left=months,
            dv_m_s=float(opt["dv_m_s"]),
            unit_id=hauler.id,
            contract_id=contract_id,
        )
        # Hauler rides the cargo (ark stays home as command node)
        if hauler.kind != "ark":
            hauler.status = "en_route"
            hauler.order = "haul"
            hauler.target_id = dest_id if dest_id != "ark" else self.home_body_id
            hauler.months_left = months
        res_name = RESOURCE_NAMES.get(resource, resource)
        dest_label = self._location_label(dest_id)
        link = f" (contract)" if contract_id else ""
        self._log(
            "haul",
            f"{hauler.name}: {amount_t:.1f} t {res_name} → {dest_label} via {opt['name']} "
            f"({months:.1f} mo, {prop:.1f} t prop, Δv {opt['dv_m_s']:.0f} m/s){link}.",
        )
        return self.snapshot()

    def _location_label(self, location_id: str) -> str:
        if location_id in ("ark", "ark_orbit"):
            return "ark"
        if self.system:
            b = self.system.body_by_id(location_id)
            if b:
                return b.name
        return location_id

    def _stock_for(self, location_id: str) -> Dict[str, float]:
        if location_id in ("ark", "ark_orbit"):
            return self.ark_stock
        site = self.sites.setdefault(location_id, Site(body_id=location_id))
        return site.stockpile

    def stocks_at(self, location_id: str) -> Dict[str, float]:
        """Public view of stockpile at a location (for haul UI)."""
        return {k: round(v, 2) for k, v in self._stock_for(location_id).items() if v > 1e-6}

    def _complete_haul(self, h: Haul) -> None:
        h.status = "arrived"
        h.months_left = 0.0
        if h.dest_id in ("ark", "ark_orbit"):
            dest_stock = self.ark_stock
        else:
            site = self.sites.setdefault(h.dest_id, Site(body_id=h.dest_id))
            dest_stock = site.stockpile
        dest_stock[h.resource] = dest_stock.get(h.resource, 0.0) + h.amount_t

        # Free hauler at destination
        if h.unit_id and h.unit_id in self.fleet:
            u = self.fleet[h.unit_id]
            if u.kind != "ark":
                if h.dest_id in ("ark", "ark_orbit"):
                    u.location_id = self.home_body_id or u.location_id
                else:
                    u.location_id = h.dest_id
                u.status = "idle"
                u.order = ""
                u.target_id = ""
                u.months_left = 0.0

        cid = h.contract_id
        if cid and cid in self.contracts:
            c = self.contracts[cid]
            if c.status == "open":
                room = c.amount_t - c.delivered_t
                apply = min(room, h.amount_t)
                c.delivered_t += apply
                if c.delivered_t >= c.amount_t - 1e-6:
                    c.status = "filled"
                    proj = self.projects.get(c.project_id)
                    if proj:
                        self._try_complete_project(proj)
        dest_label = self._location_label(h.dest_id)
        self._log(
            "haul",
            f"Haul arrived: {h.amount_t:.1f} t {RESOURCE_NAMES.get(h.resource, h.resource)} → {dest_label}.",
        )

    def _ark_tick(self, months: float) -> None:
        """Slow ark recipes if inputs available — bootstrap, never zero forever."""
        if months <= 0:
            return
        for rid in ("ark_steel", "ark_chip", "ark_panel", "ark_prop"):
            recipe = RECIPES.get(rid)
            if not recipe:
                continue
            batches = months / max(recipe.months, 1e-6)
            if batches <= 0:
                continue
            max_b = batches
            for res, need in recipe.inputs.items():
                have = self.ark_stock.get(res, 0.0)
                if need > 0:
                    max_b = min(max_b, have / need)
            if max_b <= 1e-9:
                continue
            for res, need in recipe.inputs.items():
                self.ark_stock[res] = self.ark_stock.get(res, 0.0) - need * max_b
            for res, out in recipe.outputs.items():
                self.ark_stock[res] = self.ark_stock.get(res, 0.0) + out * max_b

    def _tick_population(self, months: float) -> None:
        """
        Natural growth only when habitat volume exists off-ark.
        Ark sustains the founding 10k forever; growth needs settlement.
        """
        if months <= 0:
            return
        hab_sites = sum(
            1
            for s in self.sites.values()
            if s.body_id != "ark_orbit" and "habitat" in s.buildings
        )
        if hab_sites <= 0:
            return
        # ~1.2% / year per habitat site, soft cap far away
        rate_per_year = 0.012 * hab_sites
        growth = self.population * rate_per_year * (months / 12.0)
        # Soft approach toward 2e6 * hab_sites
        cap = 2_000_000.0 * hab_sites + ARK_POPULATION
        room = max(0.0, cap - self.population)
        self.population = min(cap, self.population + min(growth, room))

    def _site_tick(self, months: float) -> None:
        if not self.system:
            return
        for site in self.sites.values():
            if site.body_id == "ark_orbit":
                continue
            body = self.system.body_by_id(site.body_id)
            if not body:
                continue
            if "extractor" in site.buildings:
                for dep in body.deposits:
                    if not dep.known or dep.amount_t <= 0:
                        continue
                    rate = 20.0 * dep.grade  # t/month
                    took = min(dep.amount_t, rate * months)
                    dep.amount_t -= took
                    site.stockpile[dep.resource] = site.stockpile.get(dep.resource, 0.0) + took
            if "refinery" in site.buildings and site.stockpile.get("Fe", 0) > 0:
                recipe = RECIPES["refine_fe"]
                batches = months / recipe.months
                max_b = min(batches, site.stockpile.get("Fe", 0) / 1.2)
                if max_b > 0:
                    site.stockpile["Fe"] -= 1.2 * max_b
                    site.stockpile["steel"] = site.stockpile.get("steel", 0) + 1.0 * max_b
            if "scoop" in site.buildings and body.has_atmosphere and "CH4" in (body.atmosphere_note or "CH4"):
                site.stockpile["CH4"] = site.stockpile.get("CH4", 0) + 8.0 * months
            # also allow scoop if deposit CH4 known
            if "scoop" in site.buildings:
                for dep in body.deposits:
                    if dep.known and dep.resource == "CH4" and dep.amount_t > 0:
                        took = min(dep.amount_t, 15.0 * months)
                        dep.amount_t -= took
                        site.stockpile["CH4"] = site.stockpile.get("CH4", 0) + took

    def snapshot(self) -> dict:
        self.catch_up()
        months = self.sim_time_s / (SECONDS_PER_DAY * DAYS_PER_MONTH)
        data: Dict[str, Any] = {
            "phase": self.phase,
            "message": self.message,
            "sim_months": round(months, 3),
            "sim_years": round(months / 12.0, 3),
            "population": self.population,
            "ark_stock": {k: round(v, 2) for k, v in self.ark_stock.items()},
            "events": self.events[:30],
            "catalog": self.catalog,
            "archive_opened": self.archive_opened,
            "survey_archive_count": len(self.survey_archive),
            "projects": [p.to_dict() for p in self.projects.values()],
            "contracts": [c.to_dict() for c in self.contracts.values()],
            "hauls": [h.to_dict() for h in self.hauls.values() if h.status == "in_flight"],
            "fleet": [u.to_dict() for u in self.fleet.values()],
            "builds": [j.to_dict() for j in self.build_queue],
            "sites": {k: v.to_dict() for k, v in self.sites.items()},
            "scanned": list(self.scanned),
            "tech": tech_book_summary(),
            "unit_builds": UNIT_BUILDS,
            "structure_builds": STRUCTURE_BUILDS,
            "transit_months_left": round(self.transit_months_left, 2),
            "event_queue": self.event_queue()[:8],
            "next_event": (self.event_queue() or [None])[0],
            "ark_scan_goals": list(self.ark_scan_goals),
            "ark_scan_goal_specs": self.ARK_SCAN_GOAL_SPECS,
            "hab_intel": dict(self.hab_intel),
            "terraform_dossiers": (
                {
                    b.id: self.terraform_dossier(b.id)
                    for b in self.system.bodies
                    if b.kind in ("planet", "moon")
                    and b.planet_class in ("rocky", "moon", "gas_giant", "ice_giant")
                }
                if self.phase == "system" and self.system
                else {}
            ),
            "body_tree": self.body_tree() if self.phase == "system" else [],
            "home_body_id": self.home_body_id,
            "ark_location_body_id": self.home_body_id,  # map: ark marker near this body
            "build_options": {
                "power": {k: {"name": v["name"], "description": v["description"]} for k, v in POWER_OPTIONS.items()},
                "hab": {k: {"name": v["name"], "description": v["description"]} for k, v in HAB_OPTIONS.items()},
            },
        }
        if self.system:
            data["system"] = self.system.to_dict(self.sim_time_s)
            # attach hab_intel + site stockpile onto body dicts for UI convenience
            for b in data["system"].get("bodies", []):
                lv = self.hab_intel.get(b["id"], 0)
                b["hab_intel"] = lv
                # Always attach habitability checklist (physics + fogged survey fields)
                if b.get("kind") in ("planet", "moon") or b.get("planet_class") in (
                    "rocky",
                    "moon",
                    "gas_giant",
                    "ice_giant",
                ):
                    b["terraform_dossier"] = self.terraform_dossier(b["id"])
                # Fog of war: hide unsurveyed terraform truth in raw body dump
                if lv < 5:
                    b.pop("has_active_core", None)
                    b.pop("has_magnetosphere", None)
                if lv < 4:
                    b.pop("water_class", None)
                if lv < 3:
                    b.pop("atmosphere_class", None)
                site = self.sites.get(b["id"])
                full_body = self.system.body_by_id(b["id"])
                b["mass_driver_ok"] = self.body_allows_mass_driver(full_body)
                power = self.site_power_mw(b["id"])
                b["site_power_mw"] = round(power, 1)
                b["mass_driver_power_need_mw"] = MASS_DRIVER_POWER_MW
                if site:
                    b["site_stockpile"] = {
                        k: round(v, 2) for k, v in site.stockpile.items() if v > 1e-6
                    }
                    b["site_buildings"] = list(site.buildings)
                    b["has_mass_driver"] = "mass_driver" in site.buildings
                    b["mass_driver_online"] = self.mass_driver_online(b["id"])
                    b["has_l1_shield"] = "l1_magnetic_shield" in site.buildings
                else:
                    b["site_stockpile"] = {}
                    b["site_buildings"] = []
                    b["has_mass_driver"] = False
                    b["mass_driver_online"] = False
                    b["has_l1_shield"] = False
        return data


# Global room (solo host)
ROOM = Game()
