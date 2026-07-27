"""Game state: colony room, contracts, production, hauls."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import (
    ARK_POPULATION,
    DAYS_PER_MONTH,
    SECONDS_PER_DAY,
    SEED_FE_TONNES,
)
from .orbits import transfer_options
from .system_gen import StarSystem, generate_system, survey_catalog
from .tech import (
    BUILDINGS,
    HAB_OPTIONS,
    POWER_OPTIONS,
    RECIPES,
    RESOURCE_NAMES,
    expand_base_plan,
    tech_book_summary,
)


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
    location_id: str  # body id or "transit"
    status: str = "idle"  # idle | en_route | working
    order: str = ""
    target_id: str = ""
    months_left: float = 0.0
    capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "location_id": self.location_id,
            "status": self.status,
            "order": self.order,
            "target_id": self.target_id,
            "months_left": round(self.months_left, 2),
            "capabilities": self.capabilities,
        }


class Game:
    """Single colony room simulation."""

    def __init__(self) -> None:
        self.phase = "menu"  # menu | transit | system
        self.system: Optional[StarSystem] = None
        self.catalog: List[dict] = []
        self.sim_time_s: float = 0.0
        self.wall_anchor: float = time.time()
        self.last_wall: float = self.wall_anchor
        self.events: List[dict] = []
        self.projects: Dict[str, Project] = {}
        self.contracts: Dict[str, Contract] = {}
        self.hauls: Dict[str, Haul] = {}
        self.sites: Dict[str, Site] = {}
        self.fleet: Dict[str, FleetUnit] = {}
        # Ark inventory (orbital, at star capture)
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
        self.message: str = "Pick a star to commit your colony ship."
        self.scanned: set[str] = set()
        self.auto_warp_votes = 0

    # --- time ---
    def catch_up(self) -> float:
        """Advance sim from wall clock. Returns months advanced."""
        now = time.time()
        dt = max(0.0, now - self.last_wall)
        self.last_wall = now
        if self.phase == "menu":
            return 0.0
        # Believable sky: live clock is slow. 1 wall second ≈ 1 game day / 7
        # (Earth year ~ 42 wall minutes). Use Warp for logistics jumps.
        game_dt_s = dt * (SECONDS_PER_DAY / 7.0)
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
            if u.status in ("en_route", "working") and u.months_left > 0:
                u.months_left -= months
                if u.months_left <= 0:
                    self._complete_unit_order(u)

        # No auto ark consumption. Sites tick only with buildings.
        self._site_tick(months)
        return months

    def warp_to_next_event(self) -> dict:
        """Single-player auto-approve vote-warp to next interesting event."""
        self.catch_up()
        targets: List[float] = []
        if self.phase == "transit" and self.transit_months_left > 0:
            targets.append(self.transit_months_left)
        for h in self.hauls.values():
            if h.status == "in_flight" and h.months_left > 0:
                targets.append(h.months_left)
        for u in self.fleet.values():
            if u.months_left > 0 and u.status in ("en_route", "working"):
                targets.append(u.months_left)
        if not targets:
            # Small nudge: 1 week of game time (not a full month of chaos)
            self.advance(SECONDS_PER_DAY * 7)
            self._log("event", "No pending orders — advanced 1 week.")
            return {"warped_months": 7.0 / DAYS_PER_MONTH, "reason": "idle_nudge"}
        m = min(targets)
        self.advance(m * SECONDS_PER_DAY * DAYS_PER_MONTH)
        self.auto_warp_votes += 1
        self._log("event", f"Warped {m:.2f} months to next order/event.")
        return {"warped_months": m, "reason": "next_event"}

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
    def refresh_catalog(self) -> List[dict]:
        self.catalog = survey_catalog(6)
        return self.catalog

    def select_star(self, seed: int) -> dict:
        self.selected_seed = seed
        self.system = generate_system(seed=seed)
        # transit time: years based on handwave distance — use difficulty-ish
        self.transit_months_left = 12.0 * (8.0 + self.system.difficulty)  # ~8–18 years
        self.phase = "transit"
        self.sim_time_s = 0.0
        self.last_wall = time.time()
        self._log(
            "transit",
            f"Committed to seed {seed}. Transit ~{self.transit_months_left/12:.1f} years. Xe reserved for capture burn.",
        )
        return self.snapshot()

    def _arrive(self) -> None:
        self.phase = "system"
        self.ark_stock["Xe"] = 0.0
        assert self.system
        # Park near innermost rocky planet (or first planet)
        home = next(
            (b for b in self.system.bodies if b.kind == "planet" and b.planet_class == "rocky"),
            next(b for b in self.system.bodies if b.kind == "planet"),
        )
        self.sites["ark_orbit"] = Site(body_id=home.id, buildings=["ark"], stockpile={})
        self._spawn_starting_fleet(home.id)
        self._log(
            "arrival",
            f"Capture complete at {home.name}. Xe tanks dry. Select a unit, click a body, give an order.",
        )

    def _spawn_starting_fleet(self, home_id: str) -> None:
        self.fleet.clear()
        units = [
            FleetUnit("ark", "Colony Ark", "ark", home_id, capabilities=[CAP_COMMAND, CAP_BUILD, CAP_HAUL]),
            FleetUnit("sv1", "Survey Sat-1", "survey", home_id, capabilities=[CAP_SURVEY]),
            FleetUnit("sv2", "Survey Sat-2", "survey", home_id, capabilities=[CAP_SURVEY]),
            FleetUnit("mn1", "Miner Bot-1", "miner", home_id, capabilities=[CAP_MINE]),
            FleetUnit("mn2", "Miner Bot-2", "miner", home_id, capabilities=[CAP_MINE]),
            FleetUnit("hl1", "Hauler-1", "hauler", home_id, capabilities=[CAP_HAUL]),
            FleetUnit("hl2", "Hauler-2", "hauler", home_id, capabilities=[CAP_HAUL]),
        ]
        for u in units:
            self.fleet[u.id] = u

    def _travel_months(self, from_id: str, to_id: str) -> float:
        """Rough cruise time from orbital radii (economy transfer)."""
        if from_id == to_id:
            return 0.05
        try:
            opts = self.haul_options(from_id if from_id != "ark" else "ark", to_id)
            return max(0.05, opts[0]["months"]) if opts else 1.0
        except Exception:
            return 1.0

    def issue_order(self, unit_id: str, order: str, target_id: str = "") -> dict:
        """
        Apply a unit's capability to a target: survey | mine | move | build_base prep.
        Pattern: select unit → select body → order.
        """
        self.catch_up()
        u = self.fleet.get(unit_id)
        if not u:
            raise ValueError("unknown unit")
        if u.status in ("en_route", "working") and u.months_left > 0:
            raise ValueError(f"{u.name} is busy ({u.status})")
        assert self.system

        if order == "idle":
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.months_left = 0.0
            self._log("order", f"{u.name}: standing by.")
            return self.snapshot()

        if order == "survey":
            if CAP_SURVEY not in u.capabilities:
                raise ValueError("unit cannot survey")
            body = self.system.body_by_id(target_id)
            if not body:
                raise ValueError("pick a body to survey")
            travel = self._travel_months(u.location_id, target_id)
            work = 0.15  # survey pass
            u.order = "survey"
            u.target_id = target_id
            u.status = "en_route" if travel > 0.05 else "working"
            u.months_left = travel + work
            self._log("order", f"{u.name} → survey {body.name} ({u.months_left:.2f} mo).")
            return self.snapshot()

        if order == "mine":
            if CAP_MINE not in u.capabilities:
                raise ValueError("unit cannot mine")
            body = self.system.body_by_id(target_id)
            if not body:
                raise ValueError("pick a body to mine")
            if target_id not in self.scanned and not any(d.known for d in body.deposits):
                raise ValueError("survey this body before mining")
            travel = self._travel_months(u.location_id, target_id)
            u.order = "mine"
            u.target_id = target_id
            u.status = "en_route"
            u.months_left = travel + 0.5  # start a mining shift
            self._log("order", f"{u.name} → mine {body.name}.")
            return self.snapshot()

        if order == "move":
            body = self.system.body_by_id(target_id)
            if not body:
                raise ValueError("pick a destination")
            travel = self._travel_months(u.location_id, target_id)
            u.order = "move"
            u.target_id = target_id
            u.status = "en_route"
            u.months_left = max(0.05, travel)
            self._log("order", f"{u.name} → move to {body.name} ({u.months_left:.2f} mo).")
            return self.snapshot()

        raise ValueError(f"unknown order {order}")

    def _complete_unit_order(self, u: FleetUnit) -> None:
        assert self.system
        if u.order == "move":
            u.location_id = u.target_id
            u.status = "idle"
            u.order = ""
            body = self.system.body_by_id(u.location_id)
            self._log("order", f"{u.name} arrived at {body.name if body else u.location_id}.")
            u.target_id = ""
            u.months_left = 0.0
            return

        if u.order == "survey":
            u.location_id = u.target_id
            body = self.system.body_by_id(u.target_id)
            if body:
                for d in body.deposits:
                    d.known = True
                self.scanned.add(body.id)
                self._log("scan", f"{u.name} surveyed {body.name}. Deposits known.")
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.months_left = 0.0
            return

        if u.order == "mine":
            u.location_id = u.target_id
            body = self.system.body_by_id(u.target_id)
            site = self.sites.setdefault(u.target_id, Site(body_id=u.target_id))
            if "extractor" not in site.buildings:
                site.buildings.append("extractor")  # bot sets up a rudimentary dig
            extracted = 0.0
            if body:
                for dep in body.deposits:
                    if dep.known and dep.amount_t > 0:
                        took = min(dep.amount_t, 40.0 * dep.grade)
                        dep.amount_t -= took
                        site.stockpile[dep.resource] = site.stockpile.get(dep.resource, 0.0) + took
                        extracted += took
            self._log("mine", f"{u.name} mined at {body.name if body else u.target_id}: {extracted:.0f} t to site stockpile.")
            u.status = "idle"
            u.order = ""
            u.target_id = ""
            u.months_left = 0.0
            return

        u.status = "idle"
        u.months_left = 0.0

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
        Ark/orbital haulers start in space. Cost ≈ interplanetary Hohmann
        + a partial destination landing burn (surface well still matters).
        Hauler dry mass kept modest so seed chem_prop can close early loops.
        """
        assert self.system
        o = self._radius_of(origin_id)
        d = self._radius_of(dest_id)
        extra = 0.0
        dest = self.system.body_by_id(dest_id)
        if dest and dest.kind in ("planet", "moon", "asteroid"):
            from .orbits import dv_surface_to_orbit

            # Landing / surface delivery leg (not full SSTO both ways)
            extra += 0.35 * dv_surface_to_orbit(dest.mass_kg, dest.radius_m)
        # Avoid identical radii (same orbit) — tiny hop
        if abs(o - d) / max(o, d) < 0.02:
            o *= 0.98
        opts = transfer_options(
            o, d, self.system.star_mu, ship_dry_mass_t=8.0, extra_dv_m_s=extra, isp_s=340.0
        )
        return [x.to_dict() for x in opts]

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
    ) -> dict:
        self.catch_up()
        opts = self.haul_options(origin_id, dest_id)
        if not opts or option_index < 0 or option_index >= len(opts):
            raise ValueError("bad transfer option")
        opt = opts[option_index]
        # take cargo + propellant from origin stock (ark or site)
        stock = self._stock_for(origin_id)
        if stock.get(resource, 0.0) < amount_t:
            raise ValueError(f"insufficient {resource} at origin")
        prop = opt["propellant_t"]
        if stock.get("chem_prop", 0.0) < prop:
            raise ValueError(f"need {prop:.1f} t chem_prop for this transfer; have {stock.get('chem_prop', 0):.1f}")
        stock[resource] -= amount_t
        stock["chem_prop"] -= prop
        hid = _id()
        self.hauls[hid] = Haul(
            id=hid,
            origin_id=origin_id,
            dest_id=dest_id,
            resource=resource,
            amount_t=amount_t,
            option_name=opt["name"],
            propellant_t=prop,
            months_total=opt["months"],
            months_left=opt["months"],
            dv_m_s=opt["dv_m_s"],
        )
        if contract_id:
            # remember linkage in note via events
            self._log("haul", f"Haul {amount_t:.1f} t {resource} via {opt['name']} ({opt['months']:.1f} mo, {prop:.1f} t prop). Linked contract {contract_id}.")
        else:
            self._log("haul", f"Haul {amount_t:.1f} t {resource} via {opt['name']} ({opt['months']:.1f} mo, {prop:.1f} t prop).")
        # stash contract id on haul via dynamic attr
        self.hauls[hid].__dict__["contract_id"] = contract_id
        return self.snapshot()

    def _stock_for(self, location_id: str) -> Dict[str, float]:
        if location_id in ("ark", "ark_orbit"):
            return self.ark_stock
        site = self.sites.setdefault(location_id, Site(body_id=location_id))
        return site.stockpile

    def _complete_haul(self, h: Haul) -> None:
        h.status = "arrived"
        h.months_left = 0.0
        dest_stock = self._stock_for(h.dest_id if h.dest_id != "ark_orbit" else "ark")
        if h.dest_id in ("ark", "ark_orbit"):
            dest_stock = self.ark_stock
        else:
            site = self.sites.setdefault(h.dest_id, Site(body_id=h.dest_id))
            dest_stock = site.stockpile
        dest_stock[h.resource] = dest_stock.get(h.resource, 0.0) + h.amount_t
        cid = h.__dict__.get("contract_id")
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
        self._log("haul", f"Haul arrived: {h.amount_t:.1f} t {h.resource} → {h.dest_id}.")

    def _ark_tick(self, months: float) -> None:
        """Slow ark recipes if inputs available."""
        for rid in ("ark_steel", "ark_chip", "ark_panel", "ark_prop"):
            recipe = RECIPES[rid]
            # fractional batches
            batches = months / max(recipe.months, 1e-6)
            if batches <= 0:
                continue
            # limit by inputs
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
            "projects": [p.to_dict() for p in self.projects.values()],
            "contracts": [c.to_dict() for c in self.contracts.values()],
            "hauls": [h.to_dict() for h in self.hauls.values()],
            "fleet": [u.to_dict() for u in self.fleet.values()],
            "sites": {k: v.to_dict() for k, v in self.sites.items()},
            "scanned": list(self.scanned),
            "tech": tech_book_summary(),
            "transit_months_left": round(self.transit_months_left, 2),
            "build_options": {
                "power": {k: {"name": v["name"], "description": v["description"]} for k, v in POWER_OPTIONS.items()},
                "hab": {k: {"name": v["name"], "description": v["description"]} for k, v in HAB_OPTIONS.items()},
            },
        }
        if self.system:
            data["system"] = self.system.to_dict(self.sim_time_s)
        return data


# Global room (solo host)
ROOM = Game()
