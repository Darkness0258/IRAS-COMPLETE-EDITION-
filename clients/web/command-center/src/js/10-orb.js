/* ==========================================================================
   The orb shows what IRAS is doing, live.

   idle       slow breathing glow (4s loop)
   listening  rings grow with your voice
   thinking   orbiting light
   speaking   waveform follows IRAS's voice
   acting     scan sweep around the core
   approval   amber or red pulse and a countdown ring

   Three quality levels:
     full   60fps, particles, trails
     lite   Performance mode: 20fps, 1x pixel ratio, no particles or trails
     still  reduced motion: frozen time, redraw only when something changes
   ========================================================================== */
"use strict";

(function () {
  const TAU = Math.PI * 2;
  const hex = (h) => {
    h = String(h || "#4C8DFF").trim().replace("#", "");
    if (h.length === 3) h = h.split("").map((c) => c + c).join("");
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${clamp(a, 0, 1)})`;
  const mix = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];

  class Orb {
    constructor(canvas) {
      this.c = canvas;
      this.g = canvas.getContext("2d");
      this.size = 0;
      this.dpr = 1;
      this.time = 2.4;
      this.last = 0;
      this.active = false;
      this.raf = 0;
      this.k = { listen: 0, think: 0, speak: 0, act: 0, appr: 0 };
      this.lvMic = 0;
      this.lvTts = 0;
      this.rings = [];
      this.lastSpawn = 0;
      this.parts = Array.from({ length: 34 }, () => ({ a: rand(0, TAU), r: rand(1.3, 2.05), sp: rand(.05, .22) * (Math.random() < .5 ? -1 : 1), s: rand(.8, 2.1), al: rand(.25, .9), ph: rand(0, TAU) }));
      this.acc = 0; this.n = 0;
      this.frame = this.frame.bind(this);
      this.readColors();
      this.ro = new ResizeObserver(() => this.resize());
      this.ro.observe(canvas);
      this.resize();
    }

    readColors() {
      const cs = getComputedStyle(document.documentElement);
      const v = (n) => hex(cs.getPropertyValue(n));
      this.col = { core: v("--orb-core"), mid: v("--orb-mid"), deep: v("--orb-deep"), accent: v("--accent-fill"), warn: v("--warn-fill"), crit: v("--crit-fill"), light: IRAS.env.theme === "light" };
    }

    quality() {
      if (IRAS.env.reduceMotion) return "still";
      return IRAS.env.perf === "lite" ? "lite" : "full";
    }

    resize() {
      const r = this.c.getBoundingClientRect();
      const css = Math.round(r.width);
      if (!css) return;
      this.dpr = Math.min(window.devicePixelRatio || 1, this.quality() === "full" ? 2 : 1);
      this.size = css;
      this.c.width = Math.round(css * this.dpr);
      this.c.height = Math.round(css * this.dpr);
      this.g.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this.draw();
    }

    setActive(on) {
      if (on === this.active) return;
      this.active = on;
      cancelAnimationFrame(this.raf);
      if (on) { this.last = performance.now(); this.raf = requestAnimationFrame(this.frame); this.resize(); }
    }

    frame(ts) {
      if (!this.active) return;
      this.raf = requestAnimationFrame(this.frame);
      const q = this.quality();
      const minDt = q === "full" ? 0 : q === "lite" ? 49 : 160;
      const raw = ts - this.last;
      if (raw < minDt) return;
      this.dt = Math.min(.1, raw / 1000);
      this.last = ts;
      if (q !== "still") this.time += this.dt;
      this.step(this.dt, q);
      this.draw();
      this.sample(raw, q);
    }

    /* If the window is struggling, Auto mode quietly switches to Performance mode. */
    sample(raw, q) {
      if (q !== "full" || IRAS.settings.perf !== "auto" || document.hidden) { this.acc = 0; this.n = 0; return; }
      this.acc += raw; this.n++;
      if (this.n >= 150) {
        const avg = this.acc / this.n;
        this.acc = 0; this.n = 0;
        if (avg > 36 && IRAS.onSlow) IRAS.onSlow(avg);
      }
    }

    step(dt, q) {
      const ui = S.ui;
      const tgt = { listen: ui === "listening", think: ui === "thinking", speak: ui === "speaking", act: ui === "acting", appr: ui === "approval" };
      const ease = 1 - Math.exp(-dt * 7);
      for (const key in tgt) this.k[key] += ((tgt[key] ? 1 : 0) - this.k[key]) * ease;
      const m = S.level.mic, t = S.level.tts;
      this.lvMic += (m - this.lvMic) * (1 - Math.exp(-dt * (m > this.lvMic ? 20 : 7)));
      this.lvTts += (t - this.lvTts) * (1 - Math.exp(-dt * (t > this.lvTts ? 22 : 8)));
      if (q === "full") for (const p of this.parts) p.a += p.sp * dt * (1 + 2.2 * this.k.think + .8 * this.k.act);
      if (this.k.listen > .3 && this.lvMic > .1 && this.time - this.lastSpawn > .2 && q !== "still") {
        this.rings.push({ t0: this.time, s: this.lvMic });
        this.lastSpawn = this.time;
        if (this.rings.length > 7) this.rings.shift();
      }
    }

    orbit(g, cx, cy, r, acc, core, half, q) {
      const k = this.k.think;
      if (k < .02) return;
      const rx = r * 1.44, ry = r * 1.1, tilt = -.34;
      g.save();
      g.translate(cx, cy);
      g.rotate(tilt);
      if (half === "back") {
        g.lineWidth = 1;
        g.strokeStyle = rgba(acc, .2 * k);
        g.beginPath(); g.ellipse(0, 0, rx, ry, 0, 0, TAU); g.stroke();
      }
      const trail = q === "full" ? 15 : 0;
      for (let j = 0; j < 3; j++) {
        const base = this.time * (1.55 + .22 * j) + (j * TAU) / 3;
        for (let n = trail; n >= 0; n--) {
          const a = base - n * .075;
          const front = Math.sin(a) > 0;
          if ((half === "front") !== front) continue;
          const f = 1 - n / (trail + 1);
          const x = Math.cos(a) * rx, y = Math.sin(a) * ry;
          g.fillStyle = rgba(mix(core, acc, n ? .5 : .15), (n ? .75 * f * f : 1) * k);
          g.beginPath(); g.arc(x, y, n ? 1.1 + 2.1 * f : 3.6, 0, TAU); g.fill();
          if (n === 0 && q === "full") {
            const gl = g.createRadialGradient(x, y, 0, x, y, 16);
            gl.addColorStop(0, rgba(acc, .55 * k)); gl.addColorStop(1, rgba(acc, 0));
            g.fillStyle = gl; g.beginPath(); g.arc(x, y, 16, 0, TAU); g.fill();
          }
        }
      }
      g.restore();
    }

    draw() {
      const g = this.g, S_ = this.size;
      if (!S_) return;
      const q = this.quality(), t = this.time, k = this.k, col = this.col, light = col.light;
      const cx = S_ / 2, cy = S_ / 2, R = S_ * .23;
      g.clearRect(0, 0, S_, S_);

      const authCol = S.authority === "critical" ? col.crit : col.warn;
      const ta = k.appr;
      const acc = mix(col.accent, authCol, ta);
      const core = mix(col.core, mix(authCol, [255, 255, 255], .55), ta * .55);
      const mid = mix(col.mid, authCol, ta * .85);
      const deep = mix(col.deep, mix(authCol, [0, 0, 0], .45), ta * .85);

      const breathe = Math.sin((t * TAU) / 4);
      const voice = k.speak * this.lvTts + k.listen * this.lvMic;
      const pulse = .5 + .5 * Math.sin((t * TAU) / 1.1);
      const r = R * (1 + .022 * breathe * (1 - .6 * (k.speak + k.listen)) + .07 * k.speak * this.lvTts + .05 * k.listen * this.lvMic + .02 * k.appr * (pulse - .5));

      /* halo: glass needs something to catch the light */
      g.save();
      g.globalCompositeOperation = light ? "source-over" : "lighter";
      const haloA = (light ? .34 : .6) * (.78 + .1 * breathe + .5 * voice + .3 * k.think + .2 * k.act + .3 * k.appr * pulse);
      const hr = R * (2.2 + .25 * voice);
      const gh = g.createRadialGradient(cx, cy, r * .5, cx, cy, hr);
      gh.addColorStop(0, rgba(acc, haloA));
      gh.addColorStop(.35, rgba(acc, haloA * .36));
      gh.addColorStop(1, rgba(acc, 0));
      g.fillStyle = gh;
      g.beginPath(); g.arc(cx, cy, hr, 0, TAU); g.fill();
      g.restore();

      /* dust */
      if (q === "full") {
        for (const p of this.parts) {
          const rr = R * (p.r + .2 * Math.sin(t * .7 + p.ph) - .25 * k.listen * this.lvMic + .3 * k.speak * this.lvTts);
          const x = cx + Math.cos(p.a) * rr, y = cy + Math.sin(p.a) * rr * .84;
          g.fillStyle = rgba(light ? deep : mix(core, acc, .4), (light ? .35 : .5) * p.al * (.6 + .4 * Math.sin(t * 1.3 + p.ph)));
          g.beginPath(); g.arc(x, y, p.s, 0, TAU); g.fill();
        }
      }

      /* ambient rings */
      g.lineWidth = 1.2;
      for (let i = 0; i < 2; i++) {
        g.strokeStyle = rgba(acc, (light ? .24 : .17) * (1 - .4 * i) * (1 - .6 * k.appr));
        g.beginPath(); g.arc(cx, cy, r * (1.26 + i * .22) + 3 * Math.sin(t * .9 + i), 0, TAU); g.stroke();
      }

      /* listening: rings grow with your voice */
      if (k.listen > .02) {
        g.lineWidth = 2;
        g.strokeStyle = rgba(acc, .55 * k.listen);
        g.beginPath(); g.arc(cx, cy, r * (1.12 + .32 * this.lvMic), 0, TAU); g.stroke();
        for (const rg of this.rings) {
          const age = (t - rg.t0) / 1.5;
          if (age >= 1 || age < 0) continue;
          g.lineWidth = 2.4 * (1 - age) + .5;
          g.strokeStyle = rgba(acc, (1 - age) * (.55 * rg.s + .1) * k.listen);
          g.beginPath(); g.arc(cx, cy, r * (1.1 + age * (.55 + .6 * rg.s)), 0, TAU); g.stroke();
        }
      }

      /* acting: scan sweep and ticks */
      if (k.act > .02) {
        if (g.createConicGradient) {
          const cg = g.createConicGradient(t * 2.4, cx, cy);
          cg.addColorStop(0, rgba(acc, 0)); cg.addColorStop(.7, rgba(acc, 0)); cg.addColorStop(.985, rgba(acc, .6 * k.act)); cg.addColorStop(1, rgba(acc, 0));
          g.strokeStyle = cg; g.lineWidth = r * .44;
          g.beginPath(); g.arc(cx, cy, r * 1.36, 0, TAU); g.stroke();
        } else {
          g.strokeStyle = rgba(acc, .4 * k.act); g.lineWidth = 3;
          g.beginPath(); g.arc(cx, cy, r * 1.36, t * 2.4, t * 2.4 + 1.2); g.stroke();
        }
        g.lineWidth = 1.5;
        for (let i = 0; i < 36; i++) {
          const a = (i / 36) * TAU - t * .25, major = i % 3 === 0, r0 = r * 1.66, r1 = r0 + (major ? 9 : 5);
          g.strokeStyle = rgba(acc, (major ? .65 : .3) * k.act);
          g.beginPath(); g.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0); g.lineTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1); g.stroke();
        }
      }

      /* approval: countdown ring */
      if (k.appr > .02) {
        const frac = clamp(IRAS.approvalFrac ? IRAS.approvalFrac() : 1, 0, 1);
        g.lineCap = "round"; g.lineWidth = 7;
        g.strokeStyle = rgba(authCol, .2 * k.appr);
        g.beginPath(); g.arc(cx, cy, r * 1.5, 0, TAU); g.stroke();
        g.strokeStyle = rgba(authCol, .96 * k.appr);
        g.beginPath(); g.arc(cx, cy, r * 1.5, -Math.PI / 2, -Math.PI / 2 + TAU * frac); g.stroke();
        g.lineCap = "butt";
      }

      /* speaking: waveform follows IRAS's voice */
      if (k.speak > .02) {
        const N = q === "lite" ? 44 : 88, lv = this.lvTts;
        g.lineCap = "round"; g.lineWidth = q === "lite" ? 4 : 3;
        for (let i = 0; i < N; i++) {
          const a = (i / N) * TAU - Math.PI / 2;
          const e1 = Math.sin(i * .53 + t * 7.3), e2 = Math.sin(i * 1.31 - t * 5.1), e3 = Math.sin(i * .21 + t * 2.3);
          const env = (.45 + .55 * Math.abs(e1 * .6 + e2 * .4)) * (.65 + .35 * e3);
          const len = (r * (.05 + .55 * lv * env) + r * .03) * k.speak;
          const r0 = r * 1.18;
          g.strokeStyle = rgba(acc, (.3 + .6 * Math.min(1, len / (r * .38))) * k.speak);
          g.beginPath();
          g.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
          g.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
          g.stroke();
        }
        g.lineCap = "butt";
      }

      /* thinking: orbiting light, the back half passes behind the core */
      this.orbit(g, cx, cy, r, acc, core, "back", q);

      /* the core: a dark socket with a luminous sphere in it, like the logo */
      g.fillStyle = light ? "rgba(255,255,255,.55)" : "rgba(2,5,14,.7)";
      g.beginPath(); g.arc(cx, cy, r * 1.08, 0, TAU); g.fill();
      g.lineWidth = 1.5; g.strokeStyle = rgba(acc, .42);
      g.beginPath(); g.arc(cx, cy, r * 1.08, 0, TAU); g.stroke();

      const sg = g.createRadialGradient(cx - r * .32, cy - r * .38, r * .06, cx, cy, r * 1.04);
      sg.addColorStop(0, rgba(core, 1));
      sg.addColorStop(.2, rgba(mix(core, mid, .55), 1));
      sg.addColorStop(.48, rgba(mid, 1));
      sg.addColorStop(.8, rgba(mix(mid, deep, .75), 1));
      sg.addColorStop(1, rgba(deep, 1));
      g.fillStyle = sg;
      g.beginPath(); g.arc(cx, cy, r, 0, TAU); g.fill();

      /* a soft light drifting inside the sphere */
      g.save();
      g.beginPath(); g.arc(cx, cy, r, 0, TAU); g.clip();
      const ix = cx + Math.cos(t * .6) * r * .28, iy = cy + Math.sin(t * .5) * r * .24;
      const ig = g.createRadialGradient(ix, iy, 0, ix, iy, r * .85);
      ig.addColorStop(0, rgba(core, .32 + .25 * voice + .2 * k.think)); ig.addColorStop(1, rgba(core, 0));
      g.fillStyle = ig; g.fillRect(cx - r, cy - r, r * 2, r * 2);
      /* rim shadow */
      const rim = g.createRadialGradient(cx, cy, r * .66, cx, cy, r);
      rim.addColorStop(0, rgba(deep, 0)); rim.addColorStop(1, rgba(deep, .5));
      g.fillStyle = rim; g.fillRect(cx - r, cy - r, r * 2, r * 2);
      g.restore();

      const lg = g.createLinearGradient(cx - r, cy - r, cx + r, cy + r);
      lg.addColorStop(0, "rgba(255,255,255,.7)"); lg.addColorStop(.45, "rgba(255,255,255,0)"); lg.addColorStop(1, rgba(acc, .5));
      g.lineWidth = 1.4; g.strokeStyle = lg;
      g.beginPath(); g.arc(cx, cy, r, 0, TAU); g.stroke();

      /* specular */
      const sp = g.createRadialGradient(cx - r * .36, cy - r * .44, 0, cx - r * .36, cy - r * .44, r * .34);
      sp.addColorStop(0, "rgba(255,255,255,.55)"); sp.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = sp;
      g.beginPath(); g.ellipse(cx - r * .36, cy - r * .44, r * .34, r * .24, -.6, 0, TAU); g.fill();

      this.orbit(g, cx, cy, r, acc, core, "front", q);
    }
  }

  IRAS.initOrb = function () {
    const canvas = $("#orb");
    if (!canvas || !canvas.getContext) { document.documentElement.classList.add("no-canvas"); return; }
    let orb;
    try { orb = new Orb(canvas); } catch (e) { console.error(e); document.documentElement.classList.add("no-canvas"); return; }
    IRAS.orb = orb;
    const refresh = () => { orb.readColors(); orb.resize(); };
    bus.on("appearance", refresh);
    bus.on("ui", () => { if (orb.quality() === "still") orb.draw(); });
    bus.on("view", (e) => orb.setActive(e.view === "home" && !document.hidden));
    bus.on("visibility", (e) => orb.setActive(!e.hidden && IRAS.view() === "home"));
    orb.setActive(IRAS.view() === "home" && !document.hidden);
  };
})();
