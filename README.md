# Colony

Humanity is a **going concern**. You lead one colony ship into a system that already has remote survey data on file; you settle with real orbital logistics until you can build more colony ships.

## Intended loop (current playable)

1. **View survey results** — open the pre-existing remote dossier archive (not “invent 8 systems on click”).
2. **Commit** to a dossier → multi-year transit.
3. **Arrive materials-only** — people, know-how, seed stock. **No** pre-built survey sats / miners / haulers.
4. **Authorize builds** on the ark (survey sat, miner, hauler) — materials + time.
5. **Warp** to complete fabrication and orders.
6. **Map-first** — orbit/zoom/focus in 3D; order units to bodies; survey deepens over time until **mine sites** unlock; mine sites only.

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
| GET | `/api/state` | Snapshot (advances wall clock) |
| POST | `/api/open_archive` or `/api/catalog` | View survey dossiers |
| POST | `/api/select_star` | `{"seed": N}` commit dossier |
| POST | `/api/build` | `{"unit_kind": "survey"\|"miner"\|"hauler"}` |
| POST | `/api/order` | unit order (survey/mine/move/idle) |
| POST | `/api/warp` | Advance to next event |

## Design docs

- [docs/PLAYABLE_LADDER.md](docs/PLAYABLE_LADDER.md) — A→B→C milestones
- [docs/TECH_BOOK_v1.md](docs/TECH_BOOK_v1.md) — materials / tech graph
- [docs/GOING_CONCERN.md](docs/GOING_CONCERN.md) — continuous world loop

## Not done yet

Multiplayer corps, Director AI, full surface industry depth, managed hosting.
