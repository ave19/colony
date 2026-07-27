"""Orbital-mechanics foundation: Kepler, Roche, Hill, no co-orbital moons."""

from colony.sim.constants import G, SOLAR_MASS
from colony.sim.orbits import (
    density_sphere,
    hill_radius,
    mutual_hill_radius,
    period_seconds,
    roche_limit_rigid,
)
from colony.sim.system_gen import generate_system


def test_kepler_period_matches_semi_major_for_all_planets():
    sys = generate_system(seed=7, star_type_id="G2V")
    mu = sys.star_mu
    for b in sys.bodies:
        if b.kind not in ("planet", "asteroid"):
            continue
        P = period_seconds(b.semi_major_m, mu)
        # invert: a^3 = mu P^2 / 4pi^2
        a_back = (mu * P**2 / (4 * 3.141592653589793**2)) ** (1 / 3)
        assert abs(a_back - b.semi_major_m) / b.semi_major_m < 1e-9


def test_moons_orbit_planet_not_star_and_respect_roche_hill():
    sys = generate_system(seed=42, star_type_id="G2V")
    star_m = sys.star_mass_kg
    checked = 0
    for m in sys.bodies:
        if m.kind != "moon":
            continue
        parent = sys.body_by_id(m.parent_id)
        assert parent is not None and parent.kind == "planet"
        # Period about parent
        P_p = period_seconds(m.semi_major_m, G * parent.mass_kg)
        # Period if mistakenly about star would be different order of magnitude for close moons
        assert P_p > 0
        r_h = hill_radius(parent.semi_major_m, parent.mass_kg, star_m)
        assert m.semi_major_m < 0.5 * r_h + 1.0, "moon outside Hill sphere"
        rho_p = density_sphere(parent.mass_kg, parent.radius_m)
        roche = roche_limit_rigid(parent.radius_m, rho_p, 2000.0)
        assert m.semi_major_m > roche * 0.9, "moon inside Roche"
        assert m.semi_major_m > 2.0 * parent.radius_m
        checked += 1
    assert checked >= 1


def test_sibling_moons_not_coorbital_mutual_hill():
    sys = generate_system(seed=99, star_type_id="G2V")
    by_p = {}
    for m in sys.bodies:
        if m.kind == "moon":
            by_p.setdefault(m.parent_id, []).append(m)
    multi = 0
    for pid, sibs in by_p.items():
        if len(sibs) < 2:
            continue
        multi += 1
        parent = sys.body_by_id(pid)
        sibs = sorted(sibs, key=lambda x: x.semi_major_m)
        for a, b in zip(sibs, sibs[1:]):
            assert b.semi_major_m > a.semi_major_m * 1.1
            rh = mutual_hill_radius(
                a.semi_major_m, b.semi_major_m, a.mass_kg, b.mass_kg, parent.mass_kg
            )
            da = b.semi_major_m - a.semi_major_m
            # Generator targets K~8–12; allow some slack after mass finalization
            assert da / rh > 5.0, f"moons too close in Hill units: {da/rh:.2f}"
    assert multi >= 1


def test_no_jupiter_special_case_required():
    """Model must work for non-Sol stars without Galilean templates."""
    sys = generate_system(seed=3, star_type_id="M5V")
    assert sys.star["spectral"] == "M5V"
    planets = [b for b in sys.bodies if b.kind == "planet"]
    assert len(planets) >= 2
    for m in sys.bodies:
        if m.kind != "moon":
            continue
        parent = sys.body_by_id(m.parent_id)
        r_h = hill_radius(parent.semi_major_m, parent.mass_kg, sys.star_mass_kg)
        assert m.semi_major_m < 0.5 * r_h
