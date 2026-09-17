const params = new URLSearchParams(window.location.search);
const isin = String(params.get("isin") || "").trim().toUpperCase();

const els = {
  isin: document.getElementById("news-isin"),
  title: document.getElementById("news-title"),
  sub: document.getElementById("news-sub"),
  nameRow: document.getElementById("name-row"),
  articleList: document.getElementById("article-list"),
  empty: document.getElementById("news-empty"),
  stockBtn: document.getElementById("btn-stocks"),
  sectorBtn: document.getElementById("btn-sectors"),
};

const state = {
  type: "stock",
  selected: null,
  payload: null,
};

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatChange(pct) {
  if (pct == null || Number.isNaN(Number(pct))) return "";
  const value = Number(pct);
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

function targetsOfType(type) {
  return (state.payload.targets || []).filter((row) => row.type === type);
}

function setType(type) {
  state.type = type;
  els.stockBtn.className = type === "stock" ? "type-btn active" : "type-btn";
  els.sectorBtn.className = type === "sector" ? "type-btn active" : "type-btn";
  els.stockBtn.setAttribute("aria-pressed", String(type === "stock"));
  els.sectorBtn.setAttribute("aria-pressed", String(type === "sector"));
  const rows = targetsOfType(type);
  state.selected = rows[0] ? rows[0].name : null;
  renderNames();
  renderArticles();
}

function renderNames() {
  const rows = targetsOfType(state.type);
  if (!rows.length) {
    els.nameRow.innerHTML = "";
    return;
  }
  els.nameRow.innerHTML = rows
    .map((row) => {
      const change = formatChange(row.weekly_change_pct);
      const down = Number(row.weekly_change_pct) < 0;
      const active = row.name === state.selected ? " active" : "";
      const sentiment = escapeHtml(row.target_sentiment || "");
      return `<button type="button" class="name-chip${active}" data-name="${escapeHtml(row.name)}">
        <span class="name-chip-title">${escapeHtml(row.name)}</span>
        <span class="name-chip-meta">
          ${change ? `<span class="${down ? "down" : "up"}">${change}</span>` : ""}
          ${sentiment ? `<span class="pill">${sentiment}</span>` : ""}
        </span>
      </button>`;
    })
    .join("");
  els.nameRow.querySelectorAll(".name-chip").forEach((button) => {
    button.addEventListener("click", () => {
      state.selected = button.dataset.name;
      renderNames();
      renderArticles();
    });
  });
}

function renderArticles() {
  const rows = targetsOfType(state.type);
  const target = rows.find((row) => row.name === state.selected);
  if (!rows.length) {
    els.articleList.classList.add("hidden");
    els.articleList.innerHTML = "";
    els.empty.classList.remove("hidden");
    els.empty.textContent =
      state.type === "stock"
        ? "No stock targets in this week's clustered news."
        : "No sector targets in this week's clustered news.";
    return;
  }
  const articles = (target && target.articles) || [];
  if (!articles.length) {
    els.articleList.classList.add("hidden");
    els.articleList.innerHTML = "";
    els.empty.classList.remove("hidden");
    els.empty.textContent = `No article titles kept for ${target ? target.name : "this name"}.`;
    return;
  }
  els.empty.classList.add("hidden");
  els.articleList.classList.remove("hidden");
  els.articleList.innerHTML = articles
    .map((item) => {
      const score =
        item.relevancy_score == null || Number.isNaN(Number(item.relevancy_score))
          ? "—"
          : String(item.relevancy_score);
      const width = item.relevancy_score == null ? 0 : Math.max(8, Math.min(100, Number(item.relevancy_score) * 10));
      const source = item.source ? `<span>${escapeHtml(item.source)}</span>` : "";
      const date = item.date ? `<span>${escapeHtml(item.date)}</span>` : "";
      const reason = String(item.reasoning || "").trim();
      const reasonHtml = reason
        ? `<p class="story-reason"><span class="reason-label">Reason</span> ${escapeHtml(reason)}</p>`
        : "";
      return `<article class="story-card">
        <a class="story-title" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a>
        ${reasonHtml}
        <p class="story-score">Relevancy score <strong>${escapeHtml(score)}</strong></p>
        <span class="score-bar"><span style="width:${width}%"></span></span>
        <p class="story-meta">${source}${date}</p>
      </article>`;
    })
    .join("");
}

async function boot() {
  if (!isin) {
    els.title.textContent = "No ISIN in the link";
    els.sub.textContent = "Go back to the summary and use Link for relevant news after a run.";
    return;
  }
  els.isin.textContent = isin;
  try {
    const response = await fetch(`/api/clustered/${encodeURIComponent(isin)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Clustered news is not available yet.");
    }
    state.payload = data;
    els.title.textContent = data.fund_name || isin;
    const week =
      data.week_start && data.nav_date
        ? `${data.week_start} → ${data.nav_date}`
        : "Click a name to open the full article titles.";
    els.sub.textContent = data.subtitle ? `${data.subtitle} · ${week}` : week;
    const stocks = targetsOfType("stock");
    const sectors = targetsOfType("sector");
    if (!stocks.length && sectors.length) {
      setType("sector");
    } else {
      setType("stock");
    }
  } catch (error) {
    els.title.textContent = isin;
    els.empty.textContent = error.message;
  }
}

els.stockBtn.addEventListener("click", () => setType("stock"));
els.sectorBtn.addEventListener("click", () => setType("sector"));
boot();
