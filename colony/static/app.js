/* Colony web client */

let state = null;
let selectedBodyId = null;
let haulOptions = [];

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || res.statusText);
  }
  return res.json();
}

async function refresh() {
  state = await api("/api/state");
  render();
}

function render() {
  if (!state) return;
  $("phase").textContent = state.phase;
  $("pop").textContent = state.population.toLocaleString();
  if (state.phase === "transit") {
    $("clock").textContent = `${state.transit_months_left.toFixed(1)} mo left`;
  } else {
    $("clock").textContent = `${state.sim_years.toFixed(2)} y`;
  }
  $("toast").textContent = state.message || "";

  $("panel-menu").hidden = state.phase !== "menu";
  $("panel-transit").hidden = state.phase !== "transit";
  $("panel-system").hidden = state.phase !== "system";

  if (state.phase === "transit") {
    $("transit-msg").textContent = `Coasting… ${state.transit_months_left.toFixed(1)} months to capture. Xe will be spent on arrival burn.`;
  }

  renderCatalog();
  renderStock();
  renderContracts();
  renderProjects();
  renderHauls();
  renderEvents();
  renderBodyDetail();
  renderHaulResourceSelect();
  drawMap();
}

function renderCatalog() {
  const el = $("catalog");
  if (!state.catalog || !state.catalog.length) {
    el.innerHTML = '<p class="empty">No survey yet.</p>';
    return;
  }
  el.innerHTML = state.catalog
    .map(
      (c) => `
    <div class="card">
      <h3>${c.star.name}</h3>
      <p>${c.survey_summary}</p>
      <p>Difficulty <strong>${c.difficulty}</strong>/10 · seed ${c.seed}</p>
      <div class="row">
        <button class="primary" data-seed="${c.seed}">Commit transit</button>
      </div>
    </div>`
    )
    .join("");
  el.querySelectorAll("button[data-seed]").forEach((btn) => {
    btn.onclick = async () => {
      state = await api("/api/select_star", {
        method: "POST",
        body: JSON.stringify({ seed: Number(btn.dataset.seed) }),
      });
      render();
    };
  });
}

function renderStock() {
  const s = state.ark_stock || {};
  const keys = Object.keys(s).sort();
  $("ark-stock").innerHTML = keys
    .map((k) => `<span class="k">${k}</span><span class="v">${s[k]} t</span>`)
    .join("");
}

function renderContracts() {
  const el = $("contracts");
  const list = state.contracts || [];
  if (!list.length) {
    el.innerHTML = '<p class="empty">No contracts — plan a base.</p>';
    return;
  }
  el.innerHTML = list
    .map(
      (c) => `
    <div class="card">
      <h3>${c.title} <span class="badge ${c.status}">${c.status}</span></h3>
      <p>${c.resource_name}: ${c.delivered_t} / ${c.amount_t} t</p>
      <p class="muted">${c.note || ""}</p>
      ${
        c.status === "open"
          ? `<div class="row"><button class="good" data-deliver="${c.id}">Deliver from ark</button>
             <button data-haul-c="${c.id}" data-res="${c.resource}" data-amt="${Math.min(
              10,
              c.remaining_t
            )}">Haul 10t…</button></div>`
          : ""
      }
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
        alert(e.message);
      }
    };
  });
  el.querySelectorAll("[data-haul-c]").forEach((btn) => {
    btn.onclick = () => {
      $("haul-resource").value = btn.dataset.res;
      $("haul-amount").value = btn.dataset.amt;
      if (selectedBodyId) $("haul-dest").value = selectedBodyId;
      $("btn-haul-opts").click();
    };
  });
}

function renderProjects() {
  const el = $("projects");
  const list = state.projects || [];
  if (!list.length) {
    el.innerHTML = '<p class="empty">None yet.</p>';
    return;
  }
  el.innerHTML = list
    .map(
      (p) => `
    <div class="card">
      <h3>${p.name} <span class="badge">${p.status}</span></h3>
      <p class="muted">Body ${p.body_id} · ${p.power_id} / ${p.hab_id}</p>
      <p class="muted">Buildings: ${(p.buildings || []).join(", ") || "—"}</p>
    </div>`
    )
    .join("");
}

function renderHauls() {
  const el = $("hauls");
  const list = (state.hauls || []).filter((h) => h.status === "in_flight");
  if (!list.length) {
    el.innerHTML = '<p class="empty">No active hauls.</p>';
    return;
  }
  el.innerHTML = list
    .map(
      (h) => `
    <div class="card">
      <h3>${h.resource} ${h.amount_t}t <span class="badge in_flight">${h.option_name}</span></h3>
      <p>${h.origin_id} → ${h.dest_id}</p>
      <p class="muted">${h.months_left.toFixed(2)} / ${h.months_total.toFixed(2)} mo · Δv ${h.dv_m_s} m/s · prop ${h.propellant_t}t</p>
    </div>`
    )
    .join("");
}

function renderEvents() {
  const el = $("events");
  el.innerHTML = (state.events || [])
    .slice(0, 12)
    .map(
      (e) => `
    <div class="event">
      <div class="t">${e.kind} · t=${(e.t_months || 0).toFixed(2)} mo</div>
      <div>${e.text}</div>
    </div>`
    )
    .join("");
}

function renderBodyDetail() {
  const el = $("body-detail");
  const planBox = $("plan-box");
  if (state.phase !== "system" || !state.system) {
    el.className = "empty";
    el.textContent = "—";
    planBox.hidden = true;
    return;
  }
  const body = (state.system.bodies || []).find((b) => b.id === selectedBodyId);
  if (!body) {
    el.className = "empty";
    el.textContent = "Click a body on the map";
    planBox.hidden = true;
    return;
  }
  el.className = "card";
  const deps = (body.deposits || [])
    .map((d) =>
      d.known
        ? `${d.resource} grade ${d.grade} (${d.amount_t}t)`
        : "unsurveyed deposit"
    )
    .join("<br/>");
  el.innerHTML = `
    <h3>${body.name}</h3>
    <p class="muted">${body.kind} · ${body.density_hint}</p>
    <p>a = ${body.semi_major_au?.toFixed?.(3) ?? "?"} AU · g = ${body.surface_g} g</p>
    <p>Δv surface→orbit ≈ ${body.dv_to_orbit_m_s} m/s · orbit→escape ≈ ${body.dv_escape_from_orbit_m_s} m/s</p>
    <p class="muted">${body.atmosphere_note || "no notable atmosphere"}</p>
    <p>${deps || "no deposits listed"}</p>
    <div class="row">
      <button id="btn-scan" class="primary">Scan / survey</button>
    </div>`;
  planBox.hidden = false;
  $("haul-dest").value = body.id;
  const scanBtn = $("btn-scan");
  if (scanBtn) {
    scanBtn.onclick = async () => {
      state = await api("/api/scan", {
        method: "POST",
        body: JSON.stringify({ body_id: body.id }),
      });
      render();
    };
  }
}

function renderHaulResourceSelect() {
  const sel = $("haul-resource");
  const s = state.ark_stock || {};
  const cur = sel.value;
  sel.innerHTML = Object.keys(s)
    .filter((k) => s[k] > 0)
    .map((k) => `<option value="${k}">${k} (${s[k]}t)</option>`)
    .join("");
  if (cur) sel.value = cur;
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
    drawCenterText(ctx, w, h, "Survey stars → commit transit");
    return;
  }
  if (state.phase === "transit") {
    drawCenterText(ctx, w, h, "Deep space transit…");
    // simple star field
    ctx.fillStyle = "#fff";
    for (let i = 0; i < 80; i++) {
      const x = (Math.sin(i * 12.3 + state.sim_months) * 0.5 + 0.5) * w;
      const y = (Math.cos(i * 7.1) * 0.5 + 0.5) * h;
      ctx.fillRect(x, y, 1.5, 1.5);
    }
    return;
  }
  if (!state.system) return;

  const bodies = state.system.bodies || [];
  let maxA = 0.5;
  bodies.forEach((b) => {
    if (b.kind !== "moon") maxA = Math.max(maxA, Math.abs(b.x_au || 0), Math.abs(b.y_au || 0), b.semi_major_au || 0);
  });
  const scale = (Math.min(w, h) * 0.42) / maxA;
  const cx = w / 2;
  const cy = h / 2;

  // orbits
  ctx.strokeStyle = "#2a3a4a";
  ctx.lineWidth = 1;
  bodies
    .filter((b) => b.kind === "planet" || b.kind === "asteroid")
    .forEach((b) => {
      const r = (b.semi_major_au || 0) * scale;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.stroke();
    });

  // star
  const star = state.system.star || {};
  const grd = ctx.createRadialGradient(cx, cy, 0, cx, cy, 18);
  grd.addColorStop(0, "#fff6d0");
  grd.addColorStop(0.4, star.temp > 5000 ? "#ffd27a" : "#ff8a5c");
  grd.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grd;
  ctx.beginPath();
  ctx.arc(cx, cy, 18, 0, Math.PI * 2);
  ctx.fill();

  // bodies
  bodies.forEach((b) => {
    const x = cx + (b.x_au || 0) * scale;
    const y = cy + (b.y_au || 0) * scale;
    let r = 4;
    let color = "#8ab4f8";
    if (b.kind === "planet") {
      r = 6 + Math.min(8, Math.log10((b.mass_kg || 1e24) / 1e24 + 1) * 4);
      color = b.ice_likely ? "#7ec8e3" : b.metal_likely ? "#c4a574" : "#9aa7b5";
    } else if (b.kind === "moon") {
      r = 3;
      color = "#b0b8c0";
    } else if (b.kind === "asteroid") {
      r = 2.5;
      color = "#888";
    }
    if (b.id === selectedBodyId) {
      ctx.strokeStyle = "#3d9cf0";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, r + 4, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    if (b.kind === "planet") {
      ctx.fillStyle = "#c5d0dc";
      ctx.font = "11px system-ui";
      ctx.fillText(b.name, x + r + 4, y + 3);
    }
  });

  // hauls as arcs hint
  ctx.strokeStyle = "rgba(61,156,240,0.5)";
  (state.hauls || [])
    .filter((h) => h.status === "in_flight")
    .forEach((h) => {
      const a = bodies.find((b) => b.id === h.dest_id);
      if (!a) return;
      const x = cx + (a.x_au || 0) * scale;
      const y = cy + (a.y_au || 0) * scale;
      ctx.beginPath();
      ctx.moveTo(cx + 20, cy);
      ctx.lineTo(x, y);
      ctx.stroke();
    });
}

function drawCenterText(ctx, w, h, text) {
  ctx.fillStyle = "#8b9bb0";
  ctx.font = "16px system-ui";
  ctx.textAlign = "center";
  ctx.fillText(text, w / 2, h / 2);
}

// map click
$("map").addEventListener("click", (ev) => {
  if (state?.phase !== "system" || !state.system) return;
  const canvas = $("map");
  const rect = canvas.getBoundingClientRect();
  const mx = ev.clientX - rect.left;
  const my = ev.clientY - rect.top;
  const w = canvas.width;
  const h = canvas.height;
  const bodies = state.system.bodies || [];
  let maxA = 0.5;
  bodies.forEach((b) => {
    if (b.kind !== "moon") maxA = Math.max(maxA, Math.abs(b.x_au || 0), Math.abs(b.y_au || 0), b.semi_major_au || 0);
  });
  const scale = (Math.min(w, h) * 0.42) / maxA;
  const cx = w / 2;
  const cy = h / 2;
  let best = null;
  let bestD = 16;
  bodies.forEach((b) => {
    const x = cx + (b.x_au || 0) * scale;
    const y = cy + (b.y_au || 0) * scale;
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
$("btn-warp-transit").onclick = $("btn-warp").onclick;
$("btn-refresh").onclick = refresh;

$("btn-plan").onclick = async () => {
  if (!selectedBodyId) return alert("Select a body first");
  try {
    state = await api("/api/plan_base", {
      method: "POST",
      body: JSON.stringify({
        body_id: selectedBodyId,
        power_id: $("power-id").value,
        hab_id: $("hab-id").value,
      }),
    });
    render();
  } catch (e) {
    alert(e.message);
  }
};

$("btn-haul-opts").onclick = async () => {
  const dest = $("haul-dest").value.trim();
  if (!dest) return alert("Set destination body id");
  try {
    const data = await api("/api/haul_options", {
      method: "POST",
      body: JSON.stringify({ origin_id: "ark", dest_id: dest }),
    });
    haulOptions = data.options || [];
    const el = $("haul-opts");
    el.innerHTML = haulOptions
      .map(
        (o, i) => `
      <div class="card">
        <h3>${o.name}</h3>
        <p><strong>${o.propellant_t}</strong> t prop · <strong>${o.months}</strong> mo · Δv ${o.dv_m_s} m/s</p>
        <p class="muted">${o.description}</p>
        <button data-opt="${i}" class="primary">Launch haul</button>
      </div>`
      )
      .join("");
    el.querySelectorAll("[data-opt]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          state = await api("/api/start_haul", {
            method: "POST",
            body: JSON.stringify({
              origin_id: "ark",
              dest_id: dest,
              resource: $("haul-resource").value,
              amount_t: Number($("haul-amount").value),
              option_index: Number(btn.dataset.opt),
            }),
          });
          render();
        } catch (e) {
          alert(e.message);
        }
      };
    });
  } catch (e) {
    alert(e.message);
  }
};

// live clock tick for map animation + catch-up
setInterval(async () => {
  try {
    if (document.hidden) return;
    state = await api("/api/state");
    render();
  } catch (_) {
    /* server restarting */
  }
}, 2000);

refresh().catch((e) => {
  $("toast").textContent = "API error: " + e.message;
});
