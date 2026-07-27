"""Basic orbital math smoke tests."""

from colony.sim.constants import AU_M, G, SOLAR_MASS
from colony.sim.orbits import hohmann_transfer, propellant_for_dv, transfer_options
from colony.sim.system_gen import generate_system


def test_hohmann_earth_mars_order_of_magnitude():
    mu = G * SOLAR_MASS
    r1 = 1.0 * AU_M
    r2 = 1.524 * AU_M
    dv, tof = hohmann_transfer(r1, r2, mu)
    assert 4000 < dv < 8000  # rough Hohmann total ~5.5 km/s class
    assert tof > 100 * 86400  # months, not days


def test_transfer_options_trade_fuel_for_time():
    mu = G * SOLAR_MASS
    opts = transfer_options(1 * AU_M, 1.5 * AU_M, mu, ship_dry_mass_t=8)
    assert len(opts) >= 2
    assert opts[0].propellant_t < opts[-1].propellant_t
    assert opts[0].months > opts[-1].months


def test_propellant_positive():
    p = propellant_for_dv(3000, 50)
    assert p > 0


def test_generate_system_not_trap():
    sys = generate_system(seed=12345)
    planets = [b for b in sys.bodies if b.kind == "planet"]
    assert len(planets) >= 2
    assert 1 <= sys.difficulty <= 10
