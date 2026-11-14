"use strict";

const $ = id => document.getElementById(id);
const $$ = selector => [...document.querySelectorAll(selector)];
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const round = value => Math.round(value * 10) / 10;
const escapeHtml = value => String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const metricKeys = ["affinity", "selectivity", "safety", "stability", "solubility"];

const state = {
  briefReady: false,
  resultsReady: false,
  running: false,
  selected: null,
  weights: {affinity: 40, selectivity: 25, safety: 20, stability: 10, solubility: 5},
  candidates: [],
  ranked: []
};

function seeded(seed) {
  const value = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return value - Math.floor(value);
}

function makeCandidates() {
  return Array.from({length: 30}, (_, index) => {
    const n = index + 1;
    const affinity = round(55 + seeded(n * 7) * 43);
    const selectivity = round(clamp(52 + seeded(n * 11) * 45 - Math.max(0, affinity - 88) * .55, 35, 97));
    const aggregation = round(9 + seeded(n * 17) * 44);
    const immunogenicity = round(8 + seeded(n * 19) * 47);
    const safety = round(clamp(104 - (aggregation * .66 + immunogenicity * .58), 38, 96));
    const stability = round(55 + seeded(n * 23) * 43);
    const solubility = round(clamp(49 + seeded(n * 29) * 48 - Math.max(0, aggregation - 38) * .3, 35, 96));
    const structure = round(61 + seeded(n * 31) * 37);
    const interfaceConfidence = round(58 + seeded(n * 37) * 40);
    const uncertainty = round(5 + seeded(n * 41) * 28);
    const mutationCount = 2 + Math.floor(seeded(n * 43) * 8);
    return {
      id: `RF-${String(n).padStart(3, "0")}`,
      affinity, selectivity, safety, stability, solubility,
      aggregation, immunogenicity, structure, interfaceConfidence, uncertainty,
      mutationCount, score: 0, rank: 0, eligible: true, frontier: false, failReasons: []
    };
  });
}

state.candidates = makeCandidates();

function updateRangeVisual(input) {
  input.style.setProperty("--fill", `${(Number(input.value) / Number(input.max)) * 100}%`);
  input.closest("label").querySelector("output").value = `${input.value}%`;
}

function syncWeights(changedInput) {
  const rows = $$(".weight-row");
  if (changedInput) {
    const changedRow = changedInput.closest(".weight-row");
    const others = rows.filter(row => row !== changedRow);
    const remaining = 100 - Number(changedInput.value);
    const currentTotal = others.reduce((sum, row) => sum + Number(row.querySelector("input").value), 0);
    let assigned = 0;
    others.forEach((row, index) => {
      const input = row.querySelector("input");
      const value = index === others.length - 1
        ? remaining - assigned
        : Math.floor(remaining * (currentTotal ? Number(input.value) / currentTotal : 1 / others.length));
      input.value = clamp(value, 0, 70);
      assigned += Number(input.value);
    });
  }
  rows.forEach(row => {
    const input = row.querySelector("input");
    state.weights[row.dataset.key] = Number(input.value);
    updateRangeVisual(input);
  });
  const total = Object.values(state.weights).reduce((sum, value) => sum + value, 0);
  $("weight-total").textContent = total;
  if (state.resultsReady) {
    renderResults();
    showToast("Ranking updated — no computational jobs were rerun.");
  }
}

function inferBrief(target, intent) {
  const normalized = target.trim().toUpperCase();
  const known = {
    EGFR: ["Epidermal growth factor receptor", "P00533"],
    P00533: ["Epidermal growth factor receptor", "P00533"],
    HER2: ["Receptor tyrosine-protein kinase erbB-2", "P04626"],
    "PD-1": ["Programmed cell death protein 1", "Q15116"],
    PD1: ["Programmed cell death protein 1", "Q15116"],
    CXCR4: ["C-X-C chemokine receptor type 4", "P61073"]
  };
  const [name, id] = known[normalized] || ["Custom receptor target", "Identifier requires confirmation"];
  const lower = intent.toLowerCase();
  let action = "Simple binding / mechanism unresolved";
  if (lower.includes("dimer")) action = "Dimerisation inhibition";
  else if (lower.includes("mutant")) action = "Mutant-selective binding";
  else if (lower.includes("block") || lower.includes("antagon")) action = "Competitive blockade";
  else if (lower.includes("activat") || lower.includes("agon")) action = "Receptor activation";
  return {symbol: normalized.slice(0, 8) || "TARGET", name, id, action};
}

function buildBrief() {
  const target = $("target").value.trim();
  const intent = $("intent").value.trim();
  if (!target || !intent) {
    showToast("Add a target and intended effect before building the brief.");
    (!target ? $("target") : $("intent")).focus();
    return;
  }
  const brief = inferBrief(target, intent);
  $("brief-symbol").textContent = brief.symbol;
  $("brief-name").textContent = brief.name;
  $("brief-id").textContent = `${brief.id} · ${$("species").value}`;
  $("brief-action").textContent = brief.action;
  $("brief-modality").textContent = $("modality").value;
  $("brief-empty").hidden = true;
  $("brief-content").hidden = false;
  $("parsed-brief").querySelector(".confidence").classList.add("is-ready");
  $("parsed-brief").querySelector(".confidence").lastChild.textContent = " Ready";
  $("run-screen").disabled = false;
  state.briefReady = true;
  showToast("Design brief resolved. Review the evidence boundary before screening.");
}

function applyDecisionLogic() {
  state.candidates.forEach(candidate => {
    const reasons = [];
    if ($("constraint-structure").checked && candidate.structure < 68) reasons.push("Structure confidence below 68");
    if ($("constraint-aggregation").checked && candidate.aggregation > 35) reasons.push("Aggregation risk above 35");
    if ($("constraint-immunogenicity").checked && candidate.immunogenicity > 38) reasons.push("Immunogenicity risk above 38");
    candidate.failReasons = reasons;
    candidate.eligible = reasons.length === 0;
    const weighted = metricKeys.reduce((sum, key) => sum + candidate[key] * state.weights[key] / 100, 0);
    candidate.score = round(weighted - candidate.uncertainty * .28);
    candidate.frontier = false;
  });

  const eligible = state.candidates.filter(candidate => candidate.eligible);
  eligible.forEach(candidate => {
    candidate.frontier = !eligible.some(other => {
      if (other === candidate) return false;
      const equalOrBetter = metricKeys.every(key => other[key] >= candidate[key]);
      const strictlyBetter = metricKeys.some(key => other[key] > candidate[key]);
      return equalOrBetter && strictlyBetter;
    });
  });

  state.ranked = [...state.candidates].sort((a, b) => {
    if (a.eligible !== b.eligible) return a.eligible ? -1 : 1;
    return b.score - a.score || a.id.localeCompare(b.id);
  });
  state.ranked.forEach((candidate, index) => candidate.rank = index + 1);
}

function winnerCard(candidate, label, description, balanced = false) {
  return `<article class="winner-card ${balanced ? "balanced" : ""}" data-candidate="${candidate.id}" tabindex="0" role="button" aria-label="Open ${escapeHtml(candidate.id)}">
    <header><span>${escapeHtml(label)}</span><i>VIEW ↗</i></header>
    <h3>${escapeHtml(candidate.id)}</h3><strong class="winner-score">${candidate.score.toFixed(1)}</strong>
    <p>${escapeHtml(description)}</p>
    <footer><b>AFF ${candidate.affinity.toFixed(0)}</b><b>SEL ${candidate.selectivity.toFixed(0)}</b><b>SAFE ${candidate.safety.toFixed(0)}</b></footer>
  </article>`;
}

function metricCell(value) {
  return `<span class="bar-cell"><span class="microbar"><i style="width:${value}%"></i></span>${value.toFixed(0)}</span>`;
}

function renderTable() {
  const query = $("candidate-search").value.trim().toLowerCase();
  const candidates = state.ranked.filter(candidate => candidate.eligible && candidate.id.toLowerCase().includes(query)).slice(0, 10);
  $("candidate-body").innerHTML = candidates.length ? candidates.map(candidate => `<tr data-candidate="${candidate.id}">
    <td>${String(candidate.rank).padStart(2, "0")}</td>
    <td><span class="candidate-name"><i class="${candidate.frontier ? "is-frontier" : ""}"></i>${candidate.id}</span></td>
    <td class="score-cell">${candidate.score.toFixed(1)}</td>
    <td>${metricCell(candidate.affinity)}</td>
    <td>${metricCell(candidate.selectivity)}</td>
    <td>${metricCell(candidate.safety)}</td>
    <td>${metricCell(candidate.stability)}</td>
    <td><span class="uncertainty ${candidate.uncertainty > 20 ? "medium" : ""}">${candidate.uncertainty > 20 ? "Medium" : "Low"}</span></td>
    <td><button class="row-action" data-candidate="${candidate.id}" aria-label="Open ${candidate.id}">↗</button></td>
  </tr>`).join("") : `<tr><td colspan="9">No eligible candidate matches this search.</td></tr>`;
}

function renderResults() {
  applyDecisionLogic();
  const eligible = state.ranked.filter(candidate => candidate.eligible);
  if (!eligible.length) {
    $("winner-grid").innerHTML = `<div class="limitation"><b>No eligible candidates</b><p>Current hard constraints exclude the complete demo batch. Relax one gate to continue comparison.</p></div>`;
    renderTable();
    return;
  }
  const balanced = eligible[0];
  const affinity = [...eligible].sort((a, b) => b.affinity - a.affinity)[0];
  const selectivity = [...eligible].sort((a, b) => b.selectivity - a.selectivity)[0];
  const safety = [...eligible].sort((a, b) => b.safety - a.safety)[0];
  $("winner-grid").innerHTML = [
    winnerCard(balanced, "Balanced winner", "Best evidence-weighted compromise after uncertainty and hard gates.", true),
    winnerCard(affinity, "Affinity winner", "Strongest predicted target binding among eligible candidates."),
    winnerCard(selectivity, "Selectivity winner", "Largest predicted margin over the off-target panel."),
    winnerCard(safety, "Lowest risk", "Lowest combined computational liability profile in this batch.")
  ].join("");
  $("stat-eligible").textContent = eligible.length;
  $("stat-excluded").textContent = state.candidates.length - eligible.length;
  $("stat-frontier").textContent = eligible.filter(candidate => candidate.frontier).length;
  renderTable();
  drawScatter();
}

const activity = [
  ["Target resolved", "Mapped the receptor input to a structured target record and extracellular design context.", "UniProt-shaped resolver"],
  ["Candidate batch prepared", "Created 30 deterministic binder profiles with deliberate affinity–risk trade-offs.", "DemoProvider"],
  ["Complex metrics collected", "Attached structure, interface and target-binding confidence fields to each candidate.", "Boltz-shaped schema"],
  ["Liabilities screened", "Calculated sequence-level solubility, aggregation and immunogenicity proxies.", "Rapid property panel"],
  ["Evidence gates applied", "Excluded candidates that violated active hard constraints and retained explicit reasons.", "Policy engine"],
  ["Trade-offs ranked", "Normalized objectives, removed dominated options and applied the current preference weights.", "Decision engine"]
];

async function runScreen() {
  if (!state.briefReady || state.running) return;
  state.running = true;
  state.resultsReady = false;
  $("run-screen").disabled = true;
  $("runtime").textContent = "Screen running…";
  $("activity-log").innerHTML = "";
  $$(".pipe-step").forEach((step, index) => {
    step.classList.remove("is-running", "is-done");
    step.querySelector("i").textContent = String(index + 1).padStart(2, "0");
    step.querySelector("em").textContent = "Queued";
  });

  for (let index = 0; index < activity.length; index += 1) {
    const step = $(`pipeline-map`).querySelector(`[data-step="${index}"]`);
    step.classList.add("is-running");
    step.querySelector("em").textContent = "Running";
    await pause(260 + index * 25);
    step.classList.remove("is-running");
    step.classList.add("is-done");
    step.querySelector("i").textContent = "✓";
    step.querySelector("em").textContent = "Done";
    const [title, summary, tool] = activity[index];
    $("activity-log").insertAdjacentHTML("afterbegin", `<div class="log-entry"><span>${String(index + 1).padStart(2, "0")} / ACTION</span><b>${escapeHtml(title)}</b><p>${escapeHtml(summary)}</p><time>${escapeHtml(tool)} · ${(0.4 + index * .3).toFixed(1)}s simulated</time></div>`);
    document.querySelector(".activity-count").textContent = `${index + 1} / 6`;
  }

  state.resultsReady = true;
  state.running = false;
  renderResults();
  $("results").hidden = false;
  requestAnimationFrame(drawScatter);
  $("run-screen").disabled = false;
  $("run-screen").innerHTML = `<span class="run-icon">↻</span> Rerun simulated rapid screen`;
  $("runtime").textContent = "Completed · 5.7s simulated";
  $("export-json").disabled = false;
  await pause(80);
  $("results").scrollIntoView({behavior: "smooth", block: "start"});
}

function canvasSetup(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, rect.width);
  const height = Math.max(1, rect.height);
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const context = canvas.getContext("2d");
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  return {context, width, height};
}

function drawScatter() {
  if (!state.resultsReady || $("results").hidden) return;
  const canvas = $("scatter");
  const {context: ctx, width, height} = canvasSetup(canvas);
  ctx.clearRect(0, 0, width, height);
  const pad = {left: 38, right: 18, top: 20, bottom: 34};
  ctx.strokeStyle = "#deddd5";
  ctx.fillStyle = "#89918d";
  ctx.font = "8px SFMono-Regular, monospace";
  for (let tick = 0; tick <= 4; tick += 1) {
    const x = pad.left + (width - pad.left - pad.right) * tick / 4;
    const y = pad.top + (height - pad.top - pad.bottom) * tick / 4;
    ctx.beginPath(); ctx.moveTo(x, pad.top); ctx.lineTo(x, height - pad.bottom); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
  }
  ctx.fillText("AFFINITY →", width - 72, height - 12);
  ctx.save(); ctx.translate(11, 78); ctx.rotate(-Math.PI / 2); ctx.fillText("COMPUTATIONAL SAFETY →", 0, 0); ctx.restore();
  state.candidates.forEach(candidate => {
    const x = pad.left + (candidate.affinity - 40) / 60 * (width - pad.left - pad.right);
    const y = height - pad.bottom - (candidate.safety - 35) / 65 * (height - pad.top - pad.bottom);
    if (candidate.eligible) {
      ctx.fillStyle = candidate.frontier ? "#b9f227" : "rgba(11,116,106,.62)";
      ctx.beginPath(); ctx.arc(x, y, candidate.frontier ? 4.5 : 3, 0, Math.PI * 2); ctx.fill();
      if (candidate.frontier) {ctx.strokeStyle = "#14201d"; ctx.lineWidth = 1; ctx.stroke();}
    } else {
      ctx.strokeStyle = "rgba(189,88,78,.55)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x - 3, y - 3); ctx.lineTo(x + 3, y + 3); ctx.moveTo(x + 3, y - 3); ctx.lineTo(x - 3, y + 3); ctx.stroke();
    }
  });
}

function drawRadar(candidate) {
  const canvas = $("radar");
  const {context: ctx, width, height} = canvasSetup(canvas);
  const cx = width / 2, cy = height / 2 + 6, radius = Math.min(width, height) * .31;
  const labels = ["Affinity", "Selectivity", "Safety", "Stability", "Solubility"];
  ctx.clearRect(0, 0, width, height);
  for (let ring = 1; ring <= 4; ring += 1) {
    ctx.beginPath();
    labels.forEach((_, index) => {
      const angle = -Math.PI / 2 + index * Math.PI * 2 / labels.length;
      const r = radius * ring / 4;
      const x = cx + Math.cos(angle) * r, y = cy + Math.sin(angle) * r;
      index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.closePath(); ctx.strokeStyle = "#d8d7cf"; ctx.stroke();
  }
  ctx.beginPath();
  metricKeys.forEach((key, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / metricKeys.length;
    const r = radius * candidate[key] / 100;
    const x = cx + Math.cos(angle) * r, y = cy + Math.sin(angle) * r;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.closePath(); ctx.fillStyle = "rgba(11,116,106,.18)"; ctx.fill(); ctx.strokeStyle = "#0b746a"; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = "#6c7771"; ctx.font = "8px Avenir Next, sans-serif"; ctx.textAlign = "center";
  labels.forEach((label, index) => {
    const angle = -Math.PI / 2 + index * Math.PI * 2 / labels.length;
    ctx.fillText(label, cx + Math.cos(angle) * (radius + 22), cy + Math.sin(angle) * (radius + 17) + 3);
  });
}

const moleculeState = {rx: .28, ry: -.4, zoom: 1, drag: null, candidate: null, points: []};

function makeMoleculePoints(candidate) {
  const seed = Number(candidate.id.slice(-3));
  const points = [];
  for (let i = 0; i < 95; i += 1) {
    const t = i * .29;
    points.push({x: Math.sin(t) * 17 + Math.sin(t * .31) * 8, y: (i - 47) * .72, z: Math.cos(t) * 17 + Math.sin(seed + t * .2) * 3, chain: 0});
  }
  for (let i = 0; i < 50; i += 1) {
    const t = i * .38;
    points.push({x: 27 + Math.sin(t) * 11, y: (i - 24) * .55, z: Math.cos(t) * 10, chain: 1});
  }
  return points;
}

function drawMolecule() {
  if (!moleculeState.candidate) return;
  const canvas = $("molecule");
  const {context: ctx, width, height} = canvasSetup(canvas);
  ctx.clearRect(0, 0, width, height);
  const projected = moleculeState.points.map(point => {
    const x1 = point.x * Math.cos(moleculeState.ry) + point.z * Math.sin(moleculeState.ry);
    const z1 = -point.x * Math.sin(moleculeState.ry) + point.z * Math.cos(moleculeState.ry);
    const y1 = point.y * Math.cos(moleculeState.rx) - z1 * Math.sin(moleculeState.rx);
    const depth = point.y * Math.sin(moleculeState.rx) + z1 * Math.cos(moleculeState.rx);
    const scale = Math.min(width, height) / 100 * moleculeState.zoom;
    return {...point, px: width / 2 + x1 * scale, py: height / 2 + y1 * scale, depth};
  });
  [[0, "#58b9ae"], [1, "#b9f227"]].forEach(([chain, color]) => {
    const chainPoints = projected.filter(point => point.chain === chain);
    ctx.strokeStyle = color; ctx.lineWidth = chain === 0 ? 2.2 : 2.8; ctx.globalAlpha = .8;
    ctx.beginPath();
    chainPoints.forEach((point, index) => index ? ctx.lineTo(point.px, point.py) : ctx.moveTo(point.px, point.py));
    ctx.stroke();
    chainPoints.sort((a, b) => a.depth - b.depth).forEach(point => {
      const size = clamp(2.2 + point.depth * .012, 1.5, 3.5);
      ctx.globalAlpha = clamp(.52 + point.depth * .007, .25, 1);
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(point.px, point.py, size, 0, Math.PI * 2); ctx.fill();
    });
  });
  ctx.globalAlpha = 1;
}

function candidateCopy(candidate) {
  const strongest = metricKeys.reduce((best, key) => candidate[key] > candidate[best] ? key : best, metricKeys[0]);
  const weakest = metricKeys.reduce((worst, key) => candidate[key] < candidate[worst] ? key : worst, metricKeys[0]);
  return {
    why: `Selected for a strong ${strongest} profile while remaining inside all active evidence gates. It sits ${candidate.frontier ? "on" : "near"} the current decision frontier.`,
    concern: `${weakest[0].toUpperCase() + weakest.slice(1)} is the weakest scored dimension. Functional mechanism remains unverified in wet-lab evidence.`,
    next: `Run replicate complex prediction, then prioritise a ligand-competition assay and receptor-activation counter-screen.`
  };
}

function openDrawerShell() {
  $("drawer-backdrop").hidden = false;
  $("candidate-drawer").setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  requestAnimationFrame(() => $("candidate-drawer").classList.add("is-open"));
}

function openCandidate(id) {
  const candidate = state.candidates.find(item => item.id === id);
  if (!candidate) return;
  state.selected = candidate;
  $("drawer-rank").textContent = `RANK ${String(candidate.rank).padStart(2, "0")}`;
  $("drawer-name").textContent = candidate.id;
  $("drawer-score").textContent = candidate.score.toFixed(1);
  $("score-list").innerHTML = metricKeys.map(key => `<div class="score-row"><span>${key[0].toUpperCase() + key.slice(1)}</span><b>${candidate[key].toFixed(1)}</b><i style="--value:${candidate[key]}%"></i></div>`).join("");
  const copy = candidateCopy(candidate);
  $("drawer-why").textContent = copy.why;
  $("drawer-concern").textContent = copy.concern;
  $("drawer-next").textContent = copy.next;
  moleculeState.candidate = candidate;
  moleculeState.points = makeMoleculePoints(candidate);
  moleculeState.rx = .28; moleculeState.ry = -.4; moleculeState.zoom = 1;
  openDrawerShell();
  requestAnimationFrame(() => {drawRadar(candidate); drawMolecule();});
}

function openComparison() {
  const top = state.ranked.filter(candidate => candidate.eligible).slice(0, 3);
  if (!top.length) return;
  state.selected = top[0];
  $("drawer-rank").textContent = "DEEP VALIDATION SET";
  $("drawer-name").textContent = "Top three";
  $("drawer-score").textContent = "03";
  $("score-list").innerHTML = top.map(candidate => `<div class="score-row"><span>${candidate.id} · score ${candidate.score.toFixed(1)}</span><b>#${candidate.rank}</b><i style="--value:${candidate.score}%"></i></div>`).join("");
  $("drawer-why").textContent = `${top.map(item => item.id).join(", ")} preserve three different trade-off profiles for validation instead of collapsing the decision to one score.`;
  $("drawer-concern").textContent = "All three remain computational hypotheses. Cross-model agreement and functional counter-screens are missing.";
  $("drawer-next").textContent = "Run an identical replicate panel for all three, then compare mechanism-specific assay results before selecting a lead.";
  moleculeState.candidate = top[0]; moleculeState.points = makeMoleculePoints(top[0]);
  moleculeState.rx = .28; moleculeState.ry = -.4; moleculeState.zoom = 1;
  openDrawerShell();
  requestAnimationFrame(() => {drawRadar(top[0]); drawMolecule();});
}

function closeDrawer() {
  $("candidate-drawer").classList.remove("is-open");
  $("candidate-drawer").setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  setTimeout(() => {$("drawer-backdrop").hidden = true;}, 400);
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove("is-visible"), 2600);
}

function download(name, content, type) {
  const link = document.createElement("a");
  const url = URL.createObjectURL(new Blob([content], {type}));
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 800);
}

function exportJson() {
  if (!state.resultsReady) return;
  const payload = {
    provider: "DemoProvider",
    simulated: true,
    target: $("target").value,
    intent: $("intent").value,
    weights: state.weights,
    candidates: state.ranked
  };
  download("receptorflow-demo-run.json", JSON.stringify(payload, null, 2), "application/json");
}

function exportCsv() {
  const columns = ["rank", "id", "eligible", "score", ...metricKeys, "uncertainty", "failReasons"];
  const rows = state.ranked.map(candidate => columns.map(column => {
    const value = column === "failReasons" ? candidate.failReasons.join("; ") : candidate[column];
    return `"${String(value).replace(/"/g, '""')}"`;
  }).join(","));
  download("receptorflow-demo-candidates.csv", [columns.join(","), ...rows].join("\n"), "text/csv");
}

$$(".quick-intents button").forEach(button => button.addEventListener("click", () => {
  $("intent").value = `Design a protein binder that ${button.dataset.intent.charAt(0).toLowerCase() + button.dataset.intent.slice(1)}`;
  $("intent").focus();
}));
$("build-brief").addEventListener("click", buildBrief);
$("edit-brief").addEventListener("click", () => {$("target").focus(); $("design").scrollIntoView({behavior: "smooth"});});
$("run-screen").addEventListener("click", runScreen);
$$(".weight-row input").forEach(input => input.addEventListener("input", () => syncWeights(input)));
[$("constraint-structure"), $("constraint-aggregation"), $("constraint-immunogenicity")].forEach(input => input.addEventListener("change", () => state.resultsReady && renderResults()));
$("candidate-search").addEventListener("input", renderTable);
$("export-json").addEventListener("click", exportJson);
$("export-csv").addEventListener("click", exportCsv);
$("compare-top").addEventListener("click", openComparison);
$("drawer-close").addEventListener("click", closeDrawer);
$("drawer-backdrop").addEventListener("click", closeDrawer);
document.addEventListener("keydown", event => {if (event.key === "Escape") closeDrawer();});
document.addEventListener("click", event => {
  const target = event.target.closest("[data-candidate]");
  if (target) openCandidate(target.dataset.candidate);
});
document.addEventListener("keydown", event => {
  const target = event.target.closest?.(".winner-card[data-candidate]");
  if (target && (event.key === "Enter" || event.key === " ")) {event.preventDefault(); openCandidate(target.dataset.candidate);}
});

const molecule = $("molecule");
molecule.addEventListener("pointerdown", event => {moleculeState.drag = [event.clientX, event.clientY]; molecule.setPointerCapture(event.pointerId);});
molecule.addEventListener("pointermove", event => {
  if (!moleculeState.drag) return;
  moleculeState.ry += (event.clientX - moleculeState.drag[0]) * .01;
  moleculeState.rx += (event.clientY - moleculeState.drag[1]) * .01;
  moleculeState.drag = [event.clientX, event.clientY]; drawMolecule();
});
molecule.addEventListener("pointerup", () => {moleculeState.drag = null;});
molecule.addEventListener("pointercancel", () => {moleculeState.drag = null;});
molecule.addEventListener("wheel", event => {event.preventDefault(); moleculeState.zoom = clamp(moleculeState.zoom * Math.exp(-event.deltaY * .001), .5, 2.4); drawMolecule();}, {passive: false});

const sectionObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (!entry.isIntersecting) return;
    $$(".nav-item").forEach(link => link.classList.toggle("is-active", link.getAttribute("href") === `#${entry.target.id}`));
  });
}, {rootMargin: "-30% 0px -60%"});
[$("design"), $("pipeline"), $("results")].forEach(section => sectionObserver.observe(section));

window.addEventListener("resize", () => {
  if (state.resultsReady) drawScatter();
  if (state.selected && $("candidate-drawer").classList.contains("is-open")) {drawRadar(state.selected); drawMolecule();}
});

syncWeights();
