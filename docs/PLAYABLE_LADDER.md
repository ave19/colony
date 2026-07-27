# Colony — Playable ladder (A → B → C)

Planning doc synced with the GitHub umbrella issue set.
Created from design grilling (2026-07).

## Goal

Build **Colony** as a science-driven orbital logistics sim: player-authored goals → needs → contracts, real orbital mechanics, formation-based systems, constrained exponential growth. Deliver in three milestones (**A → B → C**).

## Architecture decisions

| Area | Decision |
|------|----------|
| Orbit | Planned transfers (not hand-pilot); real mechanics; fuel vs time options; Δv to orbit/escape |
| Propellant | Typed cargo + Δv UI; multiple drives; materials may block some drive types |
| Time | Default 1× while process runs; event calendar; alarms; vote-warp to next event; wall-clock catch-up on wake |
| Hosting | Self-host colony room (Python); VPS optional; desk PC offline = room offline |
| Tech | Full know-how on arrival; 2536-plausible science; substitutes with mass/efficiency penalties; no research XP tree |
| Systems | Same tech every run; formation-based gen; stable orbits; difficulty metric; filter traps; pick star then commit |
| Materials | Atoms → processes → compounds; location choices (ISRU vs central); co-reactants matter (CH₄ needs O₂) |
| Growth | Constrained exponential; throughput-limited (e.g. 10 t Fe/mo still progresses) |
| View | v1 system map only (isometric/god's-eye web); no NMS zoom yet; no mid-game galaxy UI |
| Start | Heavy but limited loadout; customize before transit; scan sats, mining bots, tiny ship fabs |
| Plans | Player goals → needs → contracts (not NPC quests); multiple projects can conflict |
| MP (B) | Shared colony; corps + claims; credits + barter; demand from structure; invite-based |
| AI (C) | Suggest goals (cascades to contracts); optional full auto “watch AI solve” |
| Score (later) | Colony-ship production rate |
| Stack | Python server + web client |

## Milestone A — Solo vertical slice (first playable)

Pick star → generate system → web system map → plan base → contracts → ship bootstrap → one real physics haul → 1× time + catch-up.

### A acceptance

- [ ] Star pick → arrive in generated stable system
- [ ] Map + base plan spawns needs/contracts
- [ ] Bootstrap + one real transfer-option haul
- [ ] 1× + wall-clock catch-up
- [ ] Fully solo playable

### A sub-issues

| ID | Title | Depends on |
|----|-------|------------|
| A1 | Sim core: time, events, catch-up, vote-warp stub | — |
| A2 | System generator: formation priors, stable orbits, difficulty, reject traps | — |
| A3 | Orbital logistics: Δv orbit/escape, transfer options | A1, A2 |
| A4 | Tech/materials graph: atoms, processes, substitutes, ship fabs | — |
| A5 | Goals → needs → contracts | A4 |
| A6 | Actors: ship, scan sats, mining bots, haulers | A3, A4 |
| A7 | Web: star pick → transit → god's-eye system map | A2, A3 |
| A8 | Vertical slice: one base plan + one physics haul E2E | A1–A7 |
| A9 | Persistence + solo colony room | A1, A8 |
| A10 | Design doc: v1 element/tech book | — parallel |

## Milestone B — Multiplayer corps

Shared colony room, join link, corps claim assets, cross-corp contract fill (credits + barter thin slice).

### B acceptance

- [ ] 2+ players in one room on one system
- [ ] Corps claim assets; contracts fillable cross-corp
- [ ] Co-op loop: base needs ↔ harvester ↔ haul route
- [ ] Self-host/VPS model still holds

### B sub-issues

| ID | Title | Depends on |
|----|-------|------------|
| B1 | Colony room join (link/code); light identity | A9 |
| B2 | Corps + asset claims | B1 |
| B3 | Contract fulfillment cross-corp; credits + barter | A5, B2 |
| B4 | Settlement demand estimates from structure | A5, B3 |
| B5 | Shared calendar/alarms; multi-player vote-warp | A1, B1 |
| B6 | Two-player playtest slice | B1–B5 |

## Milestone C — Director AI

AI suggests goals (→ needs → contracts); optional auto mode to watch the system get solved.

### C acceptance

- [ ] Director proposes sensible goals from known state
- [ ] Accepting a suggestion spawns real contracts
- [ ] Auto mode can progress without cheating physics
- [ ] Human can override / disable

### C sub-issues

| ID | Title | Depends on |
|----|-------|------------|
| C1 | Director: suggest goals from sim + tech graph | A4, A5 |
| C2 | Draft plan/contracts from suggested goal (confirm) | C1 |
| C3 | Optional auto-corp / auto-director mode | C2, B2 |
| C4 | AI safety: no free resources; legal actions only | C1–C3 |

## Out of scope (for A/B/C ladder)

- Public matchmaking / managed hosting
- Site-level Factorio / NMS zoom
- Full surface transport tree as required depth
- Deep fusion as mandatory path
- True n-body chaos (stable Keplerian / patched-conics class)
- Post-system campaign UI beyond pre-game star pick
- Rich multi-corp market polish

## Creating GitHub issues

With a token that has **Issues: Read and write** on this repo:

```bash
./scripts/create-github-issues.sh
```

## Notes

- Sync code to `origin` regularly during implementation.
- Science homework for the tech book (A10) runs in parallel with engineering.

---

## Tech book

Detailed v1 materials/tech graph: [TECH_BOOK_v1.md](./TECH_BOOK_v1.md)
