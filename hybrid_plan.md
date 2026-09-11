# Hybrid Weekly NAV Intelligence — Execution Blueprint

> A complete, systematic workflow to compute weekly NAV impact for a mutual fund's top holdings and surface the **actual news events** that caused the price movements.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Input Specification](#2-input-specification)
3. [Phase 1 — Weekly Market Data & Movement Decomposition](#3-phase-1--weekly-market-data--movement-decomposition)
4. [Phase 2 — Smart News Harvesting](#4-phase-2--smart-news-harvesting)
5. [Phase 3 — Coarse Title-Based Filter](#5-phase-3--coarse-title-based-filter)
6. [Phase 4 — Scrape Survivors](#6-phase-4--scrape-survivors)
7. [Phase 5 — Full-Text Causal Scoring](#7-phase-5--full-text-causal-scoring)
8. [Phase 6 — Event Clustering & Final Selection](#8-phase-6--event-clustering--final-selection)
9. [Phase 7 — Output & Persistence](#9-phase-7--output--persistence)
10. [Complete Data Flow Diagram](#10-complete-data-flow-diagram)
11. [LLM Call Summary](#11-llm-call-summary)
12. [File & Module Mapping](#12-file--module-mapping)

---

## 1. Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        COMPLETE PIPELINE                            │
│                                                                      │
│  INPUT: Fund portfolio rows (name, industry, weight %)               │
│                                                                      │
│  Phase 1 ──► Weekly prices, daily changes, event days,               │
│              sector correlation, top 3 relevant holdings             │
│                          │                                           │
│  Phase 2 ──► RSS harvest (when:7d), deduplicate                      │
│              ~100-200 raw articles per holding                       │
│                          │                                           │
│  Phase 3 ──► Title-only LLM batch scoring                            │
│              ~100-200 → ~30-50 articles per holding                  │
│                          │                                           │
│  Phase 4 ──► Parallel scraping of survivors                          │
│              ~30-50 → ~20-35 scraped articles per holding            │
│                          │                                           │
│  Phase 5 ──► Full-text causal LLM scoring (batched)                  │
│              ~20-35 → ~8-12 high-causal articles per holding         │
│                          │                                           │
│  Phase 6 ──► Event clustering + final verdict LLM call               │
│              ~8-12 → 3-5 distinct events per holding                 │
│                          │                                           │
│  Phase 7 ──► Write result.json + stdout                              │
│                                                                      │
│  OUTPUT: Enriched JSON with causal explanations per holding          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Input Specification

The pipeline starts with the same input the current system uses — a list of fund holdings:

```python
fund_name = "Fund Name"
rows = [
    {"name": "HDFC Bank Ltd",                    "detail": "Financial Services", "percentage": "9.31%"},
    {"name": "ICICI Bank Ltd",                   "detail": "Financial Services", "percentage": "8.19%"},
    {"name": "Reliance Industries Ltd",          "detail": "Energy",             "percentage": "4.2%"},
    {"name": "Axis Bank Ltd",                    "detail": "Financial Services", "percentage": "4.06%"},
    {"name": "Bajaj Finance Ltd",                "detail": "Financial Services", "percentage": "3.52%"},
    {"name": "Larsen & Toubro Ltd",              "detail": "Industrials",        "percentage": "3.47%"},
    {"name": "GE Vernova T&D India Ltd",         "detail": "Industrials",        "percentage": "2.81%"},
    {"name": "Sun Pharmaceuticals Industries Ltd","detail": "Healthcare",        "percentage": "2.8%"},
    {"name": "Infosys Ltd",                      "detail": "Technology",         "percentage": "2.72%"},
    {"name": "Hindustan Unilever Ltd",           "detail": "Consumer Defensive", "percentage": "2.71%"},
    # ...
]
```

**No changes to the input format.** The pipeline is backward-compatible.

---

## 3. Phase 1 — Weekly Market Data & Movement Decomposition

### 3.1 Purpose
Retrieve daily closing prices for the past week, compute weekly and daily changes, identify which days had significant moves, and determine whether each holding's move is company-specific, sector-wide, or market-wide.

### 3.2 Steps

```
Step 1.1 ─── Get top 10 holdings sorted by NAV weight (existing logic)
Step 1.2 ─── For each holding, resolve NSE ticker via Yahoo Finance (existing logic)
Step 1.3 ─── Get last 7 trading sessions' closing prices (modify: period="10d" → use last 7 available)
Step 1.4 ─── Compute weekly % change and daily % changes
Step 1.5 ─── Compute weekly NAV impact per holding
Step 1.6 ─── Compute average signed weekly NAV impact
Step 1.7 ─── Select top 3 holdings by weekly NAV impact (existing logic, adapted)
Step 1.8 ─── Identify event days per holding
Step 1.9 ─── Check sector correlation across holdings
```

### 3.3 Data Structures

**After Step 1.4 — Per-holding price data:**
```json
{
  "name": "HDFC Bank Ltd",
  "industry": "Financial Services",
  "nav_percentage": 9.31,
  "ticker": "HDFCBANK.NS",
  "weekly_prices": [
    {"date": "2026-09-03", "close": 1890.50},
    {"date": "2026-09-04", "close": 1902.15},
    {"date": "2026-09-05", "close": 1895.30},
    {"date": "2026-09-08", "close": 1860.20},
    {"date": "2026-09-09", "close": 1847.10}
  ],
  "daily_changes": [
    {"date": "2026-09-04", "change_pct": 0.62},
    {"date": "2026-09-05", "change_pct": -0.36},
    {"date": "2026-09-08", "change_pct": -1.85},
    {"date": "2026-09-09", "change_pct": -0.70}
  ],
  "weekly_change_pct": -2.30,
  "weekly_nav_impact_pct": -0.214
}
```

### 3.4 Identifying Event Days

An **event day** is a trading day where the absolute daily change exceeds a threshold.

```
Threshold logic:
  - Large-cap (nav_percentage >= 3%): |daily_change| > 1.0%
  - Mid-cap  (nav_percentage >= 1%): |daily_change| > 1.5%
  - Small-cap:                       |daily_change| > 2.5%
```

**Example output:**
```json
{
  "name": "HDFC Bank Ltd",
  "event_days": [
    {"date": "2026-09-08", "change_pct": -1.85, "rank": 1}
  ],
  "move_pattern": "single_event_day"
}
```

**Move patterns:**
| Pattern | Meaning | How many event days |
|---|---|---|
| `single_event_day` | One clear catalyst day | 1 |
| `multi_event_day` | Multiple significant days | 2-3 |
| `gradual_drift` | No single day stands out | 0 |

This pattern determines how Phase 2 builds its queries.

### 3.5 Sector Correlation Check

After computing weekly changes for all top 10 holdings, group by `industry`:

```
Financial Services:
  HDFC Bank:    -2.30%
  ICICI Bank:   -2.10%
  Axis Bank:    -1.90%
  Bajaj Finance: -1.40%
  → Average: -1.93%  →  ALL negative, similar magnitude
  → Verdict: SECTOR-WIDE MOVE

Industrials:
  L&T:          +0.83%
  GE Vernova:   -1.50%
  → Mixed direction
  → Verdict: COMPANY-SPECIFIC (each moved independently)
```

**Decision logic:**
```
For each industry group with 2+ holdings in the top 10:
  1. Compute the average weekly change for the group
  2. Check if all holdings moved in the same direction
  3. Check if the spread (max - min) is small (< 1.5%)

  IF all same direction AND spread < 1.5%:
    → SECTOR-WIDE move
    → Search queries should focus on SECTOR/INDUSTRY news
  ELSE:
    → COMPANY-SPECIFIC moves
    → Search queries should focus on COMPANY-SPECIFIC news

For holdings that are the only one from their industry:
  → Always treat as COMPANY-SPECIFIC
```

**Output of Phase 1 — Per holding:**
```json
{
  "name": "HDFC Bank Ltd",
  "industry": "Financial Services",
  "nav_percentage": 9.31,
  "ticker": "HDFCBANK.NS",
  "weekly_change_pct": -2.30,
  "weekly_nav_impact_pct": -0.214,
  "daily_changes": [
    {"date": "2026-09-04", "change_pct": 0.62},
    {"date": "2026-09-05", "change_pct": -0.36},
    {"date": "2026-09-08", "change_pct": -1.85},
    {"date": "2026-09-09", "change_pct": -0.70}
  ],
  "event_days": [
    {"date": "2026-09-08", "change_pct": -1.85}
  ],
  "move_pattern": "single_event_day",
  "move_scope": "sector_wide"
}
```

---

## 4. Phase 2 — Smart News Harvesting

### 4.1 Purpose
Build targeted Google News RSS queries based on Phase 1 findings, collect all articles from the week, and deduplicate.

### 4.2 Query Strategy Based on Phase 1

The query strategy adapts based on `move_scope` and `move_pattern`:

```
┌──────────────────────┬────────────────────────────────────────────────────┐
│ Scenario             │ Queries to Build                                  │
├──────────────────────┼────────────────────────────────────────────────────┤
│ COMPANY-SPECIFIC     │ Query 1: "{company_name} when:7d"                 │
│ + single_event_day   │ Query 2: "{company_name} when:1d" (around event)  │
│                      │ Query 3: "Indian {industry} when:7d"              │
├──────────────────────┼────────────────────────────────────────────────────┤
│ COMPANY-SPECIFIC     │ Query 1: "{company_name} when:7d"                 │
│ + gradual_drift      │ Query 2: "Indian {industry} when:7d"              │
├──────────────────────┼────────────────────────────────────────────────────┤
│ SECTOR-WIDE          │ Query 1: "{company_name} when:7d"                 │
│ + any pattern        │ Query 2: "Indian {industry} when:7d"              │
│                      │ Query 3: "{industry} sector India when:7d"        │
│                      │ Query 4: "Indian {industry} policy when:7d"       │
├──────────────────────┼────────────────────────────────────────────────────┤
│ MARKET-WIDE          │ Query 1: "{company_name} when:7d"                 │
│ (all sectors down)   │ Query 2: "Indian stock market when:7d"            │
│                      │ Query 3: "Nifty Sensex when:7d"                   │
│                      │ Query 4: "FII selling India when:7d"              │
└──────────────────────┴────────────────────────────────────────────────────┘
```

### 4.3 RSS Fetching

For each query:
1. Build the Google News RSS URL: `https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en`
2. Fetch and parse with `feedparser`.
3. Parse published dates → convert UTC to IST.
4. Keep all articles from the past 7 days.
5. Clean HTML entities from titles.
6. Strip source suffix from titles (e.g., "Title - Economic Times" → "Title").

### 4.4 Deduplication

Articles from multiple queries will overlap. Deduplicate in two rounds:

**Round 1 — Exact title match:**
```python
seen_titles = set()
for article in all_articles:
    if article["title"] not in seen_titles:
        seen_titles.add(article["title"])
        deduped.append(article)
```

**Round 2 — Fuzzy title match (optional but recommended):**
Two articles are duplicates if their titles share > 80% of words:
```
"HDFC Bank Q4 profit rises 9% to Rs 17,616 crore"
"HDFC Bank Q4 net profit jumps 9% to ₹17,616 crore"
→ These are the SAME article from different outlets. Keep the first one.
```

This can be done with simple word-overlap ratio — no external library needed.

### 4.5 Article Metadata at End of Phase 2

Each article after this phase has:
```json
{
  "article_id": 1,
  "title": "RBI tightens provisioning norms for unsecured retail loans",
  "link": "https://news.google.com/rss/articles/CBMi...",
  "source": "Economic Times",
  "published": "2026-09-07T20:30:00+05:30",
  "date": "2026-09-07",
  "query_type": "industry"
}
```

**Expected volume per holding:** ~100-200 raw articles → ~60-120 after deduplication.

---

## 5. Phase 3 — Coarse Title-Based Filter

### 5.1 Purpose
Use a cheap, fast, batched LLM call to score article titles and discard obvious noise. This is the **cost gate** — it prevents irrelevant articles from entering the expensive scraping and full-text scoring phases.

### 5.2 How It Works

Send all ~60-120 deduplicated titles to the LLM in **one batch call** (or 2 calls if token limit is exceeded at ~80+ titles per batch).

### 5.3 LLM Prompt — Title Coarse Filter

```
SYSTEM:
You are a financial news relevance filter. Score each headline on a scale
of 0-10 for how likely it is to describe an event that could impact the
stock price of the target company.

Be GENEROUS — when in doubt, score higher. It is better to keep a
potentially relevant article than to discard an actually important one.

Only give 0-2 to articles that are CLEARLY unrelated (sports, entertainment,
different company with a similar name, generic lifestyle content).

OUTPUT FORMAT:
Return JSON: {"scores": [{"article_id": 1, "title_score": 7}, ...]}

USER:
Target Company: HDFC Bank Ltd
Industry: Financial Services
Weekly Price Change: -2.30%

Score these {N} headlines:
[
  {"article_id": 1, "title": "RBI tightens provisioning norms for unsecured retail loans"},
  {"article_id": 2, "title": "HDFC Bank launches new credit card for millennials"},
  {"article_id": 3, "title": "Best weekend getaways near Mumbai for bank holidays"},
  {"article_id": 4, "title": "Indian banking sector faces NPA headwinds, says RBI report"},
  ...
]

Score all {N} articles. Return exactly {N} scores.
```

### 5.4 Filtering Threshold

```
Keep:  title_score >= 3
Drop:  title_score < 3
```

**Why >= 3 and not >= 5?**
We want to be generous here. The expensive full-text analysis in Phase 5 will do the real filtering. Phase 3's job is only to **kill the obvious noise** — articles about cricket, Bollywood, travel, etc. that accidentally appeared in the RSS feed.

### 5.5 Expected Reduction

- Input: ~60-120 deduplicated articles per holding
- Output: ~30-50 articles per holding (roughly 50-60% survival rate)

### 5.6 LLM Calls for Phase 3

| Per holding | Total (3 holdings) |
|---|---|
| 1-2 calls (batch of ~60-80 titles each) | **3-6 calls** |

---

## 6. Phase 4 — Scrape Survivors

### 6.1 Purpose
Resolve Google News tracking URLs to canonical publisher URLs and extract the full article text for all Phase 3 survivors.

### 6.2 Steps

```
For each surviving article (parallel, 8 workers):
  Step 4.1 ─── Check if link is a Google News wrapper URL
  Step 4.2 ─── If yes: resolve via batchexecute RPC (lib/google_news.py)
  Step 4.3 ─── Fetch the publisher page with TLS impersonation (lib/fetch.py)
  Step 4.4 ─── Extract article text with trafilatura, fallback to BeautifulSoup (lib/extract.py)
  Step 4.5 ─── Store: article text, resolved URL, extraction status
```

### 6.3 Handling Failures

Some scrapes will fail. Expected reasons and handling:

| Failure Type | Expected Rate | Handling |
|---|---|---|
| Google News URL resolution fails | ~5-10% | Mark as `resolve_failed`, exclude from Phase 5 |
| Publisher page returns 403/429 | ~10-15% | Retry with different TLS fingerprint, then exclude |
| Paywall / login required | ~5-10% | `extract_thin` status — keep title but mark text as incomplete |
| JS-rendered page (empty body) | ~5% | Fallback to meta description, mark as thin |

**Expected survival:** ~30-50 articles → ~20-35 successfully scraped articles per holding.

### 6.4 Article Metadata After Phase 4

```json
{
  "article_id": 1,
  "title": "RBI tightens provisioning norms for unsecured retail loans",
  "link": "https://news.google.com/rss/articles/CBMi...",
  "resolved_url": "https://economictimes.com/...",
  "source": "Economic Times",
  "published": "2026-09-07T20:30:00+05:30",
  "date": "2026-09-07",
  "title_score": 7,
  "text": "The Reserve Bank of India on Friday announced...[full article text]...",
  "text_length": 2450,
  "scrape_status": "ok"
}
```

### 6.5 LLM Calls for Phase 4

**Zero.** This phase is purely HTTP + text extraction.

---

## 7. Phase 5 — Full-Text Causal Scoring

### 7.1 Purpose
This is the **heart of the pipeline**. For each scraped article, use the LLM to determine whether this article describes an event that **actually caused or contributed to** the observed weekly price movement. Not just "is this relevant?" but "does this explain the move?"

### 7.2 Batching Strategy

Instead of 1 LLM call per article (expensive), batch **5-8 articles per call**.

For each article, include only the **first ~500 words** of the article text. The lead paragraphs almost always contain the key facts. This keeps the token count manageable.

```
Per holding:
  ~20-35 scraped articles ÷ 6 articles per batch = 3-6 LLM calls
```

### 7.3 LLM Prompt — Full-Text Causal Scoring

```
SYSTEM:
You are a financial analyst investigating WHY a stock's price moved.

For each article below, determine whether it describes an event that CAUSED
or CONTRIBUTED to the observed price movement. This is NOT a relevance
question — many articles can be "relevant" to a company without explaining
its price change.

Score each article on these dimensions:

1. relevancy_score (0-10): How financially material is this to the company?
2. causal_score (0-10): How likely did this event CAUSE the observed price movement?
   - 9-10: Almost certainly the primary catalyst (earnings miss, major contract, regulatory action)
   - 7-8:  Strong contributing factor (analyst downgrade, sector policy change)
   - 5-6:  Plausible but uncertain connection
   - 3-4:  Weak or indirect connection
   - 0-2:  Unrelated to the price movement (even if "relevant" to the company)
3. causal_link: "direct" | "sector" | "macro" | "none"
   - "direct": Company-specific event (earnings, management change, fraud, contract)
   - "sector": Industry-wide event (regulatory change, sector policy, commodity price)
   - "macro":  Market-wide event (RBI rate decision, FII flows, global recession fears)
   - "none":   No meaningful causal connection
4. timing_plausible (true/false): Was this article published BEFORE or ON the
   day of the price movement? An article published AFTER the move cannot have
   caused it.
5. sentiment: "positive" | "negative" — expected stock price direction from this event
6. reasoning: 1-2 sentence explanation of the causal connection or lack thereof.

OUTPUT FORMAT:
Return JSON:
{
  "scores": [
    {
      "article_id": 1,
      "relevancy_score": 8,
      "causal_score": 9,
      "causal_link": "direct",
      "timing_plausible": true,
      "sentiment": "negative",
      "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost
                    of unsecured lending. Published evening before the -1.85% drop."
    },
    ...
  ]
}

USER:
TARGET STOCK: HDFC Bank Ltd (HDFCBANK.NS)
INDUSTRY: Financial Services
WEEKLY CHANGE: -2.30% (2026-09-03 to 2026-09-09)

DAILY PRICE BREAKDOWN:
  2026-09-04 (Thu): +0.62%
  2026-09-05 (Fri): -0.36%
  2026-09-08 (Mon): -1.85%  ← BIGGEST MOVE
  2026-09-09 (Tue): -0.70%

EVENT DAYS: 2026-09-08 (-1.85%)

Score these {N} articles:

--- Article 1 (published: 2026-09-07 20:30 IST) ---
Title: "RBI tightens provisioning norms for unsecured retail loans"
Text (first 500 words): "The Reserve Bank of India on Friday announced..."

--- Article 2 (published: 2026-09-08 09:15 IST) ---
Title: "HDFC Bank launches new credit card for millennials"
Text (first 500 words): "HDFC Bank on Monday unveiled a new credit card..."

--- Article 3 (published: 2026-09-06 14:00 IST) ---
Title: "Indian banking sector faces NPA headwinds, says RBI report"
Text (first 500 words): "A report released by the Reserve Bank..."

[...up to 6-8 articles per batch...]

Score all {N} articles.
```

### 7.4 What Makes This Different From Current Scoring

| Dimension | Current System | Phase 5 |
|---|---|---|
| **Input** | Title only | Full article text (first 500 words) |
| **Context** | None | Weekly price movement + daily breakdown + event days |
| **Question** | "Is this relevant?" | "Did this CAUSE the move?" |
| **Timing** | Not checked | Explicit timing plausibility check |
| **Output** | relevancy_score + sentiment | relevancy_score + **causal_score** + causal_link + timing + sentiment + **reasoning** |

### 7.5 Filtering After Phase 5

From the scored articles, keep those with:
```
causal_score >= 5  AND  timing_plausible == true
```

Sort by `causal_score` descending. Take the top **~8-12** per holding.

### 7.6 Article Metadata After Phase 5

```json
{
  "article_id": 1,
  "title": "RBI tightens provisioning norms for unsecured retail loans",
  "resolved_url": "https://economictimes.com/...",
  "source": "Economic Times",
  "published": "2026-09-07T20:30:00+05:30",
  "date": "2026-09-07",
  "text": "[full scraped article text]",
  "title_score": 7,
  "relevancy_score": 8,
  "causal_score": 9,
  "causal_link": "direct",
  "timing_plausible": true,
  "sentiment": "negative",
  "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost of unsecured lending. Published evening before the -1.85% drop on Monday."
}
```

### 7.7 LLM Calls for Phase 5

| Per holding | Total (3 holdings) |
|---|---|
| 3-6 calls (batches of 5-8 articles) | **9-18 calls** |

---

## 8. Phase 6 — Event Clustering & Final Selection

### 8.1 Purpose
The top ~8-12 articles from Phase 5 may contain **multiple articles about the same event** (e.g., 4 articles about the same RBI announcement). This phase groups them by underlying event and selects the best representative article per event, then ranks events by explanatory power.

### 8.2 How It Works

One LLM call per holding. Send the top ~8-12 articles' titles + reasoning to the LLM and ask it to:
1. Group articles that describe the **same underlying event**.
2. Pick the **most informative article** from each group.
3. Rank the events by **causal_score** (how well they explain the price movement).
4. Assign an overall **explanation_confidence** for the holding.

### 8.3 LLM Prompt — Event Clustering & Final Verdict

```
SYSTEM:
You are a senior financial analyst producing a final report on why a stock
moved this week. You have a list of candidate news articles, each already
scored for causal relevance.

Your job:
1. GROUP articles that describe the SAME underlying event (even if from
   different publishers or with different angles). Give each group an
   event_label (short descriptive name).
2. For each group, pick the article_id of the BEST article (most detailed,
   most informative, clearest explanation).
3. RANK the event groups by how well they explain the observed price movement.
4. Assign an overall explanation_confidence:
   - "high":   At least one event with causal_score >= 8 clearly explains the move
   - "medium": Events with causal_score 5-7 provide plausible but not certain explanation
   - "low":    No event strongly explains the move — it may be flow/technical driven

OUTPUT FORMAT:
Return JSON:
{
  "events": [
    {
      "event_rank": 1,
      "event_label": "RBI tightens unsecured loan provisioning norms",
      "best_article_id": 1,
      "article_ids_in_group": [1, 4, 7],
      "combined_causal_score": 9,
      "event_summary": "RBI announced new provisioning requirements for unsecured
                        retail loans, directly impacting HDFC Bank's lending margins."
    },
    {
      "event_rank": 2,
      "event_label": "Q4 FY26 results — profit in line but NIM compression",
      "best_article_id": 3,
      "article_ids_in_group": [3, 8],
      "combined_causal_score": 7,
      "event_summary": "HDFC Bank Q4 profit was in line but net interest margins
                        compressed 3bp QoQ, signaling pressure on lending spreads."
    }
  ],
  "explanation_confidence": "high",
  "confidence_reasoning": "The RBI provisioning norm change (causal_score 9) directly
                           explains the -1.85% drop on Monday, as the announcement
                           was made Friday evening."
}

USER:
STOCK: HDFC Bank Ltd (HDFCBANK.NS)
WEEKLY CHANGE: -2.30%
EVENT DAYS: 2026-09-08 (-1.85%)

Here are the top-scoring articles to cluster and rank:

Article 1 (causal_score=9, published 2026-09-07):
  Title: "RBI tightens provisioning norms for unsecured retail loans"
  Reasoning: "RBI provisioning norms directly increase HDFC Bank's cost..."

Article 3 (causal_score=7, published 2026-09-08):
  Title: "HDFC Bank Q4 profit in line; NIMs compress 3bp QoQ"
  Reasoning: "Margin compression signals challenges in lending spreads..."

Article 4 (causal_score=8, published 2026-09-07):
  Title: "New RBI norms to hit bank margins on personal loans"
  Reasoning: "Same RBI announcement as Article 1, different publisher..."

[...up to 8-12 articles...]

Group by event, pick the best article per event, rank events, and assign confidence.
```

### 8.4 Final Selection Logic

From the LLM's response:
1. Take the top **3-5 events** (by `event_rank`).
2. For each event, retrieve the **full article data** (including scraped text) for the `best_article_id`.
3. Attach these as the holding's `relevant_news`.
4. Attach the `explanation_confidence` and `confidence_reasoning` to the holding.

### 8.5 Handling Low-Confidence Cases

If `explanation_confidence` is `"low"`:
```json
{
  "name": "Bajaj Finance Ltd",
  "weekly_change_pct": -1.40,
  "explanation_confidence": "low",
  "confidence_reasoning": "No single news event found with causal score above 6.
    The -1.4% decline appears to align with broader financial services sector
    weakness rather than a company-specific catalyst.",
  "relevant_news": []
}
```

This is **honest output** — better than forcing 3 weak articles that don't actually explain anything.

### 8.6 LLM Calls for Phase 6

| Per holding | Total (3 holdings) |
|---|---|
| 1 call | **3 calls** |

---

## 9. Phase 7 — Output & Persistence

### 9.1 Final Output JSON Structure Per Holding

```json
{
  "name": "HDFC Bank Ltd",
  "industry": "Financial Services",
  "nav_percentage": 9.31,
  "ticker": "HDFCBANK.NS",
  "weekly_change_pct": -2.30,
  "weekly_nav_impact_pct": -0.214,
  "daily_changes": [
    {"date": "2026-09-04", "change_pct": 0.62},
    {"date": "2026-09-05", "change_pct": -0.36},
    {"date": "2026-09-08", "change_pct": -1.85},
    {"date": "2026-09-09", "change_pct": -0.70}
  ],
  "event_days": ["2026-09-08"],
  "move_scope": "sector_wide",
  "explanation_confidence": "high",
  "confidence_reasoning": "The RBI provisioning norm change clearly explains the -1.85% drop on Monday.",
  "relevant_news": [
    {
      "event_rank": 1,
      "event_label": "RBI tightens unsecured loan provisioning norms",
      "event_summary": "RBI announced new provisioning requirements...",
      "title": "RBI tightens provisioning norms for unsecured retail loans",
      "source": "Economic Times",
      "published": "2026-09-07T20:30:00+05:30",
      "link": "https://news.google.com/rss/articles/CBMi...",
      "resolved_url": "https://economictimes.com/...",
      "text": "[full scraped article text]",
      "relevancy_score": 8,
      "causal_score": 9,
      "causal_link": "direct",
      "timing_plausible": true,
      "sentiment": "negative",
      "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost..."
    },
    {
      "event_rank": 2,
      "event_label": "Q4 results — NIM compression",
      "...": "..."
    }
  ]
}
```

### 9.2 Persistence

```
Step 7.1 ─── Save individual scraped .json and .html files to out/ folder
Step 7.2 ─── Save complete enriched JSON to output-scrapper/result.json
Step 7.3 ─── Print final JSON to stdout
```

### 9.3 Sorting

Sort the final holdings list:
- If weekly average NAV impact is **negative**: sort by `weekly_nav_impact_pct` ascending (most negative first)
- If weekly average NAV impact is **positive**: sort by `weekly_nav_impact_pct` descending (most positive first)

---

## 10. Complete Data Flow Diagram

```
INPUT: Fund rows (name, detail, percentage)
  │
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 1: Weekly Market Data & Movement Decomposition        ║
║                                                               ║
║  get_top_10_holdings(rows)                                    ║
║    └─► find_ticker(name) ──► yf.Search(".NS")                ║
║    └─► get_weekly_prices(ticker) ──► yf.Ticker.history(10d)  ║
║    └─► compute_daily_changes(prices)                          ║
║    └─► compute_weekly_nav_impact(weight, weekly_change)       ║
║    └─► compute_average_signed_weekly_nav_impact(holdings)     ║
║    └─► get_top_3_nav_impact_holdings(fund_result)             ║
║    └─► identify_event_days(daily_changes, threshold)          ║
║    └─► check_sector_correlation(all_holdings)                 ║
║                                                               ║
║  Output: 3 holdings with weekly data + event days + scope     ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  3 holdings, each with: weekly_change, daily_changes,
  │  event_days, move_scope
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 2: Smart News Harvesting (per holding)                ║
║                                                               ║
║  build_queries(holding) ──► based on move_scope & pattern     ║
║    └─► build_news_url_with_date(query, days_back=7)          ║
║    └─► requests.get(rss_url) ──► feedparser.parse()          ║
║    └─► filter to past 7 days                                 ║
║    └─► clean titles, strip source suffix                     ║
║    └─► deduplicate (exact + fuzzy title match)               ║
║                                                               ║
║  Output: ~60-120 deduplicated articles per holding            ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  ~60-120 articles per holding (title, link, source, date)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 3: Coarse Title-Based Filter (per holding)            ║
║                                                               ║
║  Batch all titles into 1-2 LLM calls                         ║
║    └─► Score 0-10 on title alone                             ║
║    └─► Keep title_score >= 3                                 ║
║    └─► Drop obvious noise (sports, entertainment, unrelated) ║
║                                                               ║
║  Output: ~30-50 articles per holding                          ║
║  LLM Calls: 1-2 per holding                                  ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  ~30-50 articles per holding (title, link, source, date, title_score)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 4: Scrape Survivors (per holding, parallel)           ║
║                                                               ║
║  For each article (8 workers):                                ║
║    └─► resolve_google_news_url(link)                         ║
║    └─► fetch_url(resolved_url, TLS impersonation)            ║
║    └─► extract_article(html, url)                            ║
║    └─► Store text, resolved_url, scrape_status               ║
║                                                               ║
║  Output: ~20-35 scraped articles per holding                  ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  ~20-35 articles per holding (+ full text + resolved_url)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 5: Full-Text Causal Scoring (per holding, batched)    ║
║                                                               ║
║  Batch 5-8 articles per LLM call                             ║
║  Each article: title + first 500 words of text               ║
║  Context: weekly_change + daily_changes + event_days          ║
║    └─► Score: relevancy, causal, causal_link, timing,        ║
║              sentiment, reasoning                             ║
║    └─► Keep causal_score >= 5 AND timing_plausible == true   ║
║    └─► Sort by causal_score desc, take top ~8-12             ║
║                                                               ║
║  Output: ~8-12 causally-scored articles per holding           ║
║  LLM Calls: 3-6 per holding                                  ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  ~8-12 articles per holding (+ causal_score + reasoning)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 6: Event Clustering & Final Selection (per holding)   ║
║                                                               ║
║  1 LLM call with all ~8-12 article titles + reasoning         ║
║    └─► Group by underlying event                             ║
║    └─► Pick best article per event group                     ║
║    └─► Rank events by explanatory power                      ║
║    └─► Select top 3-5 distinct events                        ║
║    └─► Assign explanation_confidence (high/medium/low)       ║
║                                                               ║
║  Output: 3-5 events with best article each + confidence       ║
║  LLM Calls: 1 per holding                                    ║
╚═══════════════════════════════════════════════════════════════╝
  │
  │  3-5 events per holding (with full article text + reasoning)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 7: Output & Persistence                               ║
║                                                               ║
║  sort_by_nav_impact(holdings)                                ║
║  Save scraped .json/.html to out/                            ║
║  Save complete result to output-scrapper/result.json          ║
║  Print JSON to stdout                                        ║
║                                                               ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 11. LLM Call Summary

### Per Holding

| Phase | Purpose | Calls | Input Tokens (approx) | Output Tokens (approx) |
|---|---|---|---|---|
| Phase 3 | Title coarse filter | 1-2 | ~3-5K (80-120 titles) | ~1-2K (scores) |
| Phase 5 | Full-text causal scoring | 3-6 | ~6-12K per call (price context + 5-8 articles × 500 words) | ~1-2K per call |
| Phase 6 | Event clustering + final verdict | 1 | ~3-4K (8-12 titles + reasoning) | ~1-2K |
| **Subtotal** | | **5-9** | **~30-60K** | **~6-12K** |

### Total for 3 Holdings

| Metric | Minimum | Typical | Maximum |
|---|---|---|---|
| **LLM Calls** | 15 | 21 | 27 |
| **Input Tokens** | ~90K | ~135K | ~180K |
| **Output Tokens** | ~18K | ~27K | ~36K |
| **Total Tokens** | ~108K | ~162K | ~216K |
| **Estimated Time** | ~1.5 min | ~2.5 min | ~4 min |

### Comparison to Current System

| Metric | Current System | Weekly Hybrid | Increase |
|---|---|---|---|
| LLM Calls | ~6 | ~21 | ~3.5x |
| Total Tokens | ~15-20K | ~160K | ~8-10x |
| Scrapes | 3-9 articles | ~90-150 articles | ~15x |
| Time (estimated) | ~30-60s | ~2-4 min | ~4x |
| Accuracy of explanation | Title-based, often wrong | Full-text + causal, much more reliable | Significant |

---

## 12. File & Module Mapping

### Existing Files That Need Modification

| File | What Changes | Impact |
|---|---|---|
| `demo.py` | `get_last_two_closing_prices()` → `get_weekly_prices()` returning 5-7 days of prices. Add `compute_daily_changes()`. Adapt `get_fund_top_10_prices()` to compute weekly NAV impact. | Medium — core function signature changes |
| `stocks_for_news.py` | No change in logic — same `get_top_3_nav_impact_holdings()` but now operates on weekly data. | None / Minimal |
| `app.py` | `fetch_news_for_dates()` → new function `fetch_news_for_week()` with `when:7d` query support, adaptive query strategy based on `move_scope`, fuzzy deduplication. | Medium — new function, query strategy |
| `news_relevancy_agent.py` | Add new prompt for title coarse filter (Phase 3). Add new prompt + function for full-text causal scoring (Phase 5). Add new prompt + function for event clustering (Phase 6). | Heavy — 2-3 new functions + prompts |
| `main.py` | Restructure `main()` to follow 7-phase flow. Add event day identification. Add sector correlation check. Add confidence output. | Heavy — orchestration rewrite |
| `web_scrapper.py` | No functional changes — `scrape_one()` and `_write_record()` work as-is. May increase parallel workers for higher volume. | None |
| `lib/*` | No changes — `fetch.py`, `extract.py`, `google_news.py` all work as-is. | None |

### New Functions to Create

| Function | Location | Purpose |
|---|---|---|
| `get_weekly_prices(ticker)` | `demo.py` | Return last 5-7 trading day closes |
| `compute_daily_changes(prices)` | `demo.py` | Compute day-over-day % changes |
| `identify_event_days(daily_changes, threshold)` | `main.py` or new file | Find days with large |change| |
| `check_sector_correlation(holdings)` | `main.py` or new file | Determine company/sector/market scope |
| `build_adaptive_queries(holding)` | `app.py` | Build RSS queries based on move_scope |
| `fetch_news_for_week(holding)` | `app.py` | Harvest + deduplicate week's news |
| `score_titles_coarse(holding, articles)` | `news_relevancy_agent.py` | Phase 3 batch title scoring |
| `score_articles_causal(holding, articles, price_context)` | `news_relevancy_agent.py` | Phase 5 full-text causal scoring |
| `cluster_events_and_select(holding, top_articles)` | `news_relevancy_agent.py` | Phase 6 event clustering |

### New File (Optional)

| File | Purpose |
|---|---|
| `weekly_analysis.py` | Could house Phase 1 logic (event days, sector correlation) to keep `demo.py` and `main.py` cleaner |
