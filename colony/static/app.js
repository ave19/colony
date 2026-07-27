/* Colony UI — map-dominant Three.js view + floating panels */
import { SystemMap3D } from "/static/map3d.js";

let state = null;
let selectedUnitId = null;
let selectedBodyId = null;
let selectedDossierSeed = null;
let map = null;

const $ = (id) => document.getElementById(id);

/** 4.2×10⁶ t — not 16 digits of false precision */
function formatTons(x) {
  if (x == null || x === "") return null;
  if (typeof x === "string" && x.includes("10")) return x; // already formatted
  const n = Number(x);
  if (!Number.isFinite(n) || n === 0) return "0 t";
  const ax = Math.abs(n);
  let exp = Math.floor(Math.log10(ax));
  let mant = ax / Math.pow(10, exp);
  mant = Math.round(mant * 10) / 10;
  if (mant >= 10) {
    mant = 1.0;
    exp += 1;
  }
  const sign = n < 0 ? "-" : "";
  return `${sign}${mant.toFixed(1)}×10${expToSuperscript(exp)} t`;
}

function expToSuperscript(exp) {
  const map = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻",
  };
  return String(exp)
    .split("")
    .map((c) => map[c] || c)
    .join("");
}

function tonsLabel(d) {
  if (d && d.amount_display) return d.amount_display.replace("10^", "10").replace(/10\^(-?\d+)/, (_, e) => "10" + expToSuperscript(e));
  if (d && d.amount_t != null) return formatTons(d.amount_t);
  return null;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function bodyById(id) {
  return (state?.system?.bodies || []).find((b) => b.id === id);
}
function unitById(id) {
  return (state?.fleet || []).find((u) => u.id === id);
}

function initMap() {
  const canvas = $("map3d");
  if (!canvas) throw new Error("map canvas missing");
  map = new SystemMap3D(canvas);
  map.onSelect = (id) => {
    selectedBodyId = id;
    $("panel-right").classList.remove("collapsed");
    renderBodyPanel();
    renderOrders();
    renderBuild();
  };
}

function renderSafe() {
  try {
    render();
  } catch (e) {
    console.error(e);
    $("toast").textContent = "UI error: " + (e && e.message ? e.message : e);
  }
}

async function refresh() {
  state = await api("/api/state");
  renderSafe();
}

function render() {
  if (!state) return;
  $("phase").textContent = state.phase;
  $("pop").textContent = `${(state.population || 0).toLocaleString()} souls`;
  if (state.phase === "transit") {
    $("clock").textContent = `${(state.transit_months_left / 12).toFixed(1)} y transit`;
  } else {
    $("clock").textContent = `${state.sim_years.toFixed(2)} y`;
  }
  $("toast").textContent = state.message || "";
  renderNextEvent();

  $("panel-menu").hidden = state.phase !== "menu";
  $("panel-transit").hidden = state.phase !== "transit";
  $("panel-system").hidden = state.phase !== "system";
  $("right-menu").hidden = state.phase === "system";
  $("right-system").hidden = state.phase !== "system";

  if (state.phase === "menu") {
    $("panel-left").classList.remove("collapsed");
  }

  if (state.phase === "transit") {
    $("transit-msg").textContent =
      `Coasting ${(state.transit_months_left / 12).toFixed(1)} years.`;
  }

  // 3D map (optional if WebGL/init failed)
  if (map) {
    const simSec = (state.sim_months || 0) * 30 * 86400; // game month = 30 days
    if (state.phase === "system" && state.system) {
      if (!map.systemData || map.systemData.seed !== state.system.seed) {
        map.setSystem(state.system, simSec);
        map.focusSystem();
      } else {
        map.updatePositions(state.system, simSec);
      }
      if (selectedBodyId) map.setSelected(selectedBodyId);
      $("map-hint").textContent =
        "Drag orbit · Scroll zoom · Click select · Double-click focus (tracks target) · moons no longer jump";
    } else if (state.phase !== "system") {
      map.clearSystem();
      $("map-hint").textContent =
        state.phase === "menu"
          ? "Open survey archive (left ☰) — map fills once you arrive in-system"
          : "In transit — warp to arrival to enter the system map";
    }
  }

  renderCatalog();
  renderDossierDetail();
  renderFleet();
  renderArkBay();
  renderUnitPanel();
  renderBodyPanel();
  renderOrders();
  renderBuild();
  renderProjects();
  renderContracts();
  renderStock();
  renderEvents();
}

function isArkSelected() {
  const u = unitById(selectedUnitId);
  return u && u.kind === "ark";
}

/** Ark fabrication bay: queue + authorize — only when Colony Ark is selected. */
function renderArkBay() {
  const bay = $("ark-bay");
  const el = $("build-units");
  const qel = $("build-queue");
  if (!bay || !el || !qel || state.phase !== "system") return;

  if (!isArkSelected()) {
    bay.hidden = true;
    return;
  }
  bay.hidden = false;

  // Queue first — this is the "it's happening" surface
  const builds = state.builds || [];
  if (!builds.length) {
    qel.innerHTML =
      '<div class="queue-empty">Fabrication bay idle. Authorize a construction job below.</div>';
  } else {
    qel.innerHTML = builds
      .map((j) => {
        const total = j.months_total || 1;
        const left = Math.max(0, j.months_left || 0);
        const done = Math.min(100, ((total - left) / total) * 100);
        return `<div class="queue-job">
          <div class="title">${j.name}</div>
          <div class="meta">In bay · ${left.toFixed(1)} mo remaining of ${total.toFixed(1)} mo · warp to advance</div>
          <div class="queue-bar"><i style="width:${done.toFixed(1)}%"></i></div>
        </div>`;
      })
      .join("");
  }

  const specs = state.unit_builds || {};
  el.innerHTML = Object.values(specs)
    .map((s) => {
      const cost = Object.entries(s.cost || {})
        .map(([k, v]) => `${v} t ${k}`)
        .join(", ");
      return `<div class="card">
        <h3>${s.name}</h3>
        <p>${s.description || ""}</p>
        <p class="muted">${cost} · ${s.months} mo in bay</p>
        <button type="button" class="primary" data-build="${s.id}">Queue on ark</button>
      </div>`;
    })
    .join("");
  el.querySelectorAll("[data-build]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        // Keep ark selected so the queue stays visible
        selectedUnitId = "ark";
        state = await api("/api/build", {
          method: "POST",
          body: JSON.stringify({ unit_kind: btn.dataset.build }),
        });
        $("panel-left").classList.remove("collapsed");
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  });
}

function renderCatalog() {
  const el = $("catalog");
  if (!el) return;
  if (!state.catalog?.length) {
    el.innerHTML = '<p class="empty">No archive open.</p>';
    return;
  }
  // Compact list — full dossier opens on the right
  el.innerHTML = state.catalog
    .map((c) => {
      const title = c.star.name || c.star.designation;
      const spectral = c.star.spectral || "";
      const sel = Number(selectedDossierSeed) === Number(c.seed) ? "selected" : "";
      return `<button type="button" class="fleet-item dossier-row ${sel}" data-seed="${c.seed}">
        <div class="name">${title}</div>
        <div class="meta">${spectral}${c.difficulty != null ? " · difficulty " + c.difficulty : ""}</div>
      </button>`;
    })
    .join("");
  el.querySelectorAll("[data-seed]").forEach((btn) => {
    btn.onclick = () => {
      selectedDossierSeed = Number(btn.dataset.seed);
      $("panel-right").classList.remove("collapsed");
      render();
    };
  });
}

function renderDossierDetail() {
  const el = $("dossier-detail");
  const hint = $("right-menu-hint");
  if (!el) return;
  if (state.phase !== "menu") {
    el.innerHTML = "";
    return;
  }
  const c = (state.catalog || []).find((d) => Number(d.seed) === Number(selectedDossierSeed));
  if (!c) {
    if (hint) {
      hint.hidden = false;
      hint.textContent = state.catalog?.length
        ? "Select a star on the left to open its dossier."
        : "Open the survey archive on the left to begin.";
    }
    el.innerHTML = "";
    return;
  }
  if (hint) hint.hidden = true;
  const title = c.star.designation || c.star.name;
  const g =
    c.gas_giant_period_years != null
      ? `<p><strong>Gas giant period</strong> ~${c.gas_giant_period_years} y</p>`
      : "";
  el.innerHTML = `
    <h2>Dossier</h2>
    <div class="card">
      <h3>${title}</h3>
      <p class="muted">${c.dossier_id || ""} · ${c.status || "on file"}</p>
      <p>${c.survey_summary || ""}</p>
      <p><strong>Planets</strong> ${c.planet_count ?? "—"} · <strong>Moons</strong> ${c.moon_count ?? "—"}</p>
      <p><strong>Outer system</strong> ~${c.outer_au ?? "?"} AU</p>
      ${g}
      <p><strong>Survey completeness</strong> ${c.completeness != null ? Math.round(c.completeness * 100) + "%" : "—"}</p>
      <p class="muted">${c.observed_from || "Remote observation"}</p>
      <button type="button" class="primary" id="btn-commit-dossier" style="width:100%;margin-top:10px">
        Commit transit to ${c.star.name || "this star"}
      </button>
    </div>`;
  const btn = $("btn-commit-dossier");
  if (btn) {
    btn.onclick = async () => {
      state = await api("/api/select_star", {
        method: "POST",
        body: JSON.stringify({ seed: Number(c.seed) }),
      });
      selectedUnitId = null;
      selectedBodyId = null;
      selectedDossierSeed = null;
      render();
    };
  }
}

function renderFleet() {
  const el = $("fleet-list");
  if (!el || state.phase !== "system") return;
  const fleet = state.fleet || [];
  el.innerHTML = fleet
    .map((u) => {
      const loc = bodyById(u.location_id);
      const busy =
        u.status !== "idle"
          ? `<div class="meta busy">${u.status} ${u.order || ""} ${u.months_left ? u.months_left + " mo" : ""}</div>`
          : `<div class="meta">@ ${loc ? loc.name : u.location_id}</div>`;
      return `<button type="button" class="fleet-item ${selectedUnitId === u.id ? "selected" : ""}" data-unit="${u.id}">
        <div class="name">${u.name}</div>
        <div class="meta">${u.kind}</div>${busy}
      </button>`;
    })
    .join("") || '<p class="empty">No fleet</p>';
  el.querySelectorAll("[data-unit]").forEach((btn) => {
    btn.onclick = () => {
      selectedUnitId = btn.dataset.unit;
      $("panel-left").classList.remove("collapsed");
      render();
    };
  });
  // Default to ark on arrival so fabrication bay is discoverable
  if (!selectedUnitId && fleet.some((u) => u.kind === "ark")) {
    selectedUnitId = "ark";
  }
}

function renderUnitPanel() {
  const el = $("unit-panel");
  if (!el || state.phase !== "system") return;
  const u = unitById(selectedUnitId);
  // Ark uses fabrication bay instead of this generic card
  if (!u || u.kind === "ark") {
    el.hidden = !!u && u.kind === "ark";
    if (!u) {
      el.hidden = false;
      el.className = "empty";
      el.textContent = "Select a unit from the fleet list";
    }
    return;
  }
  el.hidden = false;
  const loc = bodyById(u.location_id);
  el.className = "card";
  el.innerHTML = `<h3>${u.name}</h3>
    <p>${u.kind} · ${(u.capabilities || []).join(", ")}</p>
    <p>@ ${loc ? loc.name : u.location_id}</p>
    <p>${u.status}${u.order ? " / " + u.order : ""}</p>
    <p class="muted">Select a body on the map for orders.</p>`;
}

function renderBodyPanel() {
  const el = $("body-panel");
  if (!el || state.phase !== "system") return;
  const b = bodyById(selectedBodyId);
  if (!b) {
    el.className = "empty";
    el.textContent = "Click a body in the 3D map";
    return;
  }
  el.className = "card";
  const sm = b.survey_months || 0;
  const depLines = (b.deposits || [])
    .map((d) => {
      if (d.detail <= 0) return null;
      if (d.detail === 1) return `· ${d.resource_hint || "anomaly"} (${d.hint})`;
      let s = `· ${d.resource} (${d.hint})`;
      if (d.grade != null) s += ` · grade ${d.grade}`;
      const tons = tonsLabel(d);
      if (tons) s += ` · ${tons}`;
      return s;
    })
    .filter(Boolean)
    .join("<br/>");
  const sites = (b.mine_sites || [])
    .map((s) => {
      const tons = tonsLabel(s) || formatTons(s.amount_t);
      return `· <strong>${s.resource}</strong> @ ${s.region} · grade ${s.grade}${tons ? " · " + tons : ""}`;
    })
    .join("<br/>");

  let orbitFact = "";
  if (b.kind === "moon") {
    const p = bodyById(b.parent_id);
    orbitFact = `<p><strong>Orbit</strong> moon of ${p ? p.name : b.parent_id}</p>
      <p><strong>Period</strong> ${b.period_label || "—"}</p>`;
  } else {
    orbitFact = `<p><strong>a</strong> ${b.semi_major_au ?? "—"} AU</p>
      <p><strong>Period</strong> ${b.period_label || "—"}</p>
      <p><strong>Mass</strong> ${b.mass_earth ?? "—"} M⊕</p>`;
  }

  el.innerHTML = `
    <h3>${b.name}</h3>
    <p class="muted">${b.kind}${b.planet_class ? " / " + b.planet_class : ""} · ${b.density_hint || ""}</p>
    <button type="button" id="btn-focus-body" class="primary" style="width:100%;margin:6px 0">Focus in map</button>
    <h2>Facts</h2>
    ${orbitFact}
    <p><strong>Δv</strong> ↑orbit ${b.dv_to_orbit_m_s} · esc ${b.dv_escape_from_orbit_m_s} m/s</p>
    <p><strong>Site search</strong> ${sm.toFixed(1)} mo on station</p>
    <h2>Intel</h2>
    <p>${depLines || '<span class="muted">No composition intel yet</span>'}</p>
    <h2>Extraction sites</h2>
    <p>${sites || '<span class="muted">None yet — keep searching</span>'}</p>
  `;
  const fb = $("btn-focus-body");
  if (fb) fb.onclick = () => map && map.focusBody(b.id);
}

async function renderOrders() {
  const panel = $("orders-panel");
  const el = $("orders");
  if (!panel || !el || state.phase !== "system") return;
  const u = unitById(selectedUnitId);
  const b = bodyById(selectedBodyId);
  if (!u || !b) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const caps = u.capabilities || [];
  const busy =
    (u.status === "en_route" && u.months_left > 0) ||
    (u.status === "working" && u.order === "mine") ||
    (u.status === "working" && u.order === "survey");
  const sites = b.mine_sites || [];
  const surveyingHere = u.status === "working" && u.order === "survey" && u.location_id === b.id;
  const resNames = (state.tech && state.tech.resources) || {};
  const searchable = b.searchable_resources || ["Fe", "Si", "Al", "H2O"];
  const exhausted = new Set(b.seek_exhausted || []);
  const foundRes = new Set((b.mine_sites || []).map((s) => s.resource));

  let estMove = null;
  try {
    estMove = await api("/api/estimate_order", {
      method: "POST",
      body: JSON.stringify({ unit_id: u.id, order: "move", target_id: b.id }),
    });
  } catch (_) {}

  const fmt = (e) => {
    if (!e) return "";
    if (e.years >= 0.5) return ` (~${e.years.toFixed(1)} y)`;
    if (e.months > 0) return ` (~${e.months.toFixed(1)} mo)`;
    return "";
  };

  let html = "";
  html += btn("move", `Move to ${b.name}${fmt(estMove)}`, b.id, "", !busy);
  html += btn("idle", "Stand by / recall", b.id, "", true);

  if (caps.includes("survey")) {
    html += `<h2>Search for sources</h2>`;
    if (surveyingHere) {
      const what = u.search_resource
        ? resNames[u.search_resource] || u.search_resource
        : "broad composition";
      const sm = u.search_resource
        ? (b.seek_months && b.seek_months[u.search_resource]) || 0
        : b.survey_months || 0;
      html += `<div class="queue-job">
        <div class="title">Searching: ${what}</div>
        <div class="meta">${sm.toFixed(1)} mo on station · warp to advance · stand by to reassign</div>
      </div>`;
    } else {
      html += `<p class="muted">Choose what to look for on ${b.name}:</p>`;
      for (const res of searchable) {
        const name = resNames[res] || res;
        if (foundRes.has(res)) {
          html += `<button type="button" class="order" disabled>Find sources of ${name} — site already found</button>`;
        } else if (exhausted.has(res)) {
          html += `<button type="button" class="order" disabled>Find sources of ${name} — none viable here</button>`;
        } else {
          const can = !busy;
          html += btn(
            "survey",
            `Find sources of ${name}`,
            b.id,
            res,
            can
          );
        }
      }
      html += btn("survey", "Broad composition survey", b.id, "", !busy);
    }
  }

  html += `<h2>Extraction sites</h2>`;
  if (!sites.length) {
    html += `<p class="muted">None yet — pick a search above.</p>`;
  } else {
    for (const s of sites) {
      const tons = tonsLabel(s) || formatTons(s.amount_t);
      const name = resNames[s.resource] || s.resource;
      html += btn(
        "mine",
        `Extract ${name} @ ${s.region}${tons ? " · " + tons : ""}`,
        s.id,
        "",
        caps.includes("mine") && !busy
      );
    }
  }
  el.innerHTML = html;

  function btn(order, label, target, resource, enabled) {
    return `<button type="button" class="order" data-order="${order}" data-target="${target}" data-resource="${resource || ""}" ${
      enabled ? "" : "disabled"
    }>${label}</button>`;
  }

  el.querySelectorAll("[data-order]").forEach((button) => {
    button.onclick = async () => {
      try {
        state = await api("/api/order", {
          method: "POST",
          body: JSON.stringify({
            unit_id: u.id,
            order: button.dataset.order,
            target_id: button.dataset.target,
            resource: button.dataset.resource || "",
          }),
        });
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  });
}

function renderBuild() {
  const panel = $("build-panel");
  if (!panel || state.phase !== "system") return;
  const b = bodyById(selectedBodyId);
  panel.hidden = !b;
  if (!b) return;
  const power = $("power-id").value;
  $("build-hint").textContent = state.build_options?.power?.[power]?.description || "";
  $("btn-plan").onclick = async () => {
    try {
      state = await api("/api/plan_base", {
        method: "POST",
        body: JSON.stringify({
          body_id: b.id,
          power_id: $("power-id").value,
          hab_id: $("hab-id").value,
        }),
      });
      render();
    } catch (e) {
      alert(String(e.message || e).slice(0, 280));
    }
  };
}

function renderProjects() {
  const el = $("projects");
  if (!el) return;
  const list = state.projects || [];
  el.innerHTML = list.length
    ? list
        .map((p) => {
          const b = bodyById(p.body_id);
          return `<div class="card"><h3>${p.name}</h3><p>${b ? b.name : p.body_id} · ${p.status}</p></div>`;
        })
        .join("")
    : '<p class="empty">None</p>';
}

function renderContracts() {
  const el = $("contracts");
  if (!el) return;
  const open = (state.contracts || []).filter((c) => c.status === "open");
  el.innerHTML = open.length
    ? open
        .map(
          (c) => `<div class="card">
      <h3>${c.title}</h3>
      <p>${c.resource_name}: ${c.delivered_t}/${c.amount_t} t</p>
      <button data-deliver="${c.id}">From ark cargo</button>
    </div>`
        )
        .join("")
    : '<p class="empty">No open needs</p>';
  el.querySelectorAll("[data-deliver]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        state = await api("/api/deliver_ark", {
          method: "POST",
          body: JSON.stringify({ contract_id: btn.dataset.deliver }),
        });
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  });
}

function renderStock() {
  const el = $("ark-stock");
  if (!el) return;
  const s = state.ark_stock || {};
  el.innerHTML = Object.keys(s)
    .sort()
    .map((k) => `<span class="k">${k}</span><span>${s[k]} t</span>`)
    .join("");
}

function renderEvents() {
  const el = $("events");
  if (!el) return;
  el.innerHTML = (state.events || [])
    .slice(0, 8)
    .map((e) => `<div class="event">${e.text}</div>`)
    .join("");
}

// Panel toggles — open left by default on menu so archive is findable
$("toggle-left").onclick = () => $("panel-left").classList.toggle("collapsed");
$("toggle-right").onclick = () => $("panel-right").classList.toggle("collapsed");
// Start with left panel open so "View survey results" is obvious
$("panel-left").classList.remove("collapsed");

$("btn-catalog").onclick = async () => {
  state = await api("/api/catalog", { method: "POST", body: "{}" });
  $("panel-left").classList.remove("collapsed");
  render();
};
function renderNextEvent() {
  const el = $("next-event");
  if (!el || !state) return;
  const n = state.next_event;
  if (!n) {
    el.textContent = "No event queued";
    el.title = "Warp will not skip time while nothing is scheduled";
    return;
  }
  const when =
    n.years >= 0.5
      ? `~${n.years.toFixed(2)} y`
      : n.months >= 1
        ? `~${n.months.toFixed(1)} mo`
        : `~${(n.months * 30).toFixed(0)} d`;
  el.textContent = `Next: ${n.label} (${when})`;
  el.title = n.needs_confirm
    ? "Long jump — Warp will ask before skipping this far"
    : "Warp skips to this event";
}

$("btn-warp").onclick = async () => {
  try {
    let res = await api("/api/warp", {
      method: "POST",
      body: JSON.stringify({ force: false }),
    });
    const w = res.warp || {};
    if (w.needs_confirm) {
      const n = w.next_event || {};
      const when =
        n.years >= 0.5
          ? `${n.years.toFixed(2)} years`
          : `${(n.months || 0).toFixed(2)} months`;
      const ok = confirm(
        `${w.message || "Confirm time skip"}\n\n` +
          `Skip ${when} to:\n${n.label || "next event"}?\n\n` +
          `Cancel if you were only looking for a button — no time will be lost.`
      );
      if (!ok) {
        $("toast").textContent = "Warp cancelled — no time skipped.";
        return;
      }
      res = await api("/api/warp", {
        method: "POST",
        body: JSON.stringify({ force: true }),
      });
    } else if (w.reason === "idle") {
      $("toast").textContent = w.message || "Nothing queued — no time skipped.";
      state = res;
      render();
      return;
    }
    state = res;
    if (res.warp && res.warp.message) {
      state.message = res.warp.message;
    }
    render();
  } catch (e) {
    alert(String(e.message || e).slice(0, 280));
  }
};
$("btn-warp-transit").onclick = () => $("btn-warp").click();
$("btn-reset").onclick = async () => {
  if (!confirm("Reset?")) return;
  state = await api("/api/reset", { method: "POST", body: "{}" });
  selectedUnitId = null;
  selectedBodyId = null;
  map.clearSystem();
  render();
};
$("btn-focus-system").onclick = () => map && map.focusSystem();
$("btn-focus-sel").onclick = () => {
  if (!map) return;
  if (selectedBodyId) map.focusBody(selectedBodyId);
  else map.focusSystem();
};

// Boot: never leave the user stuck on "Loading…" if 3D init fails.
(async function boot() {
  try {
    initMap();
  } catch (e) {
    console.error(e);
    $("toast").textContent =
      "3D map failed to start: " + (e && e.message ? e.message : e) +
      " — panels still work.";
  }
  try {
    await refresh();
  } catch (e) {
    $("toast").textContent = "API error: " + (e && e.message ? e.message : e);
  }
  setInterval(async () => {
    if (document.hidden) return;
    try {
      const prevSeed = state?.system?.seed;
      state = await api("/api/state");
      render();
      if (map && state?.system && prevSeed === state.system.seed) {
        const simSec = (state.sim_months || 0) * 30 * 86400;
        map.updatePositions(state.system, simSec);
      }
    } catch (_) {}
  }, 3000);
})();
