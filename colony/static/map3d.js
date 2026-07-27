/**
 * Simple Three.js system map: orbit / zoom / pan, focus planet to see moons.
 * Distances use a dual scale: heliocentric √AU, local moon rings exaggerated when focused.
 */
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const AU_SCALE = 12; // scene units per √AU at system scale

export class SystemMap3D {
  constructor(canvas) {
    this.canvas = canvas;
    this.bodyMeshes = new Map(); // id -> { mesh, data, kind }
    this.focusId = null; // null = system view
    this.selectedId = null;
    this.systemData = null;
    this.onSelect = null;
    this.onFocus = null;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x02050a, 1);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x02050a, 0.012);

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.01, 5000);
    this.camera.position.set(0, 28, 48);

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 200;
    this.controls.target.set(0, 0, 0);

    // Starfield
    this._addStars();

    // Lights
    this.scene.add(new THREE.AmbientLight(0x334455, 0.55));
    this.sunLight = new THREE.PointLight(0xfff0d0, 2.2, 0, 0);
    this.scene.add(this.sunLight);

    this.root = new THREE.Group();
    this.scene.add(this.root);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this._clock = new THREE.Clock();

    this._onResize = () => this.resize();
    window.addEventListener("resize", this._onResize);
    canvas.addEventListener("pointerdown", (e) => this._onPointerDown(e));
    canvas.addEventListener("dblclick", (e) => this._onDblClick(e));

    this.resize();
    this._anim = () => {
      this.controls.update();
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
    const mat = new THREE.PointsMaterial({ color: 0x reg, size: 0.35, sizeAttenuation: true });
    this.scene.add(new THREE.Points(geo, mat));
  }

  /** Heliocentric position in scene units from true AU coords */
  heliocentric(x_au, y_au) {
    const r = Math.hypot(x_au, y_au);
    if (r < 1e-12) return new THREE.Vector3(0, 0, 0);
    const pr = Math.sqrt(r) * AU_SCALE;
    return new THREE.Vector3((x_au / r) * pr, 0, (y_au / r) * pr);
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

  setSystem(system) {
    this.clearSystem();
    this.systemData = system;
    if (!system) return;

    // Star
    const starMat = new THREE.MeshBasicMaterial({ color: 0xffd27a });
    const star = new THREE.Mesh(new THREE.SphereGeometry(0.55, 32, 32), starMat);
    star.userData = { bodyId: "star", kind: "star" };
    this.root.add(star);
    // glow
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(0.9, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xffaa44, transparent: true, opacity: 0.2 })
    );
    this.root.add(glow);

    const bodies = system.bodies || [];
    const planets = bodies.filter((b) => b.kind === "planet" || b.kind === "asteroid");
    const moons = bodies.filter((b) => b.kind === "moon");

    // Orbit rings (heliocentric)
    for (const b of planets) {
      const a = b.semi_major_au || 0;
      if (a <= 0) continue;
      const radius = Math.sqrt(a) * AU_SCALE;
      const ring = this._makeRing(radius, b.kind === "asteroid" ? 0x333844 : 0x1a2838);
      this.root.add(ring);
    }

    // Planets / asteroids
    for (const b of planets) {
      const pos = this.heliocentric(b.x_au || 0, b.y_au || 0);
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
        new THREE.MeshStandardMaterial({ color, roughness: 0.7, metalness: 0.15 })
      );
      mesh.position.copy(pos);
      mesh.userData = { bodyId: b.id, kind: b.kind };
      this.root.add(mesh);
      this.bodyMeshes.set(b.id, { mesh, data: b, kind: b.kind, baseScale: 1 });

      // Label sprite (simple canvas)
      const label = this._makeLabel(b.name);
      label.position.copy(pos).add(new THREE.Vector3(0, radius + 0.25, 0));
      label.userData = { bodyId: b.id, isLabel: true };
      this.root.add(label);
      this.bodyMeshes.get(b.id).label = label;
    }

    // Moons — attached near parent; visible when camera is close / focused
    for (const b of moons) {
      const parent = planets.find((p) => p.id === b.parent_id);
      if (!parent) continue;
      const parentPos = this.heliocentric(parent.x_au || 0, parent.y_au || 0);
      // Local moon ring: scale so moons are readable when focused on parent
      const localR = 0.55 + (b.display_orbit_au || 0.03) * 8;
      const phase = b.phase || 0;
      const pos = parentPos
        .clone()
        .add(new THREE.Vector3(Math.cos(phase) * localR, Math.sin(phase) * 0.15 * localR, Math.sin(phase) * localR));

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.07, 16, 16),
        new THREE.MeshStandardMaterial({ color: 0xb8c0c8, roughness: 0.85 })
      );
      mesh.position.copy(pos);
      mesh.userData = { bodyId: b.id, kind: "moon", parentId: b.parent_id };
      this.root.add(mesh);

      // subtle moon orbit ring around parent (only useful when zoomed)
      const mring = this._makeRing(localR, 0x2a3545, parentPos);
      mring.userData = { moonRingFor: b.parent_id };
      this.root.add(mring);

      const label = this._makeLabel(b.name, 0.55);
      label.position.copy(pos).add(new THREE.Vector3(0, 0.14, 0));
      this.root.add(label);
      this.bodyMeshes.set(b.id, { mesh, data: b, kind: "moon", label, parentId: b.parent_id });
    }

    this._updateSelectionVisual();
    this._updateFocusVisibility();
  }

  /** Update positions when sim state refreshes (same system). */
  updatePositions(system) {
    if (!system || !this.systemData) return;
    this.systemData = system;
    const bodies = system.bodies || [];
    const byId = Object.fromEntries(bodies.map((b) => [b.id, b]));

    for (const [id, entry] of this.bodyMeshes) {
      const b = byId[id];
      if (!b) continue;
      entry.data = b;
      let pos;
      if (b.kind === "moon") {
        const parent = byId[b.parent_id];
        if (!parent) continue;
        const parentPos = this.heliocentric(parent.x_au || 0, parent.y_au || 0);
        const localR = 0.55 + (b.display_orbit_au || 0.03) * 8;
        const phase = b.phase || 0;
        pos = parentPos
          .clone()
          .add(new THREE.Vector3(Math.cos(phase) * localR, Math.sin(phase) * 0.15 * localR, Math.sin(phase) * localR));
      } else {
        pos = this.heliocentric(b.x_au || 0, b.y_au || 0);
      }
      entry.mesh.position.copy(pos);
      if (entry.label) {
        const lift = b.kind === "moon" ? 0.14 : 0.28;
        entry.label.position.copy(pos).add(new THREE.Vector3(0, lift, 0));
      }
    }
  }

  _makeRing(radius, color, center = null) {
    const pts = [];
    const n = 128;
    for (let i = 0; i <= n; i++) {
      const t = (i / n) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(t) * radius, 0, Math.sin(t) * radius));
    }
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.55 });
    const line = new THREE.Line(geo, mat);
    if (center) line.position.copy(center);
    return line;
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
    this.focusId = id;
    const entry = id ? this.bodyMeshes.get(id) : null;
    if (!entry) {
      // system view
      this.focusId = null;
      this.controls.target.set(0, 0, 0);
      this.camera.position.set(0, 28, 48);
      this.controls.minDistance = 0.8;
      this.controls.update();
      this._updateFocusVisibility();
      if (this.onFocus) this.onFocus(null);
      return;
    }
    // If moon, focus parent planet for context
    let targetEntry = entry;
    let targetId = id;
    if (entry.kind === "moon" && entry.parentId) {
      const p = this.bodyMeshes.get(entry.parentId);
      if (p) {
        targetEntry = p;
        targetId = entry.parentId;
        this.focusId = targetId;
      }
    }
    const p = targetEntry.mesh.position;
    this.controls.target.copy(p);
    // Pull camera in so moons of a giant are readable
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
    this.controls.maxDistance = 200;
  }

  _updateSelectionVisual() {
    for (const [, entry] of this.bodyMeshes) {
      const sel = entry.mesh.userData.bodyId === this.selectedId;
      if (entry.mesh.material && entry.mesh.material.emissive) {
        entry.mesh.material.emissive = new THREE.Color(sel ? 0x1a4a7a : 0x000000);
        entry.mesh.material.emissiveIntensity = sel ? 0.55 : 0;
      }
    }
  }

  _updateFocusVisibility() {
    // In system view, hide moon labels far away; when focused on a planet, emphasize its moons
    const focus = this.focusId;
    for (const [, entry] of this.bodyMeshes) {
      if (entry.kind !== "moon") {
        if (entry.label) entry.label.visible = !focus || entry.mesh.userData.bodyId === focus;
        continue;
      }
      const parentFocused = focus && entry.parentId === focus;
      const systemView = !focus;
      // Moons always rendered; labels only when parent focused or camera close
      if (entry.label) entry.label.visible = parentFocused;
      entry.mesh.visible = true;
      // scale moons up slightly when parent focused
      const s = parentFocused ? 1.6 : systemView ? 0.85 : 1;
      entry.mesh.scale.setScalar(s);
    }
    this.root.traverse((o) => {
      if (o.userData?.moonRingFor) {
        o.visible = !focus || o.userData.moonRingFor === focus;
        if (focus && o.userData.moonRingFor === focus) {
          // re-center ring on parent
          const p = this.bodyMeshes.get(focus);
          if (p) o.position.copy(p.mesh.position);
        }
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
    // ignore drag clicks: record and check on pointerup-ish via small move
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
