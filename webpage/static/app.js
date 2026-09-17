const state = {
  selectedId: null,
  selectedName: "",
  chart: null,
  pollTimer: null,
  running: false,
  selectToken: 0,
};

const els = {
  list: document.getElementById("fund-list"),
  isinForm: document.getElementById("isin-form"),
  isinInput: document.getElementById("isin-input"),
  loadBtn: document.getElementById("load-btn"),
  runBtn: document.getElementById("run-btn"),
  runHint: document.getElementById("run-hint"),
  fundLabel: document.getElementById("fund-label"),
  fundTitle: document.getElementById("fund-title"),
  fundSubtitle: document.getElementById("fund-subtitle"),
  navChip: document.getElementById("nav-chip"),
  navValue: document.getElementById("nav-value"),
  navChange: document.getElementById("nav-change"),
  holdingsList: document.getElementById("holdings-list"),
  sectorsList: document.getElementById("sectors-list"),
  chartCaption: document.getElementById("chart-caption"),
  chartEmpty: document.getElementById("chart-empty"),
  chartSkeleton: document.getElementById("chart-skeleton"),
  summaryBody: document.getElementById("summary-body"),
  summaryCaption: document.getElementById("summary-caption"),
  logTail: document.getElementById("log-tail"),
  newsList: document.getElementById("news-list"),
  newsCaption: document.getElementById("news-caption"),
  tokenBar: document.getElementById("token-bar"),
  tokenInput: document.getElementById("token-input"),
  tokenOutput: document.getElementById("token-output"),
  tokenTotal: document.getElementById("token-total"),
  tokenCalls: document.getElementById("token-calls"),
};

function formatNav(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 3,
  });
}

function formatChange(pct) {
  if (pct == null || Number.isNaN(Number(pct))) return "—";
  const value = Number(pct);
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(3)}%`;
}

function setRunEnabled(enabled, title) {
  els.runBtn.disabled = !enabled;
  els.runBtn.title = title || (enabled ? "Run the weekly pipeline" : "Load an ISIN first");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (${response.status})`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function renderFunds(funds) {
  if (!funds.length) {
    els.list.innerHTML = '<p class="muted">Recently loaded ISINs appear here.</p>';
    return;
  }
  els.list.innerHTML = "";
  funds.forEach((fund) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "fund-btn";
    button.dataset.id = fund.id;
    const subtitle = fund.subtitle ? `<span class="fund-id">${fund.subtitle}</span>` : "";
    button.innerHTML = `<span>${fund.name}</span>${subtitle}<span class="fund-id">${fund.isin || fund.id}</span>`;
    button.addEventListener("click", () => {
      els.isinInput.value = fund.isin || fund.id;
      loadIsin(fund.isin || fund.id);
    });
    els.list.appendChild(button);
  });
}

function markActive(fundId) {
  els.list.querySelectorAll(".fund-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.id === fundId);
  });
}

function renderNews(items) {
  if (!els.newsList) return;
  if (!items || !items.length) {
    els.newsCaption.textContent = "Top kept stories after a run.";
    els.newsList.innerHTML =
      '<p class="placeholder">Run a fund to fill this rail with the most important articles.</p>';
    return;
  }
  els.newsCaption.textContent = "Highest-scoring kept stories for this week.";
  els.newsList.innerHTML = items
    .map((item) => {
      const title = escapeHtml(item.title || "");
      const url = escapeHtml(item.url || "");
      const source = escapeHtml(item.source || "Publisher");
      return `<article class="news-card">
        <a href="${url}" target="_blank" rel="noopener noreferrer">${title}</a>
        <span class="source">${source}</span>
      </article>`;
    })
    .join("");
}

function formatTokens(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toLocaleString("en-IN");
}

function applyTokenUsage(usage) {
  if (!els.tokenBar) return;
  if (!usage || !(usage.total_tokens || usage.prompt_tokens || usage.completion_tokens || usage.calls)) {
    els.tokenBar.classList.add("hidden");
    return;
  }
  els.tokenInput.textContent = formatTokens(usage.prompt_tokens);
  els.tokenOutput.textContent = formatTokens(usage.completion_tokens);
  els.tokenTotal.textContent = formatTokens(usage.total_tokens);
  if (els.tokenCalls) els.tokenCalls.textContent = formatTokens(usage.calls);
  els.tokenBar.classList.remove("hidden");
}

function applyIdentity(payload) {
  const name = payload.fund_name || payload.name || payload.isin || "Fund";
  const subtitle = payload.subtitle || "";
  els.fundLabel.textContent = payload.isin || payload.fund_id || "Loaded scheme";
  els.fundTitle.textContent = name;
  if (els.fundSubtitle) {
    if (subtitle) {
      els.fundSubtitle.textContent = subtitle;
      els.fundSubtitle.classList.remove("hidden");
    } else {
      els.fundSubtitle.textContent = "";
      els.fundSubtitle.classList.add("hidden");
    }
  }
}

function applyNavChart(payload) {
  const down = (payload.change_pct || 0) < 0;
  els.navChip.classList.remove("hidden");
  els.navValue.textContent = formatNav(payload.end_nav);
  els.navChange.textContent = formatChange(payload.change_pct);
  els.navChange.classList.toggle("down", down);
  els.navChange.classList.toggle("up", !down);
  const start = payload.dates[0] || "—";
  const end = payload.dates[payload.dates.length - 1] || "—";
  els.chartCaption.textContent = `${start} → ${end}`;
  drawChart(payload);
}

function showPlaceholder(message) {
  els.summaryBody.classList.remove("fade-in");
  els.summaryBody.innerHTML = `<p class="placeholder">${message}</p>`;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function formatInline(value) {
  return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderSummary(text) {
  const cleaned = (text || "").trim();
  if (!cleaned) {
    showPlaceholder("No summary yet. Run this fund to generate the investor note.");
    return;
  }
  const blocks = [];
  let listItems = [];
  const flushList = () => {
    if (!listItems.length) return;
    blocks.push(`<ul>${listItems.map((item) => `<li>${formatInline(item)}</li>`).join("")}</ul>`);
    listItems = [];
  };
  cleaned.split(/\n+/).forEach((raw) => {
    const line = raw.trim();
    if (!line) return;
    if (/^##\s+/.test(line)) {
      flushList();
      blocks.push(`<h3>${formatInline(line.replace(/^##\s+/, ""))}</h3>`);
      return;
    }
    const bullet = line.match(/^[•\-\*]\s+(.*)$/);
    if (bullet) {
      listItems.push(bullet[1]);
      return;
    }
    flushList();
    blocks.push(`<p>${formatInline(line)}</p>`);
  });
  flushList();
  els.summaryBody.classList.remove("fade-in");
  els.summaryBody.innerHTML = blocks.join("");
  void els.summaryBody.offsetWidth;
  els.summaryBody.classList.add("fade-in");
}

function destroyChart() {
  if (state.chart) {
    state.chart.destroy();
    state.chart = null;
  }
}

function drawChart(payload) {
  const canvas = document.getElementById("nav-chart");
  destroyChart();
  const down = (payload.change_pct || 0) < 0;
  const color = down ? "#e06b6b" : "#5dbe8a";
  state.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: payload.dates,
      datasets: [
        {
          data: payload.values,
          borderColor: color,
          backgroundColor: down ? "rgba(224, 107, 107, 0.12)" : "rgba(93, 190, 138, 0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: "#f3ead3",
          pointBorderColor: color,
          borderWidth: 2.4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (item) => `NAV ${formatNav(item.parsed.y)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#8d8776", maxRotation: 0 },
          border: { color: "rgba(243, 234, 211, 0.12)" },
        },
        y: {
          grid: { color: "rgba(243, 234, 211, 0.06)" },
          ticks: {
            color: "#8d8776",
            callback: (value) => formatNav(value),
          },
          border: { display: false },
        },
      },
    },
  });
}

function setChartLoading(loading) {
  els.chartSkeleton.hidden = !loading;
  els.chartEmpty.classList.toggle("hidden", loading || Boolean(state.chart));
}

async function loadNav(fundId, token) {
  setChartLoading(true);
  els.chartEmpty.classList.add("hidden");
  try {
    const payload = await fetchJson(`/api/nav/${encodeURIComponent(fundId)}`);
    if (token !== state.selectToken) return;
    const down = (payload.change_pct || 0) < 0;
    els.navChip.classList.remove("hidden");
    els.navValue.textContent = formatNav(payload.end_nav);
    els.navChange.textContent = formatChange(payload.change_pct);
    els.navChange.classList.toggle("down", down);
    els.navChange.classList.toggle("up", !down);
    const start = payload.dates[0] || "—";
    const end = payload.dates[payload.dates.length - 1] || "—";
    els.chartCaption.textContent = `${start} → ${end}`;
    drawChart(payload);
  } catch (error) {
    if (token !== state.selectToken) return;
    destroyChart();
    els.navChip.classList.add("hidden");
    els.chartCaption.textContent = "NAV history could not be loaded.";
    els.chartEmpty.textContent = error.message;
    els.chartEmpty.classList.remove("hidden");
  } finally {
    if (token === state.selectToken) setChartLoading(false);
  }
}

async function loadExistingSummary(fundId, token) {
  try {
    const payload = await fetchJson(`/api/summary/${encodeURIComponent(fundId)}`);
    if (token !== state.selectToken) return;
    if (payload.investor_summary) {
      els.summaryCaption.textContent = "Last saved note for this fund.";
      renderSummary(payload.investor_summary);
    } else if (payload.found && payload.empty) {
      els.summaryCaption.textContent = "Last run left an empty note.";
      showPlaceholder("The last run saved a blank summary. Click Run to generate it again.");
    } else {
      els.summaryCaption.textContent = "The pipeline writes a news-backed summary after Run.";
      showPlaceholder("Select a fund, then run. The note will land here — reasons, not only percentages.");
    }
    if (payload.important_news && payload.important_news.length) {
      renderNews(payload.important_news);
    }
  } catch {
    if (token !== state.selectToken) return;
    showPlaceholder("Select a fund, then run.");
  }
}

function formatPct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toFixed(2)}%`;
}

function renderRankList(node, rows, emptyText, subtitleKey) {
  if (!node) return;
  if (!rows || !rows.length) {
    node.innerHTML = `<li class="placeholder">${emptyText}</li>`;
    return;
  }
  const peak = Math.max(...rows.map((row) => Number(row.percentage) || 0), 1);
  node.innerHTML = rows
    .map((row, index) => {
      const width = Math.max(8, Math.round(((Number(row.percentage) || 0) / peak) * 100));
      const sub = row[subtitleKey]
        ? `<span class="sub">${row[subtitleKey]}</span>`
        : "";
      return `<li class="rank-item">
        <span class="rank">${index + 1}</span>
        <span class="meta"><span class="name">${row.name}</span>${sub}</span>
        <span class="pct">${formatPct(row.percentage)}</span>
        <span class="bar"><span style="width:${width}%"></span></span>
      </li>`;
    })
    .join("");
}

async function loadBook(fundId, token) {
  const urls = [
    `/data/${encodeURIComponent(fundId)}.json`,
    `/api/book/${encodeURIComponent(fundId)}`,
    `/api/nav/${encodeURIComponent(fundId)}`,
  ];
  for (const url of urls) {
    try {
      const payload = await fetchJson(url);
      if (token !== state.selectToken) return;
      if (payload.holdings && payload.holdings.length) {
        renderRankList(els.holdingsList, payload.holdings, "No holdings in this file.", "industry");
        renderRankList(els.sectorsList, payload.sectors, "No sectors in this file.", "");
        if (payload.important_news && payload.important_news.length) {
          renderNews(payload.important_news);
        }
        return;
      }
      if (payload.important_news && payload.important_news.length) {
        renderNews(payload.important_news);
      }
    } catch {
      /* try next source */
    }
  }
  if (token !== state.selectToken) return;
  renderRankList(els.holdingsList, [], "No holdings in this file.", "industry");
  renderRankList(els.sectorsList, [], "No sectors in this file.", "");
}

async function loadIsin(rawIsin, token) {
  const isin = String(rawIsin || "").trim().toUpperCase();
  if (!isin) return;
  const selectToken = token || ++state.selectToken;
  state.selectedId = isin;
  state.selectedName = isin;
  els.isinInput.value = isin;
  markActive(isin);
  els.fundLabel.textContent = isin;
  els.fundTitle.textContent = "Loading fund…";
  if (els.fundSubtitle) els.fundSubtitle.classList.add("hidden");
  if (!state.running) {
    setRunEnabled(true, "Run the weekly pipeline");
    els.runHint.textContent = "Run builds a news-backed note. This can take several minutes.";
  }
  setChartLoading(true);
  try {
    const payload = await fetchJson("/api/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isin }),
    });
    if (selectToken !== state.selectToken) return;
    state.selectedName = payload.fund_name || isin;
    applyIdentity(payload);
    applyNavChart(payload);
    applyTokenUsage(payload.token_usage);
    renderRankList(els.holdingsList, payload.holdings, "No holdings in this file.", "industry");
    renderRankList(els.sectorsList, payload.sectors, "No sectors in this file.", "");
    if (payload.cached && payload.investor_summary) {
      els.summaryCaption.textContent = "Saved note for the current NAV date.";
      renderSummary(payload.investor_summary);
      renderNews(payload.important_news);
    } else if (payload.investor_summary) {
      els.summaryCaption.textContent = payload.nav_stale
        ? "NAV has moved since this note. Run to refresh."
        : "Last saved note for this fund.";
      renderSummary(payload.investor_summary);
      renderNews(payload.important_news);
    } else {
      els.summaryCaption.textContent = "The pipeline writes a news-backed summary after Run.";
      showPlaceholder("Load looks good. Click Run to generate the investor note.");
      renderNews([]);
    }
    if (!state.running) {
      els.runHint.textContent = payload.cached
        ? "NAV is unchanged. Run will show the saved note."
        : "NAV is new or the note is missing. Run will fetch news and score it.";
    }
    refreshRecents();
  } catch (error) {
    if (selectToken !== state.selectToken) return;
    destroyChart();
    els.navChip.classList.add("hidden");
    applyTokenUsage(null);
    els.chartCaption.textContent = "Fund could not be loaded.";
    els.chartEmpty.textContent = error.message;
    els.chartEmpty.classList.remove("hidden");
    showPlaceholder(error.message);
    setRunEnabled(false, "Fix the ISIN, then load again");
  } finally {
    if (selectToken === state.selectToken) setChartLoading(false);
  }
}

function showLog(lines) {
  if (!lines || !lines.length) {
    els.logTail.classList.add("hidden");
    els.logTail.textContent = "";
    return;
  }
  els.logTail.classList.remove("hidden");
  els.logTail.textContent = lines.slice(-12).join("\n");
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

async function pollStatus() {
  try {
    const status = await fetchJson("/api/run/status");
    showLog(status.log_tail);
    if (status.status === "running") {
      els.runBtn.textContent = "Running…";
      setRunEnabled(false, "A run is already in progress");
      els.runHint.textContent = "RSS, scrape, and DeepSeek are in flight. This can take several minutes.";
      return;
    }
    stopPolling();
    state.running = false;
    els.runBtn.textContent = "Run";
    if (state.selectedId) {
      setRunEnabled(true, "Run the weekly pipeline");
      els.runHint.textContent = "Run builds a news-backed note. This can take several minutes.";
    } else {
      setRunEnabled(false, "Select a fund first");
    }
    if (status.status === "done" && status.fund_id) {
      els.summaryCaption.textContent = "Fresh note from this run.";
      let payload = await fetchJson(`/api/summary/${encodeURIComponent(status.fund_id)}`);
      if (!payload.found || payload.empty) {
        await new Promise((resolve) => setTimeout(resolve, 400));
        payload = await fetchJson(`/api/summary/${encodeURIComponent(status.fund_id)}`);
      }
      if (payload.investor_summary) {
        renderSummary(payload.investor_summary);
        showLog([]);
      } else if (payload.found && payload.empty) {
        els.summaryCaption.textContent = "Run finished without a note.";
        showPlaceholder(
          "The pipeline finished, but the investor summary came back empty. Check the log below or run again."
        );
      } else {
        showPlaceholder("The run finished, but no summary file was found.");
      }
      renderNews(payload.important_news);
      applyTokenUsage(payload.token_usage);
    } else if (status.status === "error") {
      els.summaryCaption.textContent = "Run failed.";
      const message = status.error || "The pipeline stopped before writing a summary.";
      showPlaceholder(message);
    }
  } catch (error) {
    stopPolling();
    state.running = false;
    els.runBtn.textContent = "Run";
    if (state.selectedId) setRunEnabled(true, "Run the weekly pipeline");
    showPlaceholder(error.message);
  }
}

async function startRun() {
  const isin = String(els.isinInput.value || state.selectedId || "").trim().toUpperCase();
  if (!isin || state.running) return;
  state.selectedId = isin;
  state.running = true;
  els.runBtn.textContent = "Running…";
  setRunEnabled(false, "A run is already in progress");
  els.runHint.textContent = "Checking the latest NAV date…";
  els.summaryCaption.textContent = "Preparing the investor note…";
  showPlaceholder("Checking whether a saved note already matches the latest NAV.");
  try {
    const result = await fetchJson("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ isin }),
    });
    if (result.status === "cached") {
      state.running = false;
      els.runBtn.textContent = "Run";
      setRunEnabled(true, "Run the weekly pipeline");
      els.runHint.textContent = "NAV is unchanged. Showing the saved note.";
      els.summaryCaption.textContent = "Saved note for the current NAV date.";
      const payload = await fetchJson(`/api/summary/${encodeURIComponent(isin)}`);
      renderSummary(payload.investor_summary);
      renderNews(payload.important_news);
      applyTokenUsage(payload.token_usage);
      showLog([]);
      return;
    }
    els.runHint.textContent = "RSS, scrape, and DeepSeek are in flight. This can take several minutes.";
    els.summaryCaption.textContent = "Generating the investor note…";
    showPlaceholder("Working through prices, news, and scoring. Keep this tab open.");
    stopPolling();
    await pollStatus();
    state.pollTimer = setInterval(pollStatus, 2000);
  } catch (error) {
    state.running = false;
    els.runBtn.textContent = "Run";
    if (error.status === 409) {
      setRunEnabled(false, "A run is already in progress");
      els.runHint.textContent = "Another fund is already running. Wait for it to finish.";
      stopPolling();
      state.pollTimer = setInterval(pollStatus, 2000);
      return;
    }
    if (state.selectedId) setRunEnabled(true, "Run the weekly pipeline");
    els.summaryCaption.textContent = "Run failed.";
    showPlaceholder(error.message);
  }
}

async function refreshRecents() {
  try {
    const payload = await fetchJson("/api/funds");
    renderFunds(payload.funds || []);
    if (state.selectedId) markActive(state.selectedId);
  } catch {
    /* ignore */
  }
}

async function boot() {
  if (els.isinForm) {
    els.isinForm.addEventListener("submit", (event) => {
      event.preventDefault();
      loadIsin(els.isinInput.value);
    });
  }
  if (els.runBtn) {
    els.runBtn.addEventListener("click", startRun);
  }
  try {
    const payload = await fetchJson("/api/funds");
    renderFunds(payload.funds || []);
  } catch (error) {
    if (els.list) els.list.innerHTML = `<p class="muted">${error.message}</p>`;
  }
  try {
    const status = await fetchJson("/api/run/status");
    if (status.status === "running") {
      state.running = true;
      els.runBtn.textContent = "Running…";
      setRunEnabled(false, "A run is already in progress");
      els.runHint.textContent = "A run is already in progress.";
      state.pollTimer = setInterval(pollStatus, 2000);
    }
  } catch {
    /* ignore */
  }
}

boot();
