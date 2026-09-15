# Agent briefing — read this before any change

This is a **Python pipeline** that explains Indian mutual-fund NAV moves using NSE prices (Yahoo Finance), Google News RSS, Groq title scoring, and publisher-page scraping.

**Implemented today:** Phase 2 of the weekly pipeline is live in `python main.py`: load `data/*.json`, official NAV week, Yahoo weekly prices for ≥2% Domestic Equities + REITs **and** smaller peers in ≥3% domestic sectors, then classify **sector-wide vs stock-specific** news targets plus **drags and offsets**. News, scrape, and Groq are **not** wired yet.

**Live input is `data/`.** Hardcoded sample rows are no longer used by `main.py`.

---

## Before you edit

1. Confirm whether the request is about **current code** or a **planned** weekly / factor-graph system.
2. Prefer small, linear changes in existing modules. Do not add frameworks, extra abstraction layers, or new packages unless the task requires them.
3. Do not commit secrets. Never put `.env` or API keys in git.
4. Do not scrape more articles than selected `relevant_news` unless the task explicitly expands the pipeline.
5. `yfinance` is imported in `demo.py` but is **missing from `requirements.txt`**. If you touch deps, add it.

---

## Implemented pipeline (`python main.py`)

**Live input is `data/`.** `main.py` loads holdings, NAV, and sectors from JSON.

`python main.py` (Phase 2): load JSON → official NAV week → price ≥2% names plus peers in ≥3% domestic sectors → weekly NAV impact → **sector-wide vs stock-specific news targets** (no RSS yet) → write `output-scrapper/result.json`. **No news, scrape, or Groq in this phase.**

```
main.py
  fund_data.load_fund_bundle
  demo.get_fund_weekly_prices
  stocks_for_news.build_sector_moves / select_news_targets / select_offsets
```

Formulas (live):

- ΔP = (P_t-1 − P_t-2) / P_t-2 × 100
- NAV impact (%) = W × ΔP / 100, rounded to 3 decimals
- Average signed NAV impact = mean of `nav_impact_percentage` on holdings that resolved ticker + prices

Directional rules:

- Average impact **< 0**: holdings with negative impact, most negative first; news sentiment **negative**
- Average impact **> 0**: holdings with positive impact, most positive first; news sentiment **positive**
- Average impact **== 0**: empty list
- Relevancy filter is **strict greater than 5**, not ≥ 5

News dates are **calendar days in IST**, not trading sessions. Price “t-1 / t-2” can disagree with news T-1 / T-2 around weekends and holidays.

---

## Module map

| Path | Role |
|---|---|
| `main.py` | Orchestrator: weekly prices + news-target routing (no news fetch yet) |
| `fund_data.py` | Load holdings / NAV / sectors, official week, ≥2% rows and price universe |
| `demo.py` | Ticker search, last two closes (legacy), weekly prices, NAV math |
| `stocks_for_news.py` | Sector vs stock news targets, drags/offsets (legacy top-3 kept) |
| `app.py` | Google News RSS (`when:3d`), IST filter, title scoring hook; also interactive CLI |
| `news_relevancy_agent.py` | Groq title-only JSON scoring |
| `web_scrapper.py` | `scrape_one`, `_write_record`, CLI (`--preset india`) |
| `lib/fetch.py` | `curl_cffi` TLS impersonation + retries |
| `lib/google_news.py` | Google News `batchexecute` publisher URL resolve |
| `lib/extract.py` | trafilatura, BeautifulSoup if text < 120 chars |
| `data/fund_holding_data.json` | Real fund holdings (not wired into `main.py` yet) |
| `data/fund_nav_history.json` | Official fund NAV series (newest first; not wired yet) |
| `data/fund_sector.json` | Fund sector weights (not wired yet) |
| `output-scrapper/result.json` | Full pipeline output |
| `out/` | Per-article scrape dumps (gitignored html/json) |

---

## Real fund data (`data/`) — added, unused by code

These files are the intended production input. Treat them as source of truth for holdings/NAV/sectors. Map them into the existing `{name, detail, percentage}` shape rather than rewriting the pipeline unless asked.

### `data/fund_holding_data.json`

Array of **116** positions. Weights sum to **100**. Fields:

```json
{
  "instrument_name": "HDFC Bank Limited",
  "percentage": 7.6347068753731,
  "industry": "Banks",
  "asset_type": "Domestic Equities",
  "rating": "Equity",
  "market_value": 1125390.2,
  "fincode": 100180,
  "isin": null
}
```

| Fact | Detail |
|---|---|
| Asset mix | 59 Domestic Equities, 32 CD, 12 CP, 4 Overseas Equities, 3 REITs/InvITs, 3 T-Bills, 2 cash/net assets, 1 MF unit |
| Top 3 equity names | HDFC Bank ~7.63% (Banks), ICICI Bank ~5.67% (Banks), Power Grid ~5.58% (Power) |
| `industry` | 31 values; **can be `null`** (cash / net receivables) |
| `isin` | Almost always `null`; use `fincode` if you need an id |
| `percentage` | Float, not `"9.31%"` string |
| Name field | `instrument_name`, not `name` |

When wiring into `demo.get_top_10_holdings`, **filter to `asset_type == "Domestic Equities"`** (or `rating == "Equity"`) unless the user wants debt/cash in Yahoo ticker search. Cash, CDs, and “Net Receivables / (Payables)” will break `find_ticker`.

Field map into today’s pipeline:

- `instrument_name` → `name`
- `industry` → `detail`
- `percentage` → string with `%` **or** change parsers to accept floats

Industry labels here (`Banks`, `IT - Software`) differ from the hardcoded sample (`Financial Services`, `Technology`). RSS queries use `Indian {industry}`.

### `data/fund_nav_history.json`

**8** rows, **newest first**:

- Latest: `2026-09-11` NAV `89.5712`
- Previous: `2026-09-10` NAV `89.4845` → **+0.097%** 1-day NAV change
- Oldest: `2026-09-02` NAV `90.5023`
- Dates skip weekend 5–6 Sep (trading calendar)

Schema: `{ "nav_date": "YYYY-MM-DD", "nav_value": float }`.

This is the **actual fund NAV**, not the approximate sum of holding impacts. Use it to compare explained vs unexplained NAV move. Do not assume it matches Yahoo-based `average_signed_nav_impact`.

### `data/fund_sector.json`

**30** `{ "sector", "percentage" }` rows. Weights sum to **~90.29**, not 100 — remainder is debt/cash/overseas/other not in this equity-style breakdown.

Largest: Banks 20.91, It - Software 10.32, Realty 6.81, Automobiles 6.71.

Some names have a `##` suffix (e.g. `Computer Software: Programming, Data Processing ##`). Sector strings do **not** always equal holding `industry` (casing and aliases differ).

---

## Input / output (live)

Holding row **currently used** in `main.py` (sample, not `data/`):

```json
{"name": "HDFC Bank Ltd", "detail": "Financial Services", "percentage": "9.31%"}
```

`detail` becomes `industry`. Tickers are **not hardcoded**; first Yahoo quote ending in `.NS` wins.

Final holding object: `name`, `industry`, `nav_percentage`, `ticker`, `change_percentage`, `nav_impact_percentage`, `relevant_news[]`.

Each news item after scrape: `title`, `description`, `link`, `source`, `published`, `date`, `relevancy_score`, `sentiment`, plus `text` and optional `resolved_url`. Failed scrapes set `text` to `""`.

---

## Environment and run

`.env` (gitignored):

```
GROQ_API_KEY=...
GROQ_MODEL=openai/gpt-oss-120b
```

Defaults in code: model `openai/gpt-oss-120b`, temperature `0.1`, `max_tokens=3000`, JSON mode then text fallback.

```
pip install -r requirements.txt
python main.py
python app.py                 # interactive instrument lookup (SAMPLE_DATA)
python demo.py                # prices + top 3 only
python web_scrapper.py --preset india --limit 5
```

`main.py` redirects stdout around `demo.py` because demo prints search/progress.

Deps in `requirements.txt`: requests, groq, langchain-groq, langchain-core, pydantic, python-dotenv, feedparser, curl_cffi, trafilatura, beautifulsoup4, lxml. LangChain packages are listed but **not used** in current Python. `yfinance` is used and not listed.

---

## Plans vs code (do not confuse)

| Document | Status |
|---|---|
| `PROJECT_DOCUMENTATION.md` | Describes **current** system (some extra detail vs code) |
| `plan.md` | Research: weekly news, why title-only fails at scale |
| `hybrid_plan.md` | 7-phase weekly pipeline (weekly prices, event days, causal LLM, clustering) — **not implemented** |
| `less_llm_call.md` | Same weekly pipeline, keyword filter + code clustering, 6–9 Groq calls — **not implemented** |
| `direct_indirect_relationship.md` | Future factor-graph / attribution engine — **not implemented** |

If asked to “go weekly” or “reduce LLM calls,” start from `less_llm_call.md` unless the user says otherwise. Do not silently rewrite `main.py` into that design.

---

## Invariants

- Keep ticker resolution dynamic (Yahoo `.NS`); no company→ticker dict unless requested.
- Keep scraping in `lib/` + `web_scrapper.scrape_one`; do not invent a second fetch stack.
- Groq sees **titles only** today; full-text LLM scoring is planned, not live.
- `fetch_news_for_dates` already calls the LLM; `main.fetch_and_score_news` must not score again.
- `app.py` `SAMPLE_DATA` and `data/fund_holding_data.json` use `instrument_name`; live `main.py` still uses `name` / `detail`.
- Pipeline scrape in `main.py` is sequential; CLI scraper can use `--workers`.
- Output dirs: `out/` and `output-scrapper/`. Do not relocate without updating both write paths and docs.
- Do not ignore `data/`. Next input work should load those JSON files, not grow the hardcoded list.
- Do not send non-equity names (CDs, cash, net receivables) through Yahoo ticker search.

---

## Known gaps

- Holdings are loaded from `data/fund_holding_data.json` (Domestic Equities + REITs ≥ 2%). News/scrape/Groq not wired yet.
- `fund_nav_history.json` and `fund_sector.json` are unused (needed for actual-vs-expected NAV and sector-aware news).
- Holdings that fail ticker/price lookup are dropped and excluded from the average.
- Title scoring can mismatch full-article meaning (seen in sample `result.json`).
- RSS uses `requests`; page fetch uses `curl_cffi`.
- Google News resolve depends on `data-n-a-sg` / `data-n-a-ts` and `garturlres`.
