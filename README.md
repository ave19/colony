# Colony

Humanity is spreading among the stars. A colony ship arrives at a generated system; you settle it with real orbital logistics until you can build more colony ships.

## Playable ladder

Design and milestones: [docs/PLAYABLE_LADDER.md](docs/PLAYABLE_LADDER.md)

Tech / materials book: [docs/TECH_BOOK_v1.md](docs/TECH_BOOK_v1.md)

- **A** — Solo vertical slice (first playable) ← *in progress / running*
- **B** — Multiplayer corps
- **C** — Director AI

## Run (first playable)

```bash
pip install -r requirements.txt
python3 main.py --host 0.0.0.0 --port 8765
```

Open **http://localhost:8765/** (or put this port behind your Pangolin gateway).

### What works now

1. **Survey stars** → pick one → multi-year **transit** (warp to arrival)
2. **God’s-eye system map** — planets, moons, asteroids on stable orbits
3. **Scan** a body → reveal deposits
4. **Plan a base** (power + hab options) → **contracts** spawn from needs
5. **Deliver from ark** or **haul** with physics transfer options (economy / expedited / sprint: propellant vs months)
6. **Warp → event** advances to next arrival / haul complete
7. Ark trickle-fabs steel/chips/panels/propellant slowly; Xe is **0** on arrival

### API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check |
| GET | `/api/state` | Full snapshot |
| POST | `/api/catalog` | Generate star survey |
| POST | `/api/select_star` | `{"seed": N}` |
| POST | `/api/warp` | Warp to next event |
| POST | `/api/scan` | `{"body_id": "p0"}` |
| POST | `/api/plan_base` | body + power_id + hab_id |
| POST | `/api/deliver_ark` | fill contract from ark |
| POST | `/api/haul_options` | origin/dest transfer menu |
| POST | `/api/start_haul` | launch haul |
| POST | `/api/reset` | new room |

## Stack

Python 3 + FastAPI + static web client. Self-hosted colony room (solo).

Default port: **8765** (`COLONY_PORT` / `--port`).
