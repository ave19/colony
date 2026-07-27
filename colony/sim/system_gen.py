"""Formation-inspired star system generator with stable circular orbits."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .constants import AU_M, EARTH_MASS, EARTH_RADIUS, G, SOLAR_MASS
from .orbits import (
    dv_orbit_to_escape,
    dv_surface_to_orbit,
    period_seconds,
    surface_gravity,
)


# Star archetypes: mass (Msun), luminosity (Lsun), temp K, label
STAR_TYPES = [
    {"id": "M5V", "name": "Red dwarf (M5V)", "mass": 0.16, "lum": 0.007, "temp": 2800, "difficulty_bias": 1.3},
    {"id": "K2V", "name": "Orange dwarf (K2V)", "mass": 0.78, "lum": 0.29, "temp": 4900, "difficulty_bias": 1.0},
    {"id": "G2V", "name": "Sun-like (G2V)", "mass": 1.0, "lum": 1.0, "temp": 5772, "difficulty_bias": 0.9},
    {"id": "F5V", "name": "F-type (F5V)", "mass": 1.3, "lum": 2.5, "temp": 6500, "difficulty_bias": 1.1},
]


@dataclass
class Deposit:
    resource: str
    grade: float  # 0-1 quality
    amount_t: float
    known: bool = False  # revealed by scan

    def to_dict(self) -> dict:
        if not self.known:
            return {"resource": "?", "grade": None, "amount_t": None, "known": False, "hint": "unsurveyed"}
        return {
            "resource": self.resource,
            "grade": round(self.grade, 2),
            "amount_t": round(self.amount_t, 1),
            "known": True,
        }


@dataclass
class Body:
    id: str
    name: str
    kind: str  # star, planet, moon, asteroid_belt_member
    parent_id: Optional[str]
    mass_kg: float
    radius_m: float
    semi_major_m: float  # around parent (star for planets)
    phase0: float
    albedo: float = 0.3
    has_atmosphere: bool = False
    atmosphere_note: str = ""
    deposits: List[Deposit] = field(default_factory=list)
    # priors visible without full scan
    density_hint: str = "unknown"
    ice_likely: bool = False
    metal_likely: bool = False

    def mu(self) -> float:
        return G * self.mass_kg

    def to_dict(self, star_mu: float, t_seconds: float = 0.0) -> dict:
        from .orbits import body_phase_rad, xy_on_orbit

        phase = body_phase_rad(self.semi_major_m, star_mu if self.kind != "moon" else star_mu, t_seconds, self.phase0)
        # moons: orbit display relative — simplified on parent SMA + small offset
        if self.kind == "moon":
            # place near parent; parent position computed by caller preferably
            x, y = xy_on_orbit(self.semi_major_m, phase)
        else:
            x, y = xy_on_orbit(self.semi_major_m, phase)

        g = surface_gravity(self.mass_kg, self.radius_m)
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "parent_id": self.parent_id,
            "mass_kg": self.mass_kg,
            "radius_m": self.radius_m,
            "semi_major_m": self.semi_major_m,
            "semi_major_au": self.semi_major_m / AU_M,
            "phase0": self.phase0,
            "x_au": x,
            "y_au": y,
            "surface_g": round(g / 9.81, 3),
            "dv_to_orbit_m_s": round(dv_surface_to_orbit(self.mass_kg, self.radius_m), 1),
            "dv_escape_from_orbit_m_s": round(dv_orbit_to_escape(self.mass_kg, self.radius_m), 1),
            "has_atmosphere": self.has_atmosphere,
            "atmosphere_note": self.atmosphere_note,
            "density_hint": self.density_hint,
            "ice_likely": self.ice_likely,
            "metal_likely": self.metal_likely,
            "deposits": [d.to_dict() for d in self.deposits],
            "period_days": round(period_seconds(self.semi_major_m, star_mu) / 86400.0, 2)
            if self.kind in ("planet", "asteroid")
            else None,
        }


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
        star_mu = self.star_mu
        # compute positions: planets first, moons offset from parent
        planet_pos = {}
        out_bodies = []
        for b in self.bodies:
            if b.kind in ("planet", "asteroid"):
                d = b.to_dict(star_mu, t_seconds)
                planet_pos[b.id] = (d["x_au"], d["y_au"])
                out_bodies.append(d)
        for b in self.bodies:
            if b.kind == "moon":
                d = b.to_dict(star_mu, t_seconds)
                parent = planet_pos.get(b.parent_id, (0.0, 0.0))
                # moon SMA stored in meters around parent — convert to AU offset
                from .orbits import body_phase_rad

                phase = body_phase_rad(max(b.semi_major_m, 1e6), G * 1e22, t_seconds, b.phase0)
                offset = (b.semi_major_m / AU_M) * 15  # exaggerate for map readability
                d["x_au"] = parent[0] + offset * math.cos(phase)
                d["y_au"] = parent[1] + offset * math.sin(phase)
                out_bodies.append(d)

        return {
            "seed": self.seed,
            "star": self.star,
            "difficulty": round(self.difficulty, 2),
            "survey_summary": self.survey_summary,
            "bodies": out_bodies,
        }


def _snow_line_au(lum: float) -> float:
    # rough: snow line ~ 2.7 AU * sqrt(L/Lsun)
    return 2.7 * math.sqrt(max(lum, 1e-4))


def _reject_trap(bodies: List[Body]) -> bool:
    """True if system is an unplayable trap."""
    planets = [b for b in bodies if b.kind == "planet"]
    moons = [b for b in bodies if b.kind == "moon"]
    rocks = [b for b in bodies if b.kind in ("planet", "moon", "asteroid") and b.mass_kg < 50 * EARTH_MASS]
    if len(planets) == 1 and planets[0].mass_kg > 30 * EARTH_MASS and not moons:
        return True  # lone moonless gas giant
    if len(rocks) < 2:
        return True
    return False


def generate_system(seed: Optional[int] = None, star_type_id: Optional[str] = None) -> StarSystem:
    for attempt in range(40):
        s = (seed if seed is not None else random.randint(1, 10**9)) + attempt
        rng = random.Random(s)
        star = dict(rng.choice(STAR_TYPES) if not star_type_id else next(st for st in STAR_TYPES if st["id"] == star_type_id))
        snow = _snow_line_au(star["lum"])
        bodies: List[Body] = []

        n_planets = rng.randint(3, 7)
        used_au: List[float] = []

        for i in range(n_planets):
            # stable packing: logarithmic-ish spacing
            if i == 0:
                au = rng.uniform(0.2, 0.6) * math.sqrt(star["mass"])
            else:
                au = used_au[-1] * rng.uniform(1.4, 1.9)
            used_au.append(au)
            sma = au * AU_M

            # planet class by snow line
            roll = rng.random()
            if au < snow * 0.7:
                # rocky
                kind_mass = rng.uniform(0.1, 2.5) * EARTH_MASS
                radius = EARTH_RADIUS * (kind_mass / EARTH_MASS) ** 0.27
                pkind = "rocky"
                ice_likely = False
                metal_likely = rng.random() < 0.55
                density_hint = "dense (rocky)" if metal_likely else "rocky"
                atmo = rng.random() < 0.35
                atmo_note = "thin CO2/N2" if atmo else ""
            elif au < snow * 1.3:
                kind_mass = rng.uniform(0.5, 8) * EARTH_MASS
                radius = EARTH_RADIUS * (kind_mass / EARTH_MASS) ** 0.3
                pkind = "mixed"
                ice_likely = rng.random() < 0.6
                metal_likely = rng.random() < 0.4
                density_hint = "mixed ice-rock"
                atmo = rng.random() < 0.5
                atmo_note = "N2/CH4 traces" if atmo else ""
            else:
                # ice giant / gas
                if rng.random() < 0.55:
                    kind_mass = rng.uniform(10, 80) * EARTH_MASS
                    radius = EARTH_RADIUS * rng.uniform(3.5, 11)
                    pkind = "gas_giant"
                    ice_likely = True
                    metal_likely = False
                    density_hint = "low density (gas giant)"
                    atmo = True
                    atmo_note = "H2/He envelope; possible CH4"
                else:
                    kind_mass = rng.uniform(3, 20) * EARTH_MASS
                    radius = EARTH_RADIUS * (kind_mass / EARTH_MASS) ** 0.35
                    pkind = "ice_giant"
                    ice_likely = True
                    metal_likely = False
                    density_hint = "icy / volatile-rich"
                    atmo = True
                    atmo_note = "CH4/NH3 ices, thick air"

            pid = f"p{i}"
            deposits = _deposits_for(rng, au, snow, pkind)
            planet = Body(
                id=pid,
                name=_planet_name(rng, i),
                kind="planet",
                parent_id="star",
                mass_kg=kind_mass,
                radius_m=radius,
                semi_major_m=sma,
                phase0=rng.uniform(0, 2 * math.pi),
                has_atmosphere=atmo,
                atmosphere_note=atmo_note,
                deposits=deposits,
                density_hint=density_hint,
                ice_likely=ice_likely,
                metal_likely=metal_likely,
            )
            bodies.append(planet)

            # moons for larger worlds
            if kind_mass > 0.8 * EARTH_MASS:
                n_moons = rng.randint(0, 3 if kind_mass < 15 * EARTH_MASS else 5)
                for m in range(n_moons):
                    m_au_offset = rng.uniform(3, 30) * radius  # meters from planet
                    m_mass = rng.uniform(1e19, 1e23)
                    m_radius = max(1e5, (m_mass / EARTH_MASS) ** 0.3 * EARTH_RADIUS * 0.15)
                    moon_ice = au > snow * 0.8 or rng.random() < 0.4
                    moon_metal = rng.random() < 0.35
                    mid = f"{pid}_m{m}"
                    bodies.append(
                        Body(
                            id=mid,
                            name=f"{planet.name} {['I','II','III','IV','V'][m]}",
                            kind="moon",
                            parent_id=pid,
                            mass_kg=m_mass,
                            radius_m=m_radius,
                            semi_major_m=m_au_offset,
                            phase0=rng.uniform(0, 2 * math.pi),
                            has_atmosphere=rng.random() < 0.1 and moon_ice,
                            atmosphere_note="thin CH4" if moon_ice and rng.random() < 0.3 else "",
                            deposits=_deposits_for(rng, au, snow, "moon", moon_ice, moon_metal),
                            density_hint="icy" if moon_ice else ("dense" if moon_metal else "rocky"),
                            ice_likely=moon_ice,
                            metal_likely=moon_metal,
                        )
                    )

        # asteroid belt near snow line
        belt_au = snow * rng.uniform(0.85, 1.15)
        for a in range(rng.randint(3, 6)):
            au = belt_au * rng.uniform(0.92, 1.08)
            aid = f"a{a}"
            bodies.append(
                Body(
                    id=aid,
                    name=f"Belt object {a+1}",
                    kind="asteroid",
                    parent_id="star",
                    mass_kg=rng.uniform(1e15, 1e19),
                    radius_m=rng.uniform(5e3, 8e4),
                    semi_major_m=au * AU_M,
                    phase0=rng.uniform(0, 2 * math.pi),
                    deposits=_deposits_for(rng, au, snow, "asteroid"),
                    density_hint="metallic" if rng.random() < 0.4 else "stony",
                    ice_likely=au > snow * 0.9,
                    metal_likely=rng.random() < 0.5,
                )
            )

        if _reject_trap(bodies):
            continue

        difficulty = _difficulty(star, bodies, snow)
        summary = (
            f"{star['name']}: {len([b for b in bodies if b.kind=='planet'])} planets, "
            f"{len([b for b in bodies if b.kind=='moon'])} moons, "
            f"snow line ~{snow:.2f} AU, difficulty {difficulty:.1f}/10"
        )
        return StarSystem(seed=s, star=star, bodies=bodies, difficulty=difficulty, survey_summary=summary)

    # fallback: force G2V friendly
    return generate_system(seed=42, star_type_id="G2V")


def _deposits_for(
    rng: random.Random,
    au: float,
    snow: float,
    pkind: str,
    ice_likely: bool = False,
    metal_likely: bool = False,
) -> List[Deposit]:
    deps: List[Deposit] = []

    def add(res: str, p: float, amount: tuple[float, float], grade: tuple[float, float] = (0.3, 0.95)):
        if rng.random() < p:
            deps.append(
                Deposit(
                    resource=res,
                    grade=rng.uniform(*grade),
                    amount_t=rng.uniform(*amount),
                    known=False,
                )
            )

    if pkind in ("rocky", "mixed", "moon", "asteroid"):
        add("Fe", 0.7 if metal_likely or pkind == "asteroid" else 0.4, (5e4, 5e6))
        add("Al", 0.45, (1e4, 1e6))
        add("Si", 0.8, (1e5, 8e6))
        add("Cu", 0.2, (500, 5e4))
        add("U", 0.08, (50, 5e3))
        add("Li", 0.12, (100, 2e4))
        add("MAG", 0.1, (20, 2e3))
    if pkind in ("mixed", "ice_giant", "moon") or ice_likely or au > snow * 0.75:
        add("H2O", 0.85, (1e5, 1e8))
    if pkind in ("gas_giant", "ice_giant") or (pkind == "moon" and ice_likely):
        add("CH4", 0.55, (1e4, 5e7))
        add("He", 0.25, (100, 1e5))
        add("Ar", 0.3, (500, 1e5))
        add("Xe", 0.12, (10, 5e3))
    if pkind == "asteroid" and au > snow:
        add("H2O", 0.5, (1e3, 1e6))
        add("CH4", 0.2, (100, 5e4))
    # nitrogen sparse
    if pkind in ("rocky", "mixed") and au < snow:
        add("N", 0.25, (1e3, 5e5))
    return deps


def _planet_name(rng: random.Random, i: int) -> str:
    roots = [
        "Kepler", "Helios", "Nyx", "Astra", "Vesper", "Cinder", "Glacis", "Ferrum",
        "Thalassa", "Pebble", "Ember", "Frost", "Basalt", "Mir", "Orin", "Sable",
    ]
    return f"{rng.choice(roots)}-{i+1}"


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
    # outer-only metals
    score += max(0, 4 - metals) * 0.3
    score += max(0, 3 - ices) * 0.4
    return min(10.0, max(1.0, score))


def survey_catalog(n: int = 6) -> List[dict]:
    """Pre-game star picks with survey-level info."""
    out = []
    for i in range(n):
        seed = random.randint(1, 10**9)
        sys = generate_system(seed=seed)
        out.append(
            {
                "seed": sys.seed,
                "star": sys.star,
                "difficulty": round(sys.difficulty, 2),
                "survey_summary": sys.survey_summary,
                "planet_count": len([b for b in sys.bodies if b.kind == "planet"]),
                "moon_count": len([b for b in sys.bodies if b.kind == "moon"]),
            }
        )
    return out
