# Optimized Weekly NAV Intelligence — Minimum LLM Calls

> The same hybrid strategy from `hybrid_plan.md`, re-engineered to reduce LLM calls from **15-27 down to 6-9** without losing any data quality. Every phase is documented with the exact changes and rationale.

---

## Table of Contents

1. [What Changed From hybrid_plan.md](#1-what-changed-from-hybrid_planmd)
2. [Optimized Pipeline Overview](#2-optimized-pipeline-overview)
3. [Phase 1 — Weekly Market Data & Movement Decomposition (Unchanged)](#3-phase-1--weekly-market-data--movement-decomposition-unchanged)
4. [Phase 2 — Smart News Harvesting (Unchanged)](#4-phase-2--smart-news-harvesting-unchanged)
5. [Phase 3 — Keyword-Based Coarse Filter (CHANGED: LLM → Code)](#5-phase-3--keyword-based-coarse-filter-changed-llm--code)
6. [Phase 4 — Scrape Survivors (Unchanged)](#6-phase-4--scrape-survivors-unchanged)
7. [Phase 5 — Full-Text Causal Scoring + Event Tagging (CHANGED: Merged Phase 6)](#7-phase-5--full-text-causal-scoring--event-tagging-changed-merged-phase-6)
8. [Phase 6 — Programmatic Event Grouping & Selection (CHANGED: LLM → Code)](#8-phase-6--programmatic-event-grouping--selection-changed-llm--code)
9. [Phase 7 — Output & Persistence (Unchanged)](#9-phase-7--output--persistence-unchanged)
10. [Complete Optimized Data Flow](#10-complete-optimized-data-flow)
11. [LLM Call Comparison](#11-llm-call-comparison)
12. [File & Module Mapping (Updated)](#12-file--module-mapping-updated)

---

## 1. What Changed From hybrid_plan.md

Three targeted optimizations that cut LLM calls by ~65%:

| Phase | hybrid_plan.md | This Plan | Savings |
|---|---|---|---|
| **Phase 3** (coarse filter) | LLM batch scores titles (1-2 calls/holding) | **Keyword-based code filter** — no LLM needed | **3-6 calls eliminated** |
| **Phase 5** (causal scoring) | Batches of 5-8 articles (3-6 calls/holding) | **Batches of 10-12 articles** (2-3 calls/holding) | **3-9 calls reduced** |
| **Phase 6** (event clustering) | LLM clusters events (1 call/holding) | **Programmatic grouping** using Phase 5's `event_label` — no LLM needed | **3 calls eliminated** |
| **Total** | **15-27 calls** | **6-9 calls** | **~60-65% reduction** |

### Why No Data Quality Is Lost

- **Phase 3's job was coarse**: Kill articles about sports, entertainment, travel. Keywords do this just as well as an LLM with a threshold of ≥3. The 5% edge cases Phase 3 might miss will score low in Phase 5 anyway.
- **Phase 5 is where all intelligence lives**: The causal reasoning LLM call is unchanged in quality — only the batch size increased from 5-8 to 10-12, which is well within model capacity (~9K input tokens per batch).
- **Phase 6 was redundant with Phase 5**: If Phase 5 already assigns an `event_label` to each article (1 extra JSON field, ~zero extra tokens), then grouping by event is a trivial code operation — sort, group, pick highest score per group.

---

## 2. Optimized Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                    OPTIMIZED PIPELINE (6-9 LLM calls)               │
│                                                                      │
│  INPUT: Fund portfolio rows (name, industry, weight %)               │
│                                                                      │
│  Phase 1 ──► Weekly prices, daily changes, event days,               │
│              sector correlation, top 3 relevant holdings             │
│              [0 LLM calls]                                           │
│                          │                                           │
│  Phase 2 ──► RSS harvest (when:7d), deduplicate                      │
│              ~60-120 articles per holding                            │
│              [0 LLM calls]                                           │
│                          │                                           │
│  Phase 3 ──► KEYWORD-BASED filter (no LLM)                          │
│              ~60-120 → ~30-50 articles per holding                   │
│              [0 LLM calls]  ← was 1-2 per holding                   │
│                          │                                           │
│  Phase 4 ──► Parallel scraping of survivors                          │
│              ~30-50 → ~20-35 scraped articles per holding            │
│              [0 LLM calls]                                           │
│                          │                                           │
│  Phase 5 ──► Full-text causal scoring + EVENT TAGGING                │
│              Batches of 10-12 articles                               │
│              ~20-35 → ~8-12 high-causal articles per holding         │
│              [2-3 LLM calls per holding]  ← was 3-6                  │
│                          │                                           │
│  Phase 6 ──► PROGRAMMATIC event grouping (no LLM)                    │
│              ~8-12 → 3-5 distinct events per holding                 │
│              [0 LLM calls]  ← was 1 per holding                     │
│                          │                                           │
│  Phase 7 ──► Write result.json + stdout                              │
│              [0 LLM calls]                                           │
│                                                                      │
│  TOTAL LLM CALLS: 6-9 (all in Phase 5)                              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Phase 1 — Weekly Market Data & Movement Decomposition (Unchanged)

> **Identical to hybrid_plan.md Phase 1. No changes.**

### Steps

```
Step 1.1 ─── Get top 10 holdings sorted by NAV weight
Step 1.2 ─── For each holding, resolve NSE ticker via Yahoo Finance
Step 1.3 ─── Get last 7 trading sessions' closing prices
Step 1.4 ─── Compute weekly % change and daily % changes
Step 1.5 ─── Compute weekly NAV impact per holding
Step 1.6 ─── Compute average signed weekly NAV impact
Step 1.7 ─── Select top 3 holdings by weekly NAV impact
Step 1.8 ─── Identify event days per holding
Step 1.9 ─── Check sector correlation across holdings
```

### Output Per Holding

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

### Event Day Thresholds

```
Large-cap  (nav_percentage >= 3%):  |daily_change| > 1.0%
Mid-cap    (nav_percentage >= 1%):  |daily_change| > 1.5%
Small-cap:                          |daily_change| > 2.5%
```

### Sector Correlation Logic

```
For each industry group with 2+ holdings in top 10:
  IF all moved in same direction AND spread < 1.5%:
    → SECTOR-WIDE (search sector/industry news)
  ELSE:
    → COMPANY-SPECIFIC (search company-specific news)
```

**LLM Calls: 0**

---

## 4. Phase 2 — Smart News Harvesting (Unchanged)

> **Identical to hybrid_plan.md Phase 2. No changes.**

### Query Strategy Based on Phase 1

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
└──────────────────────┴────────────────────────────────────────────────────┘
```

### Deduplication

**Round 1 — Exact title match.**
**Round 2 — Fuzzy title match** (>80% word overlap → duplicate).

**Expected output: ~60-120 deduplicated articles per holding.**

**LLM Calls: 0**

---

## 5. Phase 3 — Keyword-Based Coarse Filter (CHANGED: LLM → Code)

> **CHANGED from hybrid_plan.md**: Replaced the LLM title-scoring call with a zero-cost keyword-based filter.

### 5.1 Why This Works Without an LLM

Phase 3's job in the original plan was to **kill obvious noise** — articles about cricket, Bollywood, travel, food, etc. that accidentally appeared in the RSS feed. The threshold was generous (≥3 out of 10), meaning only truly unrelated articles were dropped.

A keyword check does this just as well:
- If a title mentions the company name, it's relevant.
- If a title mentions financial terms, it's relevant.
- If a title is about sports or entertainment, it's noise.

The ~5% of edge cases this might miss (articles with extremely vague titles that an LLM would score 3-4) will score low in Phase 5 anyway and get filtered out there.

### 5.2 Keyword Filter Logic

```python
# Keywords that signal financial relevance
FINANCIAL_KEYWORDS = {
    # Market terms
    "stock", "share", "shares", "equity", "market", "nifty", "sensex",
    "bse", "nse", "trading", "rally", "crash", "bull", "bear",
    
    # Company actions
    "profit", "loss", "revenue", "earnings", "quarterly", "q1", "q2",
    "q3", "q4", "results", "dividend", "buyback", "bonus", "split",
    
    # Corporate events
    "merger", "acquisition", "takeover", "ipo", "listing", "delisting",
    "board", "agm", "ceo", "cfo", "chairman", "director", "resign",
    "appoint", "management",
    
    # Regulatory
    "rbi", "sebi", "regulatory", "regulation", "compliance", "penalty",
    "fine", "npa", "provisioning", "policy", "reform",
    
    # Financial instruments
    "bond", "debt", "loan", "credit", "rating", "downgrade", "upgrade",
    "mutual fund", "etf", "futures", "options",
    
    # Sector terms
    "sector", "industry", "bank", "banking", "pharma", "technology",
    "energy", "infra", "infrastructure", "auto", "fmcg", "telecom",
    
    # Flows & sentiment
    "fii", "dii", "institutional", "investor", "analyst", "target",
    "recommendation", "outlook", "forecast", "guidance",
}

def passes_keyword_filter(title: str, company_name: str, industry: str) -> bool:
    """Return True if the article title is potentially relevant."""
    title_lower = title.lower()
    
    # Rule 1: Title contains the company name (or a significant part of it)
    company_parts = company_name.lower().replace("ltd", "").replace("limited", "").split()
    significant_parts = [p for p in company_parts if len(p) > 2]  # skip "Ltd", "of", etc.
    if any(part in title_lower for part in significant_parts):
        return True
    
    # Rule 2: Title contains the industry keyword
    if industry and industry.lower() in title_lower:
        return True
    
    # Rule 3: Title contains any financial keyword
    if any(keyword in title_lower for keyword in FINANCIAL_KEYWORDS):
        return True
    
    # Rule 4: Title contains currency symbols or financial figures
    if any(marker in title for marker in ["₹", "Rs", "crore", "lakh", "%"]):
        return True
    
    # None of the above → likely noise
    return False
```

### 5.3 Expected Behavior

| Article Title | Company: HDFC Bank | Verdict |
|---|---|---|
| "RBI tightens provisioning norms for unsecured retail loans" | Matches: "rbi", "provisioning", "loan" | ✅ KEEP |
| "HDFC Bank launches new credit card for millennials" | Matches: "HDFC" (company name) | ✅ KEEP |
| "Best weekend getaways near Mumbai for bank holidays" | "bank" matches keyword → ⚠️ false positive | ✅ KEEP (Phase 5 will kill it) |
| "Mumbai Indians win IPL qualifier" | No matches | ❌ DROP |
| "Top 10 recipes for Diwali snacks" | No matches | ❌ DROP |
| "Bollywood box office: latest releases" | No matches | ❌ DROP |

**Note:** A few false positives will slip through (like "bank holidays"). This is fine — Phase 5's full-text causal scoring will assign them `causal_score: 0` and they'll be filtered out. We'd rather have a few false positives than miss a genuinely important article.

### 5.4 Expected Reduction

- Input: ~60-120 deduplicated articles per holding
- Output: ~30-50 articles per holding (~50-60% survival — same as the LLM version)

### 5.5 LLM Calls

**0 calls. This phase is pure code.**

---

## 6. Phase 4 — Scrape Survivors (Unchanged)

> **Identical to hybrid_plan.md Phase 4. No changes.**

### Steps

```
For each surviving article (parallel, 8 workers):
  Step 4.1 ─── Check if link is a Google News wrapper URL
  Step 4.2 ─── If yes: resolve via batchexecute RPC (lib/google_news.py)
  Step 4.3 ─── Fetch the publisher page with TLS impersonation (lib/fetch.py)
  Step 4.4 ─── Extract article text with trafilatura, fallback to BeautifulSoup (lib/extract.py)
  Step 4.5 ─── Store: article text, resolved URL, extraction status
```

### Failure Handling

| Failure Type | Expected Rate | Handling |
|---|---|---|
| Google News URL resolution fails | ~5-10% | Exclude from Phase 5 |
| Publisher page 403/429 | ~10-15% | Retry with different TLS fingerprint, then exclude |
| Paywall / login required | ~5-10% | Mark text as incomplete, keep title |
| JS-rendered page | ~5% | Fallback to meta description |

**Expected output: ~20-35 successfully scraped articles per holding.**

**LLM Calls: 0**

---

## 7. Phase 5 — Full-Text Causal Scoring + Event Tagging (CHANGED: Merged Phase 6)

> **CHANGED from hybrid_plan.md:**
> 1. Batch size increased from 5-8 to **10-12 articles per batch** (reduces calls from 3-6 to 2-3 per holding).
> 2. LLM now also assigns an **`event_label`** to each article (enables code-based Phase 6, eliminating its LLM call).

### 7.1 Why Larger Batches Work

Token math per batch:
```
12 articles × 500 words each  = 6,000 words of article text
Price context + daily breakdown = ~200 words
Prompt template + instructions  = ~400 words
                                  ─────────
Total input:                    ≈ 6,600 words ≈ ~9,000 tokens
```

9K input tokens is well within any modern model's capacity. Quality doesn't degrade at this size because each article is scored **independently** — the LLM doesn't need to compare articles within a batch, it just evaluates each one against the price movement context.

### 7.2 The One New Field: `event_label`

In addition to all the scores from hybrid_plan.md, the LLM now assigns a short **`event_label`** — a 3-8 word tag describing the underlying event the article is about.

Examples:
| Article Title | event_label |
|---|---|
| "RBI tightens provisioning norms for unsecured retail loans" | `"RBI unsecured loan provisioning norms"` |
| "New RBI norms to hit bank margins on personal loans" | `"RBI unsecured loan provisioning norms"` |
| "HDFC Bank Q4 profit rises 9% to Rs 17,616 crore" | `"HDFC Bank Q4 FY26 earnings"` |
| "HDFC Bank Q4 in line but NIMs compress 3bp" | `"HDFC Bank Q4 FY26 earnings"` |
| "Global banking stocks fall on US recession fears" | `"US recession fears global sell-off"` |

Articles about the **same event** get the **same or very similar label**. This is what enables code-based clustering in Phase 6.

### 7.3 LLM Prompt — Full-Text Causal Scoring + Event Tagging

```
SYSTEM:
You are a financial analyst investigating WHY a stock's price moved.

For each article below, determine whether it describes an event that CAUSED
or CONTRIBUTED to the observed price movement.

Score each article on these dimensions:

1. relevancy_score (0-10): Financial materiality to this specific company.
2. causal_score (0-10): How likely did this event CAUSE the observed price move?
   - 9-10: Almost certainly the primary catalyst
   - 7-8:  Strong contributing factor
   - 5-6:  Plausible but uncertain connection
   - 3-4:  Weak or indirect connection
   - 0-2:  Unrelated to the price movement
3. event_label: A short 3-8 word tag describing the UNDERLYING EVENT.
   Articles about the same real-world event MUST get the same event_label.
   Example: Two articles about RBI changing provisioning norms should both
   get event_label "RBI unsecured loan provisioning norms".
4. causal_link: "direct" | "sector" | "macro" | "none"
5. timing_plausible (true/false): Was this published BEFORE or ON the day
   of the price movement?
6. sentiment: "positive" | "negative"
7. reasoning: 1-2 sentence causal explanation.

OUTPUT FORMAT:
{
  "scores": [
    {
      "article_id": 1,
      "relevancy_score": 8,
      "causal_score": 9,
      "event_label": "RBI unsecured loan provisioning norms",
      "causal_link": "direct",
      "timing_plausible": true,
      "sentiment": "negative",
      "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost
                    of unsecured lending. Published Friday evening before
                    Monday's -1.85% drop."
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
Text (first 500 words): "The Reserve Bank of India on Friday announced
new provisioning requirements for unsecured retail loans, raising the
risk weight from 100% to 125%..."

--- Article 2 (published: 2026-09-08 09:15 IST) ---
Title: "HDFC Bank launches new credit card for millennials"
Text (first 500 words): "HDFC Bank on Monday unveiled a new credit card
designed for young professionals aged 25-35..."

[...up to 10-12 articles per batch...]

Score all {N} articles. Assign the SAME event_label to articles about
the same underlying event.
```

### 7.4 Filtering After Phase 5

From all scored articles across all batches:

```
Keep:  causal_score >= 5  AND  timing_plausible == true
Sort:  causal_score descending
Take:  top ~8-12 per holding
```

### 7.5 Per-Article Output After Phase 5

```json
{
  "article_id": 1,
  "title": "RBI tightens provisioning norms for unsecured retail loans",
  "resolved_url": "https://economictimes.com/...",
  "source": "Economic Times",
  "published": "2026-09-07T20:30:00+05:30",
  "date": "2026-09-07",
  "text": "[full scraped article text]",
  "relevancy_score": 8,
  "causal_score": 9,
  "event_label": "RBI unsecured loan provisioning norms",
  "causal_link": "direct",
  "timing_plausible": true,
  "sentiment": "negative",
  "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost of unsecured lending. Published Friday evening before Monday's -1.85% drop."
}
```

### 7.6 LLM Calls for Phase 5

| Per holding | Total (3 holdings) |
|---|---|
| 2-3 calls (batches of 10-12 articles) | **6-9 calls** |

**This is the ONLY phase that uses the LLM in the entire pipeline.**

---

## 8. Phase 6 — Programmatic Event Grouping & Selection (CHANGED: LLM → Code)

> **CHANGED from hybrid_plan.md**: Replaced the LLM clustering call with pure code logic, using the `event_label` field from Phase 5.

### 8.1 Why This Works Without an LLM

Phase 5 already assigned an `event_label` to every article. Articles about the same real-world event have the same (or very similar) label. Grouping is now a simple code operation.

### 8.2 Grouping Logic

```python
def group_by_event(scored_articles: list[dict]) -> dict[str, list[dict]]:
    """Group articles by event_label. Handle minor label variations."""
    groups = {}
    for article in scored_articles:
        label = article["event_label"].strip().lower()
        
        # Check if this label is similar to an existing group
        matched = False
        for existing_label in list(groups.keys()):
            if _labels_match(label, existing_label):
                groups[existing_label].append(article)
                matched = True
                break
        
        if not matched:
            groups[label] = [article]
    
    return groups


def _labels_match(label_a: str, label_b: str) -> bool:
    """Check if two event labels refer to the same event."""
    words_a = set(label_a.split())
    words_b = set(label_b.split())
    
    if not words_a or not words_b:
        return False
    
    # If labels share > 60% of their words, they're about the same event
    overlap = len(words_a & words_b)
    smaller = min(len(words_a), len(words_b))
    
    return (overlap / smaller) >= 0.6
```

### 8.3 Selection Logic

```python
def select_final_events(groups: dict, max_events: int = 5) -> list[dict]:
    """Pick the best article per event group, rank by causal_score."""
    events = []
    
    for label, articles in groups.items():
        # Pick the article with the highest causal_score
        # Tiebreaker: longest text (more informative)
        best = max(articles, key=lambda a: (
            a["causal_score"],
            len(a.get("text", ""))
        ))
        
        events.append({
            "event_label": label,
            "best_article": best,
            "article_count": len(articles),
            "combined_causal_score": best["causal_score"],
            "event_summary": best["reasoning"],
        })
    
    # Rank by causal_score descending
    events.sort(key=lambda e: e["combined_causal_score"], reverse=True)
    
    return events[:max_events]
```

### 8.4 Confidence Assignment

```python
def assign_confidence(events: list[dict]) -> tuple[str, str]:
    """Assign explanation confidence based on top event scores."""
    if not events:
        return "low", "No relevant news events found for this holding's weekly movement."
    
    top_score = events[0]["combined_causal_score"]
    
    if top_score >= 8:
        confidence = "high"
        reasoning = (
            f"Strong causal match: '{events[0]['event_label']}' "
            f"(causal_score={top_score}) clearly explains the observed price movement."
        )
    elif top_score >= 5:
        confidence = "medium"
        reasoning = (
            f"Plausible explanation: '{events[0]['event_label']}' "
            f"(causal_score={top_score}) may partially explain the movement, "
            f"but the link is not definitive."
        )
    else:
        confidence = "low"
        reasoning = (
            f"No strong news catalyst found. The best candidate "
            f"'{events[0]['event_label']}' scored only {top_score}/10. "
            f"The movement may be driven by fund flows, technical factors, "
            f"or sector rotation rather than specific news."
        )
    
    return confidence, reasoning
```

### 8.5 Example

**Input (top 8 scored articles for HDFC Bank):**

| article_id | event_label | causal_score |
|---|---|---|
| 1 | RBI unsecured loan provisioning norms | 9 |
| 4 | RBI unsecured loan provisioning norms | 8 |
| 7 | RBI unsecured loan provisioning norms | 7 |
| 3 | HDFC Bank Q4 FY26 earnings | 7 |
| 8 | HDFC Bank Q4 FY26 earnings | 6 |
| 5 | US recession fears global sell-off | 6 |
| 2 | HDFC Bank new credit card launch | 2 |
| 6 | HDFC Bank MCLR rate cut | 3 |

**After grouping + selection:**

| event_rank | event_label | best_article_id | causal_score | articles_in_group |
|---|---|---|---|---|
| 1 | RBI unsecured loan provisioning norms | 1 | 9 | 3 |
| 2 | HDFC Bank Q4 FY26 earnings | 3 | 7 | 2 |
| 3 | US recession fears global sell-off | 5 | 6 | 1 |

**Confidence: `"high"`** (top score = 9)

Articles 2 and 6 (causal_score 2 and 3) were filtered out in Phase 5's `causal_score >= 5` threshold.

### 8.6 LLM Calls

**0 calls. This phase is pure code.**

---

## 9. Phase 7 — Output & Persistence (Unchanged)

> **Identical to hybrid_plan.md Phase 7. No changes.**

### Final Output JSON Structure Per Holding

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
  "confidence_reasoning": "Strong causal match: 'RBI unsecured loan provisioning norms' (causal_score=9) clearly explains the observed price movement.",
  "relevant_news": [
    {
      "event_rank": 1,
      "event_label": "RBI unsecured loan provisioning norms",
      "event_summary": "RBI provisioning norms directly increase HDFC Bank's cost of unsecured lending. Published Friday evening before Monday's -1.85% drop.",
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
      "reasoning": "RBI provisioning norms directly increase HDFC Bank's cost of unsecured lending."
    },
    {
      "event_rank": 2,
      "event_label": "HDFC Bank Q4 FY26 earnings",
      "...": "..."
    },
    {
      "event_rank": 3,
      "event_label": "US recession fears global sell-off",
      "...": "..."
    }
  ]
}
```

### Persistence

```
Step 7.1 ─── Save individual scraped .json and .html files to out/ folder
Step 7.2 ─── Save complete enriched JSON to output-scrapper/result.json
Step 7.3 ─── Print final JSON to stdout
```

**LLM Calls: 0**

---

## 10. Complete Optimized Data Flow

```
INPUT: Fund rows (name, detail, percentage)
  │
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 1: Weekly Market Data & Movement Decomposition        ║
║  • Get top 10 → find tickers → weekly prices                 ║
║  • Daily % changes → weekly NAV impact                       ║
║  • Event days → sector correlation                           ║
║  • Select top 3 holdings                                     ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │  3 holdings + weekly data + event days + move_scope
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 2: Smart News Harvesting (per holding)                ║
║  • Build adaptive RSS queries (when:7d)                      ║
║  • Fetch + parse feeds                                       ║
║  • Exact + fuzzy title deduplication                         ║
║  Output: ~60-120 articles/holding                            ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │  ~60-120 articles/holding
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 3: Keyword-Based Coarse Filter  ◄── NO LLM           ║
║  • Company name match                                        ║
║  • Industry keyword match                                    ║
║  • Financial terminology match                               ║
║  • Currency/figure marker match                              ║
║  Output: ~30-50 articles/holding                             ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │  ~30-50 articles/holding
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 4: Parallel Scraping (8 workers)                      ║
║  • Resolve Google News URLs                                  ║
║  • TLS-impersonated fetch                                    ║
║  • trafilatura + BeautifulSoup extraction                    ║
║  Output: ~20-35 scraped articles/holding                     ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │  ~20-35 articles/holding (with full text)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 5: Full-Text Causal Scoring + Event Tagging           ║
║  ┌─────────────────────────────────────────────────────────┐ ║
║  │  THE ONLY LLM PHASE IN THE ENTIRE PIPELINE             │ ║
║  └─────────────────────────────────────────────────────────┘ ║
║  • Batches of 10-12 articles (first 500 words each)          ║
║  • Price context: weekly change + daily breakdown + events   ║
║  • Scores: relevancy, causal_score, event_label,             ║
║    causal_link, timing_plausible, sentiment, reasoning       ║
║  • Filter: causal_score >= 5 AND timing_plausible            ║
║  Output: ~8-12 high-causal articles/holding                  ║
║  LLM Calls: 2-3 per holding = 6-9 total                     ║
╚═══════════════════════════════════════════════════════════════╝
  │  ~8-12 scored articles/holding (with event_label)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 6: Programmatic Event Grouping  ◄── NO LLM           ║
║  • Group by event_label (fuzzy word-overlap matching)        ║
║  • Pick highest causal_score article per group               ║
║  • Rank event groups by causal_score                         ║
║  • Select top 3-5 distinct events                            ║
║  • Assign confidence: high / medium / low                    ║
║  Output: 3-5 events/holding + confidence                     ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
  │  3-5 events/holding (with full text + reasoning)
  ▼
╔═══════════════════════════════════════════════════════════════╗
║  PHASE 7: Output & Persistence                               ║
║  • Sort holdings by weekly_nav_impact_pct                    ║
║  • Save scraped files to out/                                ║
║  • Save result.json to output-scrapper/                      ║
║  • Print JSON to stdout                                      ║
║  LLM Calls: 0                                                ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 11. LLM Call Comparison

### Per Holding

| Phase | hybrid_plan.md | This Plan | Change |
|---|---|---|---|
| Phase 3 (coarse filter) | 1-2 LLM calls | **0** (keyword code) | Eliminated |
| Phase 5 (causal scoring) | 3-6 LLM calls | **2-3** (larger batches) | Reduced |
| Phase 6 (event clustering) | 1 LLM call | **0** (code grouping) | Eliminated |
| **Per holding total** | **5-9 calls** | **2-3 calls** | **~65% fewer** |

### Total for 3 Holdings

| Metric | hybrid_plan.md | This Plan | Reduction |
|---|---|---|---|
| **LLM Calls** | 15-27 | **6-9** | ~65% |
| **Input Tokens** | ~90-180K | **~55-80K** | ~55% |
| **Output Tokens** | ~18-36K | **~12-18K** | ~45% |
| **Total Tokens** | ~108-216K | **~67-98K** | ~55% |
| **Estimated Time** | ~2-4 min | **~1-2 min** | ~50% |

### Comparison to Current System

| Metric | Current System | This Optimized Plan | Factor |
|---|---|---|---|
| LLM Calls | ~6 | **6-9** | ~1.5x |
| Total Tokens | ~15-20K | **~67-98K** | ~4-5x |
| Articles Scraped | 3-9 | ~60-105 | ~10x |
| Time | ~30-60s | **~1-2 min** | ~2x |
| Explanation Quality | Title-based guessing | Full-text causal reasoning | Significant |

**Key takeaway:** For roughly **1.5x the LLM calls** of the current system, we get a full week of analysis with full-text causal scoring, event deduplication, and confidence-aware output.

---

## 12. File & Module Mapping (Updated)

### Existing Files That Need Modification

| File | What Changes |
|---|---|
| `demo.py` | `get_last_two_closing_prices()` → `get_weekly_prices()` returning 5-7 days. Add `compute_daily_changes()`. Adapt `get_fund_top_10_prices()` for weekly NAV impact. |
| `stocks_for_news.py` | Minimal — same `get_top_3_nav_impact_holdings()` on weekly data. |
| `app.py` | New `fetch_news_for_week()` with `when:7d`, adaptive query strategy, fuzzy dedup. |
| `news_relevancy_agent.py` | New `score_articles_causal()` with the Phase 5 prompt (causal + event_label). Remove or keep old title-only scorer as fallback. |
| `main.py` | Restructure `main()` for 7-phase flow. Add `keyword_filter()`, `identify_event_days()`, `check_sector_correlation()`, `group_by_event()`, `assign_confidence()`. |
| `web_scrapper.py` | No changes — `scrape_one()` and `_write_record()` work as-is. |
| `lib/*` | No changes. |

### New Functions to Create

| Function | Location | Purpose | Uses LLM? |
|---|---|---|---|
| `get_weekly_prices(ticker)` | `demo.py` | Return last 5-7 trading day closes | No |
| `compute_daily_changes(prices)` | `demo.py` | Day-over-day % changes | No |
| `identify_event_days(daily_changes)` | `main.py` | Find significant move days | No |
| `check_sector_correlation(holdings)` | `main.py` | Company vs. sector vs. market scope | No |
| `build_adaptive_queries(holding)` | `app.py` | Build queries based on move_scope | No |
| `fetch_news_for_week(holding)` | `app.py` | Harvest + deduplicate 7 days of news | No |
| `keyword_filter(articles, company, industry)` | `main.py` | Phase 3 coarse filter | **No** |
| `score_articles_causal(holding, articles, price_ctx)` | `news_relevancy_agent.py` | Phase 5 causal scoring + event tagging | **Yes** |
| `group_by_event(scored_articles)` | `main.py` | Phase 6 event grouping | **No** |
| `select_final_events(groups)` | `main.py` | Pick best article per event | **No** |
| `assign_confidence(events)` | `main.py` | High/medium/low confidence | **No** |

**Only 1 function out of 11 uses the LLM.** Everything else is pure code.
