"use strict";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 0) => `${(100 * x).toFixed(d)}%`;

let META = null;
let ROWS = [];
let EVAL = null;
const state = { capacity: 6, order: "model", reveal: false, selected: null, locale: "US", done: {} };

/* ---------- helpers ---------- */

function ageBand(y) { return `${y - 5}-${y + 4}`; }

function summary(f) {
  return `${ageBand(f.age_years)} ${f.gender} · ${f.time_in_hospital} days · ${f.diag_1_group} · to ${f.discharge_to}`;
}

function ordered() {
  const rows = ROWS.slice();
  if (state.order === "lace") rows.sort((a, b) => b.lace.lace - a.lace.lace || a.id.localeCompare(b.id));
  else rows.sort((a, b) => b.score - a.score);
  return rows;
}

/* Expected readmissions reached by calling the top k (ties at the cut-off split evenly), as in the evaluation. */
function expectedHits(rows, key, k) {
  if (k === 0) return 0;
  const s = rows.map(key);
  const sorted = s.slice().sort((a, b) => b - a);
  const t = sorted[k - 1];
  let above = 0, nAbove = 0, tiedY = 0, nTied = 0;
  rows.forEach((r, i) => {
    if (s[i] > t) { above += r.readmitted_30d; nAbove++; }
    else if (s[i] === t) { tiedY += r.readmitted_30d; nTied++; }
  });
  return above + (k - nAbove) * (tiedY / nTied);
}

/* ---------- detail panel (shared by list and form) ---------- */

function factorsHTML(factors) {
  if (!factors.length) return `<p class="muted small">All inputs are at their typical values.</p>`;
  const max = Math.max(8, ...factors.map((f) => Math.abs(f.points)));
  return `<div class="factors">${factors.map((f) => {
    const dir = f.points >= 0 ? "up" : "down";
    const w = (50 * Math.abs(f.points)) / max;
    return `<div class="factor">
      <div class="lab">${esc(f.label)}: <b>${esc(f.value)}</b> <small>(typical ${esc(f.typical)})</small></div>
      <div class="fbar" aria-hidden="true"><span class="${dir}" style="width:${w}%"></span></div>
      <div class="pts ${dir}">${f.points > 0 ? "+" : ""}${f.points.toFixed(1)}</div>
    </div>`;
  }).join("")}</div>
  <p class="muted small">Points = change in this patient's model score if that input were typical. A what-if, not a cause.</p>`;
}

function checklistHTML(items, key, inCall) {
  const shown = items.filter((it) => inCall || (it.id !== "call" && it.id !== "handoff"));
  if (!shown.length) return `<p class="muted small">No extra actions triggered. Standard discharge teaching applies.</p>`;
  return `<ul class="checklist">${shown.map((it) => {
    const id = `${key}:${it.id}`;
    const done = !!state.done[id];
    const src = META.sources[it.source];
    return `<li class="${done ? "done" : ""}">
      <input type="checkbox" data-done="${esc(id)}" ${done ? "checked" : ""} aria-label="Mark done">
      <div><div class="t">${esc(it.title)}</div>
      <div class="why">Because: ${esc(it.why)}</div>
      <div class="src"><a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.name)}</a></div></div>
    </li>`;
  }).join("")}</ul>`;
}

function resourcesHTML() {
  const list = META.resources[state.locale];
  return `<div class="resources">
    <div class="seg" role="group" aria-label="Region">
      ${["US", "KR"].map((l) => `<button type="button" data-locale="${l}" aria-pressed="${state.locale === l}">${l === "US" ? "United States" : "Korea"}</button>`).join("")}
    </div>
    ${list.map((r) => `<div><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a> <span class="muted">· ${esc(r.detail)}</span></div>`).join("")}
    <div class="muted small">Starting points only. Check eligibility and current contacts locally.</div>
  </div>`;
}

function detailHTML(a, opts) {
  const f = a.features;
  const inCall = opts.inCall;
  let compare = "";
  if (a.lace) {
    const obs = a.lace.observed_risk;
    compare = `LACE score ${a.lace.lace} (L${a.lace.L} A${a.lace.A} C${a.lace.C} E${a.lace.E})` +
      (obs != null ? `: ${pct(obs)} of past patients with this LACE score were readmitted.` : ".");
  } else if (a.lace_partial) {
    const p = a.lace_partial;
    compare = `LACE needs diagnosis codes for the comorbidity part; without it: L${p.L} + A${p.A} + E${p.E} = ${p.L + p.A + p.E}.`;
  }
  const outcome = opts.row && state.reveal
    ? `<div class="outcome">What happened: ${opts.row.readmitted_30d ? '<span class="tag yes">readmitted within 30 days</span>' : '<span class="tag no">not readmitted within 30 days</span>'}</div>`
    : "";
  return `
    <h2>${opts.title}</h2>
    <div class="chips">
      <span class="chip">Age ${ageBand(f.age_years)}</span><span class="chip">${esc(f.gender)}</span>
      <span class="chip">${f.time_in_hospital} days in hospital</span><span class="chip">Main diagnosis: ${esc(f.diag_1_group)}</span>
      <span class="chip">Discharged to ${esc(f.discharge_to)}</span><span class="chip">${f.number_inpatient} admissions past year</span>
    </div>
    <div class="riskbox ${inCall ? "call" : ""}">
      <div class="big">${Math.round(100 * a.risk)}<small>%</small></div>
      <div><b>estimated chance of readmission within 30 days</b></div>
      <div>${opts.rankText} ${inCall ? '<span class="tag call">CALL</span>' : ""}</div>
    </div>
    <div class="compare">${esc(compare)}</div>
    ${outcome}
    <h3>Why this rank</h3>
    ${factorsHTML(a.factors)}
    <h3>Care connection checklist</h3>
    ${checklistHTML(a.checklist, opts.key, inCall)}
    <h3>Community resources</h3>
    ${resourcesHTML()}
    <div class="safety"><b>Safety.</b> ${esc(META.safety_note)}</div>`;
}

function bindDetail(el, rerender) {
  el.querySelectorAll("[data-done]").forEach((cb) => cb.addEventListener("change", () => {
    state.done[cb.dataset.done] = cb.checked;
    cb.closest("li").classList.toggle("done", cb.checked);
  }));
  el.querySelectorAll("[data-locale]").forEach((b) => b.addEventListener("click", () => {
    state.locale = b.dataset.locale;
    rerender();
  }));
}

/* ---------- today's list ---------- */

function renderList() {
  const rows = ordered();
  const k = state.capacity;
  const ol = $("#list");
  ol.innerHTML = "";
  rows.forEach((r, i) => {
    if (i === k && k > 0 && k < rows.length) {
      const d = document.createElement("li");
      d.className = "divider";
      d.textContent = `▲ ${k} calls today · below this line: standard discharge`;
      ol.appendChild(d);
    }
    const li = document.createElement("li");
    li.className = `row ${i < k ? "call" : ""} ${state.selected === r.id ? "selected" : ""}`;
    li.tabIndex = 0;
    const outcome = state.reveal ? (r.readmitted_30d ? ' <span class="tag yes">readmitted</span>' : "") : "";
    const right = state.order === "lace"
      ? `<div class="pct">LACE ${r.lace.lace}</div><div class="muted small">${Math.round(100 * r.risk)}% model</div>`
      : `<div class="pct">${Math.round(100 * r.risk)}%</div><div class="bar"><span style="width:${Math.min(100, 250 * r.risk)}%"></span></div>`;
    li.innerHTML = `<div class="rank">${i + 1}</div>
      <div class="who"><b>${r.id}</b> ${i < k ? '<span class="tag call">CALL</span>' : ""}${outcome}
        <div class="sub">${esc(summary(r.features))}</div></div>
      <div class="riskcell">${right}</div>`;
    li.addEventListener("click", () => { state.selected = r.id; renderList(); });
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") { state.selected = r.id; renderList(); } });
    ol.appendChild(li);
  });

  const sel = rows.find((r) => r.id === state.selected) || rows[0];
  state.selected = sel.id;
  ol.querySelectorAll(".row")[rows.indexOf(sel)]?.classList.add("selected");
  const pos = rows.indexOf(sel);
  const detail = $("#detail");
  const rankText = `#${pos + 1} of ${rows.length} today · ranks above ${Math.round(sel.percentile)}% of discharges`;
  detail.innerHTML = detailHTML(sel, { title: `Patient ${sel.id}`, inCall: pos < k, rankText, row: sel, key: sel.id });
  bindDetail(detail, renderList);

  const box = $("#reveal-summary");
  box.hidden = !state.reveal;
  if (state.reveal) {
    const total = ROWS.reduce((s, r) => s + r.readmitted_30d, 0);
    const model = expectedHits(ROWS, (r) => r.score, k);
    const lace = expectedHits(ROWS, (r) => r.lace.lace, k);
    const rnd = (k * total) / ROWS.length;
    const f = (x) => (Number.isInteger(x) ? x : x.toFixed(1));
    box.innerHTML = `<b>${total} of these ${ROWS.length} patients were readmitted within 30 days.</b>
      With ${k} calls: CallFirst order reaches <b>${f(model)}</b>, LACE order ${f(lace)}, random order ${f(rnd)} on average.
      <span class="muted">24 patients is an anecdote; the Evaluation tab has 19,851.</span>`;
  }
}

/* ---------- try a patient ---------- */

const FORM = [
  { k: "age_years", type: "age" },
  { k: "gender", type: "select" },
  { k: "time_in_hospital", type: "range", min: 1, max: 14, unit: " days" },
  { k: "admission_type", type: "select" },
  { k: "admission_source", type: "select" },
  { k: "discharge_to", type: "select" },
  { k: "number_inpatient", type: "number", min: 0, max: 20 },
  { k: "number_emergency", type: "number", min: 0, max: 20 },
  { k: "number_outpatient", type: "number", min: 0, max: 20 },
  { k: "num_medications", type: "range", min: 1, max: 60 },
  { k: "number_diagnoses", type: "range", min: 1, max: 16 },
  { k: "diag_1_group", type: "select" },
  { k: "a1c", type: "select" },
  { k: "insulin", type: "select" },
];

const PRESETS = {
  typical: {},
  repeat: { age_years: 75, number_inpatient: 3, number_emergency: 1, time_in_hospital: 5, num_medications: 22,
    diag_1_group: "circulatory", discharge_to: "home" },
  insulin: { age_years: 55, insulin: "up", a1c: ">8", diag_1_group: "diabetes", admission_type: "emergency",
    admission_source: "emergency room" },
};

let formValues = {};
let tryTimer = null;

function buildForm() {
  const box = $("#form-fields");
  box.innerHTML = FORM.map((fd) => {
    const label = esc(META.labels[fd.k]);
    if (fd.type === "select" || fd.type === "age") {
      const opts = fd.type === "age" ? [15, 25, 35, 45, 55, 65, 75, 85, 95] : META.options[fd.k];
      return `<label>${label}<select name="${fd.k}">${opts.map((o) =>
        `<option value="${esc(o)}">${esc(fd.type === "age" ? ageBand(o) : o)}</option>`).join("")}</select></label>`;
    }
    if (fd.type === "range") {
      return `<label>${label} <span class="val" data-val="${fd.k}"></span>
        <input type="range" name="${fd.k}" min="${fd.min}" max="${fd.max}" step="1"></label>`;
    }
    return `<label>${label}<input type="number" name="${fd.k}" min="${fd.min}" max="${fd.max}" step="1"></label>`;
  }).join("");
  box.addEventListener("input", () => { readForm(); scheduleScore(); });
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
  applyPreset("typical");
}

function applyPreset(name) {
  formValues = {};
  FORM.forEach((fd) => { formValues[fd.k] = META.reference[fd.k]; });
  Object.assign(formValues, PRESETS[name]);
  FORM.forEach((fd) => {
    const el = document.querySelector(`#form-fields [name="${fd.k}"]`);
    el.value = String(formValues[fd.k]);
  });
  readForm();
  scheduleScore(0);
}

function readForm() {
  FORM.forEach((fd) => {
    const el = document.querySelector(`#form-fields [name="${fd.k}"]`);
    let v = el.value;
    if (fd.type !== "select") v = Number(v);
    formValues[fd.k] = v;
    const out = document.querySelector(`[data-val="${fd.k}"]`);
    if (out) out.textContent = `${v}${fd.unit || ""}`;
  });
}

function requestFeatures() {
  const f = { ...formValues };
  const changed = f.insulin === "up" || f.insulin === "down";
  f.n_dose_changes = changed ? 1 : 0;
  f.med_change = changed ? "yes" : "no";
  if (f.insulin !== "no") { f.diabetes_med = "yes"; f.n_diabetes_meds = Math.max(1, META.reference.n_diabetes_meds); }
  return f;
}

function scheduleScore(delay = 150) {
  clearTimeout(tryTimer);
  tryTimer = setTimeout(scoreForm, delay);
}

async function scoreForm() {
  const res = await fetch("/api/score", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ features: requestFeatures() }) });
  const el = $("#try-detail");
  if (!res.ok) { el.innerHTML = `<p>Could not score: ${esc((await res.json()).detail)}</p>`; return; }
  const a = await res.json();
  const rankText = `Ranks above ${Math.round(a.percentile)}% of discharges · ${a.in_top_10_percent ? "in" : "not in"} a top-10% call list`;
  const render = () => {
    el.innerHTML = detailHTML(a, { title: "Your made-up patient", inCall: a.in_top_10_percent, rankText, key: "try" });
    bindDetail(el, render);
  };
  render();
}

/* ---------- evaluation ---------- */

const NAMES = { random: "Random order", prior_admissions: "Prior admissions only*", lace: "LACE score", logistic: "CallFirst",
  boosting: "Boosting (not deployed)" };
const COLORS = { random: "#A9B4B1", prior_admissions: "#7C8A87", lace: "#4C7DB8", logistic: "#E8603F", boosting: "#F0A48F" };

function barChart(ev) {
  const cap = String(ev.config.primary_capacity);
  const order = ["random", "lace", "prior_admissions", "logistic", "boosting"];
  const W = 560, rowH = 34, left = 200, top = 10, H = top + order.length * rowH + 30;
  const max = 32;
  const x = (v) => left + ((W - left - 50) * v) / max;
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Readmissions reached per 100 calls at 10% capacity">`;
  [0, 10, 20, 30].forEach((t) => {
    s += `<line x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${H - 24}" stroke="#E1E5E3"/><text x="${x(t)}" y="${H - 8}" text-anchor="middle">${t}</text>`;
  });
  order.forEach((n, i) => {
    const c = ev.test[n].capacity[cap];
    const y = top + i * rowH;
    s += `<text class="lbl" x="${left - 10}" y="${y + 20}" text-anchor="end">${NAMES[n]}</text>`;
    s += `<rect x="${x(0)}" y="${y + 7}" width="${x(c.per_100_calls) - x(0)}" height="18" rx="4" fill="${COLORS[n]}"/>`;
    if (n !== "random") {
      const [lo, hi] = c.per_100_calls_ci;
      s += `<line x1="${x(lo)}" x2="${x(hi)}" y1="${y + 16}" y2="${y + 16}" stroke="#17201F" stroke-width="1.5"/>`;
      s += `<line x1="${x(lo)}" x2="${x(lo)}" y1="${y + 11}" y2="${y + 21}" stroke="#17201F" stroke-width="1.5"/>`;
      s += `<line x1="${x(hi)}" x2="${x(hi)}" y1="${y + 11}" y2="${y + 21}" stroke="#17201F" stroke-width="1.5"/>`;
    }
    s += `<text class="val" x="${x(Math.max(c.per_100_calls, n === "random" ? 0 : c.per_100_calls_ci[1])) + 6}" y="${y + 20}">${c.per_100_calls.toFixed(1)}</text>`;
  });
  return s + "</svg>";
}

function capacityChart(ev) {
  const caps = ev.config.capacities;
  const names = ["random", "lace", "prior_admissions", "logistic"];
  const W = 560, H = 250, l = 44, r = 150, t = 12, b = 34;
  const x = (c) => l + ((W - l - r) * (c - caps[0])) / (caps[caps.length - 1] - caps[0]);
  const y = (v) => t + (H - t - b) * (1 - v / 35);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Readmissions per 100 calls by call capacity">`;
  [0, 10, 20, 30].forEach((v) => { s += `<line x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}" stroke="#E1E5E3"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`; });
  caps.forEach((c) => { s += `<text x="${x(c)}" y="${H - 12}" text-anchor="middle">top ${Math.round(100 * c)}%</text>`; });
  const labels = [];
  names.forEach((n) => {
    const pts = caps.map((c) => [x(c), y(ev.test[n].capacity[String(c)].per_100_calls)]);
    s += `<polyline points="${pts.map((p) => p.join(",")).join(" ")}" fill="none" stroke="${COLORS[n]}" stroke-width="${n === "logistic" ? 3.5 : 2}"/>`;
    pts.forEach((p) => { s += `<circle cx="${p[0]}" cy="${p[1]}" r="3.5" fill="${COLORS[n]}"/>`; });
    const last = pts[pts.length - 1];
    labels.push({ n, x: last[0] + 8, y: last[1] + 4 });
  });
  labels.sort((a, b) => a.y - b.y);   // keep end labels at least 14px apart
  for (let i = 1; i < labels.length; i++) labels[i].y = Math.max(labels[i].y, labels[i - 1].y + 14);
  labels.forEach((lb) => { s += `<text class="lbl" x="${lb.x}" y="${lb.y}" fill="${COLORS[lb.n]}">${NAMES[lb.n]}</text>`; });
  return s + "</svg>";
}

function calibrationChart(ev) {
  const bins = ev.calibration.bins;
  const W = 380, H = 300, l = 44, r = 14, t = 12, b = 40, m = 0.3;
  const x = (v) => l + ((W - l - r) * v) / m;
  const y = (v) => t + (H - t - b) * (1 - v / m);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Calibration plot">`;
  [0, 0.1, 0.2, 0.3].forEach((v) => {
    s += `<line x1="${l}" x2="${W - r}" y1="${y(v)}" y2="${y(v)}" stroke="#E1E5E3"/><text x="${l - 6}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`;
    s += `<text x="${x(v)}" y="${H - 22}" text-anchor="middle">${v * 100}%</text>`;
  });
  s += `<line x1="${x(0)}" y1="${y(0)}" x2="${x(m)}" y2="${y(m)}" stroke="#A9B4B1" stroke-dasharray="4 4"/>`;
  s += `<polyline points="${bins.map((bb) => `${x(bb.mean_predicted)},${y(bb.observed)}`).join(" ")}" fill="none" stroke="#E8603F" stroke-width="2.5"/>`;
  bins.forEach((bb) => { s += `<circle cx="${x(bb.mean_predicted)}" cy="${y(bb.observed)}" r="4" fill="#E8603F"/>`; });
  s += `<text x="${(l + W - r) / 2}" y="${H - 4}" text-anchor="middle">predicted risk (deciles)</text>`;
  s += `<text x="12" y="${(t + H - b) / 2}" transform="rotate(-90 12 ${(t + H - b) / 2})" text-anchor="middle">observed</text>`;
  return s + "</svg>";
}

function renderEval() {
  const ev = EVAL;
  const cap = String(ev.config.primary_capacity);
  const T = ev.test;
  const c = (n) => T[n].capacity[cap];
  const pl = ev.paired.lace.logistic;
  const pp = ev.paired.prior_admissions.logistic;
  const ci = (a, d = 1) => `${a[0].toFixed(d)}–${a[1].toFixed(d)}`;
  const te = ev.data.splits.test;
  const overall = T.logistic.auroc;
  const old = ev.subgroups.find((s) => s.attribute === "age" && s.group === "80+");
  const sub = ev.subgroups.map((s) => {
    const cls = !s.interpret ? "thin" : s.auroc_model < overall - 0.05 ? "weak" : "";
    return `<tr class="${cls}"><td>${esc(s.attribute)}</td><td>${esc(s.group)}${s.interpret ? "" : " †"}</td><td>${s.n.toLocaleString()}</td>
      <td>${pct(s.readmission_rate, 1)}</td><td>${s.auroc_model.toFixed(3)}</td><td>${s.auroc_lace.toFixed(3)}</td>
      <td>${pct(s.share_called, 1)}</td><td>${s.share_of_readmissions_reached == null ? "—" : pct(s.share_of_readmissions_reached, 1)}</td></tr>`;
  }).join("");
  $("#eval").innerHTML = `
    <p class="muted">Held-out test split: <b>${te.encounters.toLocaleString()}</b> discharges of <b>${te.patients.toLocaleString()}</b> patients never seen in training
      (${pct(te.readmission_rate, 1)} readmitted within 30 days). 95% intervals from ${ev.config.bootstrap_resamples.toLocaleString()} bootstrap resamples of patients.
      Question: if a coordinator can phone only the top ${pct(ev.config.primary_capacity)} of discharges, how many of those calls reach someone who will be readmitted?</p>
    <div class="eval-grid">
      <div class="card stat hero"><div class="num">${c("logistic").per_100_calls.toFixed(1)} <small>per 100 calls</small></div>
        <div class="cap">readmissions reached by CallFirst (95% CI ${ci(c("logistic").per_100_calls_ci)})</div></div>
      <div class="card stat"><div class="num">${c("lace").per_100_calls.toFixed(1)} <small>per 100 calls</small></div>
        <div class="cap">LACE score. CallFirst adds <b>+${pl.per_100_calls_diff.toFixed(1)}</b> (paired 95% CI ${ci(pl.per_100_calls_diff_ci)})</div></div>
      <div class="card stat"><div class="num">${c("prior_admissions").per_100_calls.toFixed(1)} <small>per 100 calls</small></div>
        <div class="cap">"Call whoever was admitted most last year". CallFirst adds only <b>+${pp.per_100_calls_diff.toFixed(1)}</b> (${ci(pp.per_100_calls_diff_ci)})</div></div>
      <div class="card stat"><div class="num">${c("random").per_100_calls.toFixed(1)} <small>per 100 calls</small></div>
        <div class="cap">random order (= the readmission rate)</div></div>
      <div class="card stat"><div class="num">${T.logistic.auroc.toFixed(3)}</div>
        <div class="cap">AUROC (95% CI ${ci(T.logistic.auroc_ci, 3)}); LACE ${T.lace.auroc.toFixed(3)}</div></div>
      <div class="card stat"><div class="num">${(ev.config.minutes_per_call * c("logistic").calls / c("logistic").readmissions_reached / 60).toFixed(1)} <small>nurse-hours</small></div>
        <div class="cap">per readmission reached, vs ${(ev.config.minutes_per_call * c("lace").calls / c("lace").readmissions_reached / 60).toFixed(1)} with LACE (assumes ${ev.config.minutes_per_call} min per call)</div></div>
    </div>
    <div class="charts">
      <div class="card chart"><h3>Readmissions reached per 100 calls, top 10%</h3><div class="muted small">Bars: point estimate. Lines: 95% CI.</div>${barChart(ev)}</div>
      <div class="card chart"><h3>Gain shrinks as you call more people</h3><div class="muted small">Readmissions per 100 calls by call capacity.</div>${capacityChart(ev)}</div>
      <div class="card chart"><h3>Calibration</h3><div class="muted small">Mean predicted ${pct(ev.calibration.mean_predicted, 1)}, observed ${pct(ev.calibration.observed, 1)}. Brier ${ev.calibration.brier.toFixed(4)} (prevalence only ${ev.calibration.brier_prevalence_only.toFixed(4)}).</div>${calibrationChart(ev)}</div>
    </div>
    <div class="card tablecard"><h3>Who could be harmed: errors by group</h3>
      <div class="muted small">One shared call list (top 10%). Shaded: AUROC more than 0.05 below overall. † fewer than 50 readmissions, not interpreted.</div>
      <table><thead><tr><th>Attribute</th><th>Group</th><th>n</th><th>Readmitted</th><th>AUROC CallFirst</th><th>AUROC LACE</th><th>Share called</th><th>Group's readmissions reached</th></tr></thead>
      <tbody>${sub}</tbody></table></div>
    <div class="card limits"><h3>Where this stops being useful</h3><ul>
      <li>Most of the gain over LACE comes from one input, prior-year admissions. A nurse using that rule alone gets ${c("prior_admissions").per_100_calls.toFixed(1)} per 100 calls; the model adds ${pp.per_100_calls_diff.toFixed(1)}.</li>
      <li>Patients aged 80+ are ranked worst (AUROC ${old.auroc_model.toFixed(3)}). They get slightly more calls (${pct(old.share_called, 1)} of them) but a smaller share of their readmissions is reached (${pct(old.share_of_readmissions_reached, 1)} vs ${pct(c("logistic").share_of_readmissions, 1)} overall).</li>
      <li>US hospitals, 1999-2008, adults with diabetes only. Not validated for other populations, for current practice, or for Korea.</li>
      <li>It ranks who is likely to be readmitted, not who a call would help. Whether calls prevent readmissions is not measured here.</li>
      <li>LACE here is approximated (3 diagnosis codes; prior-year ER visits instead of 6 months), so it is likely weaker than the published score.</li>
    </ul><p class="muted small">* Prior admissions only was added after the first test run (post-hoc). Gradient boosting was not deployed: it did not beat logistic regression by 0.01 AUROC on validation, a rule set before testing.</p></div>`;
}

/* ---------- tabs and init ---------- */

function showView(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === name)));
  document.querySelectorAll(".view").forEach((v) => { v.hidden = v.id !== `view-${name}`; });
  if (name === "eval" && !EVAL) {
    $("#eval").innerHTML = "<p class='muted'>Loading…</p>";
    fetch("/api/evaluation").then((r) => r.json()).then((j) => { EVAL = j; renderEval(); });
  }
  history.replaceState(null, "", `#${name}`);
}

async function init() {
  [META, ROWS] = await Promise.all([fetch("/api/meta").then((r) => r.json()), fetch("/api/worklist").then((r) => r.json())]);
  $("#disclaimer").innerHTML = `<strong>Not medical advice.</strong> ${esc(META.disclaimer)}`;
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  const cap = $("#capacity");
  cap.max = ROWS.length;
  cap.addEventListener("input", () => { state.capacity = Number(cap.value); $("#capacity-out").textContent = cap.value; renderList(); });
  document.querySelectorAll("[data-order]").forEach((b) => b.addEventListener("click", () => {
    state.order = b.dataset.order;
    document.querySelectorAll("[data-order]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    renderList();
  }));
  $("#reveal").addEventListener("change", (e) => { state.reveal = e.target.checked; renderList(); });
  renderList();
  buildForm();
  const start = location.hash.replace("#", "");
  if (["list", "try", "eval"].includes(start)) showView(start);
}

init().catch((e) => {
  document.querySelector("main").innerHTML = `<p>Could not load the demo: ${esc(e.message)}. Is the server running and the model trained?</p>`;
});
