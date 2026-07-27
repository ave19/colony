"""FastAPI server for Colony playable slice."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import colony.sim.game as game_mod

STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Colony", version="0.1.0")


def room():
    return game_mod.ROOM


class SelectStarBody(BaseModel):
    seed: int


class ScanBody(BaseModel):
    body_id: str


class PlanBaseBody(BaseModel):
    body_id: str
    power_id: str = "solar"
    hab_id: str = "underground"
    name: str = ""


class DeliverBody(BaseModel):
    contract_id: str
    amount_t: Optional[float] = None


class HaulOptionsBody(BaseModel):
    origin_id: str
    dest_id: str


class StartHaulBody(BaseModel):
    origin_id: str = "ark"
    dest_id: str
    resource: str
    amount_t: float = Field(gt=0)
    option_index: int = 0
    contract_id: Optional[str] = None


class OrderBody(BaseModel):
    unit_id: str
    order: str  # survey | mine | move | idle
    target_id: str = ""
    resource: str = ""  # for survey: "Fe" = find sources of iron


@app.get("/api/health")
def health():
    return {"ok": True, "service": "colony", "version": "0.1.0"}


@app.get("/api/state")
def state():
    return room().snapshot()


@app.post("/api/catalog")
def catalog():
    """Open pre-existing survey archive (going-concern dossiers)."""
    room().open_survey_archive()
    return room().snapshot()


@app.post("/api/open_archive")
def open_archive():
    room().open_survey_archive()
    return room().snapshot()


class BuildBody(BaseModel):
    unit_kind: str  # survey | miner | hauler


@app.post("/api/build")
def build_unit(body: BuildBody):
    try:
        return room().queue_build(body.unit_kind)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/select_star")
def select_star(body: SelectStarBody):
    try:
        return room().select_star(body.seed)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


class WarpBody(BaseModel):
    force: bool = False  # confirm long jumps (>~1 week)


@app.post("/api/warp")
def warp(body: WarpBody = WarpBody()):
    result = room().warp_to_next_event(force=body.force)
    snap = room().snapshot()
    snap["warp"] = result
    return snap


@app.get("/api/events")
def events():
    room().catch_up()
    return {"event_queue": room().event_queue(), "next_event": (room().event_queue() or [None])[0]}


@app.post("/api/scan")
def scan(body: ScanBody):
    try:
        return room().scan_body(body.body_id)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/plan_base")
def plan_base(body: PlanBaseBody):
    try:
        return room().plan_base(body.body_id, body.power_id, body.hab_id, body.name)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/deliver_ark")
def deliver_ark(body: DeliverBody):
    try:
        return room().deliver_from_ark(body.contract_id, body.amount_t)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/haul_options")
def haul_options(body: HaulOptionsBody):
    try:
        room().catch_up()
        return {"options": room().haul_options(body.origin_id, body.dest_id)}
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/start_haul")
def start_haul(body: StartHaulBody):
    try:
        return room().start_haul(
            body.origin_id,
            body.dest_id,
            body.resource,
            body.amount_t,
            body.option_index,
            body.contract_id,
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/order")
def order(body: OrderBody):
    try:
        return room().issue_order(
            body.unit_id, body.order, body.target_id, resource=body.resource or ""
        )
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/estimate_order")
def estimate_order(body: OrderBody):
    try:
        return room().estimate_order(body.unit_id, body.order, body.target_id)
    except Exception as e:
        raise HTTPException(400, str(e)) from e


@app.post("/api/reset")
def reset():
    game_mod.ROOM = game_mod.Game()
    return room().snapshot()


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
