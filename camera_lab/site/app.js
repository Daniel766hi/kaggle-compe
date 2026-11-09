// Vision Lab: live camera or photo -> object detection, line counting and image processing, all in the browser.
(() => {
  const $ = (id) => document.getElementById(id);
  const view = $("view"), ctx = view.getContext("2d", { willReadFrequently: true });
  const video = $("video");
  const MAX_SIDE = 960, LIVE_SIDE = 640;
  let source = null;          // ImageData of the current frame at working size
  let mode = "detect";
  let model = null, modelLoading = null;
  let dets = [], detsFor = null, detBusy = false, detMs = 0;
  let picked = null;          // [r, g, b]
  let live = null;            // { stream, facing }
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // ---------- photos ----------
  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("This file could not be read as an image."));
      img.src = src;
    });
  }
  function useImage(img, label) {
    stopCamera();
    const scale = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
    view.width = Math.round(img.naturalWidth * scale);
    view.height = Math.round(img.naturalHeight * scale);
    ctx.drawImage(img, 0, 0, view.width, view.height);
    source = ctx.getImageData(0, 0, view.width, view.height);
    dets = []; detsFor = null; picked = null;
    $("hud").textContent = `${label} · ${view.width}×${view.height}`;
    render();
  }
  $("fileInput").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    try {
      useImage(await loadImage(url), file.name || "Photo");
      document.querySelectorAll(".thumbs button").forEach((b) => b.setAttribute("aria-pressed", "false"));
    } catch (err) {
      $("hud").textContent = err.message;
    } finally {
      URL.revokeObjectURL(url);
      e.target.value = "";
    }
  });
  document.querySelectorAll(".thumbs button").forEach((b) => b.addEventListener("click", async () => {
    document.querySelectorAll(".thumbs button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    useImage(await loadImage(b.dataset.sample), b.title.split(" (")[0]);
  }));

  // ---------- live camera ----------
  const camStatus = (text, error) => { $("camStatus").textContent = text; $("camStatus").classList.toggle("error", !!error); };
  async function startCamera(facing) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camStatus("This browser cannot open the camera here. Try Chrome or Safari, or upload a photo.", true);
      return;
    }
    stopCamera();
    camStatus("Asking for the camera…");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
      });
      video.srcObject = stream;
      await video.play();
      live = { stream, facing, frames: 0, t0: performance.now(), fps: 0 };
      dets = []; detsFor = null; counter.reset(); updateCounter();
      document.querySelectorAll(".thumbs button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      $("camBtn").textContent = "Stop camera"; $("camBtn").classList.add("stop"); $("camBtn").classList.remove("primary");
      $("flipBtn").hidden = false; $("freezeBtn").hidden = false; $("liveDot").hidden = false;
      $("counterHint").textContent = "Each detected object is followed from frame to frame and counted once when its centre crosses the line.";
      camStatus("");
      requestAnimationFrame(tick);
    } catch (err) {
      const name = err && err.name;
      camStatus(name === "NotAllowedError" ? "Camera permission was refused. Allow it in the browser's site settings, or upload a photo."
        : name === "NotFoundError" ? "No camera was found on this device. Upload a photo instead."
        : "The camera could not start: " + (err && err.message || err), true);
    }
  }
  function stopCamera() {
    if (!live) return;
    live.stream.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
    live = null;
    $("camBtn").textContent = "Start camera"; $("camBtn").classList.remove("stop"); $("camBtn").classList.add("primary");
    $("flipBtn").hidden = true; $("freezeBtn").hidden = true; $("liveDot").hidden = true;
  }
  $("camBtn").addEventListener("click", () => { if (live) { stopCamera(); $("hud").textContent = "Camera stopped"; } else startCamera("environment"); });
  $("flipBtn").addEventListener("click", () => live && startCamera(live.facing === "user" ? "environment" : "user"));
  $("freezeBtn").addEventListener("click", () => {
    if (!live || !source) return;
    const frame = source; stopCamera();
    source = frame; detsFor = null;
    $("hud").textContent = `Frozen frame · ${view.width}×${view.height}`;
    render();
  });

  function tick() {
    if (!live) return;
    if (video.readyState >= 2 && video.videoWidth) {
      const scale = Math.min(1, LIVE_SIDE / Math.max(video.videoWidth, video.videoHeight));
      const w = Math.round(video.videoWidth * scale), h = Math.round(video.videoHeight * scale);
      if (view.width !== w || view.height !== h) { view.width = w; view.height = h; }
      ctx.save();
      if (live.facing === "user") { ctx.translate(w, 0); ctx.scale(-1, 1); } // mirror the selfie camera
      ctx.drawImage(video, 0, 0, w, h);
      ctx.restore();
      source = ctx.getImageData(0, 0, w, h);
      live.frames++;
      const dt = performance.now() - live.t0;
      if (dt > 1000) { live.fps = Math.round(live.frames * 1000 / dt); live.frames = 0; live.t0 = performance.now(); }
      $("hud").textContent = `Live · ${w}×${h} · ${live.fps} fps` + (mode === "detect" && detMs ? ` · detector ${Math.round(1000 / detMs)}/s` : "");
      render();
    }
    requestAnimationFrame(tick);
  }

  // ---------- modes ----------
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    mode = t.dataset.mode;
    document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === t)));
    document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== mode; });
    render();
  }));
  for (const [id, fmt] of [["minScore", (v) => v + "%"], ["edgeThr", (v) => v], ["tol", (v) => v], ["levels", (v) => v], ["linePos", (v) => v + "%"]]) {
    $(id).addEventListener("input", () => { $(id + "Out").textContent = fmt($(id).value); if (!live) render(); });
  }
  for (const id of ["countClass", "lineDir"]) $(id).addEventListener("change", () => { counter.reset(); updateCounter(); if (!live) render(); });
  $("resetBtn").addEventListener("click", () => { counter.reset(); updateCounter(); });

  function render() {
    if (!source) return;
    if (mode === "detect") return renderDetect();
    if (mode === "edges") return renderEdges();
    if (mode === "colour") return renderColour();
    if (mode === "cartoon") return renderCartoon();
    if (mode === "hist") return renderHist();
  }

  // ---------- helpers ----------
  function gray(data) {
    const g = new Float32Array(data.length / 4);
    for (let i = 0, j = 0; i < data.length; i += 4, j++) g[j] = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    return g;
  }
  function sobel(g, w, h) {
    const mag = new Float32Array(w * h);
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      const gx = -g[i - w - 1] - 2 * g[i - 1] - g[i + w - 1] + g[i - w + 1] + 2 * g[i + 1] + g[i + w + 1];
      const gy = -g[i - w - 1] - 2 * g[i - w] - g[i - w + 1] + g[i + w - 1] + 2 * g[i + w] + g[i + w + 1];
      mag[i] = Math.hypot(gx, gy) / 4;
    }
    return mag;
  }
  const hex = (c) => "#" + c.map((v) => v.toString(16).padStart(2, "0")).join("");

  // ---------- detection ----------
  function ensureModel() {
    if (model || modelLoading) return modelLoading || Promise.resolve(model);
    if (!window.cocoSsd || !window.tf) {
      $("detectStatus").textContent = "The detector library did not load. Check the connection and reload the page.";
      $("detectStatus").classList.add("error");
      return Promise.resolve(null);
    }
    $("detectStatus").textContent = "Loading the model (18 MB, once per visit)…";
    modelLoading = cocoSsd.load({ base: "lite_mobilenet_v2", modelUrl: "models/coco/model.json" })
      .then((m) => { model = m; $("detectStatus").textContent = `Model ready (TensorFlow.js, ${tf.getBackend()} backend).`; if (!live) render(); return m; })
      .catch((e) => { $("detectStatus").textContent = "The model could not load: " + (e && e.message || e); $("detectStatus").classList.add("error"); modelLoading = null; return null; });
    return modelLoading;
  }
  function requestDetect() {
    if (!model || detBusy || (!live && detsFor === source)) return;
    detBusy = true;
    const src = source, t0 = performance.now();
    if (!live) $("detectStatus").textContent = "Detecting…";
    model.detect(src, 30, 0.1).then((r) => {
      detMs = performance.now() - t0;
      dets = r; detsFor = src;
      if (live) { counter.update(r, src.width, src.height, counterOpts()); updateCounter(); }
      else $("detectStatus").textContent = `Detected in ${Math.round(detMs)} ms on your device.`;
      detBusy = false;
      if (!live && mode === "detect") render();
    }).catch((e) => { detBusy = false; $("detectStatus").textContent = "Detection failed: " + (e && e.message || e); });
  }

  let lastTable = 0;
  function renderDetect() {
    ctx.putImageData(source, 0, 0);
    if (!model) ensureModel(); else requestDetect();
    const fresh = live || detsFor === source;
    const min = $("minScore").value / 100;
    const kept = fresh ? dets.filter((d) => d.score >= min) : [];
    const lw = Math.max(2, view.width / 300), fs = Math.max(12, view.width / 45);
    ctx.font = `600 ${fs}px "IBM Plex Mono", monospace`;
    const mark = css("--mark");
    kept.forEach((d) => {
      const [x, y, w, h] = d.bbox;
      ctx.strokeStyle = mark; ctx.lineWidth = lw; ctx.strokeRect(x, y, w, h);
      const text = `${d.class} ${Math.round(d.score * 100)}%`;
      const tw = ctx.measureText(text).width + 10;
      ctx.fillStyle = mark; ctx.fillRect(x, Math.max(0, y - fs - 6), tw, fs + 6);
      ctx.fillStyle = "#ffffff"; ctx.fillText(text, x + 5, Math.max(fs, y - 6));
    });
    if (live) drawCounter(lw);
    // In live mode, refresh the table a few times a second rather than every frame.
    const now = performance.now();
    if (!live || now - lastTable > 250) { lastTable = now; fillTable(kept, fresh); }
  }
  function fillTable(kept, fresh) {
    const by = {};
    kept.forEach((d) => { by[d.class] = by[d.class] || { n: 0, best: 0 }; by[d.class].n++; by[d.class].best = Math.max(by[d.class].best, d.score); });
    $("objCount").textContent = fresh ? kept.length : "–";
    $("kindCount").textContent = fresh ? Object.keys(by).length : "–";
    const rows = Object.entries(by).sort((a, b) => b[1].n - a[1].n);
    const tbody = $("objTable"); tbody.textContent = "";
    if (!rows.length) {
      const td = tbody.insertRow().insertCell(); td.colSpan = 3; td.className = "status";
      td.textContent = !fresh ? "Waiting for the model" : "Nothing above this confidence. Lower it, or try people, animals, vehicles or household objects.";
    }
    rows.forEach(([k, v]) => {
      const tr = tbody.insertRow();
      tr.insertCell().textContent = k;
      const c = tr.insertCell(); c.className = "num"; c.textContent = v.n;
      const s = tr.insertCell(); s.className = "num"; s.textContent = Math.round(v.best * 100) + "%";
    });
  }

  // ---------- line counter ----------
  // Detections are matched to the nearest track of the same class from the previous detector pass; a track is
  // counted once, in the direction its centre crosses the line. Tracks unseen for several passes are dropped.
  const counter = {
    reset() { this.tracks = []; this.next = 1; this.a = 0; this.b = 0; },
    update(found, W, H, o) {
      const line = o.vertical ? o.pos * W : o.pos * H;
      const cands = found.filter((d) => d.score >= o.min && (o.cls === "any" || d.class === o.cls))
        .map((d) => ({ x: d.bbox[0] + d.bbox[2] / 2, y: d.bbox[1] + d.bbox[3] / 2, cls: d.class }));
      const maxDist = 0.22 * Math.max(W, H);
      const pairs = [];
      this.tracks.forEach((t, ti) => cands.forEach((c, ci) => {
        if (t.cls !== c.cls) return;
        const dist = Math.hypot(t.x - c.x, t.y - c.y);
        if (dist < maxDist) pairs.push([dist, ti, ci]);
      }));
      pairs.sort((p, q) => p[0] - q[0]);
      const usedT = new Set(), usedC = new Set();
      for (const [, ti, ci] of pairs) {
        if (usedT.has(ti) || usedC.has(ci)) continue;
        usedT.add(ti); usedC.add(ci);
        const t = this.tracks[ti], c = cands[ci];
        const before = o.vertical ? t.x : t.y, after = o.vertical ? c.x : c.y;
        if (!t.counted && before < line && after >= line) { this.a++; t.counted = true; }
        else if (!t.counted && before >= line && after < line) { this.b++; t.counted = true; }
        t.x = c.x; t.y = c.y; t.missed = 0;
        t.trail.push([c.x, c.y]); if (t.trail.length > 12) t.trail.shift();
      }
      this.tracks.forEach((t, ti) => { if (!usedT.has(ti)) t.missed++; });
      this.tracks = this.tracks.filter((t) => t.missed <= 6);
      cands.forEach((c, ci) => { if (!usedC.has(ci)) this.tracks.push({ id: this.next++, x: c.x, y: c.y, cls: c.cls, missed: 0, counted: false, trail: [[c.x, c.y]] }); });
    },
  };
  counter.reset();
  const counterOpts = () => ({ cls: $("countClass").value, vertical: $("lineDir").value === "v", pos: $("linePos").value / 100, min: $("minScore").value / 100 });
  function updateCounter() {
    const v = $("lineDir").value === "v";
    $("aLabel").textContent = v ? "Right →" : "Down ↓";
    $("bLabel").textContent = v ? "← Left" : "Up ↑";
    $("countA").textContent = counter.a; $("countB").textContent = counter.b;
    $("countT").textContent = counter.tracks.filter((t) => t.missed === 0).length;
  }
  function drawCounter(lw) {
    const o = counterOpts(), accent = css("--accent");
    ctx.save();
    ctx.setLineDash([lw * 5, lw * 3]); ctx.strokeStyle = accent; ctx.lineWidth = lw * 1.5;
    ctx.beginPath();
    if (o.vertical) { ctx.moveTo(o.pos * view.width, 0); ctx.lineTo(o.pos * view.width, view.height); }
    else { ctx.moveTo(0, o.pos * view.height); ctx.lineTo(view.width, o.pos * view.height); }
    ctx.stroke(); ctx.setLineDash([]);
    counter.tracks.forEach((t) => {
      if (t.missed > 0) return;
      ctx.strokeStyle = t.counted ? accent : "#ffffff"; ctx.lineWidth = lw;
      ctx.beginPath(); t.trail.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
      ctx.fillStyle = t.counted ? accent : "#ffffff";
      ctx.beginPath(); ctx.arc(t.x, t.y, lw * 2.5, 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }

  // ---------- edges ----------
  function renderEdges() {
    const { width: w, height: h, data } = source;
    const mag = sobel(gray(data), w, h);
    const thr = +$("edgeThr").value;
    const out = ctx.createImageData(w, h);
    let n = 0;
    for (let i = 0; i < w * h; i++) {
      const on = mag[i] > thr; if (on) n++;
      const v = on ? 255 : Math.min(60, mag[i]);
      out.data[i * 4] = on ? 120 : v * 0.4; out.data[i * 4 + 1] = on ? 255 : v * 0.5; out.data[i * 4 + 2] = on ? 220 : v * 0.5; out.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    $("edgeShare").textContent = (100 * n / (w * h)).toFixed(1) + "%";
  }

  // ---------- colour ----------
  view.addEventListener("click", (e) => {
    if (mode !== "colour" || !source) return;
    const r = view.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) * view.width / r.width), y = Math.floor((e.clientY - r.top) * view.height / r.height);
    let s = [0, 0, 0], n = 0; // average a 5×5 patch so one noisy pixel does not decide
    for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) {
      const xx = Math.min(view.width - 1, Math.max(0, x + dx)), yy = Math.min(view.height - 1, Math.max(0, y + dy));
      const i = (yy * view.width + xx) * 4; s[0] += source.data[i]; s[1] += source.data[i + 1]; s[2] += source.data[i + 2]; n++;
    }
    picked = s.map((v) => Math.round(v / n));
    renderColour();
  });
  function renderColour() {
    const { width: w, height: h, data } = source;
    const out = ctx.createImageData(w, h);
    const tol = +$("tol").value;
    let hits = 0;
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      const match = picked && Math.hypot(r - picked[0], g - picked[1], b - picked[2]) <= tol;
      if (match) { hits++; out.data[i] = r; out.data[i + 1] = g; out.data[i + 2] = b; }
      else { const y = 0.299 * r + 0.587 * g + 0.114 * b; const v = picked ? y * 0.45 + 40 : y; out.data[i] = out.data[i + 1] = out.data[i + 2] = v; }
      out.data[i + 3] = 255;
    }
    ctx.putImageData(picked ? out : source, 0, 0);
    $("swatch").style.background = picked ? hex(picked) : "transparent";
    $("pickedHex").textContent = picked ? `${hex(picked)}  rgb(${picked.join(", ")})` : "tap the image";
    $("colourShare").textContent = picked ? (100 * hits / (w * h)).toFixed(1) + "%" : "–";
  }

  // ---------- cartoon ----------
  function renderCartoon() {
    const { width: w, height: h, data } = source;
    const levels = +$("levels").value, step = 255 / (levels - 1);
    const mag = sobel(gray(data), w, h);
    const out = ctx.createImageData(w, h);
    for (let i = 0, j = 0; i < data.length; i += 4, j++) {
      const ink = mag[j] > 45;
      for (let c = 0; c < 3; c++) out.data[i + c] = ink ? 25 : Math.round(Math.round(data[i + c] / step) * step);
      out.data[i + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
  }

  // ---------- histogram ----------
  function renderHist() {
    ctx.putImageData(source, 0, 0);
    const { data } = source;
    const H = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
    let sum = 0, sum2 = 0, low = 0, high = 0;
    const n = data.length / 4;
    for (let i = 0; i < data.length; i += 4) {
      H[0][data[i]]++; H[1][data[i + 1]]++; H[2][data[i + 2]]++;
      const y = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
      sum += y; sum2 += y * y; if (y < 8) low++; if (y > 247) high++;
    }
    const mean = sum / n, sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
    $("meanB").textContent = Math.round(mean);
    $("sdB").textContent = Math.round(sd);
    const notes = [];
    if (low / n > 0.03) notes.push(`${(100 * low / n).toFixed(1)}% of pixels are crushed to black`);
    if (high / n > 0.03) notes.push(`${(100 * high / n).toFixed(1)}% are blown out to white`);
    if (sd < 35) notes.push("low contrast");
    $("exposureNote").textContent = notes.length ? "Note: " + notes.join("; ") + "." : "Exposure looks balanced: no heavy clipping at either end.";
    const hc = $("histCanvas"), hx = hc.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.round(hc.clientWidth * dpr), ch = Math.round(hc.clientHeight * dpr);
    if (hc.width !== cw || hc.height !== ch) { hc.width = cw; hc.height = ch; }
    hx.clearRect(0, 0, hc.width, hc.height);
    const max = Math.max(1, ...H.map((a) => Math.max(...a.slice(2, 254))));
    const colors = ["rgba(226,83,46,0.55)", "rgba(11,160,106,0.5)", "rgba(42,120,214,0.5)"];
    H.forEach((a, c) => {
      hx.beginPath(); hx.moveTo(0, hc.height);
      for (let v = 0; v < 256; v++) hx.lineTo(v / 255 * hc.width, hc.height - Math.min(1, a[v] / max) * (hc.height - 4));
      hx.lineTo(hc.width, hc.height); hx.closePath(); hx.fillStyle = colors[c]; hx.fill();
    });
    hx.strokeStyle = css("--line"); hx.lineWidth = dpr;
    hx.beginPath(); hx.moveTo(0, hc.height - dpr / 2); hx.lineTo(hc.width, hc.height - dpr / 2); hx.stroke();
  }

  // ---------- save ----------
  $("saveBtn").addEventListener("click", () => {
    view.toBlob((blob) => {
      if (!blob) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `vision-lab-${mode}.png`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }, "image/png");
  });

  // Expose a small read-only hook for automated checks.
  window.visionLab = { counter, get live() { return !!live; }, get detections() { return dets; } };

  // ---------- start with a sample ----------
  loadImage("samples/astronaut.jpg").then((img) => useImage(img, "Astronaut")).catch(() => { $("hud").textContent = "Start the camera or upload a photo"; });
})();
