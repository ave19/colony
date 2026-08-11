"""Persistence: save/load a colony room and resume with wall-clock catch-up."""

import time

from colony.sim.game import Game


def test_load_missing_file_returns_none(tmp_path):
    assert Game.load(tmp_path / "nope.pkl") is None


def test_load_corrupt_file_returns_none(tmp_path):
    path = tmp_path / "corrupt.pkl"
    path.write_bytes(b"not a pickle")
    assert Game.load(path) is None


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "state.pkl"
    g = Game(universe_seed=11)
    g.open_survey_archive()
    seed = g.catalog[0]["seed"]
    g.select_star(seed)
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    assert g.phase == "system"

    body = next(b for b in g.system.bodies if b.kind == "planet")
    g.plan_base(body.id, "solar", "underground", "Test Base")
    g.save(path)

    loaded = Game.load(path)
    assert loaded is not None
    assert loaded.phase == "system"
    assert loaded.selected_seed == g.selected_seed
    assert list(loaded.projects.keys()) == list(g.projects.keys())
    assert loaded.contracts.keys() == g.contracts.keys()
    assert loaded.ark_stock == g.ark_stock
    assert loaded.system.seed == g.system.seed


def test_reload_catches_up_wall_clock_after_downtime(tmp_path):
    path = tmp_path / "state.pkl"
    g = Game(universe_seed=13)
    g.open_survey_archive()
    seed = g.catalog[0]["seed"]
    g.select_star(seed)
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    assert g.phase == "system"

    t_before = g.sim_time_s
    # Simulate the process having been down for an hour: back-date last_wall.
    g.last_wall -= 3600
    g.save(path)

    loaded = Game.load(path)
    assert loaded is not None
    loaded.catch_up()
    # An hour of real downtime should have advanced sim time by roughly an hour.
    assert loaded.sim_time_s >= t_before + 3500
    assert loaded.last_wall > g.last_wall


def test_save_creates_no_leftover_tmp_file(tmp_path):
    path = tmp_path / "state.pkl"
    g = Game(universe_seed=17)
    g.save(path)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
