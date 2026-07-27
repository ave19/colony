"""Formation-inspired star system generator with stable, believable orbits.

Design targets (for a 1 M☉ star, scaled with mass/luminosity for others):
  - Inner rocky worlds ~0.4–1.6 AU → periods months–~2 years
  - Asteroid belt near the snow line
  - Gas giant ~5 AU class → ~12 year period (Jupiter analogue)
  - Ice giant further out → decades
  - Moons orbit *planets* with day–month periods, not the star

Periods always come from Kepler: P = 2π √(a³/μ). No fake angular speeds.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .constants import AU_M, EARTH_MASS, EARTH_RADIUS, G, SOLAR_MASS
from .orbits import (
    dv_orbit_to_escape,
    dv_surface_to_orbit,
    period_seconds,
    surface_gravity,
)

SECONDS_PER_YEAR = 365.25 * 86400.0

# Spectral archetypes: mass (Msun), luminosity (Lsun), temp K
# Display name of a system is a proper star name (e.g. Sol); planets are Sol-1, Sol-2, …
STAR_TYPES = [
    {"id": "M5V", "spectral": "M5V", "class_label": "red dwarf", "mass": 0.16, "lum": 0.007, "temp": 2800, "difficulty_bias": 1.35},
    {"id": "K2V", "spectral": "K2V", "class_label": "orange dwarf", "mass": 0.78, "lum": 0.29, "temp": 4900, "difficulty_bias": 1.05},
    {"id": "G2V", "spectral": "G2V", "class_label": "yellow dwarf", "mass": 1.0, "lum": 1.0, "temp": 5772, "difficulty_bias": 0.9},
    {"id": "F5V", "spectral": "F5V", "class_label": "F-type", "mass": 1.3, "lum": 2.5, "temp": 6500, "difficulty_bias": 1.1},
]

# Short proper names — one per system; bodies are named Star-1, Star-2, …
STAR_PROPER_NAMES = [
    "Sol", "Helios", "Tau", "Keid", "Rigel", "Vega", "Altair", "Deneb",
    "Procyon", "Sirius", "Castor", "Pollux", "Algol", "Mira", "Spica",
    "Antares", "Regulus", "Arcturus", "Capella", "Aldebaran", "Fomalhaut",
    "Achernar", "Canopus", "Hadar", "Acrux", "Bellatrix", "Alnitak", "Saiph",
    "Luyten", "Barnard", "Wolf", "Kapteyn", "Lacaille", "Groombridge",
    "Cygnus", "Lyra", "Aquila", "Orion", "Perseus", "Draco", "Phoenix",
    "Eridanus", "Carina", "Vela", "Pictor", "Indus", "Pavo", "Tucana",
    "Hydra", "Corvus", "Crux", "Norma", "Ara", "Telescopium", "Horologium",
]


# Survey detail climbs with on-station time. Common species earlier; rares later.
# 0 hidden → 1 spectral hint → 2 detected → 3 graded → 4 site found (mineable)
_SURVEY_RESOURCE_ORDER = [
    "Fe", "Si", "Al", "H2O", "CH4", "N", "Cu", "Li", "Ar", "He", "U", "Xe", "MAG",
]

_SITE_REGION = [
    "highland plateau", "rift basin", "crater floor", "polar scarp",
    "mare plain", "canyon wall", "regolith apron", "volcanic massif",
    "ice shelf", "subsurface lens", "ring of hills", "ancient seabed",
]


@dataclass
class Deposit:
    resource: str
    grade: float
    amount_t: float
    known: bool = False
    detail: int = 0  # 0..4

    def to_dict(self) -> dict:
        labels = {
            0: "unsurveyed",
            1: "spectral hint",
            2: "detected",
            3: "graded",
            4: "site located",
        }
        if self.detail <= 0:
            return {
                "resource": "?",
                "grade": None,
                "amount_t": None,
                "known": False,
                "detail": 0,
                "hint": labels[0],
            }
        # detail 1: only a vague class, not always the element name
        if self.detail == 1:
            return {
                "resource": "?",
                "resource_hint": _resource_hint(self.resource),
                "grade": None,
                "amount_t": None,
                "known": False,
                "detail": 1,
                "hint": labels[1],
            }
        return {
            "resource": self.resource,
            "grade": round(self.grade, 2) if self.detail >= 3 else None,
            "amount_t": round(self.amount_t, 1) if self.detail >= 4 else (
                round(self.amount_t, -1) if self.detail >= 3 else None  # rough at 3
            ),
            "known": True,
            "detail": self.detail,
            "hint": labels.get(self.detail, ""),
            "mineable": self.detail >= 4,
        }


@dataclass
class MineSite:
    """A surveyed place where a mine/scoop for one resource can be ordered."""
    id: str
    body_id: str
    resource: str
    grade: float
    amount_t: float
    name: str
    region: str
    detail: int = 4  # always site-level when created

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "body_id": self.body_id,
            "resource": self.resource,
            "grade": round(self.grade, 2),
            "amount_t": round(self.amount_t, 1),
            "name": self.name,
            "region": self.region,
            "mineable": True,
        }


def _resource_hint(resource: str) -> str:
    hints = {
        "Fe": "ferromagnetic crust signatures",
        "Si": "silicate-rich regolith",
        "Al": "light-metal oxides",
        "H2O": "hydrogen-bearing ice / hydrated minerals",
        "CH4": "organic / methane absorptions",
        "N": "nitrogen compounds",
        "Cu": "conductive metal traces",
        "Li": "light alkali signatures",
        "Ar": "noble gas enrichment",
        "He": "light noble gas",
        "U": "radioisotope anomaly",
        "Xe": "heavy noble gas",
        "MAG": "rare magnetic-alloy precursors",
    }
    return hints.get(resource, "composition anomaly")


def _resource_rank(resource: str) -> int:
    try:
        return _SURVEY_RESOURCE_ORDER.index(resource)
    except ValueError:
        return 50


@dataclass
class Body:
    id: str
    name: str
    kind: str  # planet | moon | asteroid
    parent_id: Optional[str]
    mass_kg: float
    radius_m: float
    semi_major_m: float  # around parent (star for planets/asteroids, planet for moons)
    phase0: float
    has_atmosphere: bool = False
    atmosphere_note: str = ""
    deposits: List[Deposit] = field(default_factory=list)
    mine_sites: List[MineSite] = field(default_factory=list)
    density_hint: str = "unknown"
    ice_likely: bool = False
    metal_likely: bool = False
    planet_class: str = ""  # rocky | gas_giant | ice_giant | dwarf
    survey_months: float = 0.0  # cumulative on-station survey time

    def mu(self) -> float:
        return G * self.mass_kg

    def apply_survey_time(self, months: float, rng: Optional[random.Random] = None) -> List[str]:
        """
        Longer on-station survey → finer detail.
        Only after a *site* is located (detail 4) can you order a mine there.
        """
        if months <= 0:
            return []
        rng = rng or random.Random(hash((self.id, int(self.survey_months * 100))) & 0xFFFFFFFF)
        before = {d.resource: d.detail for d in self.deposits}
        sites_before = {s.resource for s in self.mine_sites}
        self.survey_months += months
        sm = self.survey_months

        for dep in sorted(self.deposits, key=lambda d: _resource_rank(d.resource)):
            r = _resource_rank(dep.resource)
            # Months on station thresholds (common resources sooner)
            t1 = 0.5 + r * 0.45  # spectral hint
            t2 = t1 + 1.0  # confirmed detection
            t3 = t2 + 1.2  # grade
            t4 = t3 + 1.8 + r * 0.25  # find a place you can actually mine
            if sm >= t1 and dep.detail < 1:
                dep.detail = 1
            if sm >= t2 and dep.detail < 2:
                dep.detail = 2
                dep.known = True
            if sm >= t3 and dep.detail < 3:
                dep.detail = 3
                dep.known = True
            if sm >= t4 and dep.detail < 4:
                dep.detail = 4
                dep.known = True
                if dep.resource not in sites_before and not any(
                    s.resource == dep.resource for s in self.mine_sites
                ):
                    region = rng.choice(_SITE_REGION)
                    site_id = f"{self.id}_{dep.resource}_site"
                    self.mine_sites.append(
                        MineSite(
                            id=site_id,
                            body_id=self.id,
                            resource=dep.resource,
                            grade=dep.grade,
                            amount_t=dep.amount_t * rng.uniform(0.15, 0.45),  # this site, not whole body
                            name=f"{dep.resource} mine — {region}",
                            region=region,
                        )
                    )

        notes: List[str] = []
        for dep in self.deposits:
            old = before.get(dep.resource, 0)
            if dep.detail > old:
                if dep.detail == 1:
                    notes.append(f"spectral hint: {_resource_hint(dep.resource)}")
                elif dep.detail == 2:
                    notes.append(f"confirmed {dep.resource} present")
                elif dep.detail == 3:
                    notes.append(f"graded {dep.resource} (≈{dep.grade:.2f})")
                elif dep.detail == 4:
                    site = next(s for s in self.mine_sites if s.resource == dep.resource)
                    notes.append(
                        f"suitable {dep.resource} site found: {site.region} "
                        f"(mine '{site.name}' now available)"
                    )
        return notes


@dataclass
class StarSystem:
    seed: int
    star: Dict[str, Any]
    bodies: List[Body]
    difficulty: float
    survey_summary: str

    @property
    def star_mass_kg(self) -> float:
        return self.star["mass"] * SOLAR_MASS

    @property
    def star_mu(self) -> float:
        return G * self.star_mass_kg

    def body_by_id(self, body_id: str) -> Optional[Body]:
        for b in self.bodies:
            if b.id == body_id:
                return b
        return None

    def to_dict(self, t_seconds: float = 0.0) -> dict:
        """Serialize with real Kepler positions; map uses √AU so outer giants fit."""
        from .orbits import body_phase_rad

        star_mu = self.star_mu
        # True AU positions for planets/asteroids
        true_xy: Dict[str, Tuple[float, float]] = {}
        out: List[dict] = []

        for b in self.bodies:
            if b.kind not in ("planet", "asteroid"):
                continue
            a_au = b.semi_major_m / AU_M
            phase = body_phase_rad(b.semi_major_m, star_mu, t_seconds, b.phase0)
            x_au = a_au * math.cos(phase)
            y_au = a_au * math.sin(phase)
            true_xy[b.id] = (x_au, y_au)
            p_s = period_seconds(b.semi_major_m, star_mu)
            out.append(self._body_dict(b, x_au, y_au, phase, p_s, star_mu))

        for b in self.bodies:
            if b.kind != "moon":
                continue
            parent = self.body_by_id(b.parent_id) if b.parent_id else None
            if not parent:
                continue
            parent_mu = G * parent.mass_kg
            phase = body_phase_rad(b.semi_major_m, parent_mu, t_seconds, b.phase0)
            px, py = true_xy.get(b.parent_id, (0.0, 0.0))
            # True moon offset in AU is tiny; for map, park moons on a small ring
            # around the parent in *display* space only — labeled with real period.
            p_s = period_seconds(b.semi_major_m, parent_mu)
            # display ring: scale with moon index-ish from SMA, ~3–8% of parent orbital radius visual
            parent_a = parent.semi_major_m / AU_M
            disp_r = max(0.015, min(0.045, parent_a * 0.02)) * (0.7 + 0.3 * (b.semi_major_m / (parent.radius_m * 40 + 1)))
            # Keep moon visually tied to parent true position (pre-sqrt); map applies √ later.
            x_au = px + disp_r * math.cos(phase)
            y_au = py + disp_r * math.sin(phase)
            d = self._body_dict(b, x_au, y_au, phase, p_s, parent_mu)
            d["orbit_parent"] = b.parent_id
            d["moon_sma_km"] = round(b.semi_major_m / 1000.0, 0)
            d["display_orbit_au"] = disp_r
            out.append(d)

        max_au = max((b.semi_major_m / AU_M for b in self.bodies if b.kind in ("planet", "asteroid")), default=5.0)
        return {
            "seed": self.seed,
            "star": self.star,
            "difficulty": round(self.difficulty, 2),
            "survey_summary": self.survey_summary,
            "bodies": out,
            "max_au": round(max_au, 2),
            "snow_line_au": round(_snow_line_au(self.star["lum"]), 2),
            # Map hint: positions are true AU; client should use sqrt scale for drawing.
            "map_projection": "sqrt_au",
        }

    def _body_dict(
        self,
        b: Body,
        x_au: float,
        y_au: float,
        phase: float,
        period_s: float,
        central_mu: float,
    ) -> dict:
        g = surface_gravity(b.mass_kg, b.radius_m)
        period_days = period_s / 86400.0
        period_years = period_s / SECONDS_PER_YEAR
        a_au = b.semi_major_m / AU_M if b.kind != "moon" else None
        return {
            "id": b.id,
            "name": b.name,
            "kind": b.kind,
            "parent_id": b.parent_id,
            "planet_class": b.planet_class,
            "mass_kg": b.mass_kg,
            "mass_earth": round(b.mass_kg / EARTH_MASS, 3),
            "radius_m": b.radius_m,
            "radius_earth": round(b.radius_m / EARTH_RADIUS, 3),
            "semi_major_m": b.semi_major_m,
            "semi_major_au": round(a_au, 3) if a_au is not None else None,
            "phase0": b.phase0,
            "phase": phase,
            "x_au": x_au,
            "y_au": y_au,
            "surface_g": round(g / 9.81, 3),
            "dv_to_orbit_m_s": round(dv_surface_to_orbit(b.mass_kg, b.radius_m), 1),
            "dv_escape_from_orbit_m_s": round(dv_orbit_to_escape(b.mass_kg, b.radius_m), 1),
            "has_atmosphere": b.has_atmosphere,
            "atmosphere_note": b.atmosphere_note,
            "density_hint": b.density_hint,
            "ice_likely": b.ice_likely,
            "metal_likely": b.metal_likely,
            "survey_months": round(b.survey_months, 2),
            "deposits": [d.to_dict() for d in b.deposits],
            "mine_sites": [s.to_dict() for s in b.mine_sites],
            "period_days": round(period_days, 2),
            "period_years": round(period_years, 3) if b.kind != "moon" else None,
            "period_label": (
                f"{period_days:.1f} d"
                if b.kind == "moon" or period_days < 400
                else f"{period_years:.1f} y"
            ),
        }


def _snow_line_au(lum: float) -> float:
    """Ice line ≈ 2.7 AU × √(L/L☉)."""
    return 2.7 * math.sqrt(max(lum, 1e-4))


def _habitable_zone(lum: float) -> Tuple[float, float]:
    """Crude HZ band in AU."""
    return (0.95 * math.sqrt(lum), 1.37 * math.sqrt(lum))


def _reject_trap(bodies: List[Body]) -> bool:
    planets = [b for b in bodies if b.kind == "planet"]
    moons = [b for b in bodies if b.kind == "moon"]
    rocks = [
        b
        for b in bodies
        if b.kind in ("planet", "moon", "asteroid") and b.mass_kg < 30 * EARTH_MASS
    ]
    gas = [b for b in planets if b.planet_class == "gas_giant"]
    if len(planets) < 3:
        return True
    if gas and not any(m.parent_id == gas[0].id for m in moons):
        # allow sometimes, but prefer moons on giants
        if random.Random(len(bodies)).random() < 0.3:
            return True
    if len(rocks) < 2:
        return True
    return False


def generate_system(seed: Optional[int] = None, star_type_id: Optional[str] = None) -> StarSystem:
    for attempt in range(50):
        s = (seed if seed is not None else random.randint(1, 10**9)) + attempt
        rng = random.Random(s)
        if star_type_id:
            star = dict(next(st for st in STAR_TYPES if st["id"] == star_type_id))
        else:
            star = dict(rng.choice(STAR_TYPES))

        # Proper name for THIS system only — planets are {name}-1, {name}-2, …
        star_name = rng.choice(STAR_PROPER_NAMES)
        star["name"] = star_name
        star["designation"] = f"{star_name} ({star['spectral']})"
        # Rough [Fe/H]-like metallicity scatter (solar = 1.0); affects rock metals
        star["metallicity"] = max(0.4, min(1.8, rng.gauss(1.0, 0.18)))

        # Scale orbital architecture with stellar mass (a ∝ M^{1/3} weak; we use √M for spacing feel)
        m = star["mass"]
        scale = math.sqrt(m)  # compress/expand Sol-like layout
        snow = _snow_line_au(star["lum"])
        hz_in, hz_out = _habitable_zone(star["lum"])
        bodies: List[Body] = []

        # --- Sol-like slots, jittered, scaled ---------------------------------
        # Each slot: (approx_au_for_1Msun, role)
        slots = [
            (rng.uniform(0.35, 0.50) * scale, "rocky_hot"),
            (rng.uniform(0.65, 0.90) * scale, "rocky"),
            (rng.uniform(0.95, 1.35) * scale, "rocky_hz"),  # near HZ for G stars
            (rng.uniform(1.5, 1.9) * scale, "rocky_outer"),
            (snow * rng.uniform(0.9, 1.1), "belt"),  # handled separately
            (rng.uniform(4.5, 5.8) * scale, "gas_giant"),  # Jupiter class → ~12 y at 1 M☉
            (rng.uniform(8.5, 12.0) * scale, "ice_giant"),
            (rng.uniform(15.0, 22.0) * scale, "ice_outer"),
        ]

        # Drop belt from planet loop; maybe drop one inner if M dwarf (tight HZ)
        planet_slots = [(au, role) for au, role in slots if role != "belt"]
        if m < 0.3:
            # M dwarfs: fewer wide giants, tighter inners
            planet_slots = [
                (rng.uniform(0.05, 0.12), "rocky_hot"),
                (rng.uniform(0.15, 0.28), "rocky_hz"),
                (rng.uniform(0.35, 0.55), "rocky"),
                (snow * rng.uniform(1.2, 1.8), "ice_giant"),
                (snow * rng.uniform(2.5, 4.0), "ice_outer"),
            ]

        # Ensure min spacing  (Hill-ish / packed systems rule of thumb ~15–20 mutual radii — we use Δln a)
        planet_slots.sort(key=lambda x: x[0])
        filtered: List[Tuple[float, str]] = []
        for au, role in planet_slots:
            if filtered and au / filtered[-1][0] < 1.35:
                continue
            filtered.append((au, role))
        planet_slots = filtered

        for i, (au, role) in enumerate(planet_slots):
            body = _make_planet(rng, i, au, role, snow, hz_in, hz_out, star_name, star["metallicity"])
            bodies.append(body)
            bodies.extend(_make_moons(rng, body, au, snow, star["metallicity"]))

        # Asteroid belt near snow line (or between rock and gas)
        rocks_au = [b.semi_major_m / AU_M for b in bodies if b.planet_class == "rocky"]
        giants_au = [b.semi_major_m / AU_M for b in bodies if b.planet_class in ("gas_giant", "ice_giant")]
        if rocks_au and giants_au:
            belt_au = 0.5 * (max(rocks_au) + min(giants_au))
        else:
            belt_au = snow * rng.uniform(0.95, 1.1)
        for a in range(rng.randint(4, 7)):
            au = belt_au * rng.uniform(0.93, 1.07)
            bodies.append(_make_asteroid(rng, a, au, snow, star_name, star["metallicity"]))

        if _reject_trap(bodies):
            continue

        # Sanity: outermost should be years-scale for G stars
        difficulty = _difficulty(star, bodies, snow)
        n_p = sum(1 for b in bodies if b.kind == "planet")
        n_m = sum(1 for b in bodies if b.kind == "moon")
        # Reference giant period for summary
        giant = next((b for b in bodies if b.planet_class == "gas_giant"), None)
        giant_note = ""
        if giant:
            py = period_seconds(giant.semi_major_m, G * star["mass"] * SOLAR_MASS) / SECONDS_PER_YEAR
            giant_note = f", gas giant ~{giant.semi_major_m/AU_M:.1f} AU ({py:.1f} y)"
        summary = (
            f"{star_name} ({star['spectral']}, {star['class_label']}): {n_p} planets, {n_m} moons, "
            f"snow line {snow:.2f} AU{giant_note}, difficulty {difficulty:.1f}/10"
        )
        return StarSystem(seed=s, star=star, bodies=bodies, difficulty=difficulty, survey_summary=summary)

    return generate_system(seed=42, star_type_id="G2V")


def _make_planet(
    rng: random.Random,
    i: int,
    au: float,
    role: str,
    snow: float,
    hz_in: float,
    hz_out: float,
    star_name: str,
    star_metallicity: float = 1.0,
) -> Body:
    if role == "gas_giant":
        mass = rng.uniform(50, 320) * EARTH_MASS  # ~0.15–1 MJup
        radius = EARTH_RADIUS * rng.uniform(9, 12)
        pclass = "gas_giant"
        ice, metal = True, False
        dens = "gas giant (low density)"
        atmo, note = True, "H₂/He envelope; deep atmosphere"
    elif role in ("ice_giant", "ice_outer"):
        mass = rng.uniform(10, 25) * EARTH_MASS
        radius = EARTH_RADIUS * rng.uniform(3.5, 5.0)
        pclass = "ice_giant"
        ice, metal = True, False
        dens = "ice giant"
        atmo, note = True, "H₂/He + CH₄/NH₃ ices"
    else:
        # rocky
        if role == "rocky_hot":
            mass = rng.uniform(0.3, 1.2) * EARTH_MASS
        elif role == "rocky_hz":
            mass = rng.uniform(0.5, 2.0) * EARTH_MASS
        else:
            mass = rng.uniform(0.1, 1.8) * EARTH_MASS
        radius = EARTH_RADIUS * (mass / EARTH_MASS) ** 0.27
        pclass = "rocky"
        ice = au > snow * 0.85
        metal = rng.random() < 0.55
        dens = "dense rocky" if metal else "rocky"
        atmo = rng.random() < (0.55 if hz_in <= au <= hz_out else 0.3)
        note = "N₂/O₂/CO₂ mix possible" if atmo and hz_in <= au <= hz_out else ("thin CO₂" if atmo else "")

    # Convention: Sol-3 style — star proper name + orbit index from the star
    return Body(
        id=f"p{i}",
        name=f"{star_name}-{i + 1}",
        kind="planet",
        parent_id="star",
        mass_kg=mass,
        radius_m=radius,
        semi_major_m=au * AU_M,
        phase0=rng.uniform(0, 2 * math.pi),
        has_atmosphere=atmo,
        atmosphere_note=note,
        deposits=_deposits_for(
            rng, au, snow, pclass, ice, metal,
            body_mass_kg=mass, star_metallicity=star_metallicity,
        ),
        density_hint=dens,
        ice_likely=ice,
        metal_likely=metal,
        planet_class=pclass,
    )


def _make_moons(
    rng: random.Random, planet: Body, au: float, snow: float, star_metallicity: float = 1.0
) -> List[Body]:
    moons: List[Body] = []
    if planet.planet_class == "gas_giant":
        n = rng.randint(3, 5)
    elif planet.planet_class == "ice_giant":
        n = rng.randint(1, 3)
    elif planet.mass_kg > 0.7 * EARTH_MASS:
        n = rng.randint(0, 2)
    else:
        n = 1 if rng.random() < 0.35 else 0

    # Real-ish moon SMAs: 3–40 planetary radii (Earth–Moon ~60 R⊕ is large; Io–Callisto ~6–26 RJup)
    for m in range(n):
        if planet.planet_class in ("gas_giant", "ice_giant"):
            r_mult = rng.uniform(5, 30)
        else:
            r_mult = rng.uniform(8, 45)
        sma = r_mult * planet.radius_m
        # Mass: Luna ~0.012 M⊕; major icy moons smaller
        m_mass = rng.uniform(1e20, 1.5e23) if planet.planet_class != "rocky" else rng.uniform(1e19, 8e22)
        m_radius = max(1.5e5, EARTH_RADIUS * (m_mass / EARTH_MASS) ** 0.3 * 0.2)
        moon_ice = au > snow * 0.75 or planet.planet_class != "rocky" or rng.random() < 0.35
        moon_metal = rng.random() < 0.3
        roman = ["I", "II", "III", "IV", "V", "VI"][m]
        moons.append(
            Body(
                id=f"{planet.id}_m{m}",
                name=f"{planet.name} {roman}",
                kind="moon",
                parent_id=planet.id,
                mass_kg=m_mass,
                radius_m=m_radius,
                semi_major_m=sma,
                phase0=rng.uniform(0, 2 * math.pi),
                has_atmosphere=rng.random() < 0.08 and moon_ice,
                atmosphere_note="tenuous" if moon_ice else "",
                deposits=_deposits_for(
                    rng, au, snow, "moon", moon_ice, moon_metal,
                    body_mass_kg=m_mass, star_metallicity=star_metallicity,
                ),
                density_hint="icy" if moon_ice else ("dense" if moon_metal else "rocky"),
                ice_likely=moon_ice,
                metal_likely=moon_metal,
                planet_class="moon",
            )
        )
    return moons


def _make_asteroid(
    rng: random.Random, a: int, au: float, snow: float, star_name: str, star_metallicity: float = 1.0
) -> Body:
    # Taxonomic family from heliocentric distance (formation + thermal processing)
    # Inner / mid belt: more S/M; beyond snow line: C/D + ice.
    roll = rng.random()
    if au < snow * 0.85:
        family = "M" if roll < 0.22 else ("S" if roll < 0.75 else "C")
    elif au < snow * 1.15:
        family = "S" if roll < 0.35 else ("C" if roll < 0.8 else "M")
    else:
        family = "C" if roll < 0.55 else ("D" if roll < 0.9 else "M")

    mass = rng.uniform(1e15, 5e18)
    radius = rng.uniform(5e3, 1.2e5)
    metal = family == "M"
    ice = family in ("C", "D") or au > snow * 0.95
    dens = {
        "M": "metallic (M-type)",
        "S": "stony (S-type)",
        "C": "carbonaceous (C-type)",
        "D": "primitive / icy (D-type)",
    }[family]

    return Body(
        id=f"a{a}",
        name=f"{star_name} Belt-{a + 1}",
        kind="asteroid",
        parent_id="star",
        mass_kg=mass,
        radius_m=radius,
        semi_major_m=au * AU_M,
        phase0=rng.uniform(0, 2 * math.pi),
        deposits=_deposits_for(
            rng, au, snow, "asteroid", ice_likely=ice, metal_likely=metal,
            body_mass_kg=mass, asteroid_family=family, star_metallicity=star_metallicity,
        ),
        density_hint=dens,
        ice_likely=ice,
        metal_likely=metal,
        planet_class="asteroid",
    )


def _crust_mass_t(body_mass_kg: float, fraction: float = 3e-4) -> float:
    """
    Order-of-magnitude accessible crust/regolith budget (tonnes).
    Not whole-planet mass — only a thin mineable shell / ISRU-accessible layer.
    Earth mass ~6e21 t; fraction ~3e-4 → ~2e18 t total crust-ish; we use much
    smaller effective industrial budgets per resource via further fractions.
    """
    body_t = body_mass_kg / 1000.0
    return max(1e3, body_t * fraction)


def _deposits_for(
    rng: random.Random,
    au: float,
    snow: float,
    pkind: str,
    ice_likely: bool = False,
    metal_likely: bool = False,
    body_mass_kg: float = EARTH_MASS,
    asteroid_family: str = "",
    star_metallicity: float = 1.0,  # 1 = solar Z; scales metal availability
) -> List[Deposit]:
    """
    Formation-linked resource priors (playable, not a full geochem sim).

    Rules of thumb encoded:
    - Inside snow line: dry rock, silicates + metals; little free ice/CH4
    - Beyond snow line: water ice / organics / CH4 more common
    - Gas/ice giant *planets*: no surface mines — atmosphere/envelope volatiles only
      (real digging happens on moons)
    - Asteroid family M/S/C/D changes metal vs carbon vs ice mix
    - Accessible tonnage scales with body mass (crust budget), not pure RNG ranges
    - Stellar metallicity boosts rock metals; volatiles less so
    """
    deps: List[Deposit] = []
    z = max(0.3, min(2.0, star_metallicity))
    crust = _crust_mass_t(body_mass_kg)
    dry = au < snow * 0.9
    wet = au > snow * 0.95 or ice_likely

    def add(res: str, p: float, mass_frac: float, grade: Tuple[float, float], force: bool = False):
        """mass_frac = fraction of accessible crust budget for this resource at this site pool."""
        p = min(0.98, p)
        if force or rng.random() < p:
            # grade: ore quality / concentration
            g = rng.uniform(*grade)
            # available tonnes for industry (site-level pool before splitting into mine sites)
            amt = crust * mass_frac * g * rng.uniform(0.4, 1.2)
            amt = max(10.0, amt)
            deps.append(Deposit(res, g, amt, False))

    # --- Gas / ice giant PLANETS: envelope volatiles only (no Fe mines on Jupiter) ---
    if pkind in ("gas_giant", "ice_giant"):
        env = max(1e8, body_mass_kg / 1000.0 * 1e-6)

        def add_env(res: str, p: float, frac_lo: float, frac_hi: float, grade: Tuple[float, float], force: bool = False):
            if force or rng.random() < p:
                deps.append(
                    Deposit(res, rng.uniform(*grade), env * rng.uniform(frac_lo, frac_hi), False)
                )

        add_env("H2O", 0.75 if pkind == "ice_giant" else 0.35, 1e-4, 1e-3, (0.3, 0.7), force=pkind == "ice_giant")
        add_env("CH4", 0.9 if pkind == "ice_giant" else 0.55, 5e-5, 8e-4, (0.35, 0.9))
        add_env("He", 0.95, 1e-5, 2e-4, (0.4, 0.95), force=True)
        add_env("Ar", 0.5, 1e-6, 5e-5, (0.3, 0.8))
        add_env("Xe", 0.28 if pkind == "ice_giant" else 0.12, 1e-8, 5e-7, (0.2, 0.7))
        return _filter_book_resources(deps)

    # --- Asteroids by family ---
    if pkind == "asteroid":
        fam = asteroid_family or ("M" if metal_likely else ("C" if wet else "S"))
        if fam == "M":
            add("Fe", 0.98, 0.12 * z, (0.55, 0.95), force=True)
            add("Si", 0.5, 0.03, (0.25, 0.55))
            add("Cu", 0.35 * z, 0.001 * z, (0.25, 0.6))
            add("MAG", 0.35 * z, 0.0002 * z, (0.2, 0.6))
            add("U", 0.08 * z, 1e-6 * z, (0.15, 0.45))
        elif fam == "S":
            add("Si", 0.95, 0.08, (0.4, 0.85), force=True)
            add("Fe", 0.7 * z, 0.04 * z, (0.35, 0.75))
            add("Al", 0.55, 0.02, (0.3, 0.65))
            add("Cu", 0.2 * z, 0.0005 * z, (0.2, 0.5))
            add("Li", 0.12, 0.0001, (0.2, 0.55))
        elif fam in ("C", "D"):
            add("Si", 0.7, 0.04, (0.25, 0.6))
            add("Fe", 0.35 * z, 0.015 * z, (0.2, 0.5))
            add("H2O", 0.85 if wet or fam == "D" else 0.45, 0.06, (0.4, 0.9), force=wet)
            add("CH4", 0.35 if wet else 0.1, 0.008, (0.25, 0.7))
            add("C", 0.55, 0.02, (0.3, 0.7))
            add("N", 0.2, 0.001, (0.15, 0.45))
        return _filter_book_resources(deps)

    # --- Rocky planets ---
    if pkind == "rocky":
        # Differentiated rock: silicates ubiquitous; Fe more if metal_likely (smaller/stripped or Fe-rich)
        metal_boost = 1.35 if metal_likely else 1.0
        # Inner dry worlds: less hydration
        add("Si", 0.98, 0.06, (0.45, 0.9), force=True)
        # Almost all rocky worlds have some Fe; metal_likely raises grade/fraction
        add("Fe", min(0.97, 0.7 * metal_boost * z), 0.025 * metal_boost * z, (0.3, 0.85), force=True)
        add("Al", 0.85, 0.015, (0.35, 0.75), force=True)
        add("Cu", 0.25 * z, 0.0003 * z, (0.2, 0.55))
        add("U", 0.12 * z, 2e-6 * z, (0.15, 0.5))
        add("Li", 0.15, 8e-5, (0.2, 0.55))
        add("MAG", 0.1 * z, 5e-5 * z, (0.15, 0.5))
        if dry:
            add("H2O", 0.15, 0.002, (0.15, 0.45))  # rare hydrated minerals / polar ice
            add("N", 0.35, 0.0008, (0.2, 0.6))  # atmosphere / nitrate chance
        else:
            add("H2O", 0.7, 0.03, (0.35, 0.85))
            add("CH4", 0.2, 0.002, (0.2, 0.55))
            add("N", 0.25, 0.0005, (0.2, 0.5))
        return _filter_book_resources(deps)

    # --- Moons: depend on heliocentric distance + ice flag ---
    if pkind == "moon":
        if wet or ice_likely:
            # Icy moons (Europa/Titan/Enceladus-like mix)
            add("H2O", 0.95, 0.12, (0.5, 0.95), force=True)
            add("CH4", 0.45, 0.015, (0.3, 0.8))
            add("Si", 0.55, 0.02, (0.25, 0.6))  # rocky core material at surface sometimes
            add("Fe", 0.25 * z, 0.008 * z, (0.2, 0.55))
            add("N", 0.3, 0.002, (0.2, 0.55))  # Titan-like
            add("Ar", 0.15, 0.0002, (0.2, 0.5))
            add("Xe", 0.08, 1e-5, (0.15, 0.45))
        else:
            # Rocky moons (Luna-like)
            add("Si", 0.95, 0.05, (0.4, 0.85), force=True)
            add("Fe", 0.6 * z, 0.02 * z, (0.3, 0.75))
            add("Al", 0.65, 0.012, (0.3, 0.7))
            add("H2O", 0.2, 0.003, (0.15, 0.45))  # polar ice chance
            add("Cu", 0.12 * z, 0.0002 * z, (0.15, 0.45))
        return _filter_book_resources(deps)

    return deps


def _filter_book_resources(deps: List[Deposit]) -> List[Deposit]:
    """Keep only resources the v1 tech book understands (+ drop empty)."""
    book = {
        "Fe", "Al", "Si", "H2O", "CH4", "O2", "H", "O", "N", "C",
        "Cu", "U", "Xe", "Ar", "Li", "MAG", "He",
    }
    # merge duplicates of same resource (sum amounts, max grade)
    merged: Dict[str, Deposit] = {}
    for d in deps:
        if d.resource not in book:
            continue
        if d.resource in merged:
            m = merged[d.resource]
            m.amount_t += d.amount_t
            m.grade = max(m.grade, d.grade)
        else:
            merged[d.resource] = Deposit(d.resource, d.grade, d.amount_t, False)
    return list(merged.values())


def _difficulty(star: dict, bodies: List[Body], snow: float) -> float:
    score = 3.0 * star.get("difficulty_bias", 1.0)
    metals = sum(1 for b in bodies for d in b.deposits if d.resource == "Fe")
    ices = sum(1 for b in bodies for d in b.deposits if d.resource in ("H2O", "CH4"))
    if metals < 2:
        score += 2
    if ices < 2:
        score += 2
    if star["lum"] < 0.05:
        score += 1.5
    # Wide systems are logistically harder
    max_au = max((b.semi_major_m / AU_M for b in bodies if b.kind == "planet"), default=1.0)
    if max_au > 12:
        score += 0.8
    return min(10.0, max(1.0, score))


def survey_catalog(n: int = 6) -> List[dict]:
    out = []
    for _ in range(n):
        seed = random.randint(1, 10**9)
        sys = generate_system(seed=seed)
        giant = next((b for b in sys.bodies if b.planet_class == "gas_giant"), None)
        giant_years = None
        if giant:
            giant_years = round(
                period_seconds(giant.semi_major_m, sys.star_mu) / SECONDS_PER_YEAR, 1
            )
        out.append(
            {
                "seed": sys.seed,
                "star": sys.star,
                "difficulty": round(sys.difficulty, 2),
                "survey_summary": sys.survey_summary,
                "planet_count": len([b for b in sys.bodies if b.kind == "planet"]),
                "moon_count": len([b for b in sys.bodies if b.kind == "moon"]),
                "outer_au": round(
                    max(b.semi_major_m / AU_M for b in sys.bodies if b.kind == "planet"), 1
                ),
                "gas_giant_period_years": giant_years,
            }
        )
    return out
