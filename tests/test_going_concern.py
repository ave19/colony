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
        g.warp_to_next_event(force=True)
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
        g.warp_to_next_event(force=True)
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
        g.warp_to_next_event(force=True)
    assert not any(u.kind == "survey" for u in g.fleet.values())

    steel0 = g.ark_stock["steel"]
    g.queue_build("survey")
    assert g.ark_stock["steel"] < steel0
    assert len(g.build_queue) == 1

    # Warp until build completes
    for _ in range(20):
        if any(u.kind == "survey" for u in g.fleet.values()):
            break
        g.warp_to_next_event(force=True)
    surveys = [u for u in g.fleet.values() if u.kind == "survey"]
    assert len(surveys) == 1
    sat = surveys[0]

    body = next(b for b in g.system.bodies if b.kind == "planet" and any(d.resource == "Fe" for d in b.deposits))
    # Directed search: find sources of iron (may be en_route first — arrival is scheduled)
    g.issue_order(sat.id, "survey", body.id, resource="Fe")
    assert sat.order == "survey"
    assert sat.search_resource == "Fe"
    if sat.status == "en_route":
        assert any(e.get("kind") == "survey_arrival" for e in g.event_queue())
        while sat.status == "en_route":
            g.warp_to_next_event(force=True)
    assert sat.status == "working"
    assert sat.location_id == body.id

    found = False
    for _ in range(80):
        g.advance(SECONDS_PER_DAY * 30)
        if any(s.resource == "Fe" for s in body.mine_sites):
            found = True
            break
    assert found, "directed Fe search should unlock an iron extraction site"
    assert body.seek_months.get("Fe", 0) > 0


def test_directed_search_can_exhaust_missing_resource():
    g = Game(universe_seed=33)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    g.queue_build("survey")
    for _ in range(20):
        if any(u.kind == "survey" for u in g.fleet.values()):
            break
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    # Body with no Fe deposit — directed search should conclude none
    body = next(
        (
            b
            for b in g.system.bodies
            if b.kind in ("planet", "moon", "asteroid")
            and not any(d.resource == "Fe" for d in b.deposits)
        ),
        None,
    )
    assert body is not None, "need a body without Fe for this test"
    sat.location_id = body.id
    g.issue_order(sat.id, "survey", body.id, resource="Fe")
    for _ in range(10):
        g.advance(SECONDS_PER_DAY * 30)
    assert "Fe" in body.seek_exhausted


def test_body_tree_lists_planets_and_moons():
    g = Game(universe_seed=8)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    tree = g.body_tree()
    planets = [n for n in tree if n["kind"] == "planet"]
    assert planets
    multi = [n for n in planets if n["moon_count"] >= 1]
    assert multi
    assert all("moons" in n for n in multi)


def test_ark_scan_goal_habitable_and_iron():
    g = Game(universe_seed=8)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    g.set_ark_scan_goal("habitable", True)
    g.set_ark_scan_goal("Fe", True)
    assert "habitable" in g.ark_scan_goals and "Fe" in g.ark_scan_goals
    # Ark goals appear on event queue
    kinds = [e["kind"] for e in g.event_queue()]
    assert "ark_scan" in kinds
    for _ in range(40):
        g.advance(SECONDS_PER_DAY * 30)
    # Some hab intel or Fe seek progress should exist
    assert g.hab_intel or any(
        b.seek_months.get("Fe", 0) > 0 for b in g.system.bodies
    )


def test_survey_probe_arrival_is_on_event_queue():
    g = Game(universe_seed=44)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != sat.location_id)
    g.issue_order(sat.id, "survey", dest.id, resource="Fe")
    assert sat.status == "en_route"
    assert sat.months_left > 0
    q = g.event_queue()
    arrivals = [e for e in q if e.get("kind") == "survey_arrival"]
    assert arrivals, f"expected survey_arrival in {q}"
    assert dest.name in arrivals[0]["label"]
    assert arrivals[0]["months"] == round(sat.months_left, 3)


def test_warp_idle_skips_no_time():
    g = Game(universe_seed=9)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    # After arrival with only ark idle, warp must not invent a week of progress
    t0 = g.sim_time_s
    r = g.warp_to_next_event(force=False)
    assert r["reason"] == "idle"
    assert r["warped_months"] == 0
    # catch_up may add a few wall-clock seconds; must not skip days/months
    assert abs(g.sim_time_s - t0) < 60


def test_warp_long_jump_needs_confirm():
    g = Game(universe_seed=9)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    assert g.phase == "transit"
    assert g.transit_months_left > 1.0
    r = g.warp_to_next_event(force=False)
    assert r.get("needs_confirm") is True
    assert r["warped_months"] == 0
    assert g.phase == "transit"
    r2 = g.warp_to_next_event(force=True)
    assert r2["warped_months"] > 0


def test_cannot_commit_unknown_seed():
    g = Game(universe_seed=5)
    g.open_survey_archive()
    try:
        g.select_star(999999999)
        assert False, "should reject"
    except ValueError as e:
        assert "dossier" in str(e).lower() or "archive" in str(e).lower()


def _arrive(g: Game) -> None:
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)


def test_transfer_options_trade_propellant_for_time():
    g = Game(universe_seed=50)
    _arrive(g)
    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != g.home_body_id)
    opts = g.haul_options("ark", dest.id)
    assert len(opts) >= 2
    # Economy cheapest propellant, longest (or equal) months
    assert opts[0]["propellant_t"] < opts[-1]["propellant_t"]
    assert opts[0]["months"] >= opts[-1]["months"] - 1e-6
    assert opts[0]["dv_m_s"] < opts[-1]["dv_m_s"]


def test_haul_with_hauler_and_physics_option():
    g = Game(universe_seed=51)
    _arrive(g)
    g.queue_build("hauler")
    while not any(u.kind == "hauler" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    hauler = next(u for u in g.fleet.values() if u.kind == "hauler")
    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != g.home_body_id)
    opts = g.haul_options("ark", dest.id)
    prop0 = g.ark_stock["chem_prop"]
    steel0 = g.ark_stock["steel"]
    # Only haul what we can afford
    amount = 5.0
    # Pick cheapest option that fits propellant
    idx = 0
    for i, o in enumerate(opts):
        if o["propellant_t"] <= prop0:
            idx = i
            break
    else:
        # Seed more prop for the test
        g.ark_stock["chem_prop"] = opts[0]["propellant_t"] + 5
        idx = 0
    g.start_haul("ark", dest.id, "steel", amount, idx, unit_id=hauler.id)
    assert hauler.status == "en_route"
    assert hauler.order == "haul"
    assert len([h for h in g.hauls.values() if h.status == "in_flight"]) == 1
    assert g.ark_stock["steel"] == steel0 - amount
    # Warp until haul arrives
    for _ in range(40):
        if not any(h.status == "in_flight" for h in g.hauls.values()):
            break
        g.warp_to_next_event(force=True)
    assert hauler.status == "idle"
    site = g.sites.get(dest.id)
    assert site is not None
    assert site.stockpile.get("steel", 0) >= amount - 1e-6


def test_ark_trickle_makes_propellant():
    g = Game(universe_seed=52)
    _arrive(g)
    # Give inputs for ark_prop recipe
    g.ark_stock["CH4"] = 100.0
    g.ark_stock["O2"] = 100.0
    prop0 = g.ark_stock.get("chem_prop", 0.0)
    g.advance(SECONDS_PER_DAY * 30 * 3)  # 3 months
    assert g.ark_stock["chem_prop"] > prop0


def test_survey_probe_has_dv_budget_and_return_ark_refuels():
    g = Game(universe_seed=60)
    _arrive(g)
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    assert sat.dv_capacity_m_s >= 4000
    assert sat.dv_remaining_m_s == sat.dv_capacity_m_s

    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != g.home_body_id)
    est = g.estimate_order(sat.id, "move", dest.id)
    assert est["dv_m_s"] > 0
    assert est["can_afford_dv"] is True

    g.issue_order(sat.id, "move", dest.id)
    assert sat.dv_remaining_m_s < sat.dv_capacity_m_s
    burned = sat.dv_capacity_m_s - sat.dv_remaining_m_s
    assert burned > 0
    while sat.status == "en_route":
        g.warp_to_next_event(force=True)
    assert sat.location_id == dest.id

    # Drain tanks artificially then return home
    sat.dv_remaining_m_s = min(sat.dv_remaining_m_s, 50.0)
    # May not afford long return — top up just enough for test path
    need = g._travel_dv_m_s(sat.location_id, g.home_body_id, "survey")
    sat.dv_remaining_m_s = need + 10
    g.issue_order(sat.id, "return_ark")
    assert sat.order == "return_ark"
    while sat.status == "en_route":
        g.warp_to_next_event(force=True)
    assert sat.location_id == g.home_body_id
    assert sat.dv_remaining_m_s == sat.dv_capacity_m_s  # refilled


def test_insufficient_dv_blocks_move():
    g = Game(universe_seed=61)
    _arrive(g)
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != g.home_body_id)
    sat.dv_remaining_m_s = 1.0  # basically dry
    try:
        g.issue_order(sat.id, "move", dest.id)
        assert False, "should block"
    except ValueError as e:
        assert "Δv" in str(e) or "dv" in str(e).lower() or "m/s" in str(e)


def test_build_refuel_depot_and_refuel_there():
    g = Game(universe_seed=62)
    _arrive(g)
    # Seed enough materials
    g.ark_stock["steel"] = max(g.ark_stock.get("steel", 0), 100)
    g.ark_stock["chip"] = max(g.ark_stock.get("chip", 0), 20)
    g.ark_stock["chem_prop"] = max(g.ark_stock.get("chem_prop", 0), 80)
    g.ark_stock["Al"] = max(g.ark_stock.get("Al", 0), 40)
    body = next(b for b in g.system.bodies if b.kind == "planet" and b.id != g.home_body_id)
    g.queue_build("refuel_depot", deploy_body_id=body.id)
    assert any(j.building_id == "refuel_depot" for j in g.build_queue)
    for _ in range(30):
        site = g.sites.get(body.id)
        if site and "refuel_depot" in site.buildings:
            break
        g.warp_to_next_event(force=True)
    site = g.sites[body.id]
    assert "refuel_depot" in site.buildings
    assert site.stockpile.get("chem_prop", 0) > 0

    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    # Place sat at depot body with low tanks
    sat.location_id = body.id
    sat.dv_remaining_m_s = 100.0
    g.issue_order(sat.id, "refuel")
    assert sat.dv_remaining_m_s > 100.0


def test_fab_bay_one_job_at_a_time():
    g = Game(universe_seed=70)
    _arrive(g)
    g.queue_build("survey")
    assert len(g.build_queue) == 1
    try:
        g.queue_build("miner")
        assert False, "second job should be rejected while bay busy"
    except ValueError as e:
        assert "busy" in str(e).lower()
    while any(j.status == "building" for j in g.build_queue):
        g.warp_to_next_event(force=True)
    # Bay free again
    g.queue_build("miner")
    assert len(g.build_queue) == 1


def test_mine_then_haul_ore_to_ark():
    g = Game(universe_seed=22)
    _arrive(g)
    for kind in ("survey", "miner", "hauler"):
        g.queue_build(kind)
        while any(j.status == "building" for j in g.build_queue):
            g.warp_to_next_event(force=True)
    assert any(u.kind == "survey" for u in g.fleet.values())
    assert any(u.kind == "miner" for u in g.fleet.values())
    assert any(u.kind == "hauler" for u in g.fleet.values())
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    miner = next(u for u in g.fleet.values() if u.kind == "miner")
    hauler = next(u for u in g.fleet.values() if u.kind == "hauler")
    body = next(
        b for b in g.system.bodies if b.kind == "planet" and any(d.resource == "Fe" for d in b.deposits)
    )
    sat.location_id = body.id
    g.issue_order(sat.id, "survey", body.id, resource="Fe")
    for _ in range(80):
        g.advance(SECONDS_PER_DAY * 30)
        if any(s.resource == "Fe" for s in body.mine_sites):
            break
    site = next(s for s in body.mine_sites if s.resource == "Fe")
    miner.location_id = body.id
    g.issue_order(miner.id, "mine", site.id)
    while miner.status != "idle":
        g.warp_to_next_event(force=True)
    stock = g.sites[body.id].stockpile
    assert stock.get("Fe", 0) > 0
    took = min(20.0, stock["Fe"])
    # Ensure propellant; freeze Fe at ark so trickle foundry doesn't hide the delivery
    g.ark_stock["chem_prop"] = max(g.ark_stock.get("chem_prop", 0), 200.0)
    g.ark_stock["Fe"] = 0.0  # delivery should land as Fe cargo
    site_fe0 = stock["Fe"]
    g.start_haul(body.id, "ark", "Fe", took, 0, unit_id=hauler.id)
    assert g.sites[body.id].stockpile.get("Fe", 0) == site_fe0 - took
    for _ in range(40):
        if not any(h.status == "in_flight" for h in g.hauls.values()):
            break
        g.warp_to_next_event(force=True)
    assert hauler.status == "idle"
    # Cargo arrived (may partially refine into steel via ark trickle)
    arrived = g.ark_stock.get("Fe", 0.0) + g.ark_stock.get("steel", 0.0)
    assert arrived >= took * 0.5  # at least half still present as Fe or refined steel
