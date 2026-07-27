# System model (foundation)

This is the **source of truth** for how star systems exist in Colony.
UI and game loops build *on top of* this — they do not invent special-case orbits.

## Principles (apply everywhere)

1. **Kepler III** — For any two-body circular orbit,  
   \(P = 2\pi\sqrt{a^3/\mu}\), \(\mu = GM_{\mathrm{central}}\).  
   Periods are never hand-assigned independent of \(a\).

2. **Hierarchy** — Planets/asteroids orbit the **star**.  
   Moons orbit their **parent planet** (not the star).

3. **Roche** — Moons sit **outside** a Roche-like limit so they are not shredded.

4. **Hill** — Moons sit **inside** a fraction of the planet’s Hill sphere  
   \(R_H \approx a_p (m_p / 3M_\star)^{1/3}\)  
   so they remain bound to the planet.

5. **No co-orbitals by default** — Adjacent moons are separated by  
   \(\Delta a \gtrsim K\,R_{H,\mathrm{mut}}\) (and a mild period-ratio floor).  
   Two moons do not share one \(a\).

6. **Formation priors** — Snow line from luminosity; rock inside / ice & giants beyond;  
   resources follow class + location (not loot tables alone).

7. **Stability packing for planets** — Adjacent planet orbits keep a minimum period/spacing  
   ratio so the system is not instantly chaotic.

## What we deliberately do *not* do

- Hard-code “Jupiter’s moons” or “Saturn’s rings” as templates.  
  Those systems are **examples** of the rules above (including cases where  
  period ratios land near 1:2:4 — that can *emerge* from packing + Kepler,  
  it is not a special Jupiter mode).

- Fake angular rates for display. Map phase uses the same Kepler periods.

## Constants / knobs

| Symbol | Role | Typical |
|--------|------|---------|
| \(f_H\) | Outer moon cap as fraction of \(R_H\) | ~0.4 |
| \(K\) | Mutual Hill separations between moons | ~8–12 |
| Snow line | \(2.7\,\mathrm{AU}\sqrt{L/L_\odot}\) | — |

## Tests

See `tests/test_orbits.py` and `tests/test_system_model.py` for Roche/Hill nesting,  
Kepler consistency, and non-coorbital moons.
