/* Colony UI — map-dominant Three.js view + floating panels */
import { SystemMap3D } from "/static/map3d.js";

let state = null;
let selectedUnitId = null;
let selectedBodyId = null;
let map = null;

const $ = (id) => document.getElementById(id);

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
  map = new SystemMap3D(canvas);
  map.onSelect = (id) => {
    selectedBodyId = id;
    $("panel-right").classList.remove("collapsed");
    renderBodyPanel();
    renderOrders();
    renderBuild();
  };
}

async function refresh() {
  state = await api("/api/state");
  render();
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

  // 3D map
  if (state.phase === "system" && state.system) {
    if (!map.systemData || map.systemData.seed !== state.system.seed) {
      map.setSystem(state.system);
      map.focusSystem();
    } else {
      map.updatePositions(state.system);
    }
    if (selectedBodyId) map.setSelected(selectedBodyId);
    $("map-hint").textContent =
      "Drag orbit · Scroll zoom · Click select · Double-click focus planet (see moons)";
  } else if (state.phase !== "system") {
    map.clearSystem();
    $("map-hint").textContent =
      state.phase === "menu"
        ? "Open survey archive (left) — map fills once you arrive in-system"
        : "In transit — warp to arrival to enter the system map";
  }

  renderCatalog();
  renderBuildUnits();
  renderFleet();
  renderUnitPanel();
  renderBodyPanel();
  renderOrders();
  renderBuild();
  renderProjects();
  renderContracts();
  renderStock();
  renderEvents();
}

function renderBuildUnits() {
  const el = $("build-units");
  const qel = $("build-queue");
  if (!el || state.phase !== "system") return;
  const specs = state.unit_builds || {};
  el.innerHTML = Object.values(specs)
    .map((s) => {
      const cost = Object.entries(s.cost || {})
        .map(([k, v]) => `${v}t ${k}`)
        .join(", ");
      return `<div class="card">
        <h3>${s.name}</h3>
        <p>${s.description || ""}</p>
        <p class="muted">${cost} · ${s.months} mo</p>
        <button type="button" class="primary" data-build="${s.id}">Authorize build</button>
      </div>`;
    })
    .join("");
  el.querySelectorAll("[data-build]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        state = await api("/api/build", {
          method: "POST",
          body: JSON.stringify({ unit_kind: btn.dataset.build }),
        });
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  });
  if (qel) {
    const builds = state.builds || [];
    qel.innerHTML = builds.length
      ? builds
          .map(
            (j) =>
              `<p class="muted">Building ${j.name}: ${j.months_left.toFixed(1)} / ${j.months_total} mo left</p>`
          )
          .join("")
      : '<p class="empty">No fab jobs</p>';
  }
}

function renderCatalog() {
  const el = $("catalog");
  if (!el) return;
  if (!state.catalog?.length) {
    el.innerHTML = '<p class="empty">No archive open.</p>';
    return;
  }
  el.innerHTML = state.catalog
    .map((c) => {
      const title = c.star.designation || c.star.name;
      const g =
        c.gas_giant_period_years != null ? ` · gas giant ~${c.gas_giant_period_years} y` : "";
      const ds = c.dossier_id ? `<p class="muted">${c.dossier_id} · ${c.status || "on file"} · completeness ${c.completeness ?? "?"}</p>` : "";
      return `<div class="card">
        <h3>${title}</h3>
        ${ds}
        <p>${c.survey_summary}</p>
        <p>Outer ~${c.outer_au ?? "?"} AU${g}</p>
        <button class="primary" data-seed="${c.seed}">Commit to this dossier</button>
      </div>`;
    })
    .join("");
  el.querySelectorAll("[data-seed]").forEach((btn) => {
    btn.onclick = async () => {
      state = await api("/api/select_star", {
        method: "POST",
        body: JSON.stringify({ seed: Number(btn.dataset.seed) }),
      });
      selectedUnitId = null;
      selectedBodyId = null;
      render();
    };
  });
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
}

function renderUnitPanel() {
  const el = $("unit-panel");
  if (!el || state.phase !== "system") return;
  const u = unitById(selectedUnitId);
  if (!u) {
    el.className = "empty";
    el.textContent = "Select a unit";
    return;
  }
  const loc = bodyById(u.location_id);
  el.className = "card";
  el.innerHTML = `<h3>${u.name}</h3>
    <p>${u.kind} · ${(u.capabilities || []).join(", ")}</p>
    <p>@ ${loc ? loc.name : u.location_id}</p>
    <p>${u.status}${u.order ? " / " + u.order : ""}</p>`;
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
      if (d.grade != null) s += ` g${d.grade}`;
      if (d.amount_t != null) s += ` ~${Math.round(d.amount_t)}t`;
      return s;
    })
    .filter(Boolean)
    .join("<br/>");
  const sites = (b.mine_sites || [])
    .map((s) => `· ${s.name} — ${s.resource}`)
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
    <p><strong>Survey</strong> ${sm.toFixed(1)} mo on station</p>
    <h2>Intel</h2>
    <p>${depLines || '<span class="muted">No composition intel yet</span>'}</p>
    <h2>Mine sites</h2>
    <p>${sites || '<span class="muted">None — keep surveying</span>'}</p>
  `;
  const fb = $("btn-focus-body");
  if (fb) fb.onclick = () => map.focusBody(b.id);
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

  let estMove = null;
  let estSurvey = null;
  try {
    estMove = await api("/api/estimate_order", {
      method: "POST",
      body: JSON.stringify({ unit_id: u.id, order: "move", target_id: b.id }),
    });
    estSurvey = await api("/api/estimate_order", {
      method: "POST",
      body: JSON.stringify({ unit_id: u.id, order: "survey", target_id: b.id }),
    });
  } catch (_) {}

  const fmt = (e) => {
    if (!e) return "";
    if (e.years >= 0.5) return ` (~${e.years.toFixed(1)} y)`;
    if (e.months > 0) return ` (~${e.months.toFixed(1)} mo)`;
    return "";
  };

  let html = "";
  html += btn("move", `Move to ${b.name}${fmt(estMove)}`, b.id, !busy);
  html += btn(
    "survey",
    surveyingHere
      ? `Surveying… ${((b.survey_months || 0).toFixed(1))} mo — warp for detail`
      : `Survey ${b.name}${fmt(estSurvey)}`,
    b.id,
    caps.includes("survey") && !surveyingHere && !(busy && u.order !== "survey")
  );
  html += btn("idle", "Stand by / recall", b.id, true);

  html += `<h2>Mine sites</h2>`;
  if (!sites.length) {
    html += `<p class="muted">No sites yet — survey longer.</p>`;
  } else {
    for (const s of sites) {
      html += btn(
        "mine",
        `Mine ${s.resource} @ ${s.region}`,
        s.id,
        caps.includes("mine") && !busy
      );
    }
  }
  el.innerHTML = html;

  function btn(order, label, target, enabled) {
    return `<button type="button" class="order" data-order="${order}" data-target="${target}" ${
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

// Panel toggles
$("toggle-left").onclick = () => $("panel-left").classList.toggle("collapsed");
$("toggle-right").onclick = () => $("panel-right").classList.toggle("collapsed");

$("btn-catalog").onclick = async () => {
  state = await api("/api/catalog", { method: "POST", body: "{}" });
  $("panel-left").classList.remove("collapsed");
  render();
};
$("btn-warp").onclick = async () => {
  state = await api("/api/warp", { method: "POST", body: "{}" });
  render();
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
$("btn-focus-system").onclick = () => map.focusSystem();
$("btn-focus-sel").onclick = () => {
  if (selectedBodyId) map.focusBody(selectedBodyId);
  else map.focusSystem();
};

initMap();
setInterval(async () => {
  if (document.hidden) return;
  try {
    const prevSeed = state?.system?.seed;
    state = await api("/api/state");
    // light update without rebuilding whole UI thrash
    render();
    if (state?.system && prevSeed === state.system.seed) {
      map.updatePositions(state.system);
    }
  } catch (_) {}
}, 3000);

refresh().catch((e) => {
  $("toast").textContent = "API error: " + e.message;
});
