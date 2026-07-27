"""Orbital math and system realism smoke tests."""

from colony.sim.constants import AU_M, G, SOLAR_MASS
from colony.sim.orbits import hohmann_transfer, propellant_for_dv, period_seconds, transfer_options
from colony.sim.system_gen import generate_system

SECONDS_PER_YEAR = 365.25 * 86400.0


def test_hohmann_earth_mars_order_of_magnitude():
    mu = G * SOLAR_MASS
    r1 = 1.0 * AU_M
    r2 = 1.524 * AU_M
    dv, tof = hohmann_transfer(r1, r2, mu)
    assert 4000 < dv < 8000
    assert tof > 100 * 86400


def test_kepler_earth_year():
    mu = G * SOLAR_MASS
    p = period_seconds(1.0 * AU_M, mu)
    years = p / SECONDS_PER_YEAR
    assert 0.98 < years < 1.02


def test_kepler_jupiter_class():
    mu = G * SOLAR_MASS
    p = period_seconds(5.2 * AU_M, mu)
    years = p / SECONDS_PER_YEAR
    assert 11.0 < years < 13.0


def test_transfer_options_trade_fuel_for_time():
    mu = G * SOLAR_MASS
    opts = transfer_options(1 * AU_M, 1.5 * AU_M, mu, ship_dry_mass_t=8)
    assert len(opts) >= 2
    assert opts[0].propellant_t < opts[-1].propellant_t
    assert opts[0].months > opts[-1].months


def test_propellant_positive():
    assert propellant_for_dv(3000, 50) > 0


def test_generate_system_believable():
    sys = generate_system(seed=12345, star_type_id="G2V")
    planets = [b for b in sys.bodies if b.kind == "planet"]
    assert len(planets) >= 3
    max_au = max(b.semi_major_m / AU_M for b in planets)
    assert max_au > 4.0  # system is wide
    giant = next((b for b in planets if b.planet_class == "gas_giant"), None)
    if giant:
        years = period_seconds(giant.semi_major_m, sys.star_mu) / SECONDS_PER_YEAR
        assert years > 8.0  # not weeks
    moons = [b for b in sys.bodies if b.kind == "moon"]
    for m in moons:
        assert m.parent_id and m.parent_id.startswith("p")
        parent = sys.body_by_id(m.parent_id)
        assert parent and parent.kind == "planet"
