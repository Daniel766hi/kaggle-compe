// Vision Lab: a live camera or a photo, then detection, counting, privacy blur, motion, QR codes, colour and filters.
// Everything runs in the browser.
(() => {
  const $ = (id) => document.getElementById(id);
  const view = $("view"), ctx = view.getContext("2d", { willReadFrequently: true });
  const video = $("video");
  const MAX_SIDE = 960, LIVE_SIDE = 640;
  let source = null;          // ImageData of the current frame at working size
  let mode = "detect";
  let model = null, modelLoading = null;
  let dets = [], detsFor = null, detBusy = false, detMs = 0;
  let picked = null;          // [r, g, b] for colour measure
  let live = null;            // { stream, facing, frames, t0, fps }
  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const AI_MODES = new Set(["detect", "blur"]);

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
      dets = []; detsFor = null; motion.reset();
      document.querySelectorAll(".thumbs button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      $("camBtn").textContent = "Stop camera"; $("camBtn").classList.add("stop"); $("camBtn").classList.remove("primary");
      $("flipBtn").hidden = false; $("freezeBtn").hidden = false; $("liveDot").hidden = false;
      $("recBtn").hidden = !canRecord;
      $("counterHint").textContent = "Each detected object is followed from frame to frame and counted once when its centre crosses the line.";
      $("motionNote").textContent = "";
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
    if (recorder) recorder.stop();
    live.stream.getTracks().forEach((t) => t.stop());
    video.srcObject = null;
    live = null;
    $("camBtn").textContent = "Start camera"; $("camBtn").classList.remove("stop"); $("camBtn").classList.add("primary");
    $("flipBtn").hidden = true; $("freezeBtn").hidden = true; $("liveDot").hidden = true; $("recBtn").hidden = true;
    $("motionNote").textContent = "Start the camera to see motion.";
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
      motion.update(source);
      live.frames++;
      const dt = performance.now() - live.t0;
      if (dt > 1000) { live.fps = Math.round(live.frames * 1000 / dt); live.frames = 0; live.t0 = performance.now(); }
      $("hud").textContent = `Live · ${w}×${h} · ${live.fps} fps` + (AI_MODES.has(mode) && detMs ? ` · detector ${Math.round(1000 / detMs)}/s` : "");
      render();
    }
    requestAnimationFrame(tick);
  }

  // ---------- recording the processed view ----------
  const canRecord = typeof MediaRecorder !== "undefined" && typeof view.captureStream === "function";
  let recorder = null;
  $("recBtn").addEventListener("click", () => {
    if (recorder) { recorder.stop(); return; }
    const type = ["video/webm;codecs=vp9", "video/webm", "video/mp4"].find((t) => MediaRecorder.isTypeSupported(t));
    let rec;
    try { rec = new MediaRecorder(view.captureStream(20), type ? { mimeType: type } : undefined); }
    catch (e) { camStatus("Recording is not supported in this browser.", true); return; }
    const chunks = [], started = performance.now();
    rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const timer = setInterval(() => {
      const s = Math.round((performance.now() - started) / 1000);
      $("recBtn").textContent = `Stop recording · 0:${String(s).padStart(2, "0")}`;
      if (s >= 60) rec.stop(); // keep clips short
    }, 250);
    rec.onstop = () => {
      clearInterval(timer);
      recorder = null;
      $("recBtn").textContent = "Record clip"; $("recBtn").classList.remove("rec");
      const blob = new Blob(chunks, { type: rec.mimeType || type || "video/webm" });
      if (blob.size) download(blob, `vision-lab-${mode}.${blob.type.includes("mp4") ? "mp4" : "webm"}`);
    };
    rec.start(500);
    recorder = rec;
    $("recBtn").classList.add("rec"); $("recBtn").textContent = "Stop recording · 0:00";
  });

  // ---------- tool menu ----------
  function selectMode(m) {
    mode = m;
    document.querySelectorAll(".tool").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.mode === m)));
    document.querySelectorAll("[data-panel]").forEach((p) => { p.hidden = p.dataset.panel !== m; });
    render();
  }
  document.querySelectorAll(".tool").forEach((t) => t.addEventListener("click", () => selectMode(t.dataset.mode)));
  const sliders = [["minScore", "%"], ["edgeThr", ""], ["tol", ""], ["levels", ""], ["linePos", "%"], ["blurMin", "%"],
    ["blurBlock", ""], ["motionThr", ""], ["kColours", ""], ["filterAmt", ""]];
  for (const [id, unit] of sliders) {
    $(id).addEventListener("input", () => { $(id + "Out").textContent = $(id).value + unit; if (!live) render(); });
  }
  for (const id of ["countClass", "lineDir"]) $(id).addEventListener("change", () => { counter.reset(); updateCounter(); if (!live) render(); });
  for (const id of ["blurWhat", "blurStyle", "motionView", "filterKind"]) $(id).addEventListener("change", () => { if (!live) render(); });
  $("resetBtn").addEventListener("click", () => { counter.reset(); updateCounter(); });

  function render() {
    if (!source) return;
    switch (mode) {
      case "detect": return renderDetect();
      case "blur": return renderBlur();
      case "motion": return renderMotion();
      case "qr": return renderQr();
      case "palette": return renderPalette();
      case "colour": return renderColour();
      case "hist": return renderHist();
      case "edges": return renderEdges();
      case "filters": return renderFilters();
      case "cartoon": return renderCartoon();
    }
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
  const clamp = (v) => (v < 0 ? 0 : v > 255 ? 255 : v);
  function download(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  function pixelate(img, x0, y0, w, h, block) {
    const { width: W, data } = img;
    x0 = Math.max(0, Math.floor(x0)); y0 = Math.max(0, Math.floor(y0));
    const x1 = Math.min(img.width, Math.ceil(x0 + w)), y1 = Math.min(img.height, Math.ceil(y0 + h));
    for (let by = y0; by < y1; by += block) for (let bx = x0; bx < x1; bx += block) {
      const ex = Math.min(bx + block, x1), ey = Math.min(by + block, y1);
      let r = 0, g = 0, b = 0, n = 0;
      for (let y = by; y < ey; y++) for (let x = bx; x < ex; x++) { const i = (y * W + x) * 4; r += data[i]; g += data[i + 1]; b += data[i + 2]; n++; }
      r /= n; g /= n; b /= n;
      for (let y = by; y < ey; y++) for (let x = bx; x < ex; x++) { const i = (y * W + x) * 4; data[i] = r; data[i + 1] = g; data[i + 2] = b; }
    }
  }
  const copyOf = (img) => new ImageData(new Uint8ClampedArray(img.data), img.width, img.height);

  // ---------- detection (shared by Detect and Privacy blur) ----------
  function ensureModel() {
    if (model || modelLoading) return modelLoading || Promise.resolve(model);
    if (!window.cocoSsd || !window.tf) {
      for (const id of ["detectStatus", "blurStatus"]) { $(id).textContent = "The detector library did not load. Check the connection and reload the page."; $(id).classList.add("error"); }
      return Promise.resolve(null);
    }
    $("detectStatus").textContent = $("blurStatus").textContent = "Loading the model (18 MB, once per visit)…";
    modelLoading = cocoSsd.load({ base: "lite_mobilenet_v2", modelUrl: "models/coco/model.json" })
      .then((m) => { model = m; $("detectStatus").textContent = `Model ready (TensorFlow.js, ${tf.getBackend()} backend).`; $("blurStatus").textContent = ""; if (!live) render(); return m; })
      .catch((e) => { $("detectStatus").textContent = "The model could not load: " + (e && e.message || e); $("detectStatus").classList.add("error"); modelLoading = null; return null; });
    return modelLoading;
  }
  function requestDetect() {
    if (!model) { ensureModel(); return; }
    if (detBusy || (!live && detsFor === source)) return;
    detBusy = true;
    const src = source, t0 = performance.now();
    if (!live) $("detectStatus").textContent = "Detecting…";
    model.detect(src, 30, 0.1).then((r) => {
      detMs = performance.now() - t0;
      dets = r; detsFor = src;
      if (live) { counter.update(r, src.width, src.height, counterOpts()); updateCounter(); }
      else $("detectStatus").textContent = `Detected in ${Math.round(detMs)} ms on your device.`;
      detBusy = false;
      if (!live && AI_MODES.has(mode)) render();
    }).catch((e) => { detBusy = false; $("detectStatus").textContent = "Detection failed: " + (e && e.message || e); });
  }
  const detsFresh = () => live || detsFor === source;

  let lastTable = 0;
  function renderDetect() {
    ctx.putImageData(source, 0, 0);
    requestDetect();
    const fresh = detsFresh();
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
    const now = performance.now(); // in live mode, refresh the table a few times a second rather than every frame
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

  // ---------- line counter and its log ----------
  // Detections are matched to the nearest track of the same class from the previous detector pass; a track is
  // counted once, in the direction its centre crosses the line. Tracks unseen for several passes are dropped.
  const counter = {
    reset() { this.tracks = []; this.next = 1; this.a = 0; this.b = 0; this.events = []; },
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
        let dir = null;
        if (!t.counted && before < line && after >= line) { this.a++; dir = o.vertical ? "right" : "down"; }
        else if (!t.counted && before >= line && after < line) { this.b++; dir = o.vertical ? "left" : "up"; }
        if (dir) { t.counted = true; this.events.push({ time: new Date(), cls: t.cls, dir, id: t.id }); }
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
  const pad = (n) => String(n).padStart(2, "0");
  const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  let shownEvents = -1;
  function updateCounter() {
    const v = $("lineDir").value === "v";
    $("aLabel").textContent = v ? "Right →" : "Down ↓";
    $("bLabel").textContent = v ? "← Left" : "Up ↑";
    $("countA").textContent = counter.a; $("countB").textContent = counter.b;
    $("countT").textContent = counter.tracks.filter((t) => t.missed === 0).length;
    if (shownEvents === counter.events.length) return;
    shownEvents = counter.events.length;
    const log = $("countLog"); log.textContent = "";
    if (!counter.events.length) { const li = document.createElement("li"); li.className = "status"; li.textContent = "No crossings yet."; log.appendChild(li); }
    counter.events.slice(-5).reverse().forEach((e) => {
      const li = document.createElement("li");
      li.textContent = `${clock(e.time)}  ${e.cls} #${e.id}  ${e.dir}`;
      log.appendChild(li);
    });
    $("csvBtn").disabled = !counter.events.length;
  }
  $("csvBtn").addEventListener("click", () => {
    const rows = [["timestamp", "object", "direction", "track_id"]].concat(
      counter.events.map((e) => [e.time.toISOString(), e.cls, e.dir, e.id]));
    const csv = rows.map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\r\n") + "\r\n";
    download(new Blob([csv], { type: "text/csv" }), "vision-lab-count-log.csv");
  });
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

  // ---------- privacy blur ----------
  const VEHICLES = new Set(["car", "bus", "truck", "motorcycle", "bicycle", "train"]);
  function renderBlur() {
    requestDetect();
    if (!detsFresh()) { ctx.putImageData(source, 0, 0); $("blurCount").textContent = "–"; return; }
    const what = $("blurWhat").value, min = $("blurMin").value / 100;
    const hide = dets.filter((d) => d.score >= min && (what === "any" || (what === "vehicle" ? VEHICLES.has(d.class) : d.class === what)));
    const block = +$("blurBlock").value;
    if ($("blurStyle").value === "pixel") {
      const out = copyOf(source);
      // Pad each box a little: detector boxes are often tight around heads and hands.
      hide.forEach((d) => { const [x, y, w, h] = d.bbox; pixelate(out, x - w * 0.06, y - h * 0.06, w * 1.12, h * 1.12, block); });
      ctx.putImageData(out, 0, 0);
    } else {
      ctx.putImageData(source, 0, 0);
      ctx.fillStyle = "#111";
      hide.forEach((d) => { const [x, y, w, h] = d.bbox; ctx.fillRect(x - w * 0.06, y - h * 0.06, w * 1.12, h * 1.12); });
    }
    $("blurCount").textContent = hide.length;
    if (!live) $("blurStatus").textContent = hide.length ? "" : "Nothing to hide at this sensitivity. Raise it (lower the minimum confidence) if someone is missed.";
  }

  // ---------- motion ----------
  const motion = {
    reset() { this.prev = null; this.heat = null; this.mask = null; this.share = 0; this.peak = 0; this.history = []; },
    update(img) {
      const g = gray(img.data), n = g.length;
      if (!this.prev || this.prev.length !== n) { this.prev = g; this.heat = new Float32Array(n); this.mask = new Uint8Array(n); return; }
      const thr = +$("motionThr").value;
      let moving = 0;
      for (let i = 0; i < n; i++) {
        const m = Math.abs(g[i] - this.prev[i]) > thr ? 1 : 0;
        this.mask[i] = m; moving += m;
        this.heat[i] = this.heat[i] * 0.995 + m;
      }
      this.prev = g;
      this.share = moving / n;
      this.peak = Math.max(this.peak, this.share);
      this.history.push(this.share); if (this.history.length > 150) this.history.shift();
    },
  };
  motion.reset();
  $("motionReset").addEventListener("click", () => { motion.reset(); if (!live) render(); });
  function heatColour(t) { // 0..1 -> dark blue, teal, yellow, red
    const stops = [[0, [20, 30, 80]], [0.35, [20, 160, 150]], [0.7, [240, 210, 60]], [1, [230, 60, 40]]];
    for (let s = 1; s < stops.length; s++) if (t <= stops[s][0]) {
      const [t0, c0] = stops[s - 1], [t1, c1] = stops[s], f = (t - t0) / (t1 - t0);
      return c0.map((v, k) => v + (c1[k] - v) * f);
    }
    return stops[stops.length - 1][1];
  }
  function renderMotion() {
    const { width: w, height: h, data } = source;
    if (!live || !motion.mask || motion.mask.length !== w * h) {
      ctx.putImageData(source, 0, 0);
      $("motionNow").textContent = "–"; $("motionPeak").textContent = "–";
      return;
    }
    const out = ctx.createImageData(w, h);
    const heatView = $("motionView").value === "heat";
    let hmax = 1;
    if (heatView) for (let i = 0; i < w * h; i++) if (motion.heat[i] > hmax) hmax = motion.heat[i];
    for (let i = 0, p = 0; i < w * h; i++, p += 4) {
      const y = 0.299 * data[p] + 0.587 * data[p + 1] + 0.114 * data[p + 2];
      if (heatView) {
        const t = Math.sqrt(motion.heat[i] / hmax);
        const [r, g, b] = heatColour(t);
        out.data[p] = y * 0.35 + r * 0.65; out.data[p + 1] = y * 0.35 + g * 0.65; out.data[p + 2] = y * 0.35 + b * 0.65;
      } else if (motion.mask[i]) {
        out.data[p] = 255; out.data[p + 1] = 90; out.data[p + 2] = 50;
      } else {
        out.data[p] = out.data[p + 1] = out.data[p + 2] = y * 0.6;
      }
      out.data[p + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    $("motionNow").textContent = (100 * motion.share).toFixed(1) + "%";
    $("motionPeak").textContent = (100 * motion.peak).toFixed(1) + "%";
    const c = $("motionSpark"), sx = c.getContext("2d"), dpr = window.devicePixelRatio || 1;
    const cw = Math.round(c.clientWidth * dpr), ch = Math.round(c.clientHeight * dpr);
    if (c.width !== cw || c.height !== ch) { c.width = cw; c.height = ch; }
    sx.clearRect(0, 0, cw, ch);
    const top = Math.max(0.02, ...motion.history);
    sx.strokeStyle = css("--accent"); sx.lineWidth = 2 * dpr; sx.beginPath();
    motion.history.forEach((v, i) => { const x = i / 149 * cw, y = ch - 2 * dpr - v / top * (ch - 4 * dpr); i ? sx.lineTo(x, y) : sx.moveTo(x, y); });
    sx.stroke();
  }

  // ---------- QR codes ----------
  let qrFor = null, qrLast = 0, qrHit = null;
  const qrSeen = [];
  function renderQr() {
    ctx.putImageData(source, 0, 0);
    if (!window.jsQR) { $("qrStatus").textContent = "The QR library did not load. Check the connection and reload the page."; $("qrStatus").classList.add("error"); return; }
    const now = performance.now();
    if (live ? now - qrLast > 200 : qrFor !== source) {
      qrLast = now; qrFor = source;
      const code = jsQR(source.data, source.width, source.height, { inversionAttempts: live ? "dontInvert" : "attemptBoth" });
      if (code && code.data) {
        qrHit = { code, at: now };
        showQr(code.data);
      } else if (!live) {
        qrHit = null;
        $("qrStatus").textContent = "No QR code found in this picture. Fill more of the frame with the code and keep it sharp.";
      }
    }
    if (qrHit && (!live || now - qrHit.at < 600)) {
      const L = qrHit.code.location, lw = Math.max(3, view.width / 200);
      ctx.strokeStyle = css("--accent"); ctx.lineWidth = lw; ctx.beginPath();
      [L.topLeftCorner, L.topRightCorner, L.bottomRightCorner, L.bottomLeftCorner].forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath(); ctx.stroke();
    }
  }
  function showQr(text) {
    $("qrResult").textContent = text;
    $("qrStatus").textContent = "";
    let url = null;
    try { const u = new URL(text); if (u.protocol === "https:" || u.protocol === "http:") url = u; } catch (e) { /* not a link */ }
    $("qrLink").hidden = !url;
    if (url) { $("qrLink").href = url.href; $("qrLink").textContent = `Open ${url.hostname}`; }
    if (qrSeen[0] === text) return;
    const at = qrSeen.indexOf(text); if (at >= 0) qrSeen.splice(at, 1);
    qrSeen.unshift(text); qrSeen.length = Math.min(qrSeen.length, 5);
    const list = $("qrHistory"); list.textContent = "";
    qrSeen.forEach((t) => { const li = document.createElement("li"); li.textContent = t; list.appendChild(li); });
  }

  // ---------- colour palette (k-means) ----------
  let paletteFor = null, paletteK = 0, paletteLast = 0, palette = [];
  function kmeans(img, k) {
    const { data } = img, n = data.length / 4;
    const step = Math.max(1, Math.floor(n / 6000));
    const pts = [];
    for (let i = 0; i < n; i += step) pts.push([data[i * 4], data[i * 4 + 1], data[i * 4 + 2]]);
    let seed = 12345; const rand = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
    // k-means++ start: spread the first centres out.
    const cent = [pts[Math.floor(rand() * pts.length)].slice()];
    const d2 = new Float64Array(pts.length);
    while (cent.length < k) {
      let sum = 0;
      pts.forEach((p, i) => { let best = Infinity; for (const c of cent) best = Math.min(best, (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2); d2[i] = best; sum += best; });
      if (!sum) break;
      let r = rand() * sum, i = 0; while (r > d2[i] && i < pts.length - 1) { r -= d2[i]; i++; }
      cent.push(pts[i].slice());
    }
    const lab = new Int32Array(pts.length);
    for (let it = 0; it < 12; it++) {
      const acc = cent.map(() => [0, 0, 0, 0]);
      pts.forEach((p, i) => {
        let best = 0, bd = Infinity;
        cent.forEach((c, j) => { const d = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2; if (d < bd) { bd = d; best = j; } });
        lab[i] = best; const a = acc[best]; a[0] += p[0]; a[1] += p[1]; a[2] += p[2]; a[3]++;
      });
      acc.forEach((a, j) => { if (a[3]) cent[j] = [a[0] / a[3], a[1] / a[3], a[2] / a[3]]; });
    }
    const counts = cent.map(() => 0); lab.forEach((j) => counts[j]++);
    return cent.map((c, j) => ({ rgb: c.map((v) => Math.round(v)), share: counts[j] / pts.length }))
      .filter((c) => c.share > 0).sort((a, b) => b.share - a.share);
  }
  function renderPalette() {
    const k = +$("kColours").value, now = performance.now();
    const stale = live ? now - paletteLast > 700 : paletteFor !== source || paletteK !== k;
    if (stale) {
      palette = kmeans(source, k); paletteFor = source; paletteK = k; paletteLast = now;
      const list = $("paletteList"); list.textContent = "";
      palette.forEach((c) => {
        const li = document.createElement("li"), b = document.createElement("button"), chip = document.createElement("span");
        const code = hex(c.rgb);
        b.type = "button"; chip.className = "chip"; chip.style.background = code;
        const name = document.createElement("span"); name.textContent = code;
        const share = document.createElement("span"); share.textContent = (100 * c.share).toFixed(1) + "%";
        b.append(chip, name, share);
        b.addEventListener("click", async () => {
          try { await navigator.clipboard.writeText(code); $("paletteStatus").textContent = `Copied ${code}.`; }
          catch (e) { $("paletteStatus").textContent = `${code} (copying is blocked here; select it by hand).`; }
        });
        li.appendChild(b); list.appendChild(li);
      });
    }
    ctx.putImageData(source, 0, 0);
    const barH = Math.round(view.height * 0.1);
    let x = 0;
    palette.forEach((c, i) => {
      const w = i === palette.length - 1 ? view.width - x : Math.round(c.share * view.width);
      ctx.fillStyle = hex(c.rgb); ctx.fillRect(x, view.height - barH, w, barH); x += w;
    });
  }

  // ---------- colour measure ----------
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

  // ---------- filters ----------
  function convolve3(img, k, bias = 0) {
    const { width: w, height: h, data } = img, out = new ImageData(w, h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const o = (y * w + x) * 4;
      for (let c = 0; c < 3; c++) {
        let s = 0;
        for (let ky = -1; ky <= 1; ky++) for (let kx = -1; kx <= 1; kx++) {
          const xx = Math.min(w - 1, Math.max(0, x + kx)), yy = Math.min(h - 1, Math.max(0, y + ky));
          s += data[(yy * w + xx) * 4 + c] * k[(ky + 1) * 3 + kx + 1];
        }
        out.data[o + c] = clamp(s + bias);
      }
      out.data[o + 3] = 255;
    }
    return out;
  }
  function boxBlur(img, r) { // separable running-sum blur, radius r
    const { width: w, height: h } = img;
    const tmp = new Float32Array(w * h * 3), out = new ImageData(w, h);
    for (let y = 0; y < h; y++) for (let c = 0; c < 3; c++) {
      let s = 0;
      for (let x = -r; x <= r; x++) s += img.data[(y * w + Math.min(w - 1, Math.max(0, x))) * 4 + c];
      for (let x = 0; x < w; x++) {
        tmp[(y * w + x) * 3 + c] = s / (2 * r + 1);
        s += img.data[(y * w + Math.min(w - 1, x + r + 1)) * 4 + c] - img.data[(y * w + Math.max(0, x - r)) * 4 + c];
      }
    }
    for (let x = 0; x < w; x++) for (let c = 0; c < 3; c++) {
      let s = 0;
      for (let y = -r; y <= r; y++) s += tmp[(Math.min(h - 1, Math.max(0, y)) * w + x) * 3 + c];
      for (let y = 0; y < h; y++) {
        out.data[(y * w + x) * 4 + c] = s / (2 * r + 1);
        s += tmp[(Math.min(h - 1, y + r + 1) * w + x) * 3 + c] - tmp[(Math.max(0, y - r) * w + x) * 3 + c];
      }
    }
    for (let i = 3; i < out.data.length; i += 4) out.data[i] = 255;
    return out;
  }
  function otsu(g) {
    const hist = new Float64Array(256); g.forEach((v) => hist[Math.min(255, Math.round(v))]++);
    const n = g.length; let sumAll = 0; for (let t = 0; t < 256; t++) sumAll += t * hist[t];
    let wB = 0, sumB = 0, best = 0, thr = 127;
    for (let t = 0; t < 256; t++) {
      wB += hist[t]; if (!wB) continue;
      const wF = n - wB; if (!wF) break;
      sumB += t * hist[t];
      const mB = sumB / wB, mF = (sumAll - sumB) / wF, between = wB * wF * (mB - mF) ** 2;
      if (between > best) { best = between; thr = t; }
    }
    return thr;
  }
  function renderFilters() {
    const kind = $("filterKind").value, amt = +$("filterAmt").value;
    $("filterAmtRow").hidden = !["sharpen", "blur", "pixelate"].includes(kind);
    const { width: w, height: h, data } = source;
    let out, note = "";
    if (kind === "sharpen") { const a = amt / 5; out = convolve3(source, [0, -a, 0, -a, 1 + 4 * a, -a, 0, -a, 0]); }
    else if (kind === "emboss") out = convolve3(source, [-2, -1, 0, -1, 1, 1, 0, 1, 2]);
    else if (kind === "blur") out = boxBlur(source, amt);
    else if (kind === "pixelate") { out = copyOf(source); pixelate(out, 0, 0, w, h, Math.max(2, Math.round(amt * Math.max(w, h) / 160))); }
    else {
      out = ctx.createImageData(w, h);
      const g = gray(data);
      const t = kind === "threshold" ? otsu(g) : 0;
      if (kind === "threshold") note = `Otsu's method chose a cut-off of ${t} (0 to 255); ${(100 * g.filter((v) => v > t).length / g.length).toFixed(0)}% of pixels are white.`;
      for (let i = 0, j = 0; i < data.length; i += 4, j++) {
        const r = data[i], gg = data[i + 1], b = data[i + 2];
        if (kind === "gray") out.data[i] = out.data[i + 1] = out.data[i + 2] = g[j];
        else if (kind === "sepia") { out.data[i] = clamp(0.393 * r + 0.769 * gg + 0.189 * b); out.data[i + 1] = clamp(0.349 * r + 0.686 * gg + 0.168 * b); out.data[i + 2] = clamp(0.272 * r + 0.534 * gg + 0.131 * b); }
        else if (kind === "invert") { out.data[i] = 255 - r; out.data[i + 1] = 255 - gg; out.data[i + 2] = 255 - b; }
        else out.data[i] = out.data[i + 1] = out.data[i + 2] = g[j] > t ? 255 : 0;
        out.data[i + 3] = 255;
      }
    }
    ctx.putImageData(out, 0, 0);
    $("filterNote").textContent = note;
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

  // ---------- save ----------
  $("saveBtn").addEventListener("click", () => {
    view.toBlob((blob) => { if (blob) download(blob, `vision-lab-${mode}.png`); }, "image/png");
  });

  // Open a tool from the address, e.g. ...#qr, so a tool can be shared as a link.
  const fromHash = location.hash.slice(1);
  if (document.querySelector(`.tool[data-mode="${CSS.escape(fromHash)}"]`)) selectMode(fromHash);
  document.querySelectorAll(".tool").forEach((t) => t.addEventListener("click", () => history.replaceState(null, "", "#" + t.dataset.mode)));

  // Expose a small read-only hook for automated checks.
  window.visionLab = { counter, motion, get live() { return !!live; }, get detections() { return dets; }, get palette() { return palette; } };

  // ---------- start with a sample ----------
  loadImage("samples/astronaut.jpg").then((img) => useImage(img, "Astronaut")).catch(() => { $("hud").textContent = "Start the camera or upload a photo"; });
})();
