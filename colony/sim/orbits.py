"""Keplerian orbits and transfer option math."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

from .constants import AU_M, G, DAYS_PER_MONTH, SECONDS_PER_DAY


@dataclass
class TransferOption:
    name: str
    propellant_t: float  # tonnes chemical propellant (game unit)
    months: float
    dv_m_s: float
    description: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "propellant_t": round(self.propellant_t, 2),
            "months": round(self.months, 2),
            "dv_m_s": round(self.dv_m_s, 1),
            "description": self.description,
        }


def period_seconds(semi_major_m: float, mu: float) -> float:
    """Orbital period from Kepler's third law: P = 2π √(a³/μ)."""
    return 2.0 * math.pi * math.sqrt(semi_major_m**3 / mu)


def semi_major_from_period(period_s: float, mu: float) -> float:
    """Invert Kepler III: a = (μ P² / 4π²)^{1/3}."""
    return (mu * period_s**2 / (4.0 * math.pi**2)) ** (1.0 / 3.0)


def hill_radius(a_m: float, m_secondary: float, m_primary: float) -> float:
    """
    Approximate Hill sphere radius of a secondary orbiting a primary on a circular orbit.
    R_H ≈ a (m / (3 M))^{1/3}
    """
    if m_primary <= 0 or a_m <= 0 or m_secondary <= 0:
        return 0.0
    return a_m * (m_secondary / (3.0 * m_primary)) ** (1.0 / 3.0)


def roche_limit_rigid(radius_primary: float, density_primary: float, density_secondary: float) -> float:
    """
    Rigid-body Roche limit (center of secondary): R_roche ≈ R_p * (2 ρ_p / ρ_s)^{1/3}
    Densities in same units (e.g. kg/m³).
    """
    if density_secondary <= 0:
        return 2.44 * radius_primary
    return radius_primary * (2.0 * density_primary / density_secondary) ** (1.0 / 3.0)


def mutual_hill_radius(a1: float, a2: float, m1: float, m2: float, m_central: float) -> float:
    """Mutual Hill radius of two coplanar secondaries about the same central mass."""
    a_bar = 0.5 * (a1 + a2)
    return a_bar * ((m1 + m2) / (3.0 * m_central)) ** (1.0 / 3.0)


def min_period_ratio_for_stability(k_hill: float = 8.0) -> float:
    """
    Rough lower bound on adjacent period ratio for packed circular coplanar orbits.
    Using Δa ≳ k R_H,mut and Kepler: not exact — used only as a generator floor.
    k_hill ~ 7–10 is typical for long-term packed systems.
    """
    # For equal-mass moons, R_H/a ~ (2m/(3M))^{1/3}; we enforce via placement instead.
    return 1.0  # placeholder — packing enforced in meters via mutual Hill


def density_sphere(mass_kg: float, radius_m: float) -> float:
    if radius_m <= 0:
        return 1000.0
    vol = (4.0 / 3.0) * math.pi * radius_m**3
    return mass_kg / vol


def circular_velocity(r_m: float, mu: float) -> float:
    return math.sqrt(mu / r_m)


def escape_velocity(r_m: float, mu: float) -> float:
    return math.sqrt(2.0 * mu / r_m)


def surface_gravity(mass_kg: float, radius_m: float) -> float:
    return G * mass_kg / (radius_m**2)


def dv_surface_to_orbit(body_mass_kg: float, body_radius_m: float, orbit_altitude_m: float = 200_000.0) -> float:
    """Rough Δv to low orbit (circularize at altitude), ignoring atmosphere."""
    mu = G * body_mass_kg
    r_surf = body_radius_m
    r_orb = body_radius_m + orbit_altitude_m
    # Idealized: burn to elliptical then circularize — use vis-viva approximation
    v_circ_orb = circular_velocity(r_orb, mu)
    # Hohmann-like from surface is wrong; use energy-ish estimate: orbital + gravity losses fudge
    v_esc_surf = escape_velocity(r_surf, mu)
    # Playable approximation used by many space games:
    dv = v_circ_orb + 0.15 * v_esc_surf
    return dv


def dv_orbit_to_escape(body_mass_kg: float, body_radius_m: float, orbit_altitude_m: float = 200_000.0) -> float:
    mu = G * body_mass_kg
    r_orb = body_radius_m + orbit_altitude_m
    v_c = circular_velocity(r_orb, mu)
    v_e = escape_velocity(r_orb, mu)
    return max(0.0, v_e - v_c)


def hohmann_transfer(
    r1_m: float,
    r2_m: float,
    mu_star: float,
) -> tuple[float, float]:
    """
    Hohmann transfer between two circular coplanar orbits around the star.
    Returns (total_dv m/s, time of flight seconds).
    """
    a_t = 0.5 * (r1_m + r2_m)
    v1 = circular_velocity(r1_m, mu_star)
    v2 = circular_velocity(r2_m, mu_star)
    v_p = math.sqrt(mu_star * (2.0 / r1_m - 1.0 / a_t))
    v_a = math.sqrt(mu_star * (2.0 / r2_m - 1.0 / a_t))
    dv = abs(v_p - v1) + abs(v2 - v_a)
    tof = math.pi * math.sqrt(a_t**3 / mu_star)
    return dv, tof


def synodic_period_seconds(p1_s: float, p2_s: float) -> float:
    if abs(p1_s - p2_s) < 1e-6:
        return p1_s
    return abs(1.0 / (1.0 / p1_s - 1.0 / p2_s))


def propellant_for_dv(
    dv_m_s: float,
    dry_mass_t: float,
    isp_s: float = 320.0,
    g0: float = 9.81,
) -> float:
    """Rocket equation: propellant mass tonnes for given Δv and dry mass."""
    if dv_m_s <= 0:
        return 0.0
    ve = isp_s * g0
    # m0/m1 = exp(dv/ve); prop = m0 - m1; m1 = dry
    mass_ratio = math.exp(dv_m_s / ve)
    wet = dry_mass_t * mass_ratio
    return wet - dry_mass_t


def transfer_options(
    r1_m: float,
    r2_m: float,
    mu_star: float,
    ship_dry_mass_t: float = 8.0,
    extra_dv_m_s: float = 0.0,
    isp_s: float = 340.0,
) -> List[TransferOption]:
    """
    Real-ish options:
    - Economy: pure Hohmann (low fuel, long)
    - Fast: higher-energy transfer (scale dv up, cut TOF)
    Propellant from rocket equation on hauler dry mass + cargo-free burns.
    """
    if r1_m <= 0 or r2_m <= 0:
        return []

    dv_h, tof_h = hohmann_transfer(r1_m, r2_m, mu_star)
    dv_h += extra_dv_m_s

    # Faster: higher energy / shorter TOF (still ordered by rocket equation)
    energy_factor = 1.55
    time_factor = 0.62
    dv_fast = dv_h * energy_factor
    tof_fast = max(tof_h * time_factor, tof_h * 0.2)

    dv_sprint = dv_h * 2.05
    tof_sprint = max(tof_h * 0.4, tof_h * 0.15)

    def months(tof_s: float) -> float:
        return max(0.05, tof_s / (SECONDS_PER_DAY * DAYS_PER_MONTH))

    opts = [
        TransferOption(
            name="Economy (Hohmann)",
            propellant_t=propellant_for_dv(dv_h, ship_dry_mass_t, isp_s=isp_s),
            months=months(tof_h),
            dv_m_s=dv_h,
            description="Minimum-energy transfer. Wait for geometry; sip propellant.",
        ),
        TransferOption(
            name="Expedited",
            propellant_t=propellant_for_dv(dv_fast, ship_dry_mass_t, isp_s=isp_s),
            months=months(tof_fast),
            dv_m_s=dv_fast,
            description="Higher-energy transfer. More propellant, less flight time.",
        ),
        TransferOption(
            name="Sprint",
            propellant_t=propellant_for_dv(dv_sprint, ship_dry_mass_t, isp_s=isp_s),
            months=months(tof_sprint),
            dv_m_s=dv_sprint,
            description="Expensive burn schedule. For urgent contracts only.",
        ),
    ]
    return opts


def body_phase_rad(semi_major_m: float, mu: float, t_seconds: float, phase0: float = 0.0) -> float:
    """Mean anomaly-style phase for circular orbit display."""
    p = period_seconds(semi_major_m, mu)
    return (phase0 + 2.0 * math.pi * (t_seconds / p)) % (2.0 * math.pi)


def xy_on_orbit(semi_major_m: float, phase_rad: float) -> tuple[float, float]:
    """Position in AU-like display coords (meters → AU)."""
    x = (semi_major_m / AU_M) * math.cos(phase_rad)
    y = (semi_major_m / AU_M) * math.sin(phase_rad)
    return x, y
