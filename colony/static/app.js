/* Colony — map-first, fleet orders: you → go there → do that */

let state = null;
let selectedUnitId = null;
let selectedBodyId = null;

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function refresh() {
  state = await api("/api/state");
  render();
}

function bodyById(id) {
  return (state?.system?.bodies || []).find((b) => b.id === id);
}

function unitById(id) {
  return (state?.fleet || []).find((u) => u.id === id);
}

function render() {
  if (!state) return;
  $("phase").textContent = state.phase;
  $("pop").textContent = `${(state.population || 0).toLocaleString()} souls`;
  if (state.phase === "transit") {
    $("clock").textContent = `${(state.transit_months_left / 12).toFixed(1)} y transit`;
  } else {
    $("clock").textContent = `${state.sim_years.toFixed(2)} y in-system`;
  }
  $("toast").textContent = state.message || "";

  $("panel-menu").hidden = state.phase !== "menu";
  $("panel-transit").hidden = state.phase !== "transit";
  $("panel-system").hidden = state.phase !== "system";
  $("right-menu").hidden = state.phase === "system";
  $("right-system").hidden = state.phase !== "system";

  if (state.phase === "transit") {
    $("transit-msg").textContent =
      `Coasting ${(state.transit_months_left / 12).toFixed(1)} years. Capture will spend remaining Xe.`;
  }

  renderCatalog();
  renderFleet();
  renderUnitPanel();
  renderBodyPanel();
  renderOrders();
  renderBuild();
  renderProjects();
  renderContracts();
  renderStock();
  renderEvents();
  renderLegend();
  drawMap();
}

function renderCatalog() {
  const el = $("catalog");
  if (!el) return;
  if (!state.catalog?.length) {
    el.innerHTML = '<p class="empty">No survey yet.</p>';
    return;
  }
  el.innerHTML = state.catalog
    .map((c) => {
      const g = c.gas_giant_period_years != null
        ? ` · gas giant ~${c.gas_giant_period_years} y`
        : "";
      const title = c.star.designation || c.star.name;
      return `<div class="card">
        <h3>${title}</h3>
        <p>${c.survey_summary}</p>
        <p>Outer ~${c.outer_au ?? "?"} AU${g} · difficulty ${c.difficulty}/10</p>
        <p class="muted">Worlds named ${c.star.name}-1, ${c.star.name}-2, …</p>
        <button class="primary" data-seed="${c.seed}">Commit — go there</button>
      </div>`;
    })
    .join("");
  el.querySelectorAll("[data-seed]").forEach((btn) => {
    btn.onclick = async () => {
      state = await api("/api/select_star", {
        method: "POST",
        body: JSON.stringify({ seed: Number(btn.dataset.seed) }),
      });
      selectedUnitId = "ark";
      selectedBodyId = null;
      render();
    };
  });
}

function renderFleet() {
  const el = $("fleet-list");
  if (!el || state.phase !== "system") return;
  const fleet = state.fleet || [];
  if (!fleet.length) {
    el.innerHTML = '<p class="empty">No fleet (arrive first).</p>';
    return;
  }
  el.innerHTML = fleet
    .map((u) => {
      const loc = bodyById(u.location_id);
      const locName = loc ? loc.name : u.location_id;
      const busy =
        u.status !== "idle"
          ? `<div class="meta busy">${u.status}: ${u.order || ""} → ${u.target_id || ""} (${u.months_left} mo)</div>`
          : `<div class="meta">@ ${locName}</div>`;
      return `<button type="button" class="fleet-item ${selectedUnitId === u.id ? "selected" : ""}" data-unit="${u.id}">
        <div class="name">${u.name}</div>
        <div class="meta">${u.kind} · ${(u.capabilities || []).join(", ")}</div>
        ${busy}
      </button>`;
    })
    .join("");
  el.querySelectorAll("[data-unit]").forEach((btn) => {
    btn.onclick = () => {
      selectedUnitId = btn.dataset.unit;
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
    el.textContent = "Select a fleet unit";
    return;
  }
  const loc = bodyById(u.location_id);
  el.className = "card";
  el.innerHTML = `
    <h3>${u.name}</h3>
    <p>${u.kind} · can ${ (u.capabilities || []).join(", ") }</p>
    <p>Location: <strong>${loc ? loc.name : u.location_id}</strong></p>
    <p>Status: ${u.status}${u.order ? ` (${u.order})` : ""}</p>
  `;
}

function renderBodyPanel() {
  const el = $("body-panel");
  if (!el || state.phase !== "system") return;
  const b = bodyById(selectedBodyId);
  if (!b) {
    el.className = "empty";
    el.textContent = "Click a body on the map — that's your “there”";
    return;
  }
  el.className = "card";
  const a =
    b.kind === "moon"
      ? `moon of ${bodyById(b.parent_id)?.name || b.parent_id} · SMA ${b.moon_sma_km || "?"} km · period ${b.period_label}`
      : `${b.semi_major_au} AU · period ${b.period_label} · ${b.mass_earth} M⊕`;
  const deps = (b.deposits || [])
    .map((d) =>
      d.known ? `${d.resource} g${d.grade} (${Math.round(d.amount_t)}t)` : "unsurveyed"
    )
    .join(" · ");
  el.innerHTML = `
    <h3>${b.name}</h3>
    <p>${b.kind}${b.planet_class ? " / " + b.planet_class : ""} · ${b.density_hint}</p>
    <p>${a}</p>
    <p>Δv↑orbit ${b.dv_to_orbit_m_s} m/s · escape+ ${b.dv_escape_from_orbit_m_s} m/s</p>
    <p>${b.atmosphere_note || "no thick air noted"}</p>
    <p>${deps || "no deposits"}</p>
  `;
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
  const busy = u.status !== "idle";

  const est = async (order) => {
    try {
      return await api("/api/estimate_order", {
        method: "POST",
        body: JSON.stringify({ unit_id: u.id, order, target_id: b.id }),
      });
    } catch {
      return null;
    }
  };

  const [eMove, eSurvey, eMine] = await Promise.all([
    est("move"),
    est("survey"),
    est("mine"),
  ]);

  const fmt = (e) => {
    if (!e) return "";
    if (e.years >= 0.5) return ` (~${e.years.toFixed(1)} y)`;
    return ` (~${e.months.toFixed(1)} mo)`;
  };

  const surveyed =
    (state.scanned || []).includes(b.id) || (b.deposits || []).some((d) => d.known);

  const rows = [
    { order: "move", label: `Move to ${b.name}${fmt(eMove)}`, need: null, dis: false },
    { order: "survey", label: `Survey ${b.name}${fmt(eSurvey)}`, need: "survey", dis: false },
    {
      order: "mine",
      label: `Mine ${b.name}${fmt(eMine)}`,
      need: "mine",
      dis: !surveyed,
    },
    { order: "idle", label: "Cancel / stand by", need: null, dis: false },
  ];

  el.innerHTML =
    rows
      .map((r) => {
        const ok = !r.need || caps.includes(r.need);
        return `<button type="button" class="order" data-order="${r.order}"
          ${busy || !ok || r.dis ? "disabled" : ""}>${r.label}</button>`;
      })
      .join("") +
    (busy
      ? `<p class="muted">En route / working — use Warp to advance real transit time.</p>`
      : `<p class="muted">Transit uses Hohmann-class coast (+ window). Survey sats are slower (low thrust).</p>`);

  el.querySelectorAll("[data-order]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        state = await api("/api/order", {
          method: "POST",
          body: JSON.stringify({
            unit_id: u.id,
            order: btn.dataset.order,
            target_id: b.id,
          }),
        });
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 300));
      }
    };
  });
}

function renderBuild() {
  const panel = $("build-panel");
  if (!panel || state.phase !== "system") return;
  const b = bodyById(selectedBodyId);
  const u = unitById(selectedUnitId);
  // Build choices when a body is selected; ark preferred but any selection ok
  panel.hidden = !b;
  if (!b) return;
  const power = $("power-id").value;
  const hints = state.build_options?.power?.[power]?.description || "";
  $("build-hint").textContent = hints;
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
      alert(String(e.message || e).slice(0, 300));
    }
  };
  $("power-id").onchange = () => renderBuild();
}

function renderProjects() {
  const el = $("projects");
  if (!el) return;
  const list = state.projects || [];
  if (!list.length) {
    el.innerHTML = '<p class="empty">None — found a project on a target body.</p>';
    return;
  }
  el.innerHTML = list
    .map((p) => {
      const b = bodyById(p.body_id);
      return `<div class="card"><h3>${p.name} <span class="badge">${p.status}</span></h3>
        <p>${b ? b.name : p.body_id} · ${p.power_id} / ${p.hab_id}</p>
        <p>${(p.buildings || []).join(", ")}</p></div>`;
    })
    .join("");
}

function renderContracts() {
  const el = $("contracts");
  if (!el) return;
  const open = (state.contracts || []).filter((c) => c.status === "open");
  if (!open.length) {
    el.innerHTML = '<p class="empty">No open needs.</p>';
    return;
  }
  el.innerHTML = open
    .map(
      (c) => `<div class="card">
      <h3>${c.title} <span class="badge open">need</span></h3>
      <p>${c.resource_name}: ${c.delivered_t}/${c.amount_t} t</p>
      <p>${c.note || ""}</p>
      <button data-deliver="${c.id}">Supply from ark cargo</button>
    </div>`
    )
    .join("");
  el.querySelectorAll("[data-deliver]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        state = await api("/api/deliver_ark", {
          method: "POST",
          body: JSON.stringify({ contract_id: btn.dataset.deliver }),
        });
        render();
      } catch (e) {
        alert(String(e.message || e).slice(0, 300));
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

function renderLegend() {
  const el = $("map-legend");
  if (!el || state.phase !== "system" || !state.system) {
    if (el) el.textContent = "";
    return;
  }
  const max = state.system.max_au || "?";
  const snow = state.system.snow_line_au || "?";
  el.innerHTML = `Map: √AU scale (outer system is far).<br/>System ~${max} AU · snow line ${snow} AU<br/>Periods are Keplerian (Jupiter-class ~12 y).`;
}

/** Map projection: sqrt(|r|) keeps outer giants on screen without lying about order. */
function project(x_au, y_au, scale, cx, cy) {
  const r = Math.hypot(x_au, y_au);
  if (r < 1e-9) return [cx, cy];
  const pr = Math.sqrt(r) * scale;
  return [cx + (x_au / r) * pr, cy + (y_au / r) * pr];
}

function mapLayout(w, h) {
  const bodies = state.system?.bodies || [];
  let maxA = 1;
  bodies.forEach((b) => {
    if (b.kind !== "moon") {
      maxA = Math.max(maxA, Math.hypot(b.x_au || 0, b.y_au || 0), b.semi_major_au || 0);
    }
  });
  const scale = (Math.min(w, h) * 0.44) / Math.sqrt(maxA);
  return { scale, cx: w / 2, cy: h / 2, maxA };
}

function drawMap() {
  const canvas = $("map");
  const parent = canvas.parentElement;
  const w = parent.clientWidth;
  const h = parent.clientHeight;
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, w, h);

  if (state.phase === "menu") {
    ctx.fillStyle = "#7d8fa3";
    ctx.font = "15px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Survey stars — pick a system you can see", w / 2, h / 2);
    return;
  }
  if (state.phase === "transit") {
    ctx.fillStyle = "#fff";
    for (let i = 0; i < 100; i++) {
      ctx.fillRect(((i * 97) % w), ((i * 53) % h), 1.2, 1.2);
    }
    ctx.fillStyle = "#7d8fa3";
    ctx.font = "15px system-ui";
    ctx.textAlign = "center";
    ctx.fillText("Deep space — warp to arrival to see the system", w / 2, h / 2);
    return;
  }
  if (!state.system) return;

  const { scale, cx, cy, maxA } = mapLayout(w, h);
  const bodies = state.system.bodies || [];

  // Orbit rings (planets / asteroids) in √AU space
  ctx.strokeStyle = "#1a2836";
  ctx.lineWidth = 1;
  bodies
    .filter((b) => b.kind === "planet" || b.kind === "asteroid")
    .forEach((b) => {
      const a = b.semi_major_au || 0;
      const pr = Math.sqrt(a) * scale;
      ctx.beginPath();
      ctx.arc(cx, cy, pr, 0, Math.PI * 2);
      ctx.stroke();
    });

  // Star
  const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 14);
  g.addColorStop(0, "#fff8e0");
  g.addColorStop(0.5, "#ffd27a");
  g.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(cx, cy, 14, 0, Math.PI * 2);
  ctx.fill();

  // Bodies — small dots (planets are not huge)
  bodies.forEach((b) => {
    const [x, y] = project(b.x_au || 0, b.y_au || 0, scale, cx, cy);
    let r = 2.2;
    let color = "#8899aa";
    if (b.kind === "planet") {
      if (b.planet_class === "gas_giant") {
        r = 4.5;
        color = "#d4a574";
      } else if (b.planet_class === "ice_giant") {
        r = 3.5;
        color = "#7ec8e3";
      } else {
        r = 2.8;
        color = b.metal_likely ? "#c0a080" : "#9aa7b5";
      }
    } else if (b.kind === "moon") {
      r = 1.6;
      color = "#b8c0c8";
    } else if (b.kind === "asteroid") {
      r = 1.4;
      color = "#666";
    }

    if (b.id === selectedBodyId) {
      ctx.strokeStyle = "#4aa3f0";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r + 5, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();

    if (b.kind === "planet") {
      ctx.fillStyle = "#a8b4c0";
      ctx.font = "10px system-ui";
      ctx.textAlign = "left";
      ctx.fillText(`${b.name}  ${b.period_label || ""}`, x + r + 4, y + 3);
    }
  });

  // Fleet markers at their locations
  (state.fleet || []).forEach((u) => {
    const b = bodyById(u.location_id);
    if (!b) return;
    const [x, y] = project(b.x_au || 0, b.y_au || 0, scale, cx, cy);
    ctx.strokeStyle = u.id === selectedUnitId ? "#4aa3f0" : "#3ecf8e";
    ctx.lineWidth = 1;
    ctx.strokeRect(x - 6, y - 6, 12, 12);
  });
}

// Click map: pick body (coordinate-correct for canvas size)
$("map").addEventListener("click", (ev) => {
  if (state?.phase !== "system" || !state.system) return;
  const canvas = $("map");
  const rect = canvas.getBoundingClientRect();
  const mx = ((ev.clientX - rect.left) / rect.width) * canvas.width;
  const my = ((ev.clientY - rect.top) / rect.height) * canvas.height;
  const { scale, cx, cy } = mapLayout(canvas.width, canvas.height);

  let best = null;
  let bestD = 18;
  (state.system.bodies || []).forEach((b) => {
    const [x, y] = project(b.x_au || 0, b.y_au || 0, scale, cx, cy);
    const d = Math.hypot(mx - x, my - y);
    if (d < bestD) {
      bestD = d;
      best = b.id;
    }
  });
  if (best) {
    selectedBodyId = best;
    render();
  }
});

$("btn-catalog").onclick = async () => {
  state = await api("/api/catalog", { method: "POST", body: "{}" });
  render();
};
$("btn-warp").onclick = async () => {
  state = await api("/api/warp", { method: "POST", body: "{}" });
  render();
};
$("btn-warp-transit").onclick = () => $("btn-warp").click();
$("btn-reset").onclick = async () => {
  if (!confirm("Reset colony room?")) return;
  state = await api("/api/reset", { method: "POST", body: "{}" });
  selectedUnitId = null;
  selectedBodyId = null;
  render();
};

setInterval(async () => {
  if (document.hidden) return;
  try {
    state = await api("/api/state");
    render();
  } catch (_) {}
}, 3000);

refresh().catch((e) => {
  $("toast").textContent = "API error: " + e.message;
});
