# Weekly NAV Intelligence — Deep News Filtering Plan

## The Problem Statement

The current system operates on a **1-day price change** (last 2 trading sessions) and harvests news from **T-1 and T-2** (yesterday and day before). Title-only LLM scoring picks the top 3 articles matching the directional sentiment.

**What we want instead:**
- Compute NAV change over a **full trading week** (~5 trading sessions).
- Harvest news spanning that **entire week**.
- A week of news for a single stock can produce **50-200+ articles** — most of which are noise.
- The current title-only scoring is **insufficient** at this scale — many articles with catchy or alarming titles turn out to be generic market commentary, not the actual catalyst.
- We need a pipeline that surfaces the **actual reasons** behind the weekly price movement, not just articles that *sound* related.

---

## Core Challenges (Why This Is Hard)

### 1. Volume Explosion
A week of Google News RSS for "HDFC Bank" + "Indian Financial Services" will return **10-20x more articles** than the current 2-day window. Scoring all of them with a full-text LLM call is prohibitively expensive.

### 2. Title-Only Scoring Is Lossy
- **False Positives**: "HDFC Bank Stock Rally — What Investors Must Know" could be a generic clickbait article with zero substance.
- **False Negatives**: "RBI Announces New Provisioning Norms for Housing Loans" — boring title, but this is the exact regulatory change that moved HDFC Bank 3% on Wednesday.
- Titles are optimized for **clicks**, not for **financial causality**.

### 3. Coincidence ≠ Causation
An article published on the same day as a price move is not necessarily the cause. The price might have moved on:
- Institutional fund flows (FII/DII buying/selling)
- Technical breakouts or breakdowns
- Options expiry effects
- Sector rotation or macro sentiment shifts
- Block deals or bulk deals not covered in news

We need to distinguish **news-driven moves** from **flow-driven or technical moves**, and be honest when no news catalyst is found.

### 4. Event Duplication
One actual event (e.g., "L&T wins $2B defense contract") produces **15-30 articles** across outlets. We don't want 3 copies of the same story — we want 3 **different events** that explain the movement.

### 5. Temporal Alignment
For a weekly analysis, the question isn't just "is this news relevant?" but **"did the stock price actually respond to this news?"** A positive article published on Monday is only explanatory if the stock rose on Monday or Tuesday — not if it was flat.

---

## Approach 1: Multi-Stage Funnel (Recommended Starting Point)

The idea is a **progressively expensive** filtering pipeline. Each stage is cheaper and faster than the next, and drastically reduces the volume for the expensive stages.

```
Week's News (~150 articles)
    │
    ▼
┌─────────────────────────────────┐
│  Stage 1: Title-Only Quick     │  Cost: LOW (single LLM call per batch)
│  Coarse Filter                  │  Output: ~30-40 articles
│  • Remove score < 3             │  Purpose: Kill obvious noise fast
│  • Keep generous threshold      │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Stage 2: Scrape Survivors      │  Cost: MODERATE (HTTP + extraction)
│  Full Article Text Extraction   │  Output: ~30-40 scraped articles
│  • Resolve Google News URLs     │  Purpose: Get actual content
│  • Extract clean text           │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Stage 3: Full-Text Deep        │  Cost: HIGH (LLM on full article body)
│  Relevancy + Causality Scoring  │  Output: ~8-12 high-quality articles
│  • Score 0-10 on full content   │  Purpose: True relevancy from content
│  • Sentiment from article body  │
│  • Causal plausibility score    │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Stage 4: Event Deduplication   │  Cost: MODERATE (LLM clustering)
│  & Cross-Article Reasoning      │  Output: 3-5 unique events
│  • Cluster by underlying event  │  Purpose: One article per event
│  • Pick best article per event  │
│  • Rank events by explanatory   │
│    power for observed move      │
└─────────────────────────────────┘
    │
    ▼
  Final Output: 3-5 distinct news events
  that best explain the weekly NAV change
```

### Why This Works
- Stage 1 is cheap (title-only, batched) and kills ~70-80% of noise.
- Stage 2 is a one-time cost — scraping is parallelizable.
- Stage 3 is expensive but operates on a reduced set (~30 articles, not 150).
- Stage 4 ensures diversity of explanations.

### Risks
- If Stage 1's title filter is too aggressive, we lose articles with boring but important titles.
- Scraping 30-40 articles is heavier than the current 3-9 articles.

---

## Approach 2: Scrape Everything First, Then LLM Filter

Flip the order — scrape first, filter later.

```
Week's News (~150 articles)
    │
    ▼
┌─────────────────────────────────┐
│  Scrape ALL articles            │  Cost: HIGH upfront (HTTP + extraction)
│  Full text extraction           │  Output: ~150 full-text articles
│  (parallel, 8-16 workers)       │  Time: 2-5 minutes
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Summarize Each Article         │  Cost: MODERATE (LLM on each article)
│  2-3 sentence summary per       │  Output: ~150 summaries
│  article focusing on:           │  Purpose: Compress for batch scoring
│  • What happened                │
│  • Financial impact             │
│  • Which companies affected     │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│  Batch Score All Summaries      │  Cost: MODERATE (single large LLM call)
│  Together with Price Context    │  Output: Ranked list
│  "Stock X moved Y% this week.  │
│   Which of these 150 summaries │
│   best explain the move?"       │
└─────────────────────────────────┘
    │
    ▼
  Top 5 articles with full text
```

### Why This Could Be Better
- **No false negatives** — every article is scraped and read, so a boring title with critical content won't be missed.
- The LLM sees summaries of ALL articles together, so it can make **comparative judgments** ("Article 47 is clearly the catalyst, not Article 12").

### Risks
- Scraping 150 articles is expensive in time and bandwidth.
- Many scrapes will fail (paywalls, JS-rendered pages, anti-bot).
- Summarizing 150 articles requires many LLM calls (though they can be batched).

### Mitigation
- Scrape in parallel with high worker count (current system already supports `--workers 8`).
- Accept ~70% scrape success rate; filter out failures.
- Use a cheaper/faster model for summarization (e.g., a smaller model), reserve the expensive model for final scoring.

---

## Approach 3: Price-Anchored Day-by-Day Correlation

Instead of treating the week as a single block, **decompose it into daily movements** and correlate each day's news with that day's price action.

```
Weekly Price Data:
  Mon: +1.2%  ←  likely news-driven
  Tue: -0.1%  ←  noise / no catalyst
  Wed: -2.8%  ←  BIGGEST MOVE — focus here
  Thu: +0.3%  ←  noise / recovery
  Fri: +0.5%  ←  noise / recovery
  ─────────
  Week: -0.9%

Step 1: Identify "Event Days"
  → Wednesday (-2.8%) is the day that matters most
  → Monday (+1.2%) is secondary

Step 2: Harvest news specifically for those dates
  → News from Tuesday evening / Wednesday morning (pre-market catalysts)
  → News from Sunday evening / Monday morning

Step 3: Score only the date-aligned subset
  → Much smaller volume
  → Much higher signal-to-noise
```

### Why This Is Powerful
- A stock that drifted -0.1% per day for a week has **no single catalyst** — it's sentiment/flow. No point searching for a news explanation.
- A stock that was flat for 4 days and dropped -4% on Thursday has a **clear event day**. The catalyst is in Thursday's (or Wednesday evening's) news.
- This dramatically reduces the search space and improves accuracy.

### How to Implement
1. Get daily closing prices for the last 5-7 trading sessions (current `yf.Ticker.history(period="10d")` already does this).
2. Compute daily % changes.
3. Identify "event days" — days where `|daily_change|` exceeds some threshold (e.g., > 1.5% for large-caps, > 2.5% for mid-caps).
4. For each event day, harvest news from `[day-1 evening, day morning]` window.
5. Apply the existing title + full-text scoring pipeline on this much smaller set.

### Risks
- Some moves are gradual (sector rotation over a week) with no single event day.
- News can have a **delayed effect** — published Monday, market digests it by Wednesday.

### Mitigation
- If no event day is found (all daily changes < threshold), fall back to the full-week approach (Approach 1 or 2).
- Widen the news window to `[day-2, day+1]` to catch delayed reactions.

---

## Approach 4: Embedding-Based Semantic Clustering + Event Deduplication

Use text embeddings to **cluster articles by underlying event**, then score events (not individual articles).

```
150 scraped articles
    │
    ▼
┌─────────────────────────────────────┐
│  Generate Embeddings               │  Tool: sentence-transformers or
│  (title + first 200 words)         │  OpenAI embeddings API
│  → 150 vectors                     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Cluster by Cosine Similarity      │  Tool: DBSCAN or Agglomerative
│  Threshold: ~0.85 similarity       │  Output: ~15-25 event clusters
│  Articles about the same event     │
│  collapse into one cluster         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  For Each Cluster:                 │
│  • Pick the longest/richest article│  Output: ~15-25 representative
│  • Extract event date              │  articles (one per event)
│  • Generate event summary          │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  Score Events Against Price Move   │  LLM call with all event summaries
│  "Here are 20 events from this     │  + weekly price data
│   week. Rank by explanatory power  │
│   for the observed -2.3% move"     │
└─────────────────────────────────────┘
    │
    ▼
  Top 3-5 distinct events with best representative article each
```

### Why This Is Elegant
- **Solves deduplication** at the structural level — 15 articles about the same RBI announcement become one cluster.
- **Diverse output** — each selected article represents a genuinely different event.
- Embeddings are fast and cheap to compute.

### Risks
- Requires an embedding model (adds a dependency).
- Clustering hyperparameters (similarity threshold) need tuning.
- Some events are related but distinct (e.g., "RBI cuts rates" and "Banks lower MCLR after RBI cut" — same root cause, different events).

---

## Approach 5: Two-Pass LLM with Explicit Causal Reasoning

Use the LLM in two passes with **different prompts** — first for relevance, then for **causal explanation**.

### Pass 1: Relevance Scoring (Current Approach, Scaled Up)
Score all articles on title + optional summary. Filter to top ~20.

### Pass 2: Causal Reasoning (New)
For each surviving article, ask the LLM a **different question**:

```
PROMPT:
Stock: HDFC Bank (HDFCBANK.NS)
Weekly Price Change: -2.3% (from ₹1,890 on Mon to ₹1,847 on Fri)
Largest daily drops: Wednesday -1.8%, Thursday -0.7%

Article Title: "RBI tightens provisioning norms for unsecured retail loans"
Article Text: [full scraped text]
Published: Tuesday 8:30 PM IST

QUESTIONS:
1. Does this article describe an event that could CAUSE or CONTRIBUTE to
   the observed -2.3% decline in HDFC Bank's stock?
2. Is the timing plausible? (Published before or during the price move?)
3. How direct is the causal link? (Direct company impact vs. sector-wide
   vs. macro sentiment?)
4. Causal confidence score (0-10): How confident are you that this article
   explains part of the observed price movement?

Return JSON:
{
  "causal_score": 8,
  "causal_link": "direct",
  "timing_plausible": true,
  "reasoning": "RBI tightening provisioning norms directly impacts HDFC Bank's
                unsecured loan book margins. Published Tuesday evening before
                Wednesday's -1.8% drop. Strong causal alignment."
}
```

### Why This Changes Everything
- The current system asks: *"Is this article relevant to the stock?"*
- This approach asks: *"Does this article explain why the stock moved?"*
- These are fundamentally different questions. An article about HDFC Bank's new credit card launch is "relevant" but doesn't "explain" a -2.3% drop.

### The Key Insight
**Relevance ≠ Explanatory Power.** We want explanatory power.

---

## Approach 6: Sector-Aware Filtering (Distinguishing Company-Specific vs. Sector-Wide Catalysts)

When HDFC Bank drops -2.3%, was it:
- **Company-specific?** (Only HDFC Bank dropped, peers were flat/up)
- **Sector-wide?** (All banking stocks dropped — look for sector news, not company news)
- **Market-wide?** (Nifty 50 dropped — look for macro news)

```
Step 1: Check if the move is idiosyncratic
  HDFC Bank: -2.3%
  ICICI Bank: -0.1%  ← peers are flat
  Axis Bank: +0.3%
  → This is COMPANY-SPECIFIC. Search for HDFC-specific news.

OR:
  HDFC Bank: -2.3%
  ICICI Bank: -2.1%
  Axis Bank: -1.9%
  → This is SECTOR-WIDE. Search for banking/financial sector news.

OR:
  HDFC Bank: -2.3%
  Nifty 50:  -1.8%
  → This is MARKET-WIDE. Search for macro news (RBI, FII flows, global).

Step 2: Adjust news queries based on finding
  Company-specific → Search: "HDFC Bank"
  Sector-wide → Search: "Indian Banking sector", "RBI policy", "bank stocks"
  Market-wide → Search: "Indian stock market", "Nifty", "FII selling"
```

### Why This Matters
- If you search for "HDFC Bank" news to explain a sector-wide drop, you'll find irrelevant company-specific articles and miss the actual sector catalyst.
- This approach **narrows the search space to the right level of abstraction**.

### Implementation Idea
- Since `demo.py` already computes NAV impact for top 10 holdings, we have sector peer data.
- Group holdings by `industry` field.
- If multiple holdings in the same sector moved in the same direction, flag as sector-wide.
- Adjust the RSS query strategy accordingly.

---

## Approach 7: Confidence-Aware Output (Knowing When News Doesn't Explain the Move)

Sometimes there is **no news catalyst**. The move was driven by:
- Institutional rebalancing
- Options/futures expiry
- Technical support/resistance levels
- Passive fund flows
- Global correlation (US markets moved, India followed)

The system should be able to say: **"No high-confidence news catalyst found for this holding's weekly movement."**

```json
{
  "name": "Bajaj Finance Ltd",
  "weekly_change": "-1.4%",
  "explanation_confidence": "low",
  "explanation_note": "No single news event found with causal score > 6.
    The -1.4% decline appears to be part of a broader financial services
    sector rotation (ICICI -1.2%, Axis -0.9%) rather than company-specific
    news.",
  "best_candidates": [
    {
      "title": "...",
      "causal_score": 4,
      "reasoning": "Weakly related sector commentary, not a direct catalyst"
    }
  ]
}
```

### Why This Is Important
- Forcing the system to always return 3 articles leads to **false attribution** — "here's why the stock moved" when the real answer is "we don't know."
- A confidence score lets downstream consumers (dashboards, reports, humans) decide whether to trust the explanation.

---

## Recommended Hybrid Strategy

Combine the strongest elements of all approaches:

### Phase 1: Weekly Market Data & Movement Decomposition
1. Get **daily closing prices** for the last 7 trading sessions.
2. Compute weekly % change and daily % changes.
3. Identify **event days** (days with |change| > threshold).
4. Check **sector correlation** — is the move company-specific, sector-wide, or market-wide?

### Phase 2: Smart News Harvesting
5. Build RSS queries based on Phase 1 findings:
   - Company-specific move → company name queries, `when:7d`
   - Sector-wide move → industry/sector queries, `when:7d`
   - Market-wide move → broader macro queries, `when:7d`
6. Collect **all articles** from the week (could be 50-200 per holding).
7. **Deduplicate by title** (exact and fuzzy match).

### Phase 3: Coarse Title-Based Filter (Cheap)
8. Batch LLM call on **titles only** — score relevance 0-10.
9. Keep articles scoring ≥ 3 (generous threshold — don't lose anything potentially useful).
10. This should reduce 150 → ~40-50 articles.

### Phase 4: Scrape Survivors
11. Scrape the ~40-50 articles in parallel.
12. Extract clean text via trafilatura + BeautifulSoup fallback.
13. Discard scrape failures (paywall, JS-rendered, anti-bot blocked).

### Phase 5: Full-Text Deep Scoring with Causal Reasoning
14. For each scraped article, send to LLM with **full context**:
    - The article's full text (or first ~2000 words if very long)
    - The stock's weekly price movement and daily breakdown
    - The article's publication timestamp
15. Ask the LLM to score:
    - `relevancy_score` (0-10): How relevant is this to the stock?
    - `causal_score` (0-10): How likely is this to have caused the observed price move?
    - `causal_link`: "direct" | "sector" | "macro" | "none"
    - `timing_plausible`: Was this published before the price moved?
    - `sentiment`: "positive" | "negative"
    - `reasoning`: One-line explanation of why this article matters or doesn't.

### Phase 6: Event Clustering & Final Selection
16. Group high-scoring articles by **underlying event** (LLM-assisted or embedding-based).
17. For each event cluster, select the **richest/longest article** as representative.
18. Rank events by `causal_score` descending.
19. Select top **3-5 distinct events**.
20. Assign an overall **explanation_confidence** ("high" / "medium" / "low") based on the best causal_score.

### Phase 7: Output
21. Attach the selected articles (with full text, scores, and causal reasoning) to each holding.
22. Sort holdings by `nav_impact_percentage`.
23. Write enriched JSON to `output-scrapper/result.json`.

---

## Key LLM Prompt Design Considerations

### Current Prompt (Title-Only, Relevance + Sentiment)
```
"Score each headline for relevance (0-10) and sentiment (positive/negative)
 regarding the stock."
```

### Proposed New Prompt (Full-Text, Causal Reasoning)
```
"You are a financial analyst investigating WHY a stock's price moved.

STOCK: {name} ({ticker})
WEEKLY MOVE: {weekly_change}% ({start_date} to {end_date})
DAILY BREAKDOWN:
  Mon: {mon_change}%
  Tue: {tue_change}%
  Wed: {wed_change}%
  Thu: {thu_change}%
  Fri: {fri_change}%

ARTICLE (published {pub_date}):
{article_text_truncated_to_2000_words}

Score this article on:
1. relevancy_score (0-10): Financial materiality to this specific stock.
2. causal_score (0-10): Likelihood that this article describes an event
   that CAUSED or CONTRIBUTED to the observed price movement.
   - 9-10: Almost certainly the primary catalyst
   - 7-8: Strong contributing factor
   - 5-6: Plausible but uncertain connection
   - 3-4: Weak or indirect connection
   - 0-2: Unrelated to the price movement
3. causal_link: 'direct' (company-specific), 'sector' (industry-wide),
   'macro' (market-wide), or 'none'
4. timing_plausible: true/false — was this published BEFORE the relevant
   price movement day?
5. sentiment: 'positive' or 'negative' for stock price direction
6. reasoning: 1-2 sentence explanation of the causal connection (or lack thereof)

Return JSON:
{
  "relevancy_score": ...,
  "causal_score": ...,
  "causal_link": "...",
  "timing_plausible": ...,
  "sentiment": "...",
  "reasoning": "..."
}
```

### Why "Causal Score" Is Different From "Relevancy Score"

| Article | Relevancy | Causal Score | Why |
|---|---|---|---|
| "HDFC Bank launches new savings account" | 8 | 1 | Relevant to the company, but savings account launches don't move stocks |
| "RBI fines HDFC Bank ₹2 crore for KYC violations" | 7 | 2 | Relevant, but ₹2 crore fine is immaterial for a ₹12L crore company |
| "HDFC Bank Q4 profit misses estimates by 8%" | 9 | 9 | This is exactly what moves a stock -3% |
| "Global banking stocks fall on US recession fears" | 5 | 7 | If HDFC moved with the sector, this is the actual reason |

---

## Cost & Latency Estimates

| Stage | Articles Processed | LLM Calls | Est. Token Cost | Time |
|---|---|---|---|---|
| Title-only coarse filter | ~150 | 1 batch call | ~5K tokens | ~3s |
| Scraping | ~40-50 | 0 | Free (HTTP) | ~30-60s (parallel) |
| Full-text deep scoring | ~30-40 (successful scrapes) | 30-40 individual calls OR 5-8 batched calls | ~100-200K tokens | ~30-60s |
| Event clustering | ~10-15 high-scorers | 1 call | ~10K tokens | ~5s |
| **Total** | | ~35-50 calls | ~120-220K tokens | ~2-3 min |

Compared to the current system (~3-6 LLM calls, ~15K tokens, ~30s), this is roughly **10-15x more expensive** but covers a full week with much higher accuracy.

### Cost Reduction Strategies
- Use a **cheaper model** for Stage 1 (title scoring) and summarization.
- Reserve the expensive model for the **final causal reasoning** pass.
- **Batch articles** in groups of 5-10 per LLM call instead of individual calls.
- **Truncate article text** to first 1500-2000 words (the key facts are usually in the first few paragraphs).
- **Cache scraping results** — if the same article URL appears for multiple holdings, scrape once.

---

## Alternative Idea: "Event-First" Instead of "Article-First"

Instead of starting from articles and filtering down, start from **known event types** that move stocks, and search for evidence of those events:

```
Known Stock-Moving Event Types:
  1. Quarterly earnings beat/miss
  2. Management changes (CEO exit, board reshuffles)
  3. Regulatory actions (RBI circulars, SEBI orders, fines)
  4. Credit rating changes
  5. Major contract wins/losses
  6. M&A announcements
  7. Analyst upgrades/downgrades
  8. Dividend/buyback announcements
  9. Sector policy changes (tariffs, subsidies, tax changes)
  10. Legal/litigation developments
  11. Promoter pledge/stake changes
  12. FII/DII bulk buying/selling

For each holding:
  → Search for evidence of each event type in the week's news
  → "Did HDFC Bank report earnings this week?"
  → "Were there any regulatory actions affecting HDFC Bank?"
  → "Did any analyst change their rating on HDFC Bank?"
```

This is a fundamentally different approach — **hypothesis-driven search** instead of **open-ended filtering**.

### Pros
- Very targeted — no noise.
- Structured output — each finding maps to a known event type.

### Cons
- Misses novel or unusual catalysts that don't fit known categories.
- Requires more complex prompting or multiple targeted RSS queries.

---

## Open Questions To Consider

1. **How many final articles per holding?**
   Currently: 3. For weekly analysis with richer filtering, should it be 3-5? Or should it be variable (however many genuinely explain the move)?

2. **Should we report "no catalyst found"?**
   If the best causal_score is < 5, should the output say "no strong news catalyst identified" instead of forcing weak articles into the output?

3. **Should we track intra-week daily correlation?**
   "This article was published Tuesday evening, and the stock dropped -2.1% on Wednesday" is a much stronger signal than "this article was published sometime this week."

4. **Model choice for each stage?**
   - Title filtering: Fast/cheap model (e.g., smaller 7-8B model)
   - Summarization: Medium model
   - Causal reasoning: Best available model (current `openai/gpt-oss-120b` or better)

5. **How to handle sector-wide moves?**
   If all 3 selected holdings are from Financial Services and all dropped ~2%, should we search for one sector-level catalyst instead of 3 separate company-level searches?

6. **Caching and incremental updates?**
   If this runs daily but analyzes the trailing week, most articles from yesterday's run are still relevant today. Should we cache scraped articles and only fetch new ones?

7. **What is the right "event day" threshold?**
   For large-cap stocks like HDFC Bank, a 1.5% daily move is significant. For mid-caps like GE Vernova T&D India, even 3-4% might be normal volatility. Should the threshold be adaptive based on historical volatility?

---

## Summary of All Approaches

| # | Approach | Strengths | Weaknesses | Cost |
|---|---|---|---|---|
| 1 | Multi-Stage Funnel | Balanced cost/accuracy, progressive filtering | Title-based first pass may miss boring-titled catalysts | Medium |
| 2 | Scrape Everything First | No false negatives, sees all content | High upfront scraping cost, many failures | High |
| 3 | Price-Anchored Day-by-Day | Dramatically narrows search, strong temporal signal | Misses gradual/multi-day catalysts | Low |
| 4 | Embedding Clustering | Elegant deduplication, ensures diverse events | Needs embedding model, clustering tuning | Medium |
| 5 | Two-Pass Causal Reasoning | Asks the RIGHT question (causality, not just relevance) | Expensive per-article LLM calls | High |
| 6 | Sector-Aware Filtering | Searches at the right abstraction level | Needs peer comparison data | Low-Medium |
| 7 | Confidence-Aware Output | Honest about uncertainty, avoids false attribution | More complex output schema | Free (design pattern) |
| Alt | Event-First Hypothesis Search | Very targeted, structured output | Misses novel catalysts | Medium |

**The recommended strategy combines elements from Approaches 1, 3, 5, 6, and 7** — using price decomposition to narrow the search (3), sector awareness to pick the right queries (6), a multi-stage funnel to manage cost (1), causal reasoning for deep scoring (5), and confidence awareness to avoid false attribution (7).
