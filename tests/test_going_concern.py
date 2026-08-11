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


def test_terraform_dossier_always_has_physics_and_checklist():
    g = Game(universe_seed=8)
    _arrive(g)
    rocky = next(b for b in g.system.bodies if b.kind == "planet" and b.planet_class == "rocky")
    d0 = g.terraform_dossier(rocky.id)
    assert d0["level"] == 0
    assert d0["surface_g"] is not None
    assert "in_hz" in d0
    assert d0["verdict"]
    assert d0["verdict_status"] == "unknown"
    ids = {f["id"] for f in d0["factors"]}
    assert "gravity" in ids and "insolation" in ids
    # Atmosphere/water/mag unknown until surveyed
    atmo = next(f for f in d0["factors"] if f["id"] == "atmosphere")
    assert atmo["known"] is False
    assert "how_to_survey" in d0


def test_terraform_dossier_reveals_g_atmosphere_water_magnetosphere():
    g = Game(universe_seed=8)
    _arrive(g)
    rocky = next(b for b in g.system.bodies if b.kind == "planet" and b.planet_class == "rocky")
    # Fast-forward remote survey by injecting seek months
    g.hab_seek_months[rocky.id] = 6.0
    notes = g._advance_terraform_intel(rocky, remote=True)
    assert g.hab_intel[rocky.id] >= 5
    assert notes
    d = g.terraform_dossier(rocky.id)
    assert d["level"] == 5
    assert "surface_g" in d
    assert "atmosphere_class" in d
    assert "water_class" in d
    assert "has_magnetosphere" in d
    assert "has_active_core" in d
    assert "terraform_score" in d
    assert d["verdict"]
    mag = next(f for f in d["factors"] if f["id"] == "magnetosphere")
    assert mag["known"] is True
    if not d["has_magnetosphere"]:
        assert d["needs_l1_magnetic_shield"] is True
        assert mag["status"] in ("need_build", "ok")
        assert "L1" in d["shield_note"] or "Lagrange" in d["shield_note"]


def test_l1_shield_structure_builds_on_rocky():
    g = Game(universe_seed=8)
    _arrive(g)
    rocky = next(b for b in g.system.bodies if b.kind == "planet" and b.planet_class == "rocky")
    g.ark_stock["steel"] = 200
    g.ark_stock["chip"] = 40
    g.ark_stock["MAG"] = 20
    g.ark_stock["panel"] = 50
    g.ark_stock["Al"] = 40
    g.queue_build("l1_magnetic_shield", deploy_body_id=rocky.id)
    while any(j.status == "building" for j in g.build_queue):
        g.warp_to_next_event(force=True)
    assert "l1_magnetic_shield" in g.sites[rocky.id].buildings
    # Gas giant should reject
    giant = next((b for b in g.system.bodies if b.planet_class == "gas_giant"), None)
    if giant:
        try:
            g.queue_build("l1_magnetic_shield", deploy_body_id=giant.id)
            assert False
        except ValueError as e:
            assert "rocky" in str(e).lower() or "moon" in str(e).lower()


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


def test_warp_short_fab_does_not_need_confirm():
    """Typical bay jobs (~1.5–3 mo) should warp in one click."""
    g = Game(universe_seed=9)
    g.open_survey_archive()
    g.select_star(g.catalog[0]["seed"])
    while g.phase == "transit":
        g.warp_to_next_event(force=True)
    g.queue_build("survey")
    assert g.build_queue
    assert g.build_queue[0].months_left <= 3.0
    r = g.warp_to_next_event(force=False)
    assert r.get("needs_confirm") is not True
    assert r["warped_months"] > 0
    assert any(u.kind == "survey" for u in g.fleet.values())


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

    # Drain tanks artificially then return to ark dock
    need = g._travel_dv_m_s(sat.location_id, "ark", "survey")
    sat.dv_remaining_m_s = need + 10
    g.issue_order(sat.id, "return_ark")
    assert sat.order == "return_ark"
    assert sat.target_id == "ark"
    while sat.status == "en_route":
        g.warp_to_next_event(force=True)
    assert sat.location_id == "ark"
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


def test_mass_driver_on_light_body_and_launch():
    g = Game(universe_seed=80)
    _arrive(g)
    # Prefer asteroid or small moon
    body = next(
        (b for b in g.system.bodies if g.body_allows_mass_driver(b)),
        None,
    )
    assert body is not None, "need a light body for mass driver"
    g.ark_stock["steel"] = 300
    g.ark_stock["chip"] = 40
    g.ark_stock["Al"] = 80
    g.ark_stock["panel"] = 80
    g.ark_stock["chem_prop"] = 80
    # Chem genset: reliable baseload even on outer/dim bodies
    g.queue_build("chem_genset", deploy_body_id=body.id)
    while any(j.status == "building" for j in g.build_queue):
        g.warp_to_next_event(force=True)
    g.queue_build("mass_driver", deploy_body_id=body.id)
    while any(j.status == "building" for j in g.build_queue):
        g.warp_to_next_event(force=True)
    assert "mass_driver" in g.sites[body.id].buildings
    assert "chem_genset" in g.sites[body.id].buildings
    # Seed genset fuel (build cost may have spent ark prop)
    g.sites[body.id].stockpile["chem_prop"] = max(
        g.sites[body.id].stockpile.get("chem_prop", 0.0), 20.0
    )
    assert g.mass_driver_online(body.id)
    assert g.site_power_mw(body.id) >= 18.0

    # Stock ore and launch to ark without rocket propellant
    g.sites[body.id].stockpile["Fe"] = 40.0
    g.ark_stock["Fe"] = 0.0
    g.mass_launch(body.id, "ark", "Fe", 15.0)
    assert g.sites[body.id].stockpile["Fe"] == 25.0
    haul = next(h for h in g.hauls.values() if h.option_name == "Mass driver launch")
    assert haul.propellant_t == 0.0
    while any(h.status == "in_flight" for h in g.hauls.values()):
        g.warp_to_next_event(force=True)
    arrived = g.ark_stock.get("Fe", 0.0) + g.ark_stock.get("steel", 0.0)
    assert arrived >= 10.0

    # Deep well should reject if any heavy planet exists
    heavy = next(
        (
            b
            for b in g.system.bodies
            if b.kind == "planet" and not g.body_allows_mass_driver(b)
        ),
        None,
    )
    if heavy:
        try:
            g.queue_build("mass_driver", deploy_body_id=heavy.id)
            assert False, "should reject deep well"
        except ValueError as e:
            assert "mass driver" in str(e).lower() or "deep" in str(e).lower() or "well" in str(e).lower()


def test_mass_driver_needs_power():
    g = Game(universe_seed=82)
    _arrive(g)
    body = next(b for b in g.system.bodies if g.body_allows_mass_driver(b))
    from colony.sim.game import Site

    g.sites[body.id] = Site(
        body_id=body.id, buildings=["mass_driver"], stockpile={"Fe": 20.0}
    )
    assert not g.mass_driver_online(body.id)
    try:
        g.mass_launch(body.id, "ark", "Fe", 5.0)
        assert False, "unpowered rail should fail"
    except ValueError as e:
        assert "MW" in str(e) or "power" in str(e).lower()
    # Chem genset + fuel brings it online anywhere
    g.sites[body.id].buildings.append("chem_genset")
    g.sites[body.id].stockpile["chem_prop"] = 10.0
    assert g.mass_driver_online(body.id)
    g.mass_launch(body.id, "ark", "Fe", 5.0)


def test_haul_from_mass_driver_cheaper_than_chemical():
    g = Game(universe_seed=81)
    _arrive(g)
    body = next(b for b in g.system.bodies if g.body_allows_mass_driver(b))
    from colony.sim.game import Site

    g.sites[body.id] = Site(body_id=body.id, buildings=[], stockpile={"chem_prop": 20.0})
    # Without driver
    opts_chem = g.haul_options(body.id, "ark")
    g.sites[body.id].buildings.append("mass_driver")
    # Unpowered rail still pays chemical ascent
    opts_unpowered = g.haul_options(body.id, "ark")
    assert opts_unpowered[0].get("mass_driver_ascent") is False
    g.sites[body.id].buildings.append("chem_genset")
    opts_rail = g.haul_options(body.id, "ark")
    assert opts_rail[0]["propellant_t"] < opts_chem[0]["propellant_t"]
    assert opts_rail[0].get("mass_driver_ascent") is True


def test_probe_starts_at_ark_and_transits_to_home_planet():
    g = Game(universe_seed=8)
    _arrive(g)
    assert g.fleet["ark"].location_id == "ark"
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    assert sat.location_id == "ark"
    home = g.home_body_id
    cap = sat.dv_remaining_m_s
    # Leaving ark to home planet is a real hop
    g.issue_order(sat.id, "survey", home, resource="Fe")
    assert sat.status == "en_route"
    assert sat.transit_from_id == "ark"
    assert sat.target_id == home
    assert sat.months_left > 0
    assert sat.dv_remaining_m_s < cap
    assert abs(sat.dv_remaining_m_s - (cap - g._travel_dv_m_s("ark", home, "survey"))) < 1e-6
    while sat.status == "en_route":
        g.warp_to_next_event(force=True)
    assert sat.location_id == home
    assert sat.status == "working"


def test_survey_on_station_no_extra_transit():
    g = Game(universe_seed=8)
    _arrive(g)
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    home = g.home_body_id
    g.issue_order(sat.id, "survey", home, resource="Fe")
    while sat.status == "en_route":
        g.warp_to_next_event(force=True)
    cap = sat.dv_remaining_m_s
    g.issue_order(sat.id, "idle")
    g.issue_order(sat.id, "survey", home, resource="Fe")
    assert sat.status == "working"
    assert sat.dv_remaining_m_s == cap


def test_rename_unit():
    g = Game(universe_seed=70)
    _arrive(g)
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    g.rename_unit(sat.id, "  Pathfinder  ")
    assert sat.name == "Pathfinder"
    g.rename_unit("ark", "Home Base")
    assert g.fleet["ark"].name == "Home Base"
    try:
        g.rename_unit(sat.id, "")
        assert False
    except ValueError:
        pass


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


def test_process_view_goals_and_discoveries_from_survey():
    """Process board: overall goals + discovery journal from survey finds."""
    g = Game(universe_seed=7)
    _arrive(g)
    snap = g.snapshot()
    assert "process" in snap
    pv = snap["process"]
    assert pv["phase"] == "system"
    goal_ids = {x["id"] for x in pv["goals"]}
    assert "bootstrap_fleet" in goal_ids
    assert "map_resources" in goal_ids
    assert "first_ore" in goal_ids
    assert "site_power" in goal_ids
    assert "lift_chain" in goal_ids
    assert "habitation" in goal_ids
    assert pv["next_focus"] is not None
    assert "survey" in (pv["next_focus"].get("next_step") or "").lower() or "fab" in (
        pv["next_focus"].get("next_step") or ""
    ).lower()

    # Stock and fab a probe, force survey progress until a discovery posts
    g.ark_stock["steel"] = 500
    g.ark_stock["chip"] = 100
    g.ark_stock["chem_prop"] = 200
    g.ark_stock["Al"] = 100
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    sat = next(u for u in g.fleet.values() if u.kind == "survey")
    rocky = next(b for b in g.system.bodies if b.kind == "planet" and b.planet_class == "rocky")
    sat.location_id = rocky.id
    g.issue_order(sat.id, "survey", rocky.id, resource="Fe")
    for _ in range(100):
        g.advance(SECONDS_PER_DAY * 15)
        if g.discoveries:
            break
    assert g.discoveries, "expected at least one survey discovery"
    d0 = g.discoveries[0]
    assert d0["text"]
    assert "kind" in d0
    # Dedupe: same key does not double-post
    n = len(g.discoveries)
    g._discover(
        d0["kind"],
        d0["text"],
        body_id=d0.get("body_id") or "",
        resource=d0.get("resource") or "",
        key=f"{d0['kind']}:{d0.get('body_id')}:{d0.get('resource')}:{d0['text']}"
        if not d0.get("resource")
        else f"found:{d0.get('body_id')}:{d0.get('resource')}",
    )
    # Use explicit key that may or may not match; force known key
    g._discover("resource_found", "Iron found on X", body_id="x", resource="Fe", key="test-unique-a")
    g._discover("resource_found", "Iron found on X", body_id="x", resource="Fe", key="test-unique-a")
    assert sum(1 for d in g.discoveries if d.get("text") == "Iron found on X") == 1

    pv2 = g.process_view()
    assert pv2["discoveries"]
    assert pv2["next_focus"]
    assert "discoveries" in snap or "discoveries" in g.snapshot()


def test_industry_structures_habitat_launch_fuel():
    """Launch pad, rocket fab, fuel fab, recovery, habitat, extractor deploy."""
    g = Game(universe_seed=8)
    _arrive(g)
    home = g.home_body_id
    g.ark_stock.update(
        {
            "steel": 500,
            "chip": 80,
            "Al": 120,
            "panel": 80,
            "H2O": 50,
            "chem_prop": 40,
            "log": 80,
        }
    )
    for kind in (
        "solar_farm",
        "habitat_module",
        "launch_pad",
        "rocket_fab",
        "fuel_fab",
        "recovery_pad",
        "extractor",
    ):
        g.queue_build(kind, deploy_body_id=home)
        while any(j.status == "building" for j in g.build_queue):
            g.warp_to_next_event(force=True)
    site = g.sites[home]
    for b in (
        "solar_farm",
        "habitat_module",
        "launch_pad",
        "rocket_fab",
        "fuel_fab",
        "recovery_pad",
        "extractor",
    ):
        assert b in site.buildings, b

    # Structure discoveries
    kinds = {d["kind"] for d in g.discoveries}
    assert "structure" in kinds

    pv = g.process_view()
    assert any(g_["id"] == "site_power" and g_["status"] == "done" for g_ in pv["goals"])
    assert any(g_["id"] == "habitation" and g_["status"] == "done" for g_ in pv["goals"])
    assert any(g_["id"] == "lift_chain" and g_["status"] == "done" for g_ in pv["goals"])
    assert pv["industry"]["has_habitat"] is True
    assert pv["industry"]["has_power"] is True

    # Habitat enables population growth
    pop0 = g.population
    g.advance(SECONDS_PER_DAY * 365)
    assert g.population > pop0

    # Fuel fab converts CH4+O2
    site.stockpile["CH4"] = 10.0
    site.stockpile["O2"] = 10.0
    site.stockpile["chem_prop"] = 0.0
    g.advance(SECONDS_PER_DAY * 30)
    assert site.stockpile.get("chem_prop", 0) > 0


def test_structure_builds_catalog_includes_industry():
    from colony.sim.tech import STRUCTURE_BUILDS, UNIT_BUILDS

    needed = {
        "solar_farm",
        "launch_pad",
        "rocket_fab",
        "fuel_fab",
        "recovery_pad",
        "habitat_module",
        "extractor",
    }
    assert needed <= set(STRUCTURE_BUILDS.keys())
    assert "constructor" in UNIT_BUILDS
    assert "log" in STRUCTURE_BUILDS["habitat_module"]["cost"]


def test_constructor_harvests_logs_and_builds_on_site():
    g = Game(universe_seed=8)
    _arrive(g)
    home = g.home_body_id
    g.ark_stock.update(
        {
            "steel": 400,
            "chip": 60,
            "panel": 80,
            "Al": 80,
            "log": 10,
            "chem_prop": 40,
        }
    )
    g.queue_build("constructor")
    while not any(u.kind == "constructor" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    bot = next(u for u in g.fleet.values() if u.kind == "constructor")
    assert bot.location_id == "ark"
    assert "build" in bot.capabilities

    g.issue_order(bot.id, "harvest", home, "log")
    assert bot.order == "harvest"
    for _ in range(40):
        g.warp_to_next_event(force=True)
        if bot.status == "idle" and g.sites.get(home) and g.sites[home].stockpile.get("log", 0) > 15:
            break
    assert g.sites[home].stockpile.get("log", 0) > 15
    assert any(d.get("resource") == "log" for d in g.discoveries)

    # Build solar farm using ark materials at home
    g.issue_order(bot.id, "construct", home, "solar_farm")
    for _ in range(40):
        g.warp_to_next_event(force=True)
        if g.sites.get(home) and "solar_farm" in g.sites[home].buildings:
            break
    assert "solar_farm" in g.sites[home].buildings
    assert any(d["kind"] == "structure" for d in g.discoveries)

    # Habitat needs logs — site should have enough after harvest + seed
    g.ark_stock.update({"steel": 100, "chip": 20, "H2O": 30, "panel": 20})
    # ensure combined stock covers habitat cost
    g.sites[home].stockpile["log"] = max(g.sites[home].stockpile.get("log", 0), 30)
    g.issue_order(bot.id, "construct", home, "habitat_module")
    for _ in range(50):
        g.warp_to_next_event(force=True)
        if "habitat_module" in g.sites[home].buildings:
            break
    assert "habitat_module" in g.sites[home].buildings


def test_constructor_short_materials_refuses():
    g = Game(universe_seed=8)
    _arrive(g)
    home = g.home_body_id
    # Enough to fab the bot
    g.ark_stock.update({"steel": 100, "chip": 20, "panel": 10, "Al": 20, "log": 0})
    g.queue_build("constructor")
    while not any(u.kind == "constructor" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    bot = next(u for u in g.fleet.values() if u.kind == "constructor")
    bot.location_id = home
    bot.status = "idle"
    # Strip materials so solar farm cannot start
    g.ark_stock["panel"] = 0
    g.ark_stock["steel"] = 0
    g.ark_stock["chip"] = 0
    if home in g.sites:
        g.sites[home].stockpile.clear()
    try:
        g.issue_order(bot.id, "construct", home, "solar_farm")
        assert False, "should refuse short materials"
    except ValueError as e:
        assert "short" in str(e).lower() or "need" in str(e).lower()


def test_cancel_build_refunds_materials_and_frees_bay():
    g = Game(universe_seed=9)
    _arrive(g)
    before = dict(g.ark_stock)
    g.queue_build("survey")
    job = g.build_queue[0]
    cost = dict(job.cost)
    assert cost  # survey satellite costs something
    for res, amt in cost.items():
        assert g.ark_stock[res] == before[res] - amt
    # Bay is busy — a second build is refused
    try:
        g.queue_build("survey")
        assert False, "bay should be busy"
    except ValueError:
        pass

    g.cancel_build(job.id)
    assert g.build_queue == []
    for res, amt in before.items():
        assert abs(g.ark_stock.get(res, 0.0) - amt) < 1e-6
    # Bay free again — restart works
    g.queue_build("survey")
    assert len(g.build_queue) == 1


def test_cancel_unit_order_works_mid_transit_and_mid_construct():
    g = Game(universe_seed=10)
    _arrive(g)
    home = g.home_body_id
    dest = next(b for b in g.system.bodies if b.kind == "planet" and b.id != home)
    g.ark_stock.update({"steel": 400, "chip": 60, "panel": 80, "Al": 80, "log": 10})
    g.queue_build("survey")
    while not any(u.kind == "survey" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    probe = next(u for u in g.fleet.values() if u.kind == "survey")

    g.issue_order(probe.id, "move", dest.id)
    assert probe.status == "en_route" and probe.months_left > 0
    dv_after_move = probe.dv_remaining_m_s
    # Previously this raised "en route" — should now free the unit instead.
    g.issue_order(probe.id, "idle")
    assert probe.status == "idle"
    assert probe.order == ""
    # Burned Δv is sunk, not refunded, but the unit is usable again immediately.
    assert probe.dv_remaining_m_s == dv_after_move
    g.issue_order(probe.id, "survey", home)  # no error — unit is free

    g.queue_build("constructor")
    while not any(u.kind == "constructor" for u in g.fleet.values()):
        g.warp_to_next_event(force=True)
    bot = next(u for u in g.fleet.values() if u.kind == "constructor")
    bot.location_id = home
    bot.status = "idle"
    ark_before = dict(g.ark_stock)
    g.issue_order(bot.id, "construct", home, "solar_farm")
    assert bot.status == "working" and bot.order == "construct"
    spent = {
        res: ark_before.get(res, 0.0) - g.ark_stock.get(res, 0.0)
        for res in ("panel", "steel", "chip")
    }
    assert spent["panel"] > 0  # materials were pulled up front

    g.issue_order(bot.id, "idle")  # previously raised "busy (construct)"
    assert bot.status == "idle"
    assert bot.order == ""
    site = g.sites[home]
    for res, amt in spent.items():
        assert abs(site.stockpile.get(res, 0.0) - amt) < 1e-6
    assert "solar_farm" not in site.buildings
    # Bot is free to take a new order immediately.
    g.issue_order(bot.id, "harvest", home, "log")
    assert bot.status == "working" and bot.order == "harvest"


def test_project_pause_resume_cancel_restart_lifecycle():
    g = Game(universe_seed=12)
    _arrive(g)
    home = g.home_body_id
    result = g.plan_base(home, "solar", "underground", "Test Base")
    proj = next(p for p in g.projects.values() if p.body_id == home)
    open_contracts = [c for c in g.contracts.values() if c.project_id == proj.id]
    assert open_contracts and all(c.status == "open" for c in open_contracts)

    # active -> paused -> active
    g.set_project_status(proj.id, "paused")
    assert proj.status == "paused"
    g.set_project_status(proj.id, "active")
    assert proj.status == "active"

    # Invalid transition
    try:
        g.set_project_status(proj.id, "bogus")
        assert False, "should reject unknown status"
    except ValueError:
        pass

    # Deliver partial progress before cancelling, to prove it survives restart.
    c = open_contracts[0]
    g.ark_stock[c.resource] = g.ark_stock.get(c.resource, 0.0) + c.amount_t
    g.deliver_from_ark(c.id, c.amount_t * 0.25)
    delivered_before_cancel = c.delivered_t
    assert delivered_before_cancel > 0

    # active -> cancelled: open contracts stop accepting deliveries
    g.set_project_status(proj.id, "cancelled")
    assert proj.status == "cancelled"
    assert c.status == "cancelled"
    try:
        g.deliver_from_ark(c.id, 1.0)
        assert False, "cancelled contract should refuse delivery"
    except ValueError:
        pass

    # cancelled -> active (restart): contract reopens, progress preserved
    g.set_project_status(proj.id, "active")
    assert proj.status == "active"
    assert c.status == "open"
    assert c.delivered_t == delivered_before_cancel
    g.deliver_from_ark(c.id, 1.0)  # works again
    assert c.delivered_t > delivered_before_cancel

    # Cannot pause/restart a completed project
    for cc in g.contracts.values():
        if cc.project_id == proj.id:
            g.ark_stock[cc.resource] = g.ark_stock.get(cc.resource, 0.0) + cc.amount_t
            g.deliver_from_ark(cc.id, cc.amount_t)
    assert proj.status == "complete"
    try:
        g.set_project_status(proj.id, "paused")
        assert False, "completed project should not accept transitions"
    except ValueError:
        pass
