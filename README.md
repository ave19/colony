# Colony

You lead a colony ship into a system that already has remote survey data on file, then settle it with real orbital logistics until you can build more colony ships.

*(Design note for us: the world is a “going concern” — activity and dossiers exist before the player clicks.)*

## Intended loop (current playable)

1. **View survey results** — open the pre-existing remote dossier archive (not “invent 8 systems on click”).
2. **Commit** to a dossier → multi-year transit.
3. **Arrive materials-only** — people, know-how, seed stock. **No** pre-built survey sats / miners / haulers.
4. **Authorize builds** on the ark (survey sat, miner, hauler) — materials + time.
5. **Click the Colony Ark** — command console (survey priorities, fabrication including **refuel depots**, cargo).
6. **Click a survey probe** — action card: move (shows Δv cost), survey focus, **return to ark** (refuels), stand by.
7. Probes have **fixed Δv tanks**; hops spend budget. Refuel at ark or a deployed depot.
7. **Found a project** → contracts (needs). Bootstrap with ark cargo, or **haul** with transfer options.
8. **Cargo transfers** — Economy (Hohmann) / Expedited / Sprint: propellant vs months + real Δv.
9. **Warp** advances the event queue (fab, arrivals, survey checkpoints, hauls). Idle warp skips nothing.

## Run

```bash
pip install -r requirements.txt
python3 main.py --host 0.0.0.0 --port 8765
```

Open **http://localhost:8765/**

### API (core)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health |
| GET | `/api/state` | Snapshot (advances wall clock 1:1) |
| POST | `/api/open_archive` or `/api/catalog` | View survey dossiers |
| POST | `/api/select_star` | `{"seed": N}` commit dossier |
| POST | `/api/build` | `{"unit_kind": "survey"\|"miner"\|"hauler"}` |
| POST | `/api/ark_scan_goal` | Toggle ark system-wide scan goal |
| POST | `/api/order` | unit order (survey/mine/move/idle) |
| POST | `/api/haul_options` | Transfer menu (origin → dest) |
| POST | `/api/start_haul` | Launch haul (option index, optional hauler + contract) |
| POST | `/api/deliver_ark` | Instant local contract fill from ark stock |
| POST | `/api/plan_base` | Found project → contracts |
| POST | `/api/warp` | Advance to next event (`force` for long jumps) |

**Time:** sim runs real-time 1:1 with Earth seconds. Use **Warp** for the event queue — do not sit through multi-month fab in wall clock. Jumps longer than ~1 week ask for confirmation.

**Persistence:** the colony room is saved to disk (`.state_one` by default; override with `COLONY_SAVE_PATH`) after every state-changing request, and resumed automatically on the next `python3 main.py` — sim time catches up to wall clock on resume. Delete the save file (or `POST /api/reset`) to start over.

## Design docs

- [docs/PLAYABLE_LADDER.md](docs/PLAYABLE_LADDER.md) — A→B→C milestones
- [docs/TECH_BOOK_v1.md](docs/TECH_BOOK_v1.md) — materials / tech graph
- [docs/GOING_CONCERN.md](docs/GOING_CONCERN.md) — continuous world loop
- [docs/SYSTEM_MODEL.md](docs/SYSTEM_MODEL.md) — Kepler / Roche / Hill packing

## Not done yet (milestones B / C / later)

Multiplayer corps + claims, Director AI, pre-transit loadout customize, ship combat, full surface industry depth, managed hosting.
