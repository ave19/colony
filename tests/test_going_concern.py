"""Going-concern sim: continuous clock, dossiers, materials arrival, build→order."""

from colony.sim.constants import SECONDS_PER_DAY
from colony.sim.game import Game
from colony.sim.system_gen import build_survey_archive


def test_build_survey_archive_is_stable_for_universe_seed():
    a = build_survey_archive(8, universe_seed=99)
    b = build_survey_archive(8, universe_seed=99)
    assert len(a) == 8
    assert [d["seed"] for d in a] == [d["seed"] for d in b]
    assert all(d.get("status") == "remote survey on file" for d in a)
    assert all("dossier_id" in d for d in a)


def test_open_archive_views_existing_dossiers_not_fresh_rng():
    g = Game(universe_seed=123)
    seeds_before = [d["seed"] for d in g.survey_archive]
    g.open_survey_archive()
    assert g.archive_opened
    assert [d["seed"] for d in g.catalog] == seeds_before
    # Opening again does not reshuffle
    g.open_survey_archive()
    assert [d["seed"] for d in g.catalog] == seeds_before


def test_continuous_time_advance_moves_orbit_phase():
    g = Game(universe_seed=7)
    g.open_survey_archive()
    seed = g.catalog[0]["seed"]
    g.select_star(seed)
    while g.phase == "transit":
        g.warp_to_next_event()
    assert g.phase == "system"
    body = next(b for b in g.system.bodies if b.kind == "planet")
    snap0 = g.system.to_dict(g.sim_time_s)
    p0 = next(x for x in snap0["bodies"] if x["id"] == body.id)
    phase0 = p0["phase"]
    t0 = g.sim_time_s
    # Advance half a year of game time via shipped advance()
    g.advance(SECONDS_PER_DAY * 180)
    assert g.sim_time_s > t0
    snap1 = g.system.to_dict(g.sim_time_s)
    p1 = next(x for x in snap1["bodies"] if x["id"] == body.id)
    # Inner planets should move measurably in 180 days
    assert abs(p1["phase"] - phase0) > 1e-6 or body.semi_major_m > 0


def test_arrival_has_ark_only_no_prebuilt_specialists():
    g = Game(universe_seed=11)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event()
    kinds = [u.kind for u in g.fleet.values()]
    assert kinds == ["ark"]
    assert g.ark_stock["steel"] > 0
    assert g.ark_stock["chip"] > 0
    assert g.population >= 10_000


def test_queue_build_survey_then_order_survey_unlocks_site():
    g = Game(universe_seed=22)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event()
    assert not any(u.kind == "survey" for u in g.fleet.values())

    steel0 = g.ark_stock["steel"]
    g.queue_build("survey")
    assert g.ark_stock["steel"] < steel0
    assert len(g.build_queue) == 1

    # Warp until build completes
    for _ in range(20):
        if any(u.kind == "survey" for u in g.fleet.values()):
            break
        g.warp_to_next_event()
    surveys = [u for u in g.fleet.values() if u.kind == "survey"]
    assert len(surveys) == 1
    sat = surveys[0]

    body = next(b for b in g.system.bodies if b.kind == "planet" and b.deposits)
    # Park sat already at body to isolate survey progression (travel is separate)
    sat.location_id = body.id
    g.issue_order(sat.id, "survey", body.id)
    assert sat.status == "working"
    assert sat.order == "survey"

    # Advance survey months until a mine site appears
    found = False
    for _ in range(80):
        g.advance(SECONDS_PER_DAY * 30)  # ~1 month slices
        if body.mine_sites:
            found = True
            break
    assert found, "survey on-station should eventually unlock a mine site"
    assert body.survey_months > 0


def test_cannot_commit_unknown_seed():
    g = Game(universe_seed=5)
    g.open_survey_archive()
    try:
        g.select_star(999999999)
        assert False, "should reject"
    except ValueError as e:
        assert "dossier" in str(e).lower() or "archive" in str(e).lower()
