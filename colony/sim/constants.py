"""Shared physical constants (SI-ish game units)."""

# Game time: 1 sim-second of wall processing advances game by GAME_SECONDS_PER_REAL
# but default is 1× real wall clock when server is running.

SECONDS_PER_DAY = 86400.0
DAYS_PER_MONTH = 30.0  # game month (simplified calendar)
DAYS_PER_YEAR = 360.0

# Astronomical
AU_M = 1.495978707e11
G = 6.67430e-11
SOLAR_MASS = 1.98847e30
EARTH_MASS = 5.972e24
EARTH_RADIUS = 6.371e6

# Display / balance
SEED_FE_TONNES = 1000.0
ARK_POPULATION = 10_000
FOUNDER_POPULATION = 10_000
