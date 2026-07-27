/* Colony UI — map-dominant Three.js view + floating panels */
import { SystemMap3D } from "/static/map3d.js";

let state = null;
let selectedUnitId = null;
let selectedBodyId = null;
let selectedDossierSeed = null;
let expandedPlanets = new Set(); // body ids with moons shown
let map = null;
/** Cascade command window: null | { kind: 'ark'|'unit'|'body'|'process', tab?: string, ... } */
let cascade = null;

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
    // Expand parent planet if a moon was clicked
    const b = bodyById(id);
    if (b && b.kind === "moon" && b.parent_id) expandedPlanets.add(b.parent_id);
    selectBody(id, { focus: false, openRight: true });
  };
  map.onSelectUnit = (unitId) => {
    selectedUnitId = unitId;
    const u = unitById(unitId);
    $("panel-left").classList.remove("collapsed");
    if (u && u.kind === "ark") openArkCascade();
    else if (u) openUnitCascade(u.id, "actions");
    else render();
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
      map.updateFleet(state.fleet || [], {
        homeBodyId: state.home_body_id || state.ark_location_body_id,
        selectedUnitId,
      });
      $("map-hint").textContent =
        "Click body or fleet craft · paths show transits · double-click focuses · drag/scroll camera";
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
  renderEventSchedule();
  renderFleet();
  renderUnitPanel();
  renderCascade();
  renderBodyTree();
  renderBodyPanel();
  renderOrders();
  renderHaulPanel();
  renderHaulsList();
  renderBuild();
  renderProjects();
  renderContracts();
  renderStock();
  renderEvents();
}

function openArkCascade(tab) {
  selectedUnitId = "ark";
  cascade = { kind: "ark", tab: tab || (cascade && cascade.kind === "ark" && cascade.tab) || "survey" };
  renderSafe();
}

/** Open unit action card (survey probe, later miner/hauler). */
function openUnitCascade(unitId, tab) {
  const u = unitById(unitId);
  if (!u) return;
  selectedUnitId = unitId;
  const keepTab =
    cascade && cascade.kind === "unit" && cascade.unitId === unitId ? cascade.tab : null;
  cascade = {
    kind: "unit",
    unitId,
    tab: tab || keepTab || "actions",
  };
  renderSafe();
}

/** Open body command card over the map (ark-style tabs). */
function openBodyCascade(bodyId, tab) {
  if (!bodyId || !bodyById(bodyId)) return;
  selectedBodyId = bodyId;
  const keepTab =
    cascade && cascade.kind === "body" && cascade.bodyId === bodyId ? cascade.tab : null;
  cascade = {
    kind: "body",
    bodyId,
    tab: tab || keepTab || "habitability",
    _opened: !!(cascade && cascade.kind === "body" && cascade.bodyId === bodyId),
  };
  if (map) map.setSelected(bodyId);
  renderSafe();
}

function closeCascade() {
  cascade = null;
  renderSafe();
}

async function issueUnitOrder(unitId, order, targetId = "", resource = "") {
  state = await api("/api/order", {
    method: "POST",
    body: JSON.stringify({
      unit_id: unitId,
      order,
      target_id: targetId,
      resource: resource || "",
    }),
  });
}

async function promptRenameUnit(unitId) {
  const u = unitById(unitId);
  if (!u) return;
  const next = window.prompt(`Rename ${u.kind}:`, u.name);
  if (next == null) return; // cancelled
  const name = next.trim();
  if (!name || name === u.name) return;
  try {
    state = await api("/api/rename_unit", {
      method: "POST",
      body: JSON.stringify({ unit_id: unitId, name }),
    });
    selectedUnitId = unitId;
    // Keep current cascade context if open on this unit / ark
    if (cascade && cascade.kind === "unit" && cascade.unitId === unitId) {
      cascade = { ...cascade, unitId };
    }
    if (cascade && cascade.kind === "ark" && unitId === "ark") {
      cascade = { ...cascade };
    }
    $("toast").textContent = `Renamed to ${name}`;
    render();
  } catch (e) {
    alert(String(e.message || e).slice(0, 280));
  }
}

function unitIsBusy(u) {
  if (!u) return false;
  return (
    (u.status === "en_route" && u.months_left > 0) ||
    (u.status === "working" && u.order === "mine") ||
    (u.status === "working" && u.order === "survey")
  );
}

function bodyPickerOptions(selectedId) {
  const tree = state.body_tree || [];
  const bodies = (state.system && state.system.bodies) || [];
  // Prefer hierarchical labels; fall back to flat list
  const opts = [];
  for (const node of tree) {
    if (node.kind === "belt_group") {
      for (const a of node.asteroids || []) {
        opts.push({ id: a.id, label: `  ${a.name}`, kind: "asteroid" });
      }
      continue;
    }
    opts.push({
      id: node.id,
      label: node.name,
      kind: "planet",
    });
    for (const m of node.moons || []) {
      opts.push({ id: m.id, label: `  ${m.name}`, kind: "moon" });
    }
  }
  if (!opts.length) {
    for (const b of bodies) {
      opts.push({ id: b.id, label: b.name, kind: b.kind });
    }
  }
  return opts
    .map(
      (o) =>
        `<option value="${o.id}" ${o.id === selectedId ? "selected" : ""}>${o.label}</option>`
    )
    .join("");
}

function resName(id) {
  return ((state.tech && state.tech.resources) || {})[id] || id;
}

function formatDv(m_s) {
  if (m_s == null || !Number.isFinite(Number(m_s))) return "—";
  const n = Number(m_s);
  if (n >= 1000) return `${(n / 1000).toFixed(2)} km/s`;
  return `${Math.round(n)} m/s`;
}

function dvBarHtml(u) {
  if (!u || !(u.dv_capacity_m_s > 0)) return "";
  const frac = Math.max(0, Math.min(1, (u.dv_remaining_m_s || 0) / u.dv_capacity_m_s));
  const pct = (frac * 100).toFixed(0);
  const low = frac < 0.25 ? "dv-low" : frac < 0.5 ? "dv-mid" : "dv-ok";
  return `<div class="dv-meter ${low}">
    <div class="dv-label">Δv remaining <strong>${formatDv(u.dv_remaining_m_s)}</strong> / ${formatDv(u.dv_capacity_m_s)} (${pct}%)</div>
    <div class="queue-bar"><i style="width:${pct}%"></i></div>
  </div>`;
}

function selectBody(id, { focus = true, openRight = true, openCard = true } = {}) {
  selectedBodyId = id;
  if (openRight) $("panel-right").classList.remove("collapsed");
  if (map) {
    map.setSelected(id);
    if (focus) map.focusBody(id);
  }
  renderBodyTree();
  // Body details live in the cascade card (not buried under the list)
  if (openCard && id && state?.phase === "system") {
    openBodyCascade(id);
  } else {
    renderBodyPanel();
    renderOrders();
    renderBuild();
  }
}

function renderBodyTree() {
  const el = $("body-tree");
  if (!el || state.phase !== "system") {
    if (el) el.innerHTML = "";
    return;
  }
  const tree = state.body_tree || [];
  if (!tree.length) {
    el.innerHTML = '<p class="empty">No bodies loaded.</p>';
    return;
  }
  let html = "";
  for (const node of tree) {
    if (node.kind === "belt_group") {
      const open = expandedPlanets.has("_belt");
      html += `<button type="button" class="body-row" data-expand="_belt">
        <span class="body-expand">${open ? "▾" : "▸"}</span>
        <strong>${node.name}</strong>
        <div class="meta">${(node.asteroids || []).length} objects</div>
      </button>`;
      if (open) {
        for (const a of node.asteroids || []) {
          const sel = selectedBodyId === a.id ? "selected" : "";
          html += `<button type="button" class="body-row asteroid ${sel}" data-body="${a.id}">
            ${a.name}
            <div class="meta">${a.semi_major_au} AU · ${a.density_hint || ""}</div>
          </button>`;
        }
      }
      continue;
    }
    const open = expandedPlanets.has(node.id);
    const sel = selectedBodyId === node.id ? "selected" : "";
    const hab =
      node.hab_intel >= 2
        ? `<span class="hab-badge">hab intel ${node.hab_intel}</span>`
        : node.in_hz
          ? `<span class="hab-badge">HZ</span>`
          : "";
    html += `<button type="button" class="body-row ${sel}" data-body="${node.id}">
      ${node.moon_count ? `<span class="body-expand" data-expand="${node.id}">${open ? "▾" : "▸"}</span>` : ""}
      <strong>${node.name}</strong>${hab}
      <div class="meta">${node.planet_class || "planet"} · ${node.semi_major_au} AU${
        node.moon_count ? ` · ${node.moon_count} moon(s)` : ""
      }</div>
    </button>`;
    if (open && node.moons) {
      for (const m of node.moons) {
        const msel = selectedBodyId === m.id ? "selected" : "";
        html += `<button type="button" class="body-row moon ${msel}" data-body="${m.id}">
          ${m.name}
          <div class="meta">moon · a/R ${m.moon_a_over_R} · P ${m.period_days} d</div>
        </button>`;
      }
    }
  }
  el.innerHTML = html;

  el.querySelectorAll("[data-expand]").forEach((btn) => {
    btn.onclick = (ev) => {
      ev.stopPropagation();
      const id = btn.getAttribute("data-expand");
      if (expandedPlanets.has(id)) expandedPlanets.delete(id);
      else expandedPlanets.add(id);
      renderBodyTree();
    };
  });
  el.querySelectorAll("[data-body]").forEach((btn) => {
    btn.onclick = (ev) => {
      // expand chevron is separate; whole row selects
      if (ev.target.closest("[data-expand]") && ev.target.hasAttribute("data-expand")) return;
      const id = btn.getAttribute("data-body");
      // auto-expand planet when selected if it has moons
      const node = (state.body_tree || []).find((n) => n.id === id);
      if (node && node.moon_count) expandedPlanets.add(id);
      selectBody(id);
    };
  });
  // Expand on chevron attached to planet row
  el.querySelectorAll(".body-row > .body-expand[data-expand]").forEach((span) => {
    span.onclick = (ev) => {
      ev.stopPropagation();
      const id = span.getAttribute("data-expand");
      if (expandedPlanets.has(id)) expandedPlanets.delete(id);
      else expandedPlanets.add(id);
      renderBodyTree();
    };
  });
}

function renderEventSchedule() {
  const el = $("event-schedule");
  if (!el || state.phase === "menu") {
    if (el) el.innerHTML = "";
    return;
  }
  const q = state.event_queue || [];
  if (!q.length) {
    el.innerHTML =
      '<div class="queue-empty">No scheduled events. Real time still runs 1:1; Warp will not skip.</div>';
    return;
  }
  el.innerHTML = q
    .map((e, i) => {
      const when =
        e.years >= 0.5
          ? `~${e.years.toFixed(2)} y`
          : e.months >= 1
            ? `~${e.months.toFixed(2)} mo`
            : `~${Math.max(1, Math.round(e.months * 30))} d`;
      const mark = i === 0 ? "next" : "";
      return `<div class="queue-job ${mark}">
        <div class="title">${e.label}</div>
        <div class="meta">${when}${e.needs_confirm ? " · Warp will ask to confirm" : ""}</div>
      </div>`;
    })
    .join("");
}

/** Large command window cascade (ark console, unit action cards, body cards, process). */
function renderCascade() {
  const root = $("cascade");
  if (!root) return;

  if (!cascade) {
    root.hidden = true;
    return;
  }

  // Process board is available in every phase (menu / transit / system)
  if (cascade.kind === "process") {
    renderProcessCascade(root);
    return;
  }

  if (state.phase !== "system") {
    root.hidden = true;
    return;
  }

  if (cascade.kind === "ark") {
    if (!unitById("ark") && !(state.fleet || []).some((u) => u.kind === "ark")) {
      cascade = null;
      root.hidden = true;
      return;
    }
    renderArkCascade(root);
    return;
  }

  if (cascade.kind === "unit") {
    const u = unitById(cascade.unitId);
    if (!u) {
      cascade = null;
      root.hidden = true;
      return;
    }
    if (u.kind === "survey") {
      renderSurveyCascade(root, u);
      return;
    }
    // Generic unit card fallback
    renderGenericUnitCascade(root, u);
    return;
  }

  if (cascade.kind === "body") {
    const b = bodyById(cascade.bodyId);
    if (!b) {
      cascade = null;
      root.hidden = true;
      return;
    }
    renderBodyCascade(root, b);
    return;
  }

  cascade = null;
  root.hidden = true;
}

function openProcessCascade(tab) {
  cascade = {
    kind: "process",
    tab:
      tab ||
      (cascade && cascade.kind === "process" && cascade.tab) ||
      "overview",
  };
  renderSafe();
}

function renderProcessCascade(root) {
  root.hidden = false;
  root.querySelector(".cascade-window")?.classList.remove("unit-card");
  root.querySelector(".cascade-window")?.classList.remove("body-card");
  root.querySelector(".cascade-window")?.classList.add("process-card");

  const tab = cascade.tab || "overview";
  cascade.tab = tab;
  const p = state.process || {};
  const next = p.next_focus;
  const discCount = (p.discoveries || state.discoveries || []).length;

  $("cascade-kicker").textContent = "Colony process · research & industry";
  $("cascade-title").textContent = "Process board";
  $("cascade-sub").textContent = next
    ? `Focus: ${next.text || "—"}${next.next_step ? " → " + next.next_step : ""}`
    : state.phase === "menu"
      ? "Pick a star from the survey archive to begin."
      : state.phase === "transit"
        ? "In transit — warp to arrival, then map the system."
        : "Survey, mine, and industrialize this system.";

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "research", label: "Research" },
    { id: "discoveries", label: `Discoveries${discCount ? " · " + discCount : ""}` },
    { id: "industry", label: "Industry" },
  ];
  $("cascade-tabs").innerHTML = tabs
    .map(
      (t) =>
        `<button type="button" class="cascade-tab ${t.id === tab ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
    )
    .join("");
  $("cascade-tabs").querySelectorAll("[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "process", tab: btn.dataset.tab };
      renderCascade();
    };
  });

  const body = $("cascade-body");
  if (tab === "research") body.innerHTML = processResearchHtml(p);
  else if (tab === "discoveries") body.innerHTML = processDiscoveriesHtml(p);
  else if (tab === "industry") body.innerHTML = processIndustryHtml(p);
  else body.innerHTML = processOverviewHtml(p);

  bindProcessCascade(body, tab);
}

function goalStatusClass(st) {
  if (st === "done") return "goal-done";
  if (st === "active") return "goal-active";
  return "goal-pending";
}

function processOverviewHtml(p) {
  const goals = p.goals || [];
  const next = p.next_focus;
  const goalsHtml = goals.length
    ? goals
        .map((g) => {
          const cls = goalStatusClass(g.status);
          const mark = g.status === "done" ? "✓" : g.status === "active" ? "●" : "○";
          return `<div class="process-goal ${cls}">
            <span class="pg-mark">${mark}</span>
            <span class="pg-body">
              <strong>${escapeHtml(g.label || g.id)}</strong>
              <span class="pg-detail">${escapeHtml(g.detail || "")}</span>
            </span>
          </div>`;
        })
        .join("")
    : '<p class="muted">No goals for this phase yet.</p>';

  const focusHtml = next
    ? `<div class="card process-focus">
        <h3>Next focus</h3>
        <p class="pf-text">${escapeHtml(next.text || "")}</p>
        <p class="pf-step">${escapeHtml(next.next_step || "")}</p>
        ${
          next.body_id
            ? `<button type="button" class="primary" data-goto-body="${escapeHtml(
                next.body_id
              )}" style="margin-top:10px">Open body card</button>`
            : ""
        }
      </div>`
    : `<div class="card process-focus">
        <h3>Next focus</h3>
        <p class="muted">No active lead — open Survey priorities or fab a probe.</p>
      </div>`;

  const research = p.research || {};
  const sites = research.mine_sites || [];
  const snap = `
    <div class="cascade-split" style="margin-top:12px">
      <div class="card">
        <h3>System research</h3>
        <p><strong>${research.bodies_touched || 0}</strong> bodies touched</p>
        <p><strong>${sites.length}</strong> extraction site(s)</p>
        <p><strong>${(research.resources_known || []).length}</strong> resource type(s)</p>
        <p class="muted">${(research.resources_known || []).join(", ") || "none confirmed"}</p>
      </div>
      <div class="card">
        <h3>Industry</h3>
        <p><strong>${((p.industry || {}).structures_online || []).length}</strong> structure(s) online</p>
        <p class="muted">${
          ((p.industry || {}).built_kinds || []).join(", ") || "nothing deployed yet"
        }</p>
        <p style="margin-top:8px"><strong>Pop</strong> ${(
          p.population != null ? p.population : state.population || 0
        ).toLocaleString()}</p>
      </div>
    </div>`;

  return `
    <p class="cascade-section-lead">
      Colony goals, research state for deployment targets, and a journal of finds
      (e.g. <em>“iron found on Norma-2”</em> → next step: pin an extraction site).
      Use this board when you need “what should I do next?”
    </p>
    ${focusHtml}
    <h2 style="margin-top:16px">Goals</h2>
    <div class="process-goals">${goalsHtml}</div>
    ${snap}
  `;
}

function processResearchHtml(p) {
  const r = p.research || {};
  const sites = r.mine_sites || [];
  const leads = r.terraform_leads || [];
  const siteRows = sites.length
    ? sites
        .map(
          (s) => `<button type="button" class="process-row" data-goto-body="${s.body_id}">
            <span class="pr-title">${escapeHtml(s.resource_name || s.resource)} · ${escapeHtml(
              s.body_name
            )}</span>
            <span class="pr-meta">${escapeHtml(s.region || s.site_id || "")}${
              s.grade != null ? " · grade " + Number(s.grade).toFixed(2) : ""
            }</span>
          </button>`
        )
        .join("")
    : '<p class="muted">No extraction sites yet. Survey rocky worlds and the belt; use directed Fe/H₂O searches.</p>';

  const leadRows = leads.length
    ? leads
        .map((t) => {
          const vs = t.verdict_status || "unknown";
          return `<button type="button" class="process-row" data-goto-body="${t.body_id}">
            <span class="pr-title">${escapeHtml(t.name)} · L${t.level || 0}/5</span>
            <span class="pr-meta ${factorStatusClass(vs)}">${escapeHtml(t.verdict || "—")}${
              t.needs_l1_shield ? " · needs L1 shield" : ""
            }</span>
          </button>`;
        })
        .join("")
    : '<p class="muted">No terraform leads yet. Ark console → Survey priorities → “Find terraform / habitability targets”.</p>';

  return `
    <p class="cascade-section-lead">
      Where can you deploy miners, power, and lift? Extraction sites unlock from survey;
      terraform leads guide settlement / L1 shield work.
    </p>
    <h2>Extraction sites (${sites.length})</h2>
    <div class="process-list">${siteRows}</div>
    <h2 style="margin-top:16px">Terraform / settlement leads</h2>
    <div class="process-list">${leadRows}</div>
    <p class="muted" style="margin-top:12px">
      Bodies touched by sensors: <strong>${r.bodies_touched || 0}</strong> ·
      Confirmed resources: <strong>${(r.resources_known || []).join(", ") || "—"}</strong>
    </p>
  `;
}

function processDiscoveriesHtml(p) {
  const list = p.discoveries || state.discoveries || [];
  if (!list.length) {
    return `
      <p class="cascade-section-lead">
        Discoveries appear as the ark and probes learn the system —
        iron confirmed, sites unlocked, terraform assessments complete, structures online.
      </p>
      <p class="empty">No discoveries yet. Fab a survey sat, set ark scan goals, Warp.</p>`;
  }
  const rows = list
    .map((d) => {
      const when =
        d.t_years != null
          ? `${Number(d.t_years).toFixed(2)} y`
          : d.t_months != null
            ? `${Number(d.t_months).toFixed(1)} mo`
            : "";
      const kind = d.kind || "note";
      return `<div class="discovery-entry kind-${escapeHtml(kind)}">
        <div class="d-head">
          <span class="d-kind">${escapeHtml(kind.replace(/_/g, " "))}</span>
          <span class="d-when">${when}</span>
        </div>
        <div class="d-text">${escapeHtml(d.text || "")}</div>
        ${
          d.next_step
            ? `<div class="d-next">→ ${escapeHtml(d.next_step)}</div>`
            : ""
        }
        ${
          d.body_id
            ? `<button type="button" class="linkish" data-goto-body="${escapeHtml(
                d.body_id
              )}">Open ${escapeHtml(bodyById(d.body_id)?.name || d.body_id)}</button>`
            : ""
        }
      </div>`;
    })
    .join("");
  return `
    <p class="cascade-section-lead">
      History of research events. Read the latest, take the suggested next step
      (e.g. extraction site → send a miner).
    </p>
    <div class="discovery-log">${rows}</div>
  `;
}

function processIndustryHtml(p) {
  const ind = p.industry || {};
  const online = ind.structures_online || [];
  const gaps = ind.gaps || [];
  const onlineHtml = online.length
    ? online
        .map(
          (s) => `<div class="chip process-chip">
            <span class="k">${escapeHtml(s.body_name || s.body_id)}</span>
            <span class="v">${escapeHtml(s.building)}</span>
          </div>`
        )
        .join("")
    : '<p class="muted">No site structures deployed yet.</p>';

  // Group deployable structures for the player
  const groups = [
    {
      title: "Power",
      ids: ["solar_farm", "chem_genset"],
    },
    {
      title: "Mining & process",
      ids: ["extractor", "refuel_depot"],
    },
    {
      title: "Lift (light wells)",
      ids: ["mass_driver"],
    },
    {
      title: "Lift (chemical / heavy)",
      ids: ["launch_pad", "rocket_fab", "fuel_fab", "recovery_pad"],
    },
    {
      title: "Settlement",
      ids: ["habitat_module", "l1_magnetic_shield"],
    },
  ];
  const specs = state.structure_builds || {};
  const built = new Set(ind.built_kinds || online.map((s) => s.building));
  const groupHtml = groups
    .map((g) => {
      const cards = g.ids
        .map((id) => {
          const s = specs[id];
          if (!s) return "";
          const have = built.has(s.building || id);
          const cost = Object.entries(s.cost || {})
            .map(([k, v]) => `${v} ${k}`)
            .join(", ");
          return `<div class="card ${have ? "struct-online" : ""}">
            <h3>${escapeHtml(s.name)} ${have ? "✓" : ""}</h3>
            <p>${escapeHtml(s.description || "")}</p>
            <p class="muted">${cost} · ${s.months} mo · ark fab bay</p>
          </div>`;
        })
        .join("");
      return cards
        ? `<h2 style="margin-top:14px">${escapeHtml(g.title)}</h2>
           <div class="cascade-grid">${cards}</div>`
        : "";
    })
    .join("");

  return `
    <p class="cascade-section-lead">
      Deploy from the ark fabrication bay (one job at a time). Structures land on a chosen body.
      Power first → mining/lift → habitat. Heavy worlds need the chemical rocket chain;
      light moons/asteroids can use mass drivers.
    </p>
    <h2>Online now</h2>
    <div class="cascade-stock" style="margin-bottom:12px">${onlineHtml}</div>
    <button type="button" class="primary" id="btn-process-open-fab" style="width:100%;margin-bottom:8px"
      ${state.phase !== "system" ? "disabled" : ""}>
      Open ark fabrication bay
    </button>
    ${groupHtml}
    ${
      gaps.length
        ? `<p class="muted" style="margin-top:14px">${gaps.length} structure type(s) not yet built anywhere in-system.</p>`
        : ""
    }
  `;
}

function bindProcessCascade(bodyEl, tab) {
  bodyEl.querySelectorAll("[data-goto-body]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.dataset.gotoBody;
      if (!id || state.phase !== "system") return;
      selectedBodyId = id;
      if (map) map.setSelected(id);
      openBodyCascade(id, "overview");
    };
  });
  const fab = bodyEl.querySelector("#btn-process-open-fab");
  if (fab) {
    fab.onclick = () => {
      if (state.phase !== "system") return;
      openArkCascade("fab");
    };
  }
}

function renderBodyCascade(root, b) {
  root.hidden = false;
  root.querySelector(".cascade-window")?.classList.add("unit-card");
  root.querySelector(".cascade-window")?.classList.add("body-card");
  const tab = cascade.tab || "overview";
  cascade.tab = tab;

  const kindLabel = b.planet_class || b.kind;
  $("cascade-kicker").textContent = `${kindLabel} · body card`;
  $("cascade-title").textContent = b.name;
  const bits = [];
  if (b.semi_major_au != null) bits.push(`${b.semi_major_au} AU`);
  if (b.period_label) bits.push(b.period_label);
  if (b.surface_g != null) bits.push(`${b.surface_g} g`);
  $("cascade-sub").textContent = bits.join(" · ") || b.density_hint || "";

  // Default first open to habitability — that's what players ask first
  if (!cascade._opened) {
    cascade.tab = cascade.tab || "habitability";
    cascade._opened = true;
  }
  const tabs = [
    { id: "habitability", label: "Habitability" },
    { id: "overview", label: "Overview" },
    { id: "intel", label: "Intel" },
    { id: "tasks", label: "Tasks" },
    { id: "site", label: "Site & lift" },
  ];
  $("cascade-tabs").innerHTML = tabs
    .map(
      (t) =>
        `<button type="button" class="cascade-tab ${t.id === tab ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
    )
    .join("");
  $("cascade-tabs").querySelectorAll("[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "body", bodyId: b.id, tab: btn.dataset.tab };
      renderCascade();
    };
  });

  const bodyEl = $("cascade-body");
  if (tab === "habitability") bodyEl.innerHTML = bodyCascadeHabitabilityHtml(b);
  else if (tab === "intel") bodyEl.innerHTML = bodyCascadeIntelHtml(b);
  else if (tab === "tasks") bodyEl.innerHTML = bodyCascadeTasksHtml(b);
  else if (tab === "site") bodyEl.innerHTML = bodyCascadeSiteHtml(b);
  else bodyEl.innerHTML = bodyCascadeOverviewHtml(b);

  bindBodyCascade(bodyEl, b, tab);
}

function bodyCascadeHabitabilityHtml(b) {
  const d =
    b.terraform_dossier ||
    (state.terraform_dossiers && state.terraform_dossiers[b.id]) ||
    null;
  if (!d) {
    return `<p class="cascade-section-lead">No habitability data for this object.</p>`;
  }
  return `
    <p class="cascade-section-lead">
      Can people live here open-air? Gravity and star distance are known from physics.
      Air, water, and magnetic field need surveying. Missing field ⇒ build an L1 shield.
    </p>
    ${terraformDossierHtml(d)}
    <div class="action-stack" style="margin-top:12px">
      <button type="button" class="action-card primary-action" id="bc-start-tf-scan">
        <span class="action-title">Start ark terraform scan</span>
        <span class="action-desc">Enables system-wide habitability search (warp for progress).</span>
      </button>
      <button type="button" class="action-card" data-goto-tab="tasks">
        <span class="action-title">Send a survey probe here</span>
        <span class="action-desc">On-station survey fills the dossier faster than remote ark sensing.</span>
      </button>
    </div>
  `;
}

function bodyCascadeOverviewHtml(b) {
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
  const bld = (b.site_buildings || []).filter((x) => x && x !== "ark");
  const powerMw = b.site_power_mw || 0;
  const d =
    b.terraform_dossier ||
    (state.terraform_dossiers && state.terraform_dossiers[b.id]);
  return `
    <p class="cascade-section-lead">
      ${b.kind}${b.planet_class ? " / " + b.planet_class : ""} · ${b.density_hint || "—"}
    </p>
    ${d ? terraformDossierHtml(d, { compact: true }) : ""}
    <p class="muted" style="margin:8px 0"><button type="button" class="order" data-goto-tab="habitability">Open full habitability checklist →</button></p>
    <div class="cascade-split">
      <div class="card">
        <h3>Orbit &amp; gravity</h3>
        ${orbitFact}
        <p><strong>Δv</strong> ↑orbit ${b.dv_to_orbit_m_s} · esc ${b.dv_escape_from_orbit_m_s} m/s</p>
        <p><strong>Surface g</strong> ${b.surface_g != null ? b.surface_g + " g" : "—"}</p>
        <button type="button" class="primary" id="bc-focus" style="width:100%;margin-top:8px">Focus in map</button>
      </div>
      <div class="card">
        <h3>Site status</h3>
        <p><strong>Power</strong> ${powerMw} MW</p>
        <p><strong>Survey time</strong> ${(b.survey_months || 0).toFixed(1)} mo on station</p>
        <p><strong>Buildings</strong> ${bld.length ? bld.join(", ") : "none"}</p>
        <p class="muted">${
          b.mass_driver_online
            ? "⚡ Mass driver online"
            : b.has_mass_driver
              ? "⚡ Mass driver unpowered"
              : b.mass_driver_ok
                ? "Light well — mass driver possible"
                : "Deep well — chemical lift"
        }</p>
      </div>
    </div>
  `;
}

function bodyCascadeIntelHtml(b) {
  const depLines = (b.deposits || [])
    .map((d) => {
      if (d.detail <= 0) return null;
      if (d.detail === 1) return `· ${d.resource_hint || "anomaly"} (${d.hint})`;
      let s = `· <strong>${d.resource}</strong> (${d.hint})`;
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
      return `· <strong>${s.resource}</strong> @ ${s.region} · grade ${s.grade}${
        tons ? " · " + tons : ""
      }`;
    })
    .join("<br/>");
  return `
    <p class="cascade-section-lead">Composition intel and extraction sites. Survey probes deepen this over time.</p>
    <div class="card">
      <h3>Composition</h3>
      <p>${depLines || '<span class="muted">No composition intel yet</span>'}</p>
    </div>
    <div class="card">
      <h3>Extraction sites</h3>
      <p>${sites || '<span class="muted">None yet — survey until a site unlocks</span>'}</p>
    </div>
    ${
      b.terraform_dossier && b.terraform_dossier.level
        ? `<h2>Terraform dossier</h2>${terraformDossierHtml(b.terraform_dossier)}`
        : ""
    }
  `;
}

function bodyCascadeTasksHtml(b) {
  const fleet = state.fleet || [];
  const u = unitById(selectedUnitId);
  const unitOpts = fleet
    .filter((x) => x.kind !== "ark")
    .map(
      (x) =>
        `<option value="${x.id}" ${x.id === selectedUnitId ? "selected" : ""}>${x.name} (${x.kind}${
          x.status !== "idle" ? " · " + x.status : ""
        })</option>`
    )
    .join("");
  let tasks = "";
  if (!u || u.kind === "ark") {
    tasks = `<p class="muted">Pick a fleet unit above (survey sat, miner, hauler) to order it here.</p>`;
  } else {
    tasks = `<div id="bc-task-list" class="choice-grid"><p class="muted">Loading tasks…</p></div>`;
  }
  return `
    <p class="cascade-section-lead">
      Apply a unit’s capabilities to <strong>${b.name}</strong>. Select who acts, then issue an order.
    </p>
    <div class="card">
      <label>Acting unit
        <select id="bc-unit">${unitOpts || '<option value="">No field units — build on the ark</option>'}</select>
      </label>
    </div>
    ${tasks}
  `;
}

function bodyCascadeSiteHtml(b) {
  const stock = b.site_stockpile || {};
  const stockKeys = Object.keys(stock).filter((k) => stock[k] > 0.05 && k !== "chem_prop");
  const stockLines = Object.keys(stock)
    .sort()
    .map((k) => `· ${k}: ${stock[k]} t`)
    .join("<br/>");
  const powerMw = b.site_power_mw || 0;
  const needMw = b.mass_driver_power_need_mw || 18;
  const driverOnline = b.mass_driver_online;
  const hasDriver = b.has_mass_driver;

  let launch = "";
  if (hasDriver) {
    launch = `
      <div class="card">
        <h3>Mass driver launch</h3>
        <p class="muted">${
          driverOnline
            ? `Electric lift · ${powerMw} MW bus (need ≥${needMw} MW)`
            : `Unpowered · ${powerMw}/${needMw} MW — add solar farm or chem genset`
        }</p>
        ${
          stockKeys.length
            ? `<label>Cargo
          <select id="bc-md-resource">${stockKeys
            .map((k) => `<option value="${k}">${k} (${stock[k]} t)</option>`)
            .join("")}</select>
        </label>
        <label>Amount (t)
          <input id="bc-md-amount" type="number" value="${Math.min(20, stock[stockKeys[0]] || 10)}" min="0.1" step="1" />
        </label>
        <label>Destination
          <select id="bc-md-dest">
            <option value="ark">Colony Ark</option>
            ${(state.system.bodies || [])
              .filter((x) => x.id !== b.id)
              .map((x) => `<option value="${x.id}">${x.name}</option>`)
              .join("")}
          </select>
        </label>
        <button type="button" class="primary" id="bc-md-fire" style="width:100%;margin-top:10px" ${
          driverOnline ? "" : "disabled"
        }>${driverOnline ? "Fire mass driver" : "No power — cannot fire"}</button>`
            : `<p class="muted">Stockpile empty — mine first.</p>`
        }
      </div>`;
  } else if (b.mass_driver_ok) {
    launch = `<p class="muted">Light well — build a mass driver (ark fab) for rail lift.</p>`;
  }

  return `
    <p class="cascade-section-lead">Surface stockpile, industrial lift, and founding a project on this body.</p>
    <div class="cascade-split">
      <div class="card">
        <h3>Surface stockpile</h3>
        <p>${stockLines || '<span class="muted">Empty</span>'}</p>
      </div>
      <div class="card">
        <h3>Found project</h3>
        <label>Power
          <select id="bc-power">
            <option value="solar">Solar</option>
            <option value="chemical">Chemical</option>
            <option value="fusion">Fusion (long path)</option>
          </select>
        </label>
        <label>Habitation
          <select id="bc-hab">
            <option value="underground">Underground</option>
            <option value="surface">Surface</option>
          </select>
        </label>
        <p class="muted" id="bc-build-hint"></p>
        <button type="button" class="primary" id="bc-plan" style="width:100%;margin-top:8px">Found project here</button>
      </div>
    </div>
    ${launch}
  `;
}

async function fillBodyCascadeTasks(b) {
  const el = $("bc-task-list");
  if (!el) return;
  const u = unitById(selectedUnitId);
  if (!u || u.kind === "ark") {
    el.innerHTML = `<p class="muted">Pick a field unit to order.</p>`;
    return;
  }
  const caps = u.capabilities || [];
  const busy = unitIsBusy(u);
  const sites = b.mine_sites || [];
  const surveyingHere =
    u.status === "working" && u.order === "survey" && u.location_id === b.id;
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
  const btn = (order, label, target, resource, enabled) =>
    `<button type="button" class="order" data-order="${order}" data-target="${target}" data-resource="${
      resource || ""
    }" ${enabled ? "" : "disabled"}>${label}</button>`;

  let html = "";
  html += `<p class="muted">${u.name} · ${u.status}${u.order ? " / " + u.order : ""} · Δv ${
    u.dv_capacity_m_s > 0 ? formatDv(u.dv_remaining_m_s) + " left" : "n/a"
  }</p>`;
  if (estMove && estMove.dv_m_s != null) {
    html += `<p class="muted">Transit estimate${fmt(estMove)}${
      estMove.dv_m_s ? " · burns " + formatDv(estMove.dv_m_s) : ""
    }${estMove.can_afford_dv === false ? " · <span style='color:#e88'>insufficient Δv</span>" : ""}</p>`;
  }
  html += btn("move", `Move to ${b.name}${fmt(estMove)}`, b.id, "", !busy);
  html += btn("idle", "Stand by / recall", b.id, "", true);

  if (caps.includes("survey")) {
    html += `<h2>Scan</h2>`;
    if (surveyingHere) {
      const what = u.search_resource
        ? resNames[u.search_resource] || u.search_resource
        : "broad composition";
      const sm = u.search_resource
        ? (b.seek_months && b.seek_months[u.search_resource]) || 0
        : b.survey_months || 0;
      html += `<div class="queue-job next"><div class="title">Surveying — ${what}</div>
        <div class="meta">${Number(sm).toFixed(1)} mo on station · warp for progress</div></div>`;
    } else {
      html += btn("survey", `Scan ${b.name} (broad)`, b.id, "", !busy);
      for (const res of searchable) {
        const name = resNames[res] || res;
        if (foundRes.has(res)) {
          html += `<button type="button" class="order" disabled>Find ${name} — site found</button>`;
        } else if (exhausted.has(res)) {
          html += `<button type="button" class="order" disabled>Find ${name} — none here</button>`;
        } else {
          html += btn("survey", `Find sources of ${name}`, b.id, res, !busy);
        }
      }
    }
  }

  if (caps.includes("mine") || sites.length) {
    html += `<h2>Extraction</h2>`;
    if (!sites.length) {
      html += `<p class="muted">No mine sites yet.</p>`;
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
  }

  if (caps.includes("haul") && u.kind !== "ark") {
    html += `<h2>Logistics</h2>
      <button type="button" class="order" id="bc-haul">Plan cargo transfer involving ${b.name}</button>`;
  }

  el.innerHTML = html;
  el.querySelectorAll("[data-order]").forEach((button) => {
    button.onclick = async () => {
      try {
        await issueUnitOrder(
          u.id,
          button.dataset.order,
          button.dataset.target,
          button.dataset.resource || ""
        );
        cascade = { kind: "body", bodyId: b.id, tab: "tasks" };
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 320));
      }
    };
  });
  const haulBtn = $("bc-haul");
  if (haulBtn) {
    haulBtn.onclick = () => {
      closeCascade();
      $("panel-right").classList.remove("collapsed");
      renderHaulPanel({ preferDest: b.id, forceOpen: true });
      $("haul-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    };
  }
}

function bindBodyCascade(bodyEl, b, tab) {
  bodyEl.querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "body", bodyId: b.id, tab: btn.dataset.gotoTab, _opened: true };
      renderCascade();
    };
  });
  const tfScan = bodyEl.querySelector("#bc-start-tf-scan");
  if (tfScan) {
    tfScan.onclick = async () => {
      try {
        state = await api("/api/ark_scan_goal", {
          method: "POST",
          body: JSON.stringify({ goal_id: "habitable", enabled: true }),
        });
        $("toast").textContent =
          "Ark terraform scan enabled — Warp → event for progressive intel.";
        cascade = { kind: "body", bodyId: b.id, tab: "habitability", _opened: true };
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  }
  if (tab === "overview") {
    const fb = bodyEl.querySelector("#bc-focus");
    if (fb) fb.onclick = () => map && map.focusBody(b.id);
  }
  if (tab === "tasks") {
    const sel = bodyEl.querySelector("#bc-unit");
    if (sel) {
      sel.onchange = () => {
        selectedUnitId = sel.value || null;
        cascade = { kind: "body", bodyId: b.id, tab: "tasks" };
        renderCascade();
      };
    }
    fillBodyCascadeTasks(b);
  }
  if (tab === "site") {
    const power = bodyEl.querySelector("#bc-power");
    const hint = bodyEl.querySelector("#bc-build-hint");
    const updateHint = () => {
      if (hint && power) {
        hint.textContent =
          state.build_options?.power?.[power.value]?.description || "";
      }
    };
    if (power) power.onchange = updateHint;
    updateHint();
    const plan = bodyEl.querySelector("#bc-plan");
    if (plan) {
      plan.onclick = async () => {
        try {
          state = await api("/api/plan_base", {
            method: "POST",
            body: JSON.stringify({
              body_id: b.id,
              power_id: power?.value || "solar",
              hab_id: bodyEl.querySelector("#bc-hab")?.value || "underground",
            }),
          });
          cascade = { kind: "body", bodyId: b.id, tab: "site" };
          render();
        } catch (e) {
          alert(String(e.message || e).slice(0, 320));
        }
      };
    }
    const fire = bodyEl.querySelector("#bc-md-fire");
    if (fire) {
      fire.onclick = async () => {
        try {
          state = await api("/api/mass_launch", {
            method: "POST",
            body: JSON.stringify({
              origin_id: b.id,
              dest_id: bodyEl.querySelector("#bc-md-dest")?.value || "ark",
              resource: bodyEl.querySelector("#bc-md-resource")?.value,
              amount_t: Math.max(
                0.1,
                Number(bodyEl.querySelector("#bc-md-amount")?.value) || 1
              ),
            }),
          });
          cascade = { kind: "body", bodyId: b.id, tab: "site" };
          render();
        } catch (e) {
          alert(String(e.message || e).slice(0, 320));
        }
      };
    }
  }
}

function renderSurveyCascade(root, u) {
  root.hidden = false;
  root.querySelector(".cascade-window")?.classList.add("unit-card");
  const tab = cascade.tab || "actions";
  cascade.tab = tab;
  const loc = bodyById(u.location_id);
  const locName = loc ? loc.name : u.location_id;
  const busy = unitIsBusy(u);
  const resNames = (state.tech && state.tech.resources) || {};

  let mission = "Standing by";
  if (u.status === "en_route") {
    const dest = bodyById(u.target_id);
    const destName = dest ? dest.name : u.target_id;
    if (u.order === "survey") {
      const what = u.search_resource
        ? resNames[u.search_resource] || u.search_resource
        : "broad survey";
      mission = `En route to ${destName} (${what}) · ${u.months_left?.toFixed(1) ?? "?"} mo`;
    } else if (u.order === "move") {
      mission = `Moving to ${destName} · ${u.months_left?.toFixed(1) ?? "?"} mo`;
    } else {
      mission = `En route · ${u.months_left?.toFixed(1) ?? "?"} mo`;
    }
  } else if (u.status === "working" && u.order === "survey") {
    const what = u.search_resource
      ? `seeking ${resNames[u.search_resource] || u.search_resource}`
      : "broad composition";
    const sm = u.search_resource
      ? (loc && loc.seek_months && loc.seek_months[u.search_resource]) || 0
      : (loc && loc.survey_months) || 0;
    mission = `On station @ ${locName} · ${what} · ${Number(sm).toFixed(1)} mo`;
  }

  const dvLine =
    u.dv_capacity_m_s > 0
      ? ` · Δv ${formatDv(u.dv_remaining_m_s)} / ${formatDv(u.dv_capacity_m_s)}`
      : "";
  $("cascade-kicker").textContent = "Survey probe · action card";
  $("cascade-title").innerHTML = `${escapeHtml(u.name)} <button type="button" class="cascade-rename" id="cascade-rename" title="Edit name">✎</button>`;
  $("cascade-sub").textContent = mission + dvLine;
  const rnTitle = $("cascade-rename");
  if (rnTitle) rnTitle.onclick = (ev) => {
    ev.stopPropagation();
    promptRenameUnit(u.id);
  };

  const tabs = [
    { id: "actions", label: "Actions" },
    { id: "move", label: "Move" },
    { id: "survey", label: "Survey focus" },
  ];
  $("cascade-tabs").innerHTML = tabs
    .map(
      (t) =>
        `<button type="button" class="cascade-tab ${t.id === tab ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
    )
    .join("");
  $("cascade-tabs").querySelectorAll("[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "unit", unitId: u.id, tab: btn.dataset.tab };
      renderCascade();
    };
  });

  const body = $("cascade-body");
  if (tab === "move") body.innerHTML = surveyCascadeMoveHtml(u, loc);
  else if (tab === "survey") body.innerHTML = surveyCascadeFocusHtml(u, loc);
  else body.innerHTML = surveyCascadeActionsHtml(u, loc, mission, busy);

  bindSurveyCascade(body, u, tab);
}

function surveyCascadeActionsHtml(u, loc, mission, busy) {
  const locName = loc ? loc.name : u.location_id || "—";
  const focus = u.search_resource
    ? resName(u.search_resource)
    : u.order === "survey"
      ? "Broad composition"
      : "—";
  const home = state.home_body_id;
  const atHome = home && u.location_id === home;
  const siteBld = (loc && loc.site_buildings) || [];
  const atDepot = siteBld.includes("refuel_depot");
  const canRefuelHere = atHome || atDepot;
  const tanksLow = u.dv_capacity_m_s > 0 && u.dv_remaining_m_s < u.dv_capacity_m_s * 0.99;

  return `
    <p class="cascade-section-lead">
      Probes carry a <strong>fixed Δv budget</strong> (ion tanks). Every hop spends it.
      Return to the ark (or a refueling depot) to top off.
    </p>
    ${dvBarHtml(u)}
    <div class="card cascade-mission">
      <h3>Current mission</h3>
      <p>${mission}</p>
      <p class="muted">Location · ${locName}${u.search_resource || u.order === "survey" ? ` · focus ${focus}` : ""}</p>
    </div>
    <div class="action-stack">
      <button type="button" class="action-card" data-goto="move">
        <span class="action-title">Move to a new location</span>
        <span class="action-desc">Transit costs time and Δv. Estimate shown before you commit.</span>
      </button>
      <button type="button" class="action-card" data-goto="survey">
        <span class="action-title">Change survey priorities</span>
        <span class="action-desc">Broad scan or seek iron, ice, organics… on a chosen body.</span>
      </button>
      ${
        loc
          ? `<button type="button" class="action-card primary-action" data-quick-survey="${loc.id}" ${busy && !(u.status === "working" && u.order === "survey" && u.location_id === loc.id) ? "disabled" : ""}>
        <span class="action-title">Survey here · ${loc.name}</span>
        <span class="action-desc">Broad composition on current body (no Δv if already on station).</span>
      </button>`
          : ""
      }
      <button type="button" class="action-card primary-action" data-return-ark="1" ${busy ? "disabled" : ""}>
        <span class="action-title">Return to ark</span>
        <span class="action-desc">${
          atHome
            ? "Already at ark — tops off tanks immediately."
            : "Transit home and fully refuel Δv tanks on arrival."
        }</span>
      </button>
      ${
        canRefuelHere && tanksLow
          ? `<button type="button" class="action-card" data-refuel="1" ${busy ? "disabled" : ""}>
        <span class="action-title">Refuel here</span>
        <span class="action-desc">${atHome ? "Ark stores — free full refill." : "Depot chem_prop → Δv."}</span>
      </button>`
          : ""
      }
      <button type="button" class="action-card danger-action" data-idle="1" ${u.status === "idle" && !u.order ? "disabled" : ""}>
        <span class="action-title">Stand by / recall</span>
        <span class="action-desc">Stop surveying or cancel assignment. Free for a new order.</span>
      </button>
    </div>
  `;
}

function surveyCascadeMoveHtml(u, loc) {
  const destDefault = selectedBodyId || u.location_id || "";
  return `
    <p class="cascade-section-lead">
      Choose a destination. Travel uses orbital transfer times and burns onboard Δv.
      If tanks run dry mid-plan, return to the ark or a depot first.
    </p>
    ${dvBarHtml(u)}
    <div class="card">
      <label>Destination body
        <select id="sv-move-dest">${bodyPickerOptions(destDefault)}</select>
      </label>
      <p class="muted" id="sv-move-est" style="margin-top:8px">Estimating transit…</p>
      <button type="button" class="primary" id="sv-move-go" style="width:100%;margin-top:12px">
        Order move
      </button>
    </div>
    <p class="muted">Currently @ ${loc ? loc.name : u.location_id || "—"}</p>
  `;
}

function surveyCascadeFocusHtml(u, loc) {
  const targetDefault = selectedBodyId || u.location_id || "";
  const b = bodyById(targetDefault);
  const searchable = (b && b.searchable_resources) || ["Fe", "Si", "Al", "H2O", "CH4"];
  const exhausted = new Set((b && b.seek_exhausted) || []);
  const foundRes = new Set(((b && b.mine_sites) || []).map((s) => s.resource));
  const current = u.search_resource || "";

  const resBtns = searchable
    .map((res) => {
      const name = resName(res);
      let note = "";
      let disabled = false;
      if (foundRes.has(res)) {
        note = "site found";
        disabled = true;
      } else if (exhausted.has(res)) {
        note = "none here";
        disabled = true;
      }
      const active = current === res ? "active" : "";
      return `<button type="button" class="goal-toggle ${active}" data-res="${res}" ${disabled ? "disabled" : ""}>
        <span>
          <div class="g-title">Find sources of ${name}</div>
          <div class="g-desc">${note || "Directed search on the selected body"}</div>
        </span>
      </button>`;
    })
    .join("");

  return `
    <p class="cascade-section-lead">
      Pick where to work and what to look for. Changing focus while surveying will stand by first, then re-task.
    </p>
    <div class="card">
      <label>Target body
        <select id="sv-focus-body">${bodyPickerOptions(targetDefault)}</select>
      </label>
      <p class="muted" id="sv-focus-hint" style="margin-top:8px">
        ${b ? `${b.kind}${b.planet_class ? " / " + b.planet_class : ""} · ${b.survey_months != null ? b.survey_months.toFixed(1) + " mo surveyed" : ""}` : "Select a body"}
      </p>
    </div>
    <h2>Priorities on this body</h2>
    <div class="priority-grid" id="sv-focus-list">
      <button type="button" class="goal-toggle ${!current && u.order === "survey" ? "active" : ""}" data-res="">
        <span>
          <div class="g-title">Broad composition survey</div>
          <div class="g-desc">General intel until mine sites appear</div>
        </span>
      </button>
      ${resBtns}
    </div>
  `;
}

function bindSurveyCascade(bodyEl, u, tab) {
  const reOpen = (t) => {
    cascade = { kind: "unit", unitId: u.id, tab: t || tab };
    render();
  };

  bodyEl.querySelectorAll("[data-goto]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "unit", unitId: u.id, tab: btn.dataset.goto };
      renderCascade();
    };
  });

  const idleBtn = bodyEl.querySelector("[data-idle]");
  if (idleBtn) {
    idleBtn.onclick = async () => {
      try {
        await issueUnitOrder(u.id, "idle");
        reOpen("actions");
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  }

  const retBtn = bodyEl.querySelector("[data-return-ark]");
  if (retBtn) {
    retBtn.onclick = async () => {
      try {
        if (unitIsBusy(u)) await issueUnitOrder(u.id, "idle");
        await issueUnitOrder(u.id, "return_ark");
        reOpen("actions");
      } catch (e) {
        alert(String(e.message || e).slice(0, 320));
      }
    };
  }

  const refuelBtn = bodyEl.querySelector("[data-refuel]");
  if (refuelBtn) {
    refuelBtn.onclick = async () => {
      try {
        await issueUnitOrder(u.id, "refuel");
        reOpen("actions");
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  }

  const quick = bodyEl.querySelector("[data-quick-survey]");
  if (quick) {
    quick.onclick = async () => {
      try {
        const target = quick.dataset.quickSurvey;
        if (u.status === "working" && u.order === "survey") {
          await issueUnitOrder(u.id, "idle");
        }
        await issueUnitOrder(u.id, "survey", target, "");
        reOpen("actions");
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  }

  if (tab === "move") {
    const destSel = bodyEl.querySelector("#sv-move-dest");
    const estEl = bodyEl.querySelector("#sv-move-est");
    const go = bodyEl.querySelector("#sv-move-go");
    const updateEst = async () => {
      if (!destSel || !estEl) return;
      try {
        const est = await api("/api/estimate_order", {
          method: "POST",
          body: JSON.stringify({
            unit_id: u.id,
            order: "move",
            target_id: destSel.value,
          }),
        });
        let time = "";
        if (est.years >= 0.5) {
          time = `~${est.years.toFixed(2)} y (${est.months.toFixed(1)} mo)`;
        } else if (est.months >= 1) {
          time = `~${est.months.toFixed(1)} mo`;
        } else {
          time = `~${Math.max(1, Math.round(est.months * 30))} d`;
        }
        const dv = est.dv_m_s != null ? formatDv(est.dv_m_s) : "—";
        const after =
          est.dv_after_m_s != null ? ` → ${formatDv(est.dv_after_m_s)} left` : "";
        const ok = est.can_afford_dv !== false;
        estEl.innerHTML = ok
          ? `Transit ${time} · burns <strong>${dv}</strong> Δv${after}`
          : `<span style="color:#e88">Need ${dv} Δv — only ${formatDv(
              est.dv_remaining_m_s
            )} left. Return to ark or depot.</span>`;
        if (go) go.disabled = !ok;
      } catch (_) {
        estEl.textContent = "Could not estimate transit.";
      }
    };
    if (destSel) destSel.onchange = updateEst;
    updateEst();
    if (go) {
      go.onclick = async () => {
        try {
          if (unitIsBusy(u) && u.order === "survey") {
            await issueUnitOrder(u.id, "idle");
          }
          await issueUnitOrder(u.id, "move", destSel.value);
          selectedBodyId = destSel.value;
          reOpen("actions");
        } catch (e) {
          alert(String(e.message || e).slice(0, 320));
        }
      };
    }
  }

  if (tab === "survey") {
    const bodySel = bodyEl.querySelector("#sv-focus-body");
    if (bodySel) {
      bodySel.onchange = () => {
        selectedBodyId = bodySel.value;
        // Re-render focus tab with new body's searchable resources
        cascade = { kind: "unit", unitId: u.id, tab: "survey" };
        renderCascade();
      };
    }
    bodyEl.querySelectorAll("[data-res]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const target = bodySel ? bodySel.value : u.location_id;
          const res = btn.dataset.res || "";
          if (unitIsBusy(u)) {
            await issueUnitOrder(u.id, "idle");
          }
          await issueUnitOrder(u.id, "survey", target, res);
          selectedBodyId = target;
          reOpen("actions");
        } catch (e) {
          alert(String(e.message || e).slice(0, 280));
        }
      };
    });
  }
}

function renderGenericUnitCascade(root, u) {
  root.hidden = false;
  root.querySelector(".cascade-window")?.classList.add("unit-card");
  cascade.tab = "actions";
  const loc = bodyById(u.location_id);
  const kindLabel =
    u.kind === "miner" ? "Mining bot" : u.kind === "hauler" ? "Hauler" : u.kind;
  $("cascade-kicker").textContent = `${kindLabel} · action card`;
  $("cascade-title").innerHTML = `${escapeHtml(u.name)} <button type="button" class="cascade-rename" id="cascade-rename" title="Edit name">✎</button>`;
  $("cascade-sub").textContent = `${u.status}${u.order ? " / " + u.order : ""} · @ ${
    loc ? loc.name : u.location_id
  }${u.dv_capacity_m_s > 0 ? " · Δv " + formatDv(u.dv_remaining_m_s) : ""}`;
  const rnTitle = $("cascade-rename");
  if (rnTitle) rnTitle.onclick = (ev) => {
    ev.stopPropagation();
    promptRenameUnit(u.id);
  };
  $("cascade-tabs").innerHTML = `<button type="button" class="cascade-tab active" data-tab="actions">Actions</button>`;
  $("cascade-body").innerHTML = `
    ${dvBarHtml(u)}
    <p class="cascade-section-lead">
      Select a body on the map, open its card → <strong>Tasks</strong>, and assign this unit.
    </p>
    <div class="action-stack">
      <button type="button" class="action-card danger-action" id="gen-idle">
        <span class="action-title">Stand by</span>
        <span class="action-desc">Clear current assignment if any.</span>
      </button>
    </div>
  `;
  const idle = $("gen-idle");
  if (idle) {
    idle.onclick = async () => {
      try {
        await issueUnitOrder(u.id, "idle");
        cascade = { kind: "unit", unitId: u.id, tab: "actions" };
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 280));
      }
    };
  }
}

function renderArkCascade(root) {
  root.hidden = false;
  root.querySelector(".cascade-window")?.classList.remove("unit-card");
  const tab = cascade.tab || "survey";
  cascade.tab = tab;

  const ark = unitById("ark") || (state.fleet || []).find((u) => u.kind === "ark");
  const arkName = ark ? ark.name : "Colony Ark";
  $("cascade-kicker").textContent = "Colony ship · command console";
  $("cascade-title").textContent = arkName;
  const home = bodyById(state.home_body_id);
  const pop = (state.population || 0).toLocaleString();
  $("cascade-sub").textContent = home
    ? `Parked at ${home.name} · ${pop} souls · seed industry online`
    : `${pop} souls · seed industry online`;

  const tabs = [
    { id: "survey", label: "Survey priorities" },
    { id: "fab", label: "Fabrication" },
    { id: "cargo", label: "Cargo" },
    { id: "status", label: "Status" },
  ];
  $("cascade-tabs").innerHTML = tabs
    .map(
      (t) =>
        `<button type="button" class="cascade-tab ${t.id === tab ? "active" : ""}" data-tab="${t.id}">${t.label}</button>`
    )
    .join("");
  $("cascade-tabs").querySelectorAll("[data-tab]").forEach((btn) => {
    btn.onclick = () => {
      cascade = { kind: "ark", tab: btn.dataset.tab };
      renderCascade();
    };
  });

  // Edit name on the detail card header (next to title)
  const titleEl = $("cascade-title");
  if (titleEl) {
    titleEl.innerHTML = `${escapeHtml(arkName)} <button type="button" class="cascade-rename" id="cascade-rename" title="Edit name">✎</button>`;
    const rn = $("cascade-rename");
    if (rn) rn.onclick = (ev) => {
      ev.stopPropagation();
      promptRenameUnit(ark ? ark.id : "ark");
    };
  }

  const body = $("cascade-body");
  if (tab === "survey") body.innerHTML = arkCascadeSurveyHtml();
  else if (tab === "fab") body.innerHTML = arkCascadeFabHtml();
  else if (tab === "cargo") body.innerHTML = arkCascadeCargoHtml();
  else body.innerHTML = arkCascadeStatusHtml();

  bindArkCascade(body, tab);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function factorStatusClass(st) {
  if (st === "ok") return "tf-ok";
  if (st === "need_build") return "tf-build";
  if (st === "hard") return "tf-hard";
  if (st === "no") return "tf-no";
  return "tf-unknown";
}

function factorStatusLabel(st) {
  return (
    {
      ok: "OK",
      hard: "Hard",
      need_build: "Build",
      no: "No",
      unknown: "?",
    }[st] || st
  );
}

function terraformDossierHtml(d, { compact = false } = {}) {
  if (!d) return "";
  const vs = d.verdict_status || "unknown";
  const factors = d.factors || [];
  const factorRows = factors
    .map((f) => {
      const cls = factorStatusClass(f.status);
      return `<div class="tf-factor ${cls}">
        <span class="tf-badge">${factorStatusLabel(f.status)}</span>
        <span class="tf-body">
          <strong>${f.label}</strong>
          <span class="tf-value">${f.known ? f.value : "not surveyed yet"}</span>
          <span class="tf-fix">${f.fix || ""}</span>
        </span>
      </div>`;
    })
    .join("");
  const path = (d.path || [])
    .map((p) => `<li>${p}</li>`)
    .join("");
  const score =
    d.terraform_score != null
      ? `<div class="meta">Terraform score <strong>${d.terraform_score}/10</strong> · survey ${d.level}/${d.level_max}</div>`
      : `<div class="meta">Survey depth ${d.level || 0}/${d.level_max || 5} — complete to unlock full score</div>`;

  if (compact) {
    return `<div class="tf-verdict ${factorStatusClass(vs)}">${d.verdict || "—"}</div>`;
  }

  return `<div class="card tf-card" style="margin-bottom:8px">
    <h3>Habitability · ${d.name || d.body_id}</h3>
    <div class="tf-verdict ${factorStatusClass(vs)}">${d.verdict || "—"}</div>
    ${score}
    <div class="tf-factors">${factorRows}</div>
    ${
      path
        ? `<h2 style="margin-top:12px">What it would take</h2><ul class="tf-path">${path}</ul>`
        : ""
    }
    ${
      d.level < 5
        ? `<p class="muted" style="margin-top:10px">${d.how_to_survey || ""}</p>`
        : ""
    }
  </div>`;
}

function arkCascadeSurveyHtml() {
  const specs = state.ark_scan_goal_specs || {};
  const active = new Set(state.ark_scan_goals || []);
  const n = active.size;
  const goals = Object.values(specs)
    .map((s) => {
      const on = active.has(s.id);
      return `<label class="goal-toggle ${on ? "active" : ""}">
        <input type="checkbox" data-goal="${s.id}" ${on ? "checked" : ""} />
        <span>
          <div class="g-title">${s.label}</div>
          <div class="g-desc">${s.description || ""}</div>
        </span>
      </label>`;
    })
    .join("");
  const dossiers = Object.values(state.terraform_dossiers || {})
    .sort((a, b) => (b.level || 0) - (a.level || 0))
    .map((d) => terraformDossierHtml(d))
    .join("");
  return `
    <p class="cascade-section-lead">
      System-wide priorities. Terraform targets are scanned for <strong>surface g</strong>, <strong>atmosphere</strong>,
      <strong>water</strong>, <strong>active core</strong>, and <strong>magnetic field</strong>.
      Worlds without a magnetosphere need an artificial <strong>L1 radiation shield</strong> before open-air settlement.
      ${n ? `<strong>${n} goal(s) active.</strong>` : "None active yet."}
    </p>
    <div class="priority-grid">${goals || '<p class="empty">No scan goals defined.</p>'}</div>
    <h2 style="margin-top:18px">Terraform dossiers</h2>
    ${dossiers || '<p class="muted">Enable “Find terraform / habitability targets” and warp for progressive intel.</p>'}
  `;
}

function arkCascadeFabHtml() {
  const builds = state.builds || [];
  const busy = builds.length > 0;
  let queueHtml;
  if (!builds.length) {
    queueHtml =
      '<div class="queue-empty">Fabrication bay idle — one job at a time. Authorize construction below.</div>';
  } else {
    queueHtml = builds
      .map((j) => {
        const total = j.months_total || 1;
        const left = Math.max(0, j.months_left || 0);
        const done = Math.min(100, ((total - left) / total) * 100);
        const deploy = j.deploy_body_id
          ? ` · deploy @ ${bodyById(j.deploy_body_id)?.name || j.deploy_body_id}`
          : "";
        return `<div class="queue-job next">
          <div class="title">${j.name}</div>
          <div class="meta">Bay occupied · ${left.toFixed(1)} mo of ${total.toFixed(1)} mo${deploy} · warp to finish</div>
          <div class="queue-bar"><i style="width:${done.toFixed(1)}%"></i></div>
        </div>`;
      })
      .join("");
  }
  const specs = state.unit_builds || {};
  const cards = Object.values(specs)
    .map((s) => {
      const cost = Object.entries(s.cost || {})
        .map(([k, v]) => `${v} t ${k}`)
        .join(", ");
      const dv =
        s.dv_capacity_m_s > 0
          ? ` · Δv tank ${formatDv(s.dv_capacity_m_s)}`
          : "";
      return `<div class="card">
        <h3>${s.name}</h3>
        <p>${s.description || ""}</p>
        <p class="muted">${cost} · ${s.months} mo in bay${dv}</p>
        <button type="button" class="primary" data-build="${s.id}" ${busy ? "disabled" : ""}>
          ${busy ? "Bay busy" : "Build in bay"}
        </button>
      </div>`;
    })
    .join("");

  const structs = state.structure_builds || {};
  const bodies = (state.system && state.system.bodies) || [];
  const structCards = Object.values(structs)
    .map((s) => {
      const cost = Object.entries(s.cost || {})
        .map(([k, v]) => `${v} t ${k}`)
        .join(", ");
      // Filter deploy targets by structure type
      let destOpts;
      if (s.id === "mass_driver") {
        const light = bodies.filter((b) => b.mass_driver_ok);
        destOpts = light.length
          ? light
              .map(
                (b) =>
                  `<option value="${b.id}" ${
                    b.id === selectedBodyId ? "selected" : ""
                  }>${b.name} (↑${b.dv_to_orbit_m_s} m/s)</option>`
              )
              .join("")
          : `<option value="">No light bodies available</option>`;
      } else if (s.id === "l1_magnetic_shield") {
        const rocky = bodies.filter(
          (b) =>
            b.planet_class === "rocky" ||
            b.kind === "moon" ||
            (b.kind === "planet" && b.planet_class === "rocky")
        );
        destOpts = rocky.length
          ? rocky
              .map((b) => {
                const d = (state.terraform_dossiers || {})[b.id];
                const need =
                  d && d.level >= 5 && d.needs_l1_magnetic_shield
                    ? " · needs shield"
                    : d && d.level >= 5 && d.has_magnetosphere
                      ? " · has field"
                      : "";
                return `<option value="${b.id}" ${
                  b.id === selectedBodyId ? "selected" : ""
                }>${b.name}${need}</option>`;
              })
              .join("")
          : `<option value="">No rocky targets</option>`;
      } else {
        destOpts = bodyPickerOptions(selectedBodyId || state.home_body_id || "");
      }
      return `<div class="card">
        <h3>${s.name}</h3>
        <p>${s.description || ""}</p>
        <p class="muted">${cost} · ${s.months} mo · deploys to a body</p>
        <label>Deploy on
          <select data-struct-dest="${s.id}" ${busy ? "disabled" : ""}>${destOpts}</select>
        </label>
        <button type="button" class="primary" data-struct="${s.id}" style="margin-top:8px;width:100%" ${busy ? "disabled" : ""}>
          ${busy ? "Bay busy" : "Build in bay"}
        </button>
      </div>`;
    })
    .join("");

  return `
    <p class="cascade-section-lead">
      One fabrication bay — only <strong>one job at a time</strong>. Finish (warp) the current job before authorizing the next.
      Structures: <strong>power</strong> (solar / genset), <strong>mining</strong> (extractor),
      <strong>lift</strong> (mass driver or launch pad + rocket fab + fuel + recovery),
      <strong>habitat</strong>, depots, L1 shield. See the Process board for goals.
    </p>
    <h2>Bay (single berth)</h2>
    <div class="queue-list">${queueHtml}</div>
    <h2>Fleet units</h2>
    <div class="cascade-grid">${cards}</div>
    <h2>Site structures</h2>
    <div class="cascade-grid">${structCards || '<p class="empty">None</p>'}</div>
  `;
}

function arkCascadeCargoHtml() {
  const s = state.ark_stock || {};
  const chips = Object.keys(s)
    .sort()
    .map(
      (k) =>
        `<div class="chip"><span class="k">${k}</span><span class="v">${Number(s[k]).toFixed(1)} t</span></div>`
    )
    .join("");
  return `
    <p class="cascade-section-lead">
      Seed stock and anything hauled back to the ark. Propellant (chem_prop) is burned on cargo transfers.
      The ark also trickle-fabs steel, chips, panels, and prop from atoms when inputs allow.
    </p>
    <div class="cascade-stock">${chips || '<p class="empty">Empty holds</p>'}</div>
    <p class="muted" style="margin-top:14px">
      For interplanetary moves, select a hauler (or the ark) and use <strong>Cargo transfer</strong> on the right panel.
    </p>
  `;
}

function arkCascadeStatusHtml() {
  const fleet = state.fleet || [];
  const byKind = {};
  for (const u of fleet) byKind[u.kind] = (byKind[u.kind] || 0) + 1;
  const goals = (state.ark_scan_goals || [])
    .map((g) => (state.ark_scan_goal_specs || {})[g]?.label || g)
    .join(" · ");
  const builds = (state.builds || []).length;
  const hauls = (state.hauls || []).length;
  const home = bodyById(state.home_body_id);
  return `
    <div class="cascade-split">
      <div class="card">
        <h3>Ship</h3>
        <p><strong>Population</strong> ${(state.population || 0).toLocaleString()}</p>
        <p><strong>Orbit</strong> ${home ? home.name : "—"}</p>
        <p><strong>Sim time</strong> ${(state.sim_years || 0).toFixed(2)} y in-system</p>
        <p class="muted">Xe spent on capture — ion tanks dry.</p>
      </div>
      <div class="card">
        <h3>Operations</h3>
        <p><strong>Fleet</strong> ${Object.entries(byKind)
          .map(([k, n]) => `${n} ${k}`)
          .join(", ") || "ark only"}</p>
        <p><strong>Fab jobs</strong> ${builds} in bay</p>
        <p><strong>Hauls in flight</strong> ${hauls}</p>
        <p><strong>Scan goals</strong> ${goals || "none set"}</p>
      </div>
    </div>
    <p class="cascade-section-lead" style="margin-top:14px">
      Apply unit capabilities on the map: select a survey sat or miner, click a body, give an order.
      The ark is the command node — priorities and fabrication live here.
    </p>
  `;
}

function bindArkCascade(body, tab) {
  if (tab === "survey") {
    body.querySelectorAll("[data-goal]").forEach((inp) => {
      inp.onchange = async () => {
        try {
          state = await api("/api/ark_scan_goal", {
            method: "POST",
            body: JSON.stringify({ goal_id: inp.dataset.goal, enabled: inp.checked }),
          });
          selectedUnitId = "ark";
          cascade = { kind: "ark", tab: "survey" };
          render();
        } catch (e) {
          alert(String(e.message || e).slice(0, 280));
          inp.checked = !inp.checked;
        }
      };
    });
  }
  if (tab === "fab") {
    body.querySelectorAll("[data-build]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          selectedUnitId = "ark";
          state = await api("/api/build", {
            method: "POST",
            body: JSON.stringify({ unit_kind: btn.dataset.build }),
          });
          cascade = { kind: "ark", tab: "fab" };
          render();
        } catch (e) {
          alert(String(e.message || e).slice(0, 280));
        }
      };
    });
    body.querySelectorAll("[data-struct]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const sid = btn.dataset.struct;
          const sel = body.querySelector(`[data-struct-dest="${sid}"]`);
          const deploy = sel ? sel.value : state.home_body_id || "";
          selectedUnitId = "ark";
          state = await api("/api/build", {
            method: "POST",
            body: JSON.stringify({ unit_kind: sid, deploy_body_id: deploy }),
          });
          cascade = { kind: "ark", tab: "fab" };
          render();
        } catch (e) {
          alert(String(e.message || e).slice(0, 320));
        }
      };
    });
  }
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
      const isArk = u.kind === "ark";
      const isSurvey = u.kind === "survey";
      let locLabel = "ark";
      if (u.location_id === "ark" || u.location_id === "ark_orbit") {
        const home = bodyById(state.home_body_id);
        locLabel = home ? `ark @ ${home.name}` : "ark";
      } else {
        const loc = bodyById(u.location_id);
        locLabel = loc ? loc.name : u.location_id;
      }
      const busy =
        u.status === "en_route"
          ? `<div class="meta busy">en route ${u.months_left ? u.months_left + " mo" : ""} · path on map</div>`
          : u.status !== "idle"
            ? `<div class="meta busy">${u.status} ${u.order || ""} ${u.months_left ? u.months_left + " mo" : ""}</div>`
            : `<div class="meta">@ ${locLabel} · click for card</div>`;
      return `<button type="button" class="fleet-item ${isArk ? "ark-item" : ""} ${
        isSurvey ? "survey-item" : ""
      } ${selectedUnitId === u.id ? "selected" : ""}" data-unit="${u.id}">
        <div class="name">${u.name}</div>
        <div class="meta">${u.kind}</div>${busy}
      </button>`;
    })
    .join("") || '<p class="empty">No fleet</p>';
  el.querySelectorAll("[data-unit]").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.dataset.unit;
      const u = unitById(id);
      selectedUnitId = id;
      $("panel-left").classList.remove("collapsed");
      if (u && u.kind === "ark") {
        openArkCascade();
      } else if (u) {
        openUnitCascade(u.id, "actions");
      } else {
        if (cascade) cascade = null;
        render();
      }
    };
  });
  // Soft default select ark (does not auto-open console — click opens cascade)
  if (!selectedUnitId && fleet.some((u) => u.kind === "ark")) {
    selectedUnitId = "ark";
  }
}

function renderUnitPanel() {
  const el = $("unit-panel");
  if (!el || state.phase !== "system") return;
  const u = unitById(selectedUnitId);
  if (!u) {
    el.hidden = false;
    el.className = "empty";
    el.textContent = "Select a unit from the fleet list";
    return;
  }
  if (u.kind === "ark") {
    el.hidden = false;
    el.className = "card";
    const goals = (state.ark_scan_goals || []).length;
    const jobs = (state.builds || []).length;
    el.innerHTML = `<h3>${u.name}</h3>
      <p class="muted">Command node · survey priorities, fab bay, cargo</p>
      <p>${goals} scan goal${goals === 1 ? "" : "s"} · ${jobs} fab job${jobs === 1 ? "" : "s"}</p>
      <button type="button" class="primary open-cascade-btn" id="btn-open-ark">
        Open ark command console
      </button>`;
    const b = $("btn-open-ark");
    if (b) b.onclick = () => openArkCascade();
    return;
  }
  if (u.kind === "survey") {
    el.hidden = false;
    el.className = "card";
    const loc = bodyById(u.location_id);
    el.innerHTML = `<h3>${u.name}</h3>
      <p class="muted">Survey probe · fixed Δv tanks</p>
      <p>@ ${loc ? loc.name : u.location_id} · ${u.status}${u.order ? " / " + u.order : ""}</p>
      ${dvBarHtml(u)}
      <button type="button" class="primary open-cascade-btn" id="btn-open-survey">
        Open probe actions
      </button>`;
    const b = $("btn-open-survey");
    if (b) b.onclick = () => openUnitCascade(u.id, "actions");
    return;
  }
  el.hidden = false;
  const loc = bodyById(u.location_id);
  el.className = "card";
  el.innerHTML = `<h3>${u.name}</h3>
    <p>${u.kind} · ${(u.capabilities || []).join(", ")}</p>
    <p>@ ${loc ? loc.name : u.location_id}</p>
    <p>${u.status}${u.order ? " / " + u.order : ""}</p>
    <button type="button" class="primary open-cascade-btn" id="btn-open-unit">Open unit card</button>`;
  const open = $("btn-open-unit");
  if (open) open.onclick = () => openUnitCascade(u.id, "actions");
}

function renderBodyPanel() {
  const el = $("body-panel");
  if (!el || state.phase !== "system") return;
  const b = bodyById(selectedBodyId);
  if (!b) {
    el.className = "empty";
    el.textContent = "Click a body — opens its command card over the map";
    return;
  }
  // Compact strip: details live in the cascade card
  el.className = "card";
  el.innerHTML = `<h3>${b.name}</h3>
    <p class="muted">${b.kind}${b.planet_class ? " / " + b.planet_class : ""} · card opens on select</p>
    <button type="button" class="primary open-cascade-btn" id="btn-open-body-card">
      Open body card
    </button>`;
  const btn = $("btn-open-body-card");
  if (btn) btn.onclick = () => openBodyCascade(b.id);
}

async function renderOrders() {
  const panel = $("orders-panel");
  if (panel) panel.hidden = true;
}


function renderBuild() {
  const panel = $("build-panel");
  if (!panel || state.phase !== "system") return;
  // Found-project UI lives on the body card (Site & lift tab)
  panel.hidden = true;
}

function renderHaulsList() {
  const el = $("hauls-list");
  if (!el || state.phase !== "system") {
    if (el) el.innerHTML = "";
    return;
  }
  const hauls = state.hauls || [];
  if (!hauls.length) {
    el.innerHTML = '<div class="queue-empty">No cargo in flight.</div>';
    return;
  }
  const resNames = (state.tech && state.tech.resources) || {};
  el.innerHTML = hauls
    .map((h) => {
      const res = resNames[h.resource] || h.resource;
      const dest = bodyById(h.dest_id);
      const destName =
        h.dest_id === "ark" || h.dest_id === "ark_orbit"
          ? "ark"
          : dest
            ? dest.name
            : h.dest_id;
      const total = h.months_total || 1;
      const left = Math.max(0, h.months_left || 0);
      const done = Math.min(100, ((total - left) / total) * 100);
      const unit = unitById(h.unit_id);
      return `<div class="queue-job">
        <div class="title">${h.amount_t} t ${res} → ${destName}</div>
        <div class="meta">${h.option_name} · Δv ${Math.round(h.dv_m_s)} m/s · ${h.propellant_t} t prop${
          unit ? " · " + unit.name : ""
        } · ${left.toFixed(1)} mo left</div>
        <div class="queue-bar"><i style="width:${done.toFixed(1)}%"></i></div>
      </div>`;
    })
    .join("");
}

/** Cargo transfer panel — Economy / Expedited / Sprint. */
function renderHaulPanel(opts = {}) {
  const panel = $("haul-panel");
  if (!panel || state.phase !== "system") {
    if (panel) panel.hidden = true;
    return;
  }
  const u = unitById(selectedUnitId);
  const canHaul =
    u &&
    (u.capabilities || []).includes("haul") &&
    (u.status === "idle" || u.kind === "ark");
  // Show when a hauler/ark is selected, or user opened it from a body task
  if (!canHaul && !opts.forceOpen) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;

  const bodies = (state.system && state.system.bodies) || [];
  const originSel = $("haul-origin");
  const destSel = $("haul-dest");
  const resSel = $("haul-resource");
  const amountInp = $("haul-amount");
  const optsEl = $("haul-opts");
  if (!originSel || !destSel || !resSel || !amountInp || !optsEl) return;

  const prevOrigin = originSel.value;
  const prevDest = destSel.value || opts.preferDest || selectedBodyId || "";
  const prevRes = resSel.value;

  // Origins: ark + bodies with stock
  const origins = [{ id: "ark", label: "Colony Ark (orbit stock)" }];
  for (const b of bodies) {
    const stock = b.site_stockpile || {};
    const keys = Object.keys(stock).filter((k) => stock[k] > 0);
    if (keys.length) {
      const rail = b.mass_driver_online
        ? " ⚡rail"
        : b.has_mass_driver
          ? " ⚡unpowered"
          : "";
      origins.push({
        id: b.id,
        label: `${b.name} stockpile${rail} (${keys.map((k) => k + " " + stock[k]).join(", ")})`,
      });
    }
  }
  originSel.innerHTML = origins
    .map((o) => `<option value="${o.id}">${o.label}</option>`)
    .join("");
  if (origins.some((o) => o.id === prevOrigin)) originSel.value = prevOrigin;
  else if (u && u.kind !== "ark" && origins.some((o) => o.id === u.location_id)) {
    originSel.value = u.location_id;
  }

  destSel.innerHTML =
    `<option value="ark">Colony Ark</option>` +
    bodies
      .map((b) => `<option value="${b.id}">${b.name} (${b.kind})</option>`)
      .join("");
  if (prevDest && [...destSel.options].some((o) => o.value === prevDest)) {
    destSel.value = prevDest;
  } else if (selectedBodyId) {
    destSel.value = selectedBodyId;
  }

  function fillResources() {
    const oid = originSel.value;
    let stock = {};
    if (oid === "ark") stock = state.ark_stock || {};
    else {
      const b = bodyById(oid);
      stock = (b && b.site_stockpile) || {};
    }
    const keys = Object.keys(stock)
      .filter((k) => stock[k] > 0.05 && k !== "chem_prop")
      .sort();
    // Always list common cargo even if zero so player sees the menu; disable empty later
    const extras = ["Fe", "steel", "H2O", "CH4", "panel", "chip", "Al", "Si"];
    const all = [...new Set([...keys, ...extras])];
    resSel.innerHTML = all
      .map((k) => {
        const have = stock[k] || 0;
        return `<option value="${k}" ${have < 0.05 ? "disabled" : ""}>${k} (${have.toFixed(1)} t)</option>`;
      })
      .join("");
    if (all.includes(prevRes) && (stock[prevRes] || 0) > 0.05) resSel.value = prevRes;
    else if (keys[0]) resSel.value = keys[0];
  }
  fillResources();
  originSel.onchange = () => {
    fillResources();
    optsEl.innerHTML = "";
  };
  destSel.onchange = () => {
    optsEl.innerHTML = "";
  };

  $("btn-haul-opts").onclick = async () => {
    try {
      const origin = originSel.value;
      const dest = destSel.value;
      if (origin === dest) {
        optsEl.innerHTML = '<p class="muted">Origin and destination must differ.</p>';
        return;
      }
      const data = await api("/api/haul_options", {
        method: "POST",
        body: JSON.stringify({ origin_id: origin, dest_id: dest }),
      });
      const options = data.options || [];
      if (!options.length) {
        optsEl.innerHTML = '<p class="muted">No transfer path.</p>';
        return;
      }
      const amount = Math.max(0.1, Number(amountInp.value) || 10);
      const resource = resSel.value;
      optsEl.innerHTML = options
        .map(
          (o, i) => `<button type="button" class="order haul-opt" data-idx="${i}">
          <strong>${o.name}</strong><br/>
          <span class="muted">${o.propellant_t} t prop · ${o.months.toFixed(1)} mo · Δv ${Math.round(
            o.dv_m_s
          )} m/s</span><br/>
          <span class="muted">${o.description || ""}</span>
        </button>`
        )
        .join("");
      optsEl.querySelectorAll(".haul-opt").forEach((btn) => {
        btn.onclick = async () => {
          try {
            const contractId = panel.getAttribute("data-contract") || null;
            state = await api("/api/start_haul", {
              method: "POST",
              body: JSON.stringify({
                origin_id: origin,
                dest_id: dest,
                resource,
                amount_t: amount,
                option_index: Number(btn.dataset.idx),
                unit_id: u && u.kind !== "ark" ? u.id : "",
                contract_id: contractId || undefined,
              }),
            });
            panel.removeAttribute("data-contract");
            optsEl.innerHTML = "";
            render();
          } catch (e) {
            alert(String(e.message || e).slice(0, 320));
          }
        };
      });
    } catch (e) {
      optsEl.innerHTML = `<p class="muted">${String(e.message || e).slice(0, 200)}</p>`;
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
  const resNames = (state.tech && state.tech.resources) || {};
  el.innerHTML = open.length
    ? open
        .map((c) => {
          const proj = (state.projects || []).find((p) => p.id === c.project_id);
          const body = proj ? bodyById(proj.body_id) : null;
          return `<div class="card">
      <h3>${c.title}</h3>
      <p>${c.resource_name || resNames[c.resource] || c.resource}: ${c.delivered_t}/${c.amount_t} t</p>
      ${c.note ? `<p class="muted">${c.note}</p>` : ""}
      <button data-deliver="${c.id}">From ark (local bootstrap)</button>
      ${
        body
          ? `<button data-haul-contract="${c.id}" data-dest="${proj.body_id}" data-res="${c.resource}" data-amt="${Math.max(
              0.1,
              c.amount_t - c.delivered_t
            )}">Haul to ${body.name}…</button>`
          : ""
      }
    </div>`;
        })
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
  el.querySelectorAll("[data-haul-contract]").forEach((btn) => {
    btn.onclick = async () => {
      // Prefill haul panel: ark → project body for this need
      selectedBodyId = btn.dataset.dest;
      const freeHauler = (state.fleet || []).find(
        (u) => u.kind === "hauler" && u.status === "idle"
      );
      if (freeHauler) selectedUnitId = freeHauler.id;
      else selectedUnitId = "ark";
      renderHaulPanel({ preferDest: btn.dataset.dest, forceOpen: true });
      const resSel = $("haul-resource");
      const amountInp = $("haul-amount");
      const originSel = $("haul-origin");
      const destSel = $("haul-dest");
      if (originSel) originSel.value = "ark";
      if (destSel) destSel.value = btn.dataset.dest;
      if (resSel) {
        // re-render fills options; set after
        setTimeout(() => {
          if ($("haul-resource")) $("haul-resource").value = btn.dataset.res;
          if ($("haul-amount")) $("haul-amount").value = btn.dataset.amt;
          $("haul-panel")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }, 0);
      }
      if (amountInp) amountInp.value = btn.dataset.amt;
      // Store contract id for next start_haul via data on panel
      $("haul-panel")?.setAttribute("data-contract", btn.dataset.haulContract);
      $("panel-right").classList.remove("collapsed");
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

// Cascade close
const cascadeClose = $("cascade-close");
if (cascadeClose) cascadeClose.onclick = () => closeCascade();
const cascadeBackdrop = $("cascade-backdrop");
if (cascadeBackdrop) cascadeBackdrop.onclick = () => closeCascade();
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && cascade) {
    ev.preventDefault();
    closeCascade();
  }
});

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

async function doWarp({ force = false } = {}) {
  const res = await api("/api/warp", {
    method: "POST",
    body: JSON.stringify({ force: !!force }),
  });
  return res;
}

$("btn-warp").onclick = async () => {
  const btn = $("btn-warp");
  if (btn) btn.disabled = true;
  try {
    let res = await doWarp({ force: false });
    let w = res.warp || {};

    if (w.needs_confirm) {
      const n = w.next_event || {};
      const when =
        n.years >= 0.5
          ? `${n.years.toFixed(2)} years`
          : n.months >= 1
            ? `${(n.months || 0).toFixed(2)} months`
            : `${Math.round((n.months || 0) * 30)} days`;
      const ok = window.confirm(
        `Long warp confirmation\n\n` +
          `${w.message || "Skip ahead?"}\n\n` +
          `Jump ${when} to:\n“${n.label || "next event"}”\n\n` +
          `OK = advance time · Cancel = stay (no time lost)`
      );
      if (!ok) {
        $("toast").textContent = "Warp cancelled — no time skipped.";
        state = res;
        renderNextEvent();
        return;
      }
      res = await doWarp({ force: true });
      w = res.warp || {};
    }

    state = res;
    if (w.message) state.message = w.message;
    if (w.reason === "idle") {
      $("toast").textContent =
        w.message || "Nothing queued — no time skipped.";
    } else if (w.warped_months > 0 || w.reason === "next_event") {
      $("toast").textContent = w.message || "Warped.";
    }
    render();
  } catch (e) {
    console.error("warp failed", e);
    $("toast").textContent = "Warp failed: " + String(e.message || e).slice(0, 200);
    alert("Warp failed: " + String(e.message || e).slice(0, 280));
  } finally {
    if (btn) btn.disabled = false;
  }
};
if ($("btn-warp-transit")) {
  $("btn-warp-transit").onclick = () => $("btn-warp") && $("btn-warp").click();
}
$("btn-reset").onclick = async () => {
  if (!confirm("Reset?")) return;
  state = await api("/api/reset", { method: "POST", body: "{}" });
  selectedUnitId = null;
  selectedBodyId = null;
  cascade = null;
  map.clearSystem();
  render();
};
if ($("btn-process")) {
  $("btn-process").onclick = () => openProcessCascade("overview");
}
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
