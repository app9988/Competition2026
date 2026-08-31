"use strict";

const SCENARIO_NAMES = {
  buying: "Buying",
  browsing: "Browsing",
  boundary: "Boundary",
  intent_override: "Intent Override",
};

const QUESTION_REWRITES = {
  "To narrow things down: is there anything specific that matters to you about it?":
    "Got it! Is there anything else that's important to you? I'll factor it in.",
  "Which exact type of item are you shopping for?":
    "What type of item are you shopping for today?",
  "Do you have a material preference?":
    "Any material you prefer — cotton, leather, or something else?",
  "Is there a color you want?": "Do you have a color in mind?",
  "Any size or fit requirement?": "What size or fit works best for you?",
  "Any particular style you prefer?": "What style are you going for?",
  "Do you prefer a specific brand or store?": "Any favorite brands or stores?",
  "What budget range are you thinking of?": "Roughly what budget are you thinking of?",
  "Is there a specific feature it must have?": "Any must-have features I should know about?",
  "What will you mainly use it for?":
    "What's the occasion — everyday use, work, or something special?",
  "Based on everything so far these are my top picks - the first one should be very close.":
    "Based on everything you've told me, here are my top picks — the first one should be spot on.",
  "Here are the closest matches I found.": "Here are the closest matches I found for you.",
};

const QUESTION_SHORT = {
  "To narrow things down: is there anything specific that matters to you about it?":
    "is there anything else that's important to you?",
  "Which exact type of item are you shopping for?": "what type of item are you shopping for?",
  "Do you have a material preference?": "any material you prefer?",
  "Is there a color you want?": "do you have a color in mind?",
  "Any size or fit requirement?": "what size or fit works best for you?",
  "Any particular style you prefer?": "what style are you going for?",
  "Do you prefer a specific brand or store?": "any favorite brands or stores?",
  "What budget range are you thinking of?": "roughly what budget are you thinking of?",
  "Is there a specific feature it must have?": "any must-have features?",
  "What will you mainly use it for?": "what's the occasion?",
};

const COMBINED_ASK = "Here are my current best matches - and one more check: ";
const state = {
  bootstrap: { config: "default.json", samples: [], report: null },
  report: null,
  selectedSampleId: "",
  job: null,
  singleResult: null,
  visibleTurns: 0,
  playbackTimer: null,
  singleLoading: false,
};

const $ = (id) => document.getElementById(id);
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const fixed = (value, digits = 3) => Number(value || 0).toFixed(digits);
const scenarioName = (value) => SCENARIO_NAMES[value] || value || "-";
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");
const escapeAttr = escapeHtml;

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function polishAgentMessage(text) {
  if (!text) return text;
  if (text.startsWith(COMBINED_ASK)) {
    const question = text.slice(COMBINED_ASK.length);
    return `Here's my current best pick — ${QUESTION_SHORT[question] || question}`;
  }
  const polished = QUESTION_REWRITES[text] || text;
  return polished.replace(/^To narrow things down:\s*/i, "").replace(/^./, (char) => char.toUpperCase());
}

function statusPill(text, success = true) {
  return `<span class="status-pill status-pill--${success ? "success" : "danger"}">${success ? "✓ " : "× "}${escapeHtml(text)}</span>`;
}

function metricCard(label, value, note, accent = false) {
  return `<article class="metric-card${accent ? " metric-card--accent" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>${note ? `<small>${escapeHtml(note)}</small>` : ""}</article>`;
}

function setError(target, message) {
  const node = $(target);
  node.textContent = message || "";
  node.classList.toggle("is-hidden", !message);
}

function setTab(tab) {
  const single = tab === "single";
  $("singleTab").classList.toggle("active", single);
  $("fullTab").classList.toggle("active", !single);
  $("singleView").classList.toggle("is-hidden", !single);
  $("fullView").classList.toggle("is-hidden", single);
}

function updateIndexLoader(health) {
  const progress = Math.max(2, Math.min(100, Number(health.progress ?? (health.ready ? 100 : 8))));
  $("indexProgress").style.width = `${progress}%`;
  $("indexPercent").textContent = `${Math.round(progress)}%`;
  $("indexPhase").textContent = String(health.phase || "building").replaceAll("_", " ").toUpperCase();
  $("indexElapsed").textContent = `${fixed(health.elapsedSeconds, 1)}s`;
  $("indexMessage").textContent = health.message || "正在构建内存商品索引";
}

async function bootstrapApplication() {
  try {
    while (true) {
      const health = await api("/api/health");
      updateIndexLoader(health);
      if (health.error) throw new Error(health.error);
      if (health.ready) break;
      await delay(550);
    }

    const payload = await api("/api/bootstrap");
    state.bootstrap = payload;
    state.report = payload.report;
    state.selectedSampleId = payload.report?.results?.[0]?.sampleId || "";
    populateSamples(payload.samples || []);
    renderFullReport();
    $("app").classList.remove("app-hidden");
    $("app").setAttribute("aria-hidden", "false");
    $("indexLoader").classList.add("is-ready");
  } catch (error) {
    $("indexLoader").classList.add("has-error");
    $("indexPhase").textContent = "INDEX ERROR";
    $("indexMessage").textContent = error.message || String(error);
    $("indexPercent").textContent = "!";
  }
}

function populateSamples(samples) {
  $("singleSample").innerHTML = samples.map((sample) =>
    `<option value="${escapeAttr(sample.id)}">${escapeHtml(sample.id)} · ${escapeHtml(scenarioName(sample.scenario))} · ${escapeHtml(sample.difficulty)}</option>`
  ).join("");
}

function renderFullReport() {
  const report = state.report || { summary: {}, links: [], scenarios: [], results: [] };
  const summary = report.summary || {};
  $("metricStrip").innerHTML = [
    metricCard("TechnicalScore", fixed(summary.technicalScore, 4), "overall technical score", true),
    metricCard("Hit@10", fixed(summary.hitRate), "hit rate"),
    metricCard("MRR", fixed(summary.mrr), "mean reciprocal rank"),
    metricCard("MTTC", fixed(summary.mttc), "mean turns to complete"),
    metricCard("Rank1", `${summary.rank1 || 0}/${summary.sampleCount || 200}`, "rank-1 hits"),
    metricCard("Weak Loops", summary.weak ?? 0, "LoopScore < 0.9"),
  ].join("");

  const links = report.links || [];
  const allHealthy = links.every((link) => link.healthy);
  $("chainStatus").className = `status-pill status-pill--${allHealthy ? "success" : "danger"}`;
  $("chainStatus").textContent = allHealthy ? "✓ All healthy" : "× Needs attention";
  $("chainTrack").innerHTML = links.map((link, index) =>
    `<div class="chain-node${link.healthy ? "" : " is-weak"}" title="${escapeAttr(link.name)}: ${fixed(link.score, 4)}"><div class="chain-dot">${link.healthy ? "✓" : "!"}</div><strong>${escapeHtml(link.id)}</strong><span>${escapeHtml(link.name)}</span><small>${fixed(link.score)}</small>${index < links.length - 1 ? '<div class="chain-line"></div>' : ""}</div>`
  ).join("");

  $("scenarioRows").innerHTML = (report.scenarios || []).map((row) =>
    `<tr><td><span class="scenario-dot"></span>${escapeHtml(scenarioName(row.name))}</td><td>${row.sampleCount}</td><td>${fixed(row.hitRate)}</td><td>${fixed(row.mrr)}</td><td>${fixed(row.mttc)}</td><td>${row.rank1}/${row.sampleCount}</td><td><strong class="score-green">${fixed(row.loopScore, 4)}</strong></td></tr>`
  ).join("");

  $("jobProgressText").textContent = state.job
    ? `${state.job.current}/${state.job.total}`
    : `${summary.sampleCount || 0}/${summary.sampleCount || 200}`;
  const progress = state.job
    ? (Number(state.job.current || 0) / Math.max(Number(state.job.total || 1), 1)) * 100
    : (summary.sampleCount ? 100 : 0);
  $("jobProgressBar").style.width = `${progress}%`;
  $("jobElapsed").textContent = `${fixed(state.job?.elapsedSeconds ?? summary.elapsedSeconds, 1)}s`;
  renderResultRows();
}

function filteredResults() {
  const rows = state.report?.results || [];
  const keyword = $("resultSearch").value.trim().toLowerCase();
  if (!keyword) return rows;
  return rows.filter((row) => [row.sampleId, row.scenario, row.targetAsin, row.title]
    .some((value) => String(value || "").toLowerCase().includes(keyword)));
}

function renderResultRows() {
  const rows = filteredResults();
  $("resultCount").textContent = `${rows.length} rows · click a row for the score breakdown`;
  $("resultRows").innerHTML = rows.map((row) =>
    `<tr data-sample="${escapeAttr(row.sampleId)}" class="${row.sampleId === state.selectedSampleId ? "selected" : ""}"><td>${statusPill(row.status, row.hit)}</td><td><strong>${escapeHtml(row.sampleId)}</strong></td><td>${escapeHtml(scenarioName(row.scenario))}</td><td><span class="difficulty difficulty--${escapeAttr(row.difficulty)}">${escapeHtml(row.difficulty)}</span></td><td>${row.turn}</td><td><strong>${row.rank || "-"}</strong></td><td class="${row.hit ? "score-green" : "score-red"}">${row.hit ? "1" : "0"}</td><td><strong class="${row.loopScore >= .9 ? "score-green" : "score-red"}">${fixed(row.loopScore, 4)}</strong></td><td class="mono">${escapeHtml(row.targetAsin)}</td><td class="product-title" title="${escapeAttr(row.title)}">${escapeHtml(row.title)}</td></tr>`
  ).join("");
  const selected = (state.report?.results || []).find((row) => row.sampleId === state.selectedSampleId) || rows[0];
  if (selected && !state.selectedSampleId) state.selectedSampleId = selected.sampleId;
  renderResultDrawer(selected);
}

function renderResultDrawer(row) {
  if (!row) {
    $("resultDrawer").className = "section-card result-drawer drawer-empty";
    $("resultDrawer").innerHTML = '<span class="drawer-empty__icon" aria-hidden="true">◎</span><p>Select a result to see details</p>';
    return;
  }
  $("resultDrawer").className = "section-card result-drawer";
  $("resultDrawer").innerHTML = `
    <div class="drawer-head"><div><span>Session Detail</span><h2>${escapeHtml(row.sampleId)}</h2></div>${statusPill(row.status, row.hit)}</div>
    <dl class="detail-list"><div><dt>Scenario</dt><dd>${escapeHtml(scenarioName(row.scenario))}</dd></div><div><dt>Difficulty / Category</dt><dd>${escapeHtml(row.difficulty)} · ${escapeHtml(row.category)}</dd></div><div><dt>Turns Used</dt><dd>${row.turn} / 10</dd></div><div><dt>Final Rank</dt><dd>Rank ${row.rank || "-"}</dd></div></dl>
    <div class="score-formula"><span>LoopScore Breakdown</span><strong>${fixed(row.loopScore, 4)}</strong><div class="formula-row"><span>0.50 × Hit@10</span><b>${fixed(row.hit ? .5 : 0)}</b></div><div class="formula-row"><span>0.30 × Reciprocal Rank</span><b>${fixed(row.reciprocalRank * .3)}</b></div><div class="formula-row"><span>0.20 × Efficiency</span><b>${fixed(row.efficiency * .2)}</b></div></div>
    <div class="product-detail"><span>Target Product</span><strong>${escapeHtml(row.title)}</strong><small>${escapeHtml(row.targetAsin)}</small></div>
    <button class="secondary-action full-width" type="button" data-replay="${escapeAttr(row.sampleId)}"><span>Open Session Replay</span><b>›</b></button>`;
}

async function runFullEvaluation() {
  setError("fullError", "");
  const button = $("runFull");
  button.disabled = true;
  button.classList.add("is-running");
  button.innerHTML = '<span aria-hidden="true">◌</span>Running…';
  try {
    let job = await api("/api/eval/jobs", {
      method: "POST",
      body: JSON.stringify({
        config: "default.json",
        paraphraseLevel: Number($("fullMode").value),
        limit: Number($("fullLimit").value),
      }),
    });
    state.job = job;
    while (!["completed", "failed"].includes(job.status)) {
      updateJobProgress(job);
      await delay(700);
      job = await api(`/api/eval/jobs/${encodeURIComponent(job.id)}`);
      state.job = job;
    }
    updateJobProgress(job);
    if (job.status === "failed") throw new Error(job.error || "Evaluation failed");
    state.report = job.report;
    state.selectedSampleId = job.report?.results?.[0]?.sampleId || "";
    renderFullReport();
  } catch (error) {
    setError("fullError", error.message || String(error));
  } finally {
    button.disabled = false;
    button.classList.remove("is-running");
    button.innerHTML = '<span aria-hidden="true">▶</span>Run Full Evaluation';
  }
}

function updateJobProgress(job) {
  const total = Math.max(Number(job.total || 1), 1);
  $("jobProgressText").textContent = `${job.current || 0}/${job.total || 0}`;
  $("jobProgressBar").style.width = `${(Number(job.current || 0) / total) * 100}%`;
  $("jobElapsed").textContent = `${fixed(job.elapsedSeconds, 1)}s`;
}

function setSingleLoading(loading) {
  state.singleLoading = loading;
  const button = $("runSingle");
  button.disabled = loading;
  button.classList.toggle("is-running", loading);
  button.innerHTML = loading
    ? '<span aria-hidden="true">◌</span>Running…'
    : '<span aria-hidden="true">▶</span>Run Single Test';
  $("nextSingle").disabled = loading;
}

async function runSingleSession(forcedId) {
  const sampleId = forcedId || $("singleSample").value;
  if (!sampleId) return;
  window.clearTimeout(state.playbackTimer);
  setSingleLoading(true);
  setError("singleError", "");
  try {
    const result = await api("/api/session/run", {
      method: "POST",
      body: JSON.stringify({
        sampleId,
        paraphraseLevel: Number($("singleMode").value),
      }),
    });
    state.singleResult = result;
    state.visibleTurns = 1;
    $("singleSample").value = sampleId;
    renderSingleResult();
    scheduleNextTurn();
  } catch (error) {
    setError("singleError", error.message || String(error));
  } finally {
    setSingleLoading(false);
  }
}

function renderSingleResult() {
  const result = state.singleResult;
  if (!result) return;
  const final = result.result || {};
  $("singleEmpty").classList.add("is-hidden");
  $("singleResult").classList.remove("is-hidden");
  $("playbackActions").classList.remove("is-hidden");
  $("singleHero").innerHTML = `
    <div><span class="eyebrow">${escapeHtml(result.sample.id)}</span><h1>${escapeHtml(scenarioName(result.sample.scenario))} · ${escapeHtml(result.sample.category)}</h1><p>${escapeHtml(result.sample.profile)}</p><div class="tag-list">${(result.sample.tags || []).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}</div></div>
    <div class="single-score"><span>Final Score</span><strong>${fixed(final.score, 4)}</strong><small>${final.hit ? `Turn ${final.turns} · Rank ${final.rank}` : "No hit in 10 turns"}</small></div>`;
  $("singleMetrics").innerHTML = (result.chainMetrics || []).map((metric) =>
    metricCard(`${metric.id} · ${metric.name}`, fixed(metric.value), metric.detail)
  ).join("");
  renderTranscript();
  renderSelectedProduct(result.selectedProduct || {});
  renderScoreBreakdown(final);
}

function renderTranscript() {
  const result = state.singleResult;
  if (!result) return;
  const visible = result.transcript.slice(0, state.visibleTurns);
  $("transcriptProgress").textContent = `Real trace · showing ${visible.length}/${result.transcript.length} turns`;
  $("transcriptStatus").className = `status-pill status-pill--${result.result.hit ? "success" : "danger"}`;
  $("transcriptStatus").textContent = result.result.hit ? "✓ Target hit" : "× Replay finished";
  $("transcriptList").innerHTML = visible.map((turn, index) => transcriptTurn(turn, index === visible.length - 1)).join("");
}

function transcriptTurn(turn, active) {
  const products = (turn.products || []).slice(0, 3);
  const hiddenProducts = Math.max(0, (turn.products || []).length - products.length);
  const productMarkup = products.length ? `<div class="turn-products">${products.map((item) =>
    `<div class="product-chip${item.isTarget ? " product-chip--target" : ""}" title="${escapeAttr(item.title)}"><strong>${escapeHtml(item.title)}</strong><span>${item.isTarget ? "✓ It's a match · " : ""}${item.price ? `$${escapeHtml(item.price)}` : ""}${item.rating ? ` · ★${escapeHtml(item.rating)}` : ""} · ${escapeHtml(item.asin)}</span></div>`
  ).join("")}${hiddenProducts ? `<span class="product-chip-more">+${hiddenProducts} more</span>` : ""}</div>` : "";
  const ranked = turn.rankedPreview || [];
  const rankedMarkup = ranked.length ? `<div class="ranked-strip"><span class="ranked-strip-label">Candidate ranking</span><div class="ranked-items">${ranked.map((item) =>
    `<div class="ranked-item${item.isTarget ? " ranked-item--target" : ""}" title="${escapeAttr(item.title)}"><span class="rank-badge">#${item.rank}</span><span class="rank-title">${escapeHtml(item.title)}</span></div>`
  ).join("")}</div></div>` : "";
  return `<article class="chat-turn${active ? " chat-turn--active" : ""}"><div class="chat-turn-label"><span>Turn ${turn.turn}</span></div><div class="chat-row chat-row--user"><div class="bubble bubble--user"><p>${escapeHtml(turn.userMessage)}</p></div></div><div class="chat-row chat-row--agent"><div class="bubble bubble--agent"><p>${escapeHtml(polishAgentMessage(turn.agentMessage))}</p>${productMarkup}</div></div>${rankedMarkup}<div class="chat-turn-foot">${turn.hit ? statusPill(`Rank ${turn.shownRank}`) : '<span class="asking-chip">Still asking</span>'}<div class="turn-meta"><span>Event ${escapeHtml(turn.event)}</span><span>Gate ${fixed(turn.gate)}</span><span>Pool ${turn.cascadePool}</span><span>${fixed(turn.latencyMs, 1)}ms</span></div></div></article>`;
}

function renderSelectedProduct(product) {
  $("selectedProduct").innerHTML = `<div class="product-icon" aria-hidden="true">⌁</div><span>Final Selected Product</span><h2>${escapeHtml(product.title)}</h2><p class="mono">${escapeHtml(product.asin)}</p><dl><div><dt>Rank</dt><dd>Rank ${product.rank || "-"}</dd></div><div><dt>Rating</dt><dd>${escapeHtml(product.rating || "-")}</dd></div><div><dt>Price</dt><dd>${product.price ? `$${escapeHtml(product.price)}` : "-"}</dd></div></dl>`;
}

function renderScoreBreakdown(final) {
  $("scoreBreakdown").innerHTML = `<h2>Score Breakdown</h2><div><span>Hit@10</span><b>${final.hit ? "1.000" : "0.000"}</b></div><div><span>Reciprocal Rank</span><b>${fixed(final.reciprocalRank)}</b></div><div><span>Efficiency</span><b>${fixed(final.efficiency)}</b></div><div class="total"><span>TechnicalScore</span><b>${fixed(final.score, 4)}</b></div>`;
}

function scheduleNextTurn() {
  window.clearTimeout(state.playbackTimer);
  const transcript = state.singleResult?.transcript || [];
  if (state.visibleTurns >= transcript.length) return;
  state.playbackTimer = window.setTimeout(() => {
    state.visibleTurns += 1;
    renderTranscript();
    scheduleNextTurn();
  }, 850);
}

function replaySingle() {
  if (!state.singleResult) return;
  state.visibleTurns = 1;
  renderTranscript();
  scheduleNextTurn();
}

function nextSingle() {
  const samples = state.bootstrap.samples || [];
  if (!samples.length || state.singleLoading) return;
  const current = $("singleSample").value;
  const index = samples.findIndex((sample) => sample.id === current);
  const next = samples[(index + 1) % samples.length];
  $("singleSample").value = next.id;
  runSingleSession(next.id);
}

function openReplay(sampleId) {
  setTab("single");
  $("singleSample").value = sampleId;
  runSingleSession(sampleId);
}

function bindEvents() {
  $("fullTab").addEventListener("click", () => setTab("full"));
  $("singleTab").addEventListener("click", () => setTab("single"));
  $("runFull").addEventListener("click", runFullEvaluation);
  $("runSingle").addEventListener("click", () => runSingleSession());
  $("replaySingle").addEventListener("click", replaySingle);
  $("nextSingle").addEventListener("click", nextSingle);
  $("resultSearch").addEventListener("input", renderResultRows);
  $("resultRows").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-sample]");
    if (!row) return;
    state.selectedSampleId = row.dataset.sample;
    renderResultRows();
  });
  $("resultDrawer").addEventListener("click", (event) => {
    const button = event.target.closest("[data-replay]");
    if (button) openReplay(button.dataset.replay);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  $("headerDate").textContent = new Intl.DateTimeFormat("en-US", {
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(new Date());
  bindEvents();
  bootstrapApplication();
});
