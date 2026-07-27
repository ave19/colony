/**
 * Simple Three.js system map: orbit / zoom / pan, focus + track moving targets.
 * Positions animate smoothly from Keplerian phase + period (not discrete poll jumps).
 * Distances: heliocentric sqrt(AU); moons on exaggerated local rings when focused.
 */
import * as THREE from "/static/vendor/three/three.module.js";
import { OrbitControls } from "/static/vendor/three/addons/controls/OrbitControls.js";

const AU_SCALE = 12; // scene units per sqrt(AU)
// Match server: real time 1:1 (Earth second = sim second). Warp jumps for logistics.
const GAME_SECONDS_PER_WALL = 1;

export class SystemMap3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.bodyMeshes = new Map();
    this.focusId = null;
    this.selectedId = null;
    this.systemData = null;
    this.trackFocus = true; // telescope tracking
    this.onSelect = null;
    this.onFocus = null;

    // Visual clock: synced from server, advances smoothly between polls
    this._syncSimSeconds = 0;
    this._syncWallMs = performance.now();
    this._visualSimSeconds = 0;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x02050a, 1);

    this.scene = new THREE.Scene();
    // No distance fog — zooming out must keep planets/star readable (system map, not atmosphere).

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.01, 8000);
    this.camera.position.set(0, 28, 48);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 400;
    this.controls.target.set(0, 0, 0);

    this._addStars();
    // Strong ambient so bodies stay visible when far (point light alone falls off visually)
    this.scene.add(new THREE.AmbientLight(0x8899aa, 0.85));
    this.sunLight = new THREE.PointLight(0xfff0d0, 1.4, 0, 0);
    this.scene.add(this.sunLight);

    this.root = new THREE.Group();
    this.scene.add(this.root);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();

    this._onResize = () => this.resize();
    window.addEventListener("resize", this._onResize);
    canvas.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    canvas.addEventListener("dblclick", (e) => this._onDblClick(e));

    this.resize();
    this._anim = () => {
      this._tickVisualTime();
      this._layoutBodies();
      this._trackFocusCamera();
      this.controls.update();
      // re-apply track after controls so damping doesn't leave target behind
      this._trackFocusCamera();
      this.renderer.render(this.scene, this.camera);
      this._raf = requestAnimationFrame(this._anim);
    };
    this._anim();
  }

  dispose() {
    cancelAnimationFrame(this._raf);
    window.removeEventListener("resize", this._onResize);
    this.controls.dispose();
    this.renderer.dispose();
  }

  resize() {
    const w = this.canvas.clientWidth || this.canvas.parentElement.clientWidth;
    const h = this.canvas.clientHeight || this.canvas.parentElement.clientHeight;
    if (w < 1 || h < 1) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  /** Sync visual clock from server sim time (seconds). */
  setSimTimeSeconds(simSeconds) {
    const s = Number(simSeconds) || 0;
    this._syncSimSeconds = s;
    this._syncWallMs = performance.now();
    this._visualSimSeconds = s;
  }

  _tickVisualTime() {
    const wallDt = (performance.now() - this._syncWallMs) / 1000;
    this._visualSimSeconds = this._syncSimSeconds + wallDt * GAME_SECONDS_PER_WALL;
  }

  _addStars() {
    const n = 2500;
    const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const r = 80 + Math.random() * 400;
      const th = Math.random() * Math.PI * 2;
      const ph = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
      pos[i * 3 + 1] = r * Math.sin(ph) * Math.sin(th);
      pos[i * 3 + 2] = r * Math.cos(ph);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const mat = new THREE.PointsMaterial({ color: 0x8899aa, size: 0.35, sizeAttenuation: true });
    this.scene.add(new THREE.Points(geo, mat));
  }

  heliocentricFromPhase(a_au, phase) {
    const r = Math.max(a_au, 1e-12);
    const pr = Math.sqrt(r) * AU_SCALE;
    return new THREE.Vector3(Math.cos(phase) * pr, 0, Math.sin(phase) * pr);
  }

  _periodSeconds(b) {
    if (b.period_days && b.period_days > 0) return b.period_days * 86400;
    if (b.period_years && b.period_years > 0) return b.period_years * 365.25 * 86400;
    return 365.25 * 86400; // fallback 1 y
  }

  _phaseAt(b, tSec) {
    const P = this._periodSeconds(b);
    const omega = (Math.PI * 2) / P;
    const phase0 = b.phase0 != null ? b.phase0 : 0;
    // Prefer continuous phase0+omega*t; if server only gave current phase at sync, use that as epoch
    if (b._phaseEpoch != null && b._epochT != null) {
      return b._phaseEpoch + omega * (tSec - b._epochT);
    }
    return phase0 + omega * tSec;
  }

  clearSystem() {
    while (this.root.children.length) {
      const o = this.root.children[0];
      this.root.remove(o);
      o.traverse?.((c) => {
        if (c.geometry) c.geometry.dispose();
        if (c.material) {
          if (Array.isArray(c.material)) c.material.forEach((m) => m.dispose());
          else c.material.dispose();
        }
      });
    }
    this.bodyMeshes.clear();
    this.systemData = null;
  }

  setSystem(system, simSeconds = 0) {
    this.clearSystem();
    this.systemData = system;
    this.setSimTimeSeconds(simSeconds);
    if (!system) return;

    const starMat = new THREE.MeshBasicMaterial({ color: 0xffd27a });
    const star = new THREE.Mesh(new THREE.SphereGeometry(0.55, 32, 32), starMat);
    star.userData = { bodyId: "star", kind: "star" };
    this.root.add(star);
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(0.9, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xffaa44, transparent: true, opacity: 0.2 })
    );
    this.root.add(glow);

    const bodies = system.bodies || [];
    const planets = bodies.filter((b) => b.kind === "planet" || b.kind === "asteroid");
    const moons = bodies.filter((b) => b.kind === "moon");

    for (const b of planets) {
      const a = b.semi_major_au || 0;
      if (a <= 0) continue;
      const radius = Math.sqrt(a) * AU_SCALE;
      this.root.add(this._makeRing(radius, b.kind === "asteroid" ? 0x333844 : 0x1a2838));
    }

    for (const b of planets) {
      let radius = 0.12;
      let color = 0x9aa7b5;
      if (b.kind === "planet") {
        if (b.planet_class === "gas_giant") {
          radius = 0.38;
          color = 0xd4a574;
        } else if (b.planet_class === "ice_giant") {
          radius = 0.28;
          color = 0x7ec8e3;
        } else {
          radius = 0.16;
          color = b.metal_likely ? 0xc0a080 : 0x8a9aab;
        }
      } else {
        radius = 0.06;
        color = 0x666670;
      }
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 24, 24),
        new THREE.MeshStandardMaterial({
          color,
          roughness: 0.65,
          metalness: 0.12,
          emissive: new THREE.Color(color).multiplyScalar(0.15),
          emissiveIntensity: 0.35,
        })
      );
      mesh.userData = { bodyId: b.id, kind: b.kind };
      this.root.add(mesh);
      const label = this._makeLabel(b.name);
      this.root.add(label);
      // Epoch from server current phase so animation continues smoothly
      const orb = {
        ...b,
        _phaseEpoch: b.phase != null ? b.phase : b.phase0 || 0,
        _epochT: this._visualSimSeconds,
      };
      this.bodyMeshes.set(b.id, {
        mesh,
        label,
        data: orb,
        kind: b.kind,
        a_au: b.semi_major_au || 0,
        lift: radius + 0.25,
      });
    }

    // One ring per moon (Jupiter/Saturn style — never co-orbital display)
    for (const b of moons) {
      const parent = planets.find((p) => p.id === b.parent_id);
      if (!parent) continue;
      const localR = this._moonLocalR(b);
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.07, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xb8c0c8, roughness: 0.85, emissive: 0x000000 })
      );
      mesh.userData = { bodyId: b.id, kind: "moon", parentId: b.parent_id };
      this.root.add(mesh);
      const mring = this._makeRing(localR, 0x2a3545);
      mring.userData = { moonRingFor: b.parent_id, moonId: b.id, localR };
      this.root.add(mring);
      const label = this._makeLabel(b.name, 0.55);
      this.root.add(label);
      const orb = {
        ...b,
        _phaseEpoch: b.phase != null ? b.phase : b.phase0 || 0,
        _epochT: this._visualSimSeconds,
      };
      this.bodyMeshes.set(b.id, {
        mesh,
        label,
        data: orb,
        kind: "moon",
        parentId: b.parent_id,
        localR,
        lift: 0.14,
      });
    }

    this._layoutBodies();
    this._updateSelectionVisual();
    this._updateFocusVisibility();
  }

  /**
   * Soft-sync from server: update orbital epochs without teleporting.
   * Blends phase if close; hard-snaps only on large discontinuities (warp).
   */
  updatePositions(system, simSeconds = null) {
    if (!system || !this.systemData) return;
    this.systemData = system;
    if (simSeconds != null) {
      const s = Number(simSeconds) || 0;
      const predicted = this._visualSimSeconds;
      // If server jumped forward (warp), snap visual clock
      if (s > predicted + 3600 || s < predicted - 60) {
        this.setSimTimeSeconds(s);
      } else {
        // gentle resync
        this._syncSimSeconds = s;
        this._syncWallMs = performance.now();
      }
    }
    const bodies = system.bodies || [];
    const byId = Object.fromEntries(bodies.map((b) => [b.id, b]));
    const t = this._visualSimSeconds;

    for (const [id, entry] of this.bodyMeshes) {
      const b = byId[id];
      if (!b) continue;
      const serverPhase = b.phase != null ? b.phase : b.phase0 || 0;
      const P = this._periodSeconds(b);
      const omega = (Math.PI * 2) / P;
      // Current visual phase
      const visPhase = this._phaseAt(entry.data, t);
      let dPhase = serverPhase - visPhase;
      // wrap to [-pi, pi]
      dPhase = ((dPhase + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;
      if (Math.abs(dPhase) > 0.5) {
        // large jump (warp): snap
        entry.data = {
          ...b,
          _phaseEpoch: serverPhase,
          _epochT: t,
        };
      } else {
        // small correction: ease epoch toward server
        entry.data = {
          ...entry.data,
          ...b,
          _phaseEpoch: visPhase + dPhase * 0.25,
          _epochT: t,
          period_days: b.period_days,
          period_years: b.period_years,
          phase0: b.phase0,
          semi_major_au: b.semi_major_au,
          display_orbit_au: b.display_orbit_au,
        };
      }
      if (entry.kind !== "moon") {
        entry.a_au = b.semi_major_au || entry.a_au;
      } else {
        entry.localR = this._moonLocalR(b);
        entry.parentId = b.parent_id;
        // keep ring radius in sync
        this.root.traverse((o) => {
          if (o.userData?.moonId === id && o.userData.localR != null) {
            // rebuild not needed — position uses entry.localR; ring scale via userData
            o.userData.localR = entry.localR;
          }
        });
      }
    }
  }

  /** Map scene radius for a moon — distinct per orbit index / a/R. */
  _moonLocalR(b) {
    const idx = b.moon_orbit_index != null ? b.moon_orbit_index : 0;
    const aR = b.moon_a_over_R || 10;
    // Inner ~0.55, each step out ~+0.42; also scale gently with a/R
    return 0.5 + idx * 0.45 + Math.min(0.35, (aR / 60) * 0.4);
  }

  _layoutBodies() {
    if (!this.bodyMeshes.size) return;
    const t = this._visualSimSeconds;
    const parentPos = new Map();

    // Planets first
    for (const [id, entry] of this.bodyMeshes) {
      if (entry.kind === "moon") continue;
      const phase = this._phaseAt(entry.data, t);
      const pos = this.heliocentricFromPhase(entry.a_au || 0, phase);
      entry.mesh.position.copy(pos);
      if (entry.label) {
        entry.label.position.copy(pos).add(new THREE.Vector3(0, entry.lift || 0.3, 0));
      }
      parentPos.set(id, pos);
    }

    // Moons relative to parents
    for (const [id, entry] of this.bodyMeshes) {
      if (entry.kind !== "moon") continue;
      const ppos = parentPos.get(entry.parentId) || new THREE.Vector3();
      const phase = this._phaseAt(entry.data, t);
      const localR = entry.localR || 0.7;
      const pos = ppos
        .clone()
        .add(
          new THREE.Vector3(
            Math.cos(phase) * localR,
            Math.sin(phase) * 0.12 * localR,
            Math.sin(phase) * localR
          )
        );
      entry.mesh.position.copy(pos);
      if (entry.label) {
        entry.label.position.copy(pos).add(new THREE.Vector3(0, entry.lift || 0.14, 0));
      }
    }

    // Moon rings follow parents
    this.root.traverse((o) => {
      if (o.userData?.moonRingFor) {
        const p = parentPos.get(o.userData.moonRingFor);
        if (p) o.position.copy(p);
      }
    });
  }

  /** Keep focus target locked; camera rides with it (telescope tracking). */
  _trackFocusCamera() {
    if (!this.trackFocus || !this.focusId) return;
    const entry = this.bodyMeshes.get(this.focusId);
    if (!entry) return;
    const bodyPos = entry.mesh.position;
    const offset = this.camera.position.clone().sub(this.controls.target);
    // avoid zero offset
    if (offset.lengthSq() < 1e-6) offset.set(2.2, 1.4, 2.8);
    this.controls.target.copy(bodyPos);
    this.camera.position.copy(bodyPos).add(offset);
  }

  _makeRing(radius, color) {
    const pts = [];
    const n = 128;
    for (let i = 0; i <= n; i++) {
      const t = (i / n) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(t) * radius, 0, Math.sin(t) * radius));
    }
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 });
    return new THREE.Line(geo, mat);
  }

  _makeLabel(text, scale = 0.7) {
    const c = document.createElement("canvas");
    c.width = 256;
    c.height = 64;
    const ctx = c.getContext("2d");
    ctx.clearRect(0, 0, 256, 64);
    ctx.font = "28px system-ui, sans-serif";
    ctx.fillStyle = "rgba(200, 220, 240, 0.9)";
    ctx.textAlign = "center";
    ctx.fillText(text, 128, 40);
    const tex = new THREE.CanvasTexture(c);
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false });
    const spr = new THREE.Sprite(mat);
    spr.scale.set(2.2 * scale, 0.55 * scale, 1);
    return spr;
  }

  setSelected(id) {
    this.selectedId = id;
    this._updateSelectionVisual();
  }

  focusBody(id) {
    if (!id) {
      this.focusId = null;
      this.controls.target.set(0, 0, 0);
      this.camera.position.set(0, 28, 48);
      this.controls.minDistance = 0.8;
      this.controls.maxDistance = 400;
      this.controls.update();
      this._updateFocusVisibility();
      if (this.onFocus) this.onFocus(null);
      return;
    }

    let targetId = id;
    const entry = this.bodyMeshes.get(id);
    if (entry?.kind === "moon" && entry.parentId) {
      targetId = entry.parentId;
    }
    this.focusId = targetId;
    const targetEntry = this.bodyMeshes.get(targetId);
    if (!targetEntry) {
      this.focusId = null;
      return;
    }

    this._layoutBodies();
    const p = targetEntry.mesh.position.clone();
    this.controls.target.copy(p);
    const offset = new THREE.Vector3(2.2, 1.4, 2.8);
    this.camera.position.copy(p).add(offset);
    this.controls.minDistance = 0.2;
    this.controls.maxDistance = 40;
    this.controls.update();
    this._updateFocusVisibility();
    if (this.onFocus) this.onFocus(this.focusId);
  }

  focusSystem() {
    this.focusBody(null);
  }

  _updateSelectionVisual() {
    for (const [, entry] of this.bodyMeshes) {
      const sel = entry.mesh.userData.bodyId === this.selectedId;
      const mat = entry.mesh.material;
      if (!mat || !mat.emissive) continue;
      if (sel) {
        mat.emissive.setHex(0x3a7ab8);
        mat.emissiveIntensity = 0.65;
      } else {
        // Keep a little self-illumination so zoom-out doesn't go black
        const base = mat.color ? mat.color.clone().multiplyScalar(0.15) : new THREE.Color(0x222222);
        mat.emissive.copy(base);
        mat.emissiveIntensity = 0.35;
      }
    }
  }

  _updateFocusVisibility() {
    const focus = this.focusId;
    for (const [, entry] of this.bodyMeshes) {
      if (entry.kind !== "moon") {
        if (entry.label) entry.label.visible = !focus || entry.mesh.userData.bodyId === focus;
        continue;
      }
      const parentFocused = focus && entry.parentId === focus;
      if (entry.label) entry.label.visible = !!parentFocused;
      entry.mesh.visible = true;
      entry.mesh.scale.setScalar(parentFocused ? 1.6 : 0.85);
    }
    this.root.traverse((o) => {
      if (o.userData?.moonRingFor) {
        o.visible = !focus || o.userData.moonRingFor === focus;
      }
    });
  }

  _pick(event) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const meshes = [];
    for (const [, e] of this.bodyMeshes) meshes.push(e.mesh);
    const hits = this.raycaster.intersectObjects(meshes, false);
    if (!hits.length) return null;
    return hits[0].object.userData.bodyId || null;
  }

  _onPointerDown(event) {
    if (event.button !== 0) return;
    const id = this._pick(event);
    this._downId = id;
    this._downX = event.clientX;
    this._downY = event.clientY;
    const up = (e) => {
      window.removeEventListener("pointerup", up);
      const dist = Math.hypot(e.clientX - this._downX, e.clientY - this._downY);
      if (dist > 5) return;
      const pick = this._pick(e) || this._downId;
      if (pick) {
        this.setSelected(pick);
        if (this.onSelect) this.onSelect(pick);
      }
    };
    window.addEventListener("pointerup", up);
  }

  _onDblClick(event) {
    const id = this._pick(event);
    if (id) {
      this.setSelected(id);
      this.focusBody(id);
      if (this.onSelect) this.onSelect(id);
    }
  }
}
