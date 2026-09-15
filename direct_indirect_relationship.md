# Market Intelligence → Factor → Exposure → Impact → Attribution Engine

## Complete Technical Design for Mutual Fund Investor Explanation System

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Critical Evaluation of the Idea](#2-critical-evaluation-of-the-idea)
3. [Recommended Architecture](#3-recommended-architecture)
4. [Complete Data Model](#4-complete-data-model)
5. [Factor Taxonomy](#5-factor-taxonomy)
6. [Event Model](#6-event-model)
7. [Factor Graph](#7-factor-graph)
8. [Direct Relationship Engine](#8-direct-relationship-engine)
9. [Indirect Relationship Engine](#9-indirect-relationship-engine)
10. [Security Exposure Model](#10-security-exposure-model)
11. [Mutual Fund Exposure Model](#11-mutual-fund-exposure-model)
12. [Historical Sensitivity Model](#12-historical-sensitivity-model)
13. [Impact Calculation](#13-impact-calculation)
14. [Attribution Methodology](#14-attribution-methodology)
15. [Actual vs Expected Methodology](#15-actual-vs-expected-methodology)
16. [Benchmark Attribution](#16-benchmark-attribution)
17. [Time Decay](#17-time-decay)
18. [Market Regimes](#18-market-regimes)
19. [News Pipeline](#19-news-pipeline)
20. [LLM Architecture](#20-llm-architecture)
21. [LLM Prompts](#21-llm-prompts)
22. [Python Project Structure](#22-python-project-structure)
23. [Database Design](#23-database-design)
24. [Pydantic Models](#24-pydantic-models)
25. [Core Python Pseudocode](#25-core-python-pseudocode)
26. [Example End-to-End Calculation](#26-example-end-to-end-calculation)
27. [Example Investor Output](#27-example-investor-output)
28. [Testing Strategy](#28-testing-strategy)
29. [MVP Architecture](#29-mvp-architecture)
30. [Production Architecture](#30-production-architecture)
31. [Major Failure Modes](#31-major-failure-modes)
32. [Recommended Implementation Roadmap](#32-recommended-implementation-roadmap)

---

## 1. Executive Summary

### What This System Does

This system answers a single question for mutual fund investors:

> **"Given everything important happening in the market right now, why is this particular mutual fund performing the way it is, what is helping it, what is hurting it, and how confident are we in those explanations?"**

### The Fundamental Innovation

The system does NOT connect news articles directly to stocks. Instead, it builds a multi-layered causal chain:

```
Market News
  → Normalized Market Events
    → Market Factors (economic primitives)
      → Factor Relationships (direct + indirect paths)
        → Security-Level Factor Exposure
          → Fund-Level Factor Exposure (weighted)
            → Historical Sensitivity (statistical validation)
              → Expected Impact (quantified)
                → Comparison with Actual NAV Movement
                  → Attribution (ranked, confidence-scored)
                    → Investor-Friendly Explanation (LLM-generated)
```

### Why This Architecture Is Superior

| Approach | Example | Problem |
|---|---|---|
| **News → Stock → Fund** (naïve) | "Article mentions Infosys; fund holds Infosys" | Misses 80% of market dynamics: macro forces, sector rotation, indirect effects |
| **News → Factor → Exposure → Fund** (this system) | "Crude oil rises → inflation pressure → rate expectations → growth stock valuations → fund impact" | Captures both direct and indirect causal chains with quantified confidence |

### Scale of the Problem

- **Input**: 200–500 market news articles per day
- **After deduplication and clustering**: 30–60 meaningful market events
- **After importance filtering**: 10–20 significant events
- **Factor impacts extracted**: 40–80 factor-event relationships
- **Through the factor graph**: 100–200 direct + indirect paths
- **Against the fund**: 15–30 measurable exposure points
- **Final output**: 5–10 ranked attribution reasons with confidence scores

---

## 2. Critical Evaluation of the Idea

### What Is Fundamentally Correct

1. **The factor-mediated approach is the right architecture.** Professional fund attribution (Barra, Axioma, MSCI) works exactly this way. Connecting news to factors before connecting to portfolios is how institutional investors think.

2. **Event normalization is essential.** Treating 20 articles as 20 impacts is a fatal flaw in most news-based systems. Clustering articles into events is correct and necessary.

3. **The direct/indirect distinction is valuable.** Markets transmit shocks through multiple channels. Crude oil affects airlines directly (fuel costs) and indirectly (inflation → rates → valuations). Both channels matter.

4. **Historical sensitivity validation is critical.** Theoretical exposure alone is unreliable. A fund may theoretically have exposure to crude oil, but that does not tell us how much its NAV actually responds to crude movements.

5. **Distinguishing explained vs unexplained movement is honest and correct.** Systems that explain 100% of movement are lying. Real markets have noise, flow-driven moves, and factors you cannot observe.

6. **Separating LLM from deterministic computation is architecturally sound.** LLMs should classify and explain; Python should calculate and validate.

### What Is Flawed or Dangerous

#### Flaw 1: The Exposure Vectors Are the Hardest Part, and You Are Underestimating This

> **Severity: HIGH**

The entire system depends on accurate `security_factor_exposure` vectors. If "HDFC Bank → interest_rates = +0.8" is wrong, every downstream calculation is wrong.

**The problem**: You proposed constructing these from "fundamental knowledge, LLM classification, historical data, regression, analyst rules, sector mappings, company financial statements, machine learning." This is not a list of solutions — it is a list of unsolved research problems.

**My recommendation**: For MVP, use a **tiered approach**:
- **Tier 1 (sector-based defaults)**: Every company inherits its sector's typical factor exposure. This is crude but fast.
- **Tier 2 (statistical regression)**: For the ~200 securities in the NIFTY 500, run rolling regressions of daily stock returns against observable factor proxies (crude oil futures, 10-year yield, USDINR, etc.). This gives you empirical betas.
- **Tier 3 (LLM-augmented)**: Use LLM to adjust sector defaults for company-specific characteristics (e.g., "IndiGo is an airline, so crude_oil exposure is -0.95, not the sector default of -0.3").

**Do NOT try to build perfect exposure vectors from day one.** Start with sector defaults and iterate.

#### Flaw 2: The Factor Relationship Graph Will Generate Nonsense If Not Carefully Constrained

> **Severity: HIGH**

A graph of factor relationships where "crude_oil → inflation → rates → bond_yields → equity_valuations → growth_stocks" will produce confident-sounding but potentially false causal chains. The problem is that:

- **Causal direction is not always clear.** Do higher rates cause weaker growth, or does weaker growth cause the central bank to cut rates? Both are true at different times.
- **Strength is regime-dependent.** Crude oil → inflation is strong when crude moves from $60 to $100 but negligible when it moves from $80 to $83.
- **Lag varies.** Crude oil → petrol prices is same-week. Crude oil → CPI inflation is 2-3 months. Crude oil → RBI rate action is 6-12 months.

**My recommendation**: 
- **Hard-code the factor graph for MVP.** Use a static, expert-curated set of ~50-80 edges. Do NOT let the LLM generate new edges dynamically.
- **Each edge must have a `regime_condition` field.** "This relationship is active when crude is above $80" or "This relationship is active when inflation is above 5%."
- **Cap the graph at depth 3 absolutely.** Depth 4+ chains are almost always nonsense.
- **Add a `known_exceptions` field.** "Crude → inflation is normally positive, but in a demand-destruction scenario, crude falls AND inflation falls."

#### Flaw 3: The Impact Formula Over-Specifies Precision

> **Severity: MEDIUM**

Your proposed formula:

```
Event Strength × Relationship Strength × Factor Exposure × Historical Sensitivity × Portfolio Weight × Confidence
```

This produces a number like "-0.28%" which looks precise but is built on 5 multiplicative estimates each with wide error bars. If each factor has ±30% error, the final number has ±83% error (0.7^5 = 0.17, so the range is 0.17x to 5.9x the point estimate).

**My recommendation**: 
- **Report ranges, not point estimates.** Instead of "-0.28%", report "-0.10% to -0.50%".
- **Or use ordinal buckets**: "Strong negative impact", "Moderate negative impact", "Slight negative impact", "Neutral", etc.
- **Never present more than 1 decimal place of precision.** "-0.28%" implies precision you don't have. "-0.3%" is more honest.
- **Use the numbers internally for ranking only.** The investor-facing output should use qualitative language.

#### Flaw 4: Monthly/Quarterly Portfolio Disclosure Creates a Fundamental Data Problem

> **Severity: HIGH**

Indian mutual funds disclose their complete portfolio monthly (with a 15-day lag for most funds). This means:
- You are analyzing today's market with last month's portfolio.
- The fund manager may have already sold the positions you think are causing the impact.
- For sectoral funds, the portfolio changes less, so this is less of a problem.
- For multi-cap or flexi-cap funds, portfolio turnover can be 50-100% per year, meaning positions change significantly month to month.

**My recommendation**:
- **Always display a "Portfolio as of" date.** "Based on holdings disclosed as of August 31, 2026."
- **Add a `stale_portfolio_risk` score.** If portfolio turnover is high, warn the investor.
- **For top holdings (which change least), the analysis is most reliable.** Focus the narrative on the top 10-15 holdings which are typically stable.
- **Use AMFI data for monthly portfolio updates.** Download from amfiindia.com or morningstar.in.

#### Flaw 5: You Are Assuming the Factor Graph Is Acyclic — It Is Not

> **Severity: MEDIUM**

Real markets have feedback loops:
- Higher interest rates → weaker economy → lower corporate earnings → lower equity prices → reduced wealth effect → lower consumption → weaker economy → even lower rates eventually
- INR weakness → higher imported inflation → higher rates → foreign capital inflow → INR strengthening

These are **cycles**, not DAGs. Your graph traversal must handle this.

**My recommendation**:
- **Treat the graph as a DAG for any single analysis run.** When propagating an event's impact, mark visited nodes and never revisit them. This prevents infinite loops.
- **The direction of the edge is context-dependent.** "In the current regime, the active direction of the rates↔growth edge is: higher rates → weaker growth."
- **Use topological sort when possible, cycle-breaking when not.**

#### Flaw 6: Attribution Decomposition Will Not Sum to 100%

> **Severity: MEDIUM**

You want to decompose the fund's return into attributable causes. In theory:

```
Actual Return = Σ(attributed impacts) + unexplained
```

In practice, the attributed impacts will NEVER sum to the actual return because:
- Factors interact (crude × INR is not crude + INR)
- Nonlinear effects (a 2% crude rise and a 10% crude rise have very different impacts)
- Missing factors (private information, block deals, fund flows)
- Timing misalignment (events and returns are on different time scales)

**My recommendation**:
- **Do NOT try to make attributions sum to the actual return.** This is a constraint that will force you to either inflate attributions or shrink the unexplained component artificially.
- **Instead, present attributions as "estimated contribution" with wide confidence bands.**
- **The unexplained component should be explicitly stated and can be large (40-60% is normal).**

### What Assumptions Are Dangerous

| Assumption | Why It's Dangerous | Mitigation |
|---|---|---|
| Factor exposures are stable | Companies change strategies, take on debt, enter new markets | Re-estimate exposures quarterly; use rolling regression windows |
| The LLM can reliably extract event-factor relationships | LLMs hallucinate causal relationships | Validate LLM output against a curated rule set; use LLM as classifier, not as oracle |
| Historical sensitivity predicts future sensitivity | Regime changes break all regressions | Use regime-conditional betas; display confidence intervals; be honest about structural breaks |
| The factor graph is complete | Missing edges mean missing causal chains | Accept incompleteness; the unexplained component captures this |
| News captures all relevant information | Much market-moving information is not in news (order flow, positioning, dealer inventory) | Always have a large unexplained component; never claim full attribution |

### What Should Be Built First (MVP Priority)

1. Event extraction + clustering (this is the most unique value)
2. Factor mapping (static, expert-curated)
3. Fund exposure (sector-based defaults)
4. Simple impact ranking
5. LLM explanation

### What Should Be Postponed

1. Historical sensitivity (requires significant data infrastructure)
2. Regime detection (requires research)
3. Benchmark attribution (requires benchmark holdings data)
4. Factor graph propagation beyond depth 1 (direct only for MVP)
5. Nonlinear interaction effects

---

## 3. Recommended Architecture

### High-Level Architecture

```
                        ALL MARKET NEWS
                              │
                    ┌─────────▼──────────┐
                    │   NEWS PIPELINE     │
                    │  collect → dedupe   │
                    │  → cluster → score  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │   EVENT ENGINE      │
                    │  30-60 normalized   │
                    │  market events      │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │ FACTOR EXTRACTION   │
                    │  LLM + rules map    │
                    │  events → factors   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  FACTOR GRAPH       │
                    │  static curated     │
                    │  relationship graph │
                    └────┬─────────┬─────┘
                         │         │
              ┌──────────▼─┐  ┌───▼───────────┐
              │  DIRECT     │  │  INDIRECT      │
              │  PATHS      │  │  PATHS         │
              │  depth=0    │  │  depth=1,2,3   │
              └──────┬──────┘  └──────┬────────┘
                     │                │
                     └────────┬───────┘
                              │
                    ┌─────────▼──────────┐
                    │  FUND EXPOSURE      │
                    │  holdings × factor  │
                    │  exposure vectors   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  SENSITIVITY        │
                    │  (Phase 2+)         │
                    │  historical betas   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  IMPACT MODEL       │
                    │  quantified per     │
                    │  factor per event   │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  ATTRIBUTION        │
                    │  ranked, scored,    │
                    │  deduplicated       │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  ACTUAL vs EXPECTED │
                    │  explained /        │
                    │  unexplained split  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  LLM EXPLANATION    │
                    │  investor-friendly  │
                    │  narrative          │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │  INVESTOR INSIGHT   │
                    │  final output       │
                    └─────────────────────┘
```

### Layer Responsibility Matrix

| Layer | Owner | Input | Output |
|---|---|---|---|
| News Collection | Python (HTTP/RSS) | RSS feeds, API calls | Raw articles |
| Deduplication | Python (hashing + fuzzy) | Raw articles | Unique articles |
| Event Clustering | LLM + embeddings | Unique articles | Normalized events |
| Event Importance | Python + LLM | Events with article count, source quality | Scored events |
| Factor Extraction | LLM (structured output) | Events | Event → factor mappings |
| Factor Graph | Python (NetworkX) | Static graph definition | Traversal paths |
| Path Propagation | Python (BFS/DFS) | Factor graph + event-factor scores | Direct + indirect impact paths |
| Security Exposure | Python + data (statistical/curated) | Security metadata, historical prices | Exposure vectors |
| Fund Exposure | Python (arithmetic) | Holdings × security exposure | Fund-level exposure vector |
| Historical Sensitivity | Python (statsmodels) | NAV history, factor proxy time series | Beta coefficients |
| Impact Calculation | Python (arithmetic) | All above | Quantified impact estimates |
| Attribution | Python (sorting, dedup) | Impact estimates | Ranked contributors |
| Actual vs Expected | Python (comparison) | Attribution sum, actual NAV change | Explained / unexplained split |
| Explanation | LLM | Attribution data, fund context | Investor narrative |

---

## 4. Complete Data Model

### Entity Relationship Overview

```
NewsArticle ─┬─► ArticleEvent ──► MarketEvent ──► EventFactorImpact ──► Factor
             │                                                            │
             │                                              FactorRelationship
             │                                                            │
             │                                              SecurityFactorExposure
             │                                                    │
             │                                              FundHolding
             │                                                    │
             │                                              Fund ──► FundFactorExposure
             │                                                    │
             │                                              HistoricalSensitivity
             │                                                    │
             │                                              ImpactEstimate
             │                                                    │
             │                                              Attribution
             │                                                    │
             └──────────────────────────────────────────► InvestorExplanation
```

### Core Entities

| Entity | Description | Key Fields |
|---|---|---|
| `NewsArticle` | A single article from a news source | id, url, title, text, source, published_at, scraped_at |
| `MarketEvent` | A normalized, deduplicated market event | id, event_type, title, summary, importance, confidence, freshness, first_seen, last_seen |
| `ArticleEvent` | Many-to-many link: which articles support which event | article_id, event_id, is_primary |
| `Factor` | A single market factor from the taxonomy | id, code, name, category, parent_id, level |
| `EventFactorImpact` | How an event affects a factor | event_id, factor_id, direction, strength, confidence, time_horizon, evidence |
| `FactorRelationship` | An edge in the factor graph | source_factor_id, target_factor_id, relationship_type, strength, lag, regime_condition |
| `Security` | A stock, bond, or other security | id, ticker, name, sector, industry, market_cap_category |
| `SecurityFactorExposure` | A security's exposure to a factor | security_id, factor_id, exposure, confidence, source, as_of_date |
| `Fund` | A mutual fund | id, name, category, benchmark, amc |
| `FundHolding` | A security held by a fund | fund_id, security_id, weight, as_of_date |
| `FundFactorExposure` | Computed fund-level factor exposure | fund_id, factor_id, exposure, computed_at |
| `HistoricalSensitivity` | Regression-based sensitivity | fund_id, factor_id, beta, r_squared, p_value, window_start, window_end |
| `ImpactEstimate` | Estimated impact of an event on a fund | fund_id, event_id, factor_id, path_type, path_depth, estimated_impact_bps, confidence |
| `Attribution` | Ranked impact attribution | fund_id, analysis_date, event_id, rank, impact_bps, impact_category, confidence |
| `InvestorExplanation` | Final generated explanation | fund_id, analysis_date, explanation_text, explained_pct, unexplained_pct, confidence |

---

## 5. Factor Taxonomy

### Design Principles

1. **Hierarchical**: Macro → Category → Specific Factor
2. **Exhaustive for Indian markets**: Cover all material factors for Indian mutual funds
3. **Non-redundant**: No two factors should measure the same thing
4. **Extensible**: New factors can be added without restructuring
5. **Observable**: Each factor should have at least one market-observable proxy for regression

### Complete Factor Taxonomy for Indian Mutual Funds

```
FACTOR TAXONOMY
├── MACRO_DOMESTIC
│   ├── interest_rates                    Proxy: India 10Y Govt Bond Yield
│   ├── short_term_rates                  Proxy: 91-day T-bill rate
│   ├── rate_expectations                 Proxy: OIS 1Y rate
│   ├── inflation_actual                  Proxy: CPI YoY
│   ├── inflation_expectations            Proxy: breakeven inflation from IL bonds
│   ├── gdp_growth                        Proxy: IIP / GDP advance estimates
│   ├── credit_growth                     Proxy: RBI credit growth data
│   ├── liquidity                         Proxy: RBI net liquidity injection
│   ├── fiscal_deficit                    Proxy: Govt fiscal deficit data
│   ├── monetary_policy                   Proxy: RBI repo rate
│   ├── government_spending               Proxy: Govt capex data
│   └── tax_policy                        Proxy: Budget announcements
│
├── MACRO_GLOBAL
│   ├── us_interest_rates                 Proxy: US 10Y Treasury Yield
│   ├── us_growth                         Proxy: US GDP / PMI
│   ├── china_growth                      Proxy: China PMI / GDP
│   ├── europe_growth                     Proxy: EU PMI
│   ├── global_risk_sentiment             Proxy: VIX Index
│   ├── global_liquidity                  Proxy: Major central bank balance sheets
│   ├── global_trade                      Proxy: Baltic Dry Index / WTO data
│   └── geopolitical_risk                 Proxy: GPR Index / event-based
│
├── CURRENCY
│   ├── inr_usd                           Proxy: USDINR spot
│   ├── inr_eur                           Proxy: EURINR
│   ├── dxy                               Proxy: US Dollar Index
│   └── em_currencies                     Proxy: MSCI EM Currency Index
│
├── COMMODITIES
│   ├── crude_oil                         Proxy: Brent Crude Futures
│   ├── natural_gas                       Proxy: Henry Hub / India spot LNG
│   ├── gold                              Proxy: Gold spot price
│   ├── silver                            Proxy: Silver spot
│   ├── copper                            Proxy: LME Copper
│   ├── steel                             Proxy: HRC steel price India
│   ├── aluminum                          Proxy: LME Aluminum
│   ├── agricultural_commodities          Proxy: FAO Food Price Index
│   └── coal                              Proxy: Newcastle coal futures
│
├── MARKET_STRUCTURE
│   ├── equity_valuations                 Proxy: Nifty PE ratio
│   ├── bond_yields_domestic              Proxy: India 10Y yield
│   ├── fii_fpi_flows                     Proxy: NSDL FPI flow data
│   ├── dii_flows                         Proxy: AMFI DII flow data
│   ├── ipo_supply                        Proxy: IPO calendar / size
│   ├── market_volatility                 Proxy: India VIX
│   ├── market_breadth                    Proxy: Advance/decline ratio
│   ├── market_momentum                   Proxy: Nifty 50 returns
│   └── small_mid_cap_premium             Proxy: Nifty Smallcap/Nifty ratio
│
├── SECTOR_FACTORS
│   ├── it_spending                       Proxy: Gartner IT spending forecast / US tech capex
│   ├── banking_credit_demand             Proxy: Bank-wise credit growth
│   ├── banking_asset_quality             Proxy: GNPA ratios
│   ├── consumer_demand                   Proxy: Auto sales, FMCG volume growth
│   ├── auto_demand                       Proxy: SIAM monthly auto sales
│   ├── real_estate_demand                Proxy: PropEquity / Knight Frank data
│   ├── pharma_regulation                 Proxy: USFDA actions, ANDA approvals
│   ├── infrastructure_spending           Proxy: Govt infra capex, order book data
│   ├── telecom_arpu                      Proxy: TRAI data, company disclosures
│   ├── energy_demand                     Proxy: Power demand growth / petroleum consumption
│   ├── export_competitiveness            Proxy: REER, export growth data
│   ├── input_costs                       Proxy: WPI, PPI
│   └── wage_inflation                    Proxy: EPFO data, IT salary surveys
│
└── THEMATIC
    ├── esg_regulation                    Proxy: SEBI ESG guidelines
    ├── digital_adoption                  Proxy: UPI volumes, internet penetration
    ├── manufacturing_pli                 Proxy: PLI scheme disbursements
    ├── china_plus_one                    Proxy: FDI inflows to India manufacturing
    └── energy_transition                 Proxy: Renewable capacity additions
```

### Factor Representation in Code

```python
# factors/taxonomy.py

class FactorCategory(str, Enum):
    MACRO_DOMESTIC = "macro_domestic"
    MACRO_GLOBAL = "macro_global"
    CURRENCY = "currency"
    COMMODITIES = "commodities"
    MARKET_STRUCTURE = "market_structure"
    SECTOR_FACTORS = "sector_factors"
    THEMATIC = "thematic"

class FactorLevel(str, Enum):
    L1_CATEGORY = "l1_category"      # e.g., MACRO_DOMESTIC
    L2_FACTOR = "l2_factor"          # e.g., interest_rates
    L3_SUBFACTOR = "l3_subfactor"    # e.g., short_term_rates (optional)

FACTOR_REGISTRY = {
    "interest_rates": {
        "code": "interest_rates",
        "name": "Domestic Interest Rates",
        "category": FactorCategory.MACRO_DOMESTIC,
        "level": FactorLevel.L2_FACTOR,
        "parent": None,
        "proxy_ticker": "IN10Y.NS",  # or equivalent data source
        "proxy_description": "India 10-Year Government Bond Yield",
        "observable": True,
        "aliases": ["rates", "bond yields", "lending rates", "repo rate impact"],
    },
    # ... all other factors ...
}
```

### How New Factors Are Added

1. Add entry to `FACTOR_REGISTRY` with code, name, category, proxy
2. Add default sector exposure mappings in `SECTOR_FACTOR_DEFAULTS`
3. Add edges to the factor relationship graph if applicable
4. The system automatically picks up new factors in the next analysis run

### Redundancy Analysis

| Factor | Potential Overlap | Resolution |
|---|---|---|
| `interest_rates` vs `bond_yields_domestic` | Bond yields ARE interest rates | Keep both: `interest_rates` = policy rate expectations; `bond_yields_domestic` = market pricing |
| `inflation_actual` vs `inflation_expectations` | Related but distinct | Keep both: backward-looking vs forward-looking |
| `crude_oil` vs `input_costs` | Crude is a component of input costs | Keep both: crude_oil is specific; input_costs is aggregate |
| `inr_usd` vs `dxy` | DXY drives INR | Keep both: INR has India-specific dynamics beyond DXY |
| `fii_fpi_flows` vs `global_risk_sentiment` | Risk-off drives FII selling | Keep both: FII flows have India-specific components |

**Rule**: Two factors are NOT redundant if they can move independently under at least one realistic scenario.

---

## 6. Event Model

### Event Lifecycle

```
ARTICLES (raw)
     │
     ▼
ARTICLE CLUSTERS (semantically grouped)
     │
     ▼
MARKET EVENTS (normalized, scored)
     │
     ▼
EVENT-FACTOR MAPPINGS (what factors each event affects)
```

### Article Deduplication

**Step 1: Exact URL deduplication**
```python
def deduplicate_urls(articles: list[NewsArticle]) -> list[NewsArticle]:
    seen_urls = set()
    unique = []
    for article in articles:
        canonical = canonicalize_url(article.url)  # strip tracking params
        if canonical not in seen_urls:
            seen_urls.add(canonical)
            unique.append(article)
    return unique
```

**Step 2: Near-duplicate title detection**
```python
def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity of word sets after normalization."""
    words_a = set(normalize_title(a).split())
    words_b = set(normalize_title(b).split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)

def deduplicate_titles(articles: list[NewsArticle], threshold: float = 0.75) -> list[NewsArticle]:
    """Remove articles with near-identical titles, keeping the one from
    the most reputable source."""
    # Sort by source credibility descending so we keep the best version
    articles.sort(key=lambda a: SOURCE_CREDIBILITY.get(a.source, 0.5), reverse=True)
    kept = []
    for article in articles:
        is_duplicate = False
        for existing in kept:
            if title_similarity(article.title, existing.title) > threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(article)
    return kept
```

### Semantic Clustering (Articles → Events)

**Approach**: Sentence-transformer embeddings + agglomerative clustering.

```python
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

def cluster_into_events(articles: list[NewsArticle], similarity_threshold: float = 0.80) -> list[ArticleCluster]:
    model = SentenceTransformer("all-MiniLM-L6-v2")
    
    # Embed title + first 200 words
    texts = [f"{a.title}. {a.text[:500]}" for a in articles]
    embeddings = model.encode(texts)
    
    # Agglomerative clustering with cosine distance
    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=1 - similarity_threshold,  # cosine distance
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(embeddings)
    
    # Group articles by cluster label
    clusters = defaultdict(list)
    for article, label in zip(articles, labels):
        clusters[label].append(article)
    
    return [
        ArticleCluster(
            articles=cluster_articles,
            primary_article=max(cluster_articles, key=lambda a: len(a.text or "")),
        )
        for cluster_articles in clusters.values()
    ]
```

### Event Normalization

Each cluster becomes a normalized `MarketEvent`:

```json
{
    "event_id": "EV-2026-09-14-001",
    "event_type": "geopolitical",
    "title": "Geopolitical tensions push crude oil higher",
    "summary": "Brent crude rose 4.2% to $92/barrel following escalation in Middle East geopolitical tensions, with Houthi attacks on Red Sea shipping continuing.",
    "importance": 0.88,
    "confidence": 0.95,
    "freshness": 0.90,
    "novelty": 0.75,
    "severity": 0.80,
    "duration_estimate": "medium_term",
    "first_seen": "2026-09-12T08:00:00Z",
    "last_seen": "2026-09-14T06:00:00Z",
    "article_count": 14,
    "source_count": 9,
    "source_diversity": 0.85
}
```

### Event Importance Scoring

> **CRITICAL**: Multiple sources reporting the same event should NOT increase importance. Source count affects CONFIDENCE, not IMPORTANCE.

```python
def score_event_importance(event: MarketEvent) -> float:
    """
    Importance is about the magnitude and breadth of the event's 
    potential market impact, NOT about how many outlets covered it.
    """
    # Component 1: Inherent magnitude (LLM-assessed or rule-based)
    magnitude = event.llm_assessed_magnitude  # 0-1
    
    # Component 2: Breadth of impact (how many sectors/factors affected)
    breadth = len(event.affected_factors) / 10.0  # normalize to 0-1
    breadth = min(breadth, 1.0)
    
    # Component 3: Novelty (is this a new development or continuation?)
    novelty = event.novelty  # 0-1, where 1 = completely new
    
    # Component 4: Severity (how extreme is the event?)
    severity = event.severity  # 0-1
    
    importance = (
        0.35 * magnitude +
        0.25 * breadth +
        0.20 * novelty +
        0.20 * severity
    )
    
    return round(importance, 3)

def score_event_confidence(event: MarketEvent) -> float:
    """
    Confidence is about how sure we are that the event is real 
    and accurately described. THIS is where source count matters.
    """
    # More sources = more confident the event is real (with diminishing returns)
    source_factor = min(event.source_count / 5.0, 1.0)  # saturates at 5 sources
    
    # Higher credibility sources = higher confidence
    avg_credibility = mean([SOURCE_CREDIBILITY.get(s, 0.5) for s in event.sources])
    
    # Consistent reporting = higher confidence (low variance in descriptions)
    consistency = event.internal_consistency  # 0-1, from embedding variance
    
    confidence = (
        0.40 * source_factor +
        0.35 * avg_credibility +
        0.25 * consistency
    )
    
    return round(confidence, 3)
```

### Preventing Artificial Importance Inflation

| Problem | Solution |
|---|---|
| 20 articles about same event inflate importance | Cluster first, score events (not articles) |
| Major outlet + 19 aggregator copies | Track `source_diversity` = unique sources / total articles |
| Repetitive coverage over multiple days | Track `first_seen` and `last_seen`; importance doesn't grow with duration |
| Sensationalized headlines | Use article body, not just headlines, for magnitude assessment |
| Wire service syndication (PTI → 50 outlets) | Deduplicate by content similarity before counting sources |

### Event Freshness

```python
def compute_freshness(event: MarketEvent, analysis_time: datetime) -> float:
    """How recent is this event? Decays exponentially."""
    hours_since = (analysis_time - event.last_seen).total_seconds() / 3600
    
    # Half-life of 24 hours
    freshness = math.exp(-0.693 * hours_since / 24)
    
    return round(freshness, 3)
```

### Event Duration and Persistence

```python
class EventDuration(str, Enum):
    FLASH = "flash"              # < 1 day (flash crash, single announcement)
    SHORT_TERM = "short_term"    # 1-5 days (earnings, short-term supply disruption)
    MEDIUM_TERM = "medium_term"  # 1-4 weeks (policy change, geopolitical escalation)
    STRUCTURAL = "structural"    # 1+ months (regime change, structural reform)
```

### Event Type Taxonomy

```python
class EventType(str, Enum):
    GEOPOLITICAL = "geopolitical"
    MONETARY_POLICY = "monetary_policy"
    FISCAL_POLICY = "fiscal_policy"
    COMMODITY_PRICE = "commodity_price"
    CURRENCY_MOVE = "currency_move"
    EARNINGS = "earnings"
    REGULATORY = "regulatory"
    ECONOMIC_DATA = "economic_data"
    GLOBAL_MARKET = "global_market"
    FUND_FLOWS = "fund_flows"
    CREDIT_EVENT = "credit_event"
    TRADE_POLICY = "trade_policy"
    SECTOR_DEVELOPMENT = "sector_development"
    CORPORATE_ACTION = "corporate_action"
    TECHNICAL_MARKET = "technical_market"
```

---

## 7. Factor Graph

### Graph Technology Choice

**Recommendation: NetworkX (in-memory) for MVP, with PostgreSQL adjacency-list table for persistence.**

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **NetworkX** | Simple, Python-native, fast for small graphs (<500 nodes) | In-memory only, no native persistence | ✅ MVP |
| **Neo4j** | Beautiful graph queries, visual tools | Operational overhead, another service to run | ❌ Overkill |
| **PostgreSQL tables** | Already in stack, good for persistence and queries | Recursive CTEs for path finding are awkward | ✅ Persistence layer |
| **NetworkX + PostgreSQL** | Best of both: fast traversal + durable storage | Two representations to keep in sync | ✅ Production |

### Graph Schema

#### Node Schema

```python
@dataclass
class FactorNode:
    factor_id: str                    # e.g., "crude_oil"
    name: str                         # e.g., "Crude Oil Prices"
    category: FactorCategory          # e.g., COMMODITIES
    level: FactorLevel                # e.g., L2_FACTOR
    observable: bool                  # Can we get market data for this?
    proxy_ticker: Optional[str]       # e.g., "BZ=F" for Brent crude
    current_value: Optional[float]    # Latest observed value
    current_regime: Optional[str]     # e.g., "high" / "normal" / "low"
```

#### Edge Schema

```python
@dataclass
class FactorEdge:
    source: str                       # Source factor code
    target: str                       # Target factor code
    relationship: RelationshipType    # POSITIVE, NEGATIVE, CONDITIONAL
    base_strength: float              # 0.0 to 1.0
    confidence: float                 # 0.0 to 1.0
    lag: TimeLag                      # IMMEDIATE, DAYS, WEEKS, MONTHS
    regime_condition: Optional[str]   # e.g., "active when crude > $80"
    mechanism: str                    # Human-readable: "Higher crude increases import bill"
    evidence_type: EvidenceType       # EMPIRICAL, THEORETICAL, MIXED
    bidirectional: bool               # True if relationship can reverse
    active_direction: Optional[str]   # Current active direction if bidirectional
```

#### Relationship Types

```python
class RelationshipType(str, Enum):
    POSITIVE = "positive"        # Source ↑ → Target ↑
    NEGATIVE = "negative"        # Source ↑ → Target ↓
    CONDITIONAL = "conditional"  # Depends on regime
    NONLINEAR = "nonlinear"      # Direction changes with magnitude

class TimeLag(str, Enum):
    IMMEDIATE = "immediate"      # Same day / intraday
    DAYS = "days"                # 1-5 business days
    WEEKS = "weeks"              # 1-4 weeks
    MONTHS = "months"            # 1-3 months
    QUARTERS = "quarters"        # 3-12 months

class EvidenceType(str, Enum):
    EMPIRICAL = "empirical"      # Validated by historical data
    THEORETICAL = "theoretical"  # Economic theory
    MIXED = "mixed"              # Some empirical, some theoretical
```

### Example Factor Graph Edges (Curated)

```python
FACTOR_GRAPH_EDGES = [
    # === CRUDE OIL TRANSMISSION CHANNELS ===
    FactorEdge(
        source="crude_oil", target="inflation_expectations",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.75,
        confidence=0.90,
        lag=TimeLag.WEEKS,
        mechanism="Higher crude increases fuel and transport costs, feeding into inflation expectations",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="crude_oil", target="inr_usd",
        relationship=RelationshipType.NEGATIVE,  # crude ↑ → INR weakens (INR/USD ↓)
        base_strength=0.65,
        confidence=0.85,
        lag=TimeLag.DAYS,
        mechanism="India imports ~85% of crude; higher prices increase import bill, pressuring INR",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="crude_oil", target="input_costs",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.80,
        confidence=0.92,
        lag=TimeLag.IMMEDIATE,
        mechanism="Crude is a key input for manufacturing, chemicals, transport",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="crude_oil", target="fiscal_deficit",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.50,
        confidence=0.70,
        lag=TimeLag.MONTHS,
        mechanism="If govt absorbs fuel price rise through subsidies, fiscal deficit worsens",
        regime_condition="active when govt controls fuel prices",
        evidence_type=EvidenceType.MIXED,
    ),
    
    # === INFLATION TRANSMISSION ===
    FactorEdge(
        source="inflation_expectations", target="rate_expectations",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.80,
        confidence=0.90,
        lag=TimeLag.WEEKS,
        mechanism="Higher inflation expectations lead to expectations of tighter monetary policy",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="inflation_expectations", target="consumer_demand",
        relationship=RelationshipType.NEGATIVE,
        base_strength=0.50,
        confidence=0.70,
        lag=TimeLag.MONTHS,
        mechanism="Higher inflation erodes purchasing power, reducing discretionary spending",
        evidence_type=EvidenceType.MIXED,
    ),
    
    # === INTEREST RATE TRANSMISSION ===
    FactorEdge(
        source="rate_expectations", target="bond_yields_domestic",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.90,
        confidence=0.95,
        lag=TimeLag.IMMEDIATE,
        mechanism="Rate expectations directly drive bond yields through expectations hypothesis",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="rate_expectations", target="equity_valuations",
        relationship=RelationshipType.NEGATIVE,
        base_strength=0.65,
        confidence=0.80,
        lag=TimeLag.DAYS,
        mechanism="Higher discount rates compress equity valuations (DCF effect)",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="rate_expectations", target="banking_credit_demand",
        relationship=RelationshipType.NEGATIVE,
        base_strength=0.55,
        confidence=0.75,
        lag=TimeLag.MONTHS,
        mechanism="Higher rates reduce loan demand, slowing credit growth",
        evidence_type=EvidenceType.MIXED,
    ),
    
    # === CURRENCY TRANSMISSION ===
    FactorEdge(
        source="inr_usd", target="it_spending",
        relationship=RelationshipType.POSITIVE,  # INR weakness HELPS IT (earn in USD)
        base_strength=0.70,
        confidence=0.85,
        lag=TimeLag.IMMEDIATE,
        mechanism="IT companies earn in USD; weaker INR increases INR revenue/profit",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="inr_usd", target="input_costs",
        relationship=RelationshipType.NEGATIVE,  # INR weakness increases import costs
        base_strength=0.75,
        confidence=0.90,
        lag=TimeLag.DAYS,
        mechanism="Weaker INR makes imports more expensive",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    
    # === GLOBAL TRANSMISSION ===
    FactorEdge(
        source="us_interest_rates", target="fii_fpi_flows",
        relationship=RelationshipType.NEGATIVE,
        base_strength=0.60,
        confidence=0.75,
        lag=TimeLag.DAYS,
        mechanism="Higher US yields attract capital away from emerging markets including India",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="fii_fpi_flows", target="market_momentum",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.65,
        confidence=0.80,
        lag=TimeLag.IMMEDIATE,
        mechanism="FII buying/selling directly impacts market prices and sentiment",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    FactorEdge(
        source="global_risk_sentiment", target="fii_fpi_flows",
        relationship=RelationshipType.POSITIVE,  # risk-on → FII buying
        base_strength=0.70,
        confidence=0.80,
        lag=TimeLag.IMMEDIATE,
        mechanism="Risk-off sentiment triggers FII selling from emerging markets",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    
    # === LIQUIDITY TRANSMISSION ===
    FactorEdge(
        source="liquidity", target="equity_valuations",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.60,
        confidence=0.75,
        lag=TimeLag.WEEKS,
        mechanism="Easier liquidity supports asset prices through multiple channels",
        evidence_type=EvidenceType.MIXED,
    ),
    FactorEdge(
        source="liquidity", target="banking_credit_demand",
        relationship=RelationshipType.POSITIVE,
        base_strength=0.70,
        confidence=0.80,
        lag=TimeLag.WEEKS,
        mechanism="More system liquidity enables banks to lend more",
        evidence_type=EvidenceType.EMPIRICAL,
    ),
    
    # === INPUT COSTS TRANSMISSION ===
    FactorEdge(
        source="input_costs", target="consumer_demand",
        relationship=RelationshipType.NEGATIVE,
        base_strength=0.45,
        confidence=0.65,
        lag=TimeLag.MONTHS,
        mechanism="Higher input costs may be passed through as higher prices, reducing demand",
        evidence_type=EvidenceType.MIXED,
    ),
]
```

### Graph Traversal

```python
import networkx as nx

class FactorGraph:
    def __init__(self, edges: list[FactorEdge]):
        self.G = nx.DiGraph()
        for edge in edges:
            self.G.add_edge(
                edge.source, 
                edge.target,
                **asdict(edge),
            )
    
    def find_all_paths(
        self, 
        source_factor: str, 
        max_depth: int = 3,
        min_path_strength: float = 0.10,
    ) -> list[FactorPath]:
        """Find all paths from a source factor to any reachable factor,
        up to max_depth, with cumulative strength above min_path_strength."""
        paths = []
        
        def dfs(current: str, path: list[str], cumulative_strength: float, 
                cumulative_direction: int, depth: int, visited: set):
            if depth > max_depth:
                return
            if current in visited:
                return  # Prevent cycles
            
            visited.add(current)
            
            for neighbor in self.G.successors(current):
                edge = self.G.edges[current, neighbor]
                
                # Calculate cumulative strength with decay
                edge_strength = edge["base_strength"]
                new_strength = cumulative_strength * edge_strength
                
                # Determine cumulative direction
                if edge["relationship"] == "negative":
                    new_direction = -cumulative_direction
                else:
                    new_direction = cumulative_direction
                
                # Only keep paths with meaningful strength
                if new_strength >= min_path_strength:
                    new_path = path + [neighbor]
                    
                    paths.append(FactorPath(
                        factors=new_path,
                        depth=depth + 1,
                        cumulative_strength=new_strength,
                        cumulative_direction=new_direction,
                        edges=[self.G.edges[new_path[i], new_path[i+1]] 
                               for i in range(len(new_path)-1)],
                    ))
                    
                    # Continue deeper
                    dfs(neighbor, new_path, new_strength, new_direction, 
                        depth + 1, visited.copy())
        
        dfs(source_factor, [source_factor], 1.0, 1, 0, set())
        return paths
```

### Avoiding Common Graph Problems

| Problem | Solution |
|---|---|
| **Circular reasoning** | Track `visited` set during DFS; never revisit a node in the same path |
| **Nonsense long chains** | Max depth = 3; min cumulative strength = 0.10 |
| **Too many paths** | Rank by cumulative strength; keep top N per source factor |
| **Regime-dependent edges** | Check `regime_condition` against current market state before traversal |
| **Graph too large** | Fixed curated graph of ~50-80 edges; not dynamically generated |
| **Bidirectional confusion** | For bidirectional edges, check `active_direction` based on current regime |

---

## 8. Direct Relationship Engine

### Definition

A **direct relationship** is a path of depth 0 or 1:

```
Event → Factor → Security (depth 0: event directly affects a factor the security is exposed to)
Event → Factor → Factor → Security (depth 1: one intermediate factor)
```

### How Direct Paths Are Found

```python
def find_direct_impacts(
    event: MarketEvent,
    event_factor_impacts: list[EventFactorImpact],
    fund_holdings: list[FundHolding],
    security_exposures: dict[str, dict[str, float]],
) -> list[DirectImpact]:
    """
    For each factor directly affected by the event,
    check which securities in the fund are exposed to that factor.
    """
    impacts = []
    
    for efi in event_factor_impacts:
        factor = efi.factor_id
        
        for holding in fund_holdings:
            security_id = holding.security_id
            exposure = security_exposures.get(security_id, {}).get(factor, 0.0)
            
            if abs(exposure) < 0.05:  # Skip negligible exposures
                continue
            
            # Direction: event pushes factor in direction efi.direction
            # If exposure is positive and factor goes up, security benefits
            # If exposure is negative and factor goes up, security is hurt
            net_direction = efi.direction * (1 if exposure > 0 else -1)
            
            impact_strength = (
                efi.strength 
                * abs(exposure) 
                * holding.weight
            )
            
            impacts.append(DirectImpact(
                event_id=event.event_id,
                factor_id=factor,
                security_id=security_id,
                holding_weight=holding.weight,
                factor_exposure=exposure,
                event_factor_strength=efi.strength,
                net_direction=net_direction,
                impact_strength=impact_strength,
                path_depth=0,
                confidence=efi.confidence * 0.90,  # slight confidence decay
                explanation=f"{event.title} → {factor} → {holding.security_name}",
            ))
    
    return impacts
```

### Example Direct Relationships

```
Event: "Crude oil prices surge to $92/barrel"

Direct paths:
1. crude_oil ↑ → IndiGo (exposure: -0.95, weight: 3%)
   Impact: NEGATIVE, strength = 0.9 × 0.95 × 0.03 = 0.0257

2. crude_oil ↑ → Reliance (exposure: +0.60, weight: 5.5%)
   Impact: POSITIVE, strength = 0.9 × 0.60 × 0.055 = 0.0297

3. crude_oil ↑ → FMCG basket (exposure: -0.20, weight: 15%)
   Impact: NEGATIVE, strength = 0.9 × 0.20 × 0.15 = 0.0270
```

---

## 9. Indirect Relationship Engine

### Definition

An **indirect relationship** is a path of depth 2 or 3:

```
Event → Factor → Factor → Factor → Security (depth 2-3)
```

### Path Decay Function

Your proposed decay function:

```
depth 0 = 1.00
depth 1 = 0.70
depth 2 = 0.49
depth 3 = 0.34
```

**Evaluation**: This is a geometric decay with factor 0.70. This is reasonable but I'd recommend a **slightly steeper decay** for Indian markets because:

1. Transmission mechanisms in emerging markets are noisier
2. Multiple intermediary steps accumulate more uncertainty
3. Three hops away, you're often in speculation territory

**Recommended decay function**:

```python
def path_decay(depth: int, decay_rate: float = 0.60) -> float:
    """
    Geometric decay per hop.
    
    depth 0 = 1.00  (direct)
    depth 1 = 0.60  (one intermediary)
    depth 2 = 0.36  (two intermediaries)
    depth 3 = 0.22  (three intermediaries — barely meaningful)
    """
    return decay_rate ** depth
```

**Why 0.60 instead of 0.70**:

At depth 3 with 0.70 decay, you retain 34% of the signal. That is too high — a 3-hop chain like "crude → inflation → rates → equity valuations" should NOT be weighted at 34% of the direct crude impact. By the time you're 3 hops away, each intermediary relationship has uncertainty, and the compounding of uncertainties means the real signal is much weaker.

With 0.60 decay, depth 3 retains 22%, which is more honest.

### Better Mathematical Framework

Instead of a simple geometric decay, consider **multiplying the actual edge strengths along the path**:

```python
def compute_path_strength(path: FactorPath) -> float:
    """
    Cumulative strength is the PRODUCT of edge strengths along the path,
    multiplied by a depth penalty.
    
    This is better than simple geometric decay because it respects
    the actual relationship strengths.
    """
    # Product of edge strengths
    edge_product = 1.0
    for edge in path.edges:
        edge_product *= edge["base_strength"]
    
    # Depth penalty (additional discount beyond edge strengths)
    depth_penalty = 0.85 ** path.depth  # Mild additional penalty
    
    # Confidence discount (weakest link in the chain)
    min_confidence = min(edge["confidence"] for edge in path.edges)
    
    return edge_product * depth_penalty * min_confidence
```

**Example**:

Path: crude_oil → inflation_expectations → rate_expectations → equity_valuations

```
edge 1: crude → inflation,   strength = 0.75, confidence = 0.90
edge 2: inflation → rates,   strength = 0.80, confidence = 0.90
edge 3: rates → valuations,  strength = 0.65, confidence = 0.80

edge_product = 0.75 × 0.80 × 0.65 = 0.390
depth_penalty = 0.85^3 = 0.614
min_confidence = 0.80

path_strength = 0.390 × 0.614 × 0.80 = 0.192
```

This means the indirect path retains ~19% of the original event strength, which is reasonable for a 3-hop chain.

### Indirect Impact Computation

```python
def find_indirect_impacts(
    event: MarketEvent,
    event_factor_impacts: list[EventFactorImpact],
    factor_graph: FactorGraph,
    fund_holdings: list[FundHolding],
    security_exposures: dict[str, dict[str, float]],
    max_depth: int = 3,
) -> list[IndirectImpact]:
    """
    For each factor directly affected by the event,
    find all indirect paths through the factor graph,
    and check which securities at the end of each path are exposed.
    """
    impacts = []
    
    for efi in event_factor_impacts:
        source_factor = efi.factor_id
        
        # Find all reachable factors through the graph
        paths = factor_graph.find_all_paths(
            source_factor=source_factor,
            max_depth=max_depth,
            min_path_strength=0.10,  # Prune weak paths early
        )
        
        for path in paths:
            terminal_factor = path.factors[-1]
            
            for holding in fund_holdings:
                security_id = holding.security_id
                exposure = security_exposures.get(security_id, {}).get(terminal_factor, 0.0)
                
                if abs(exposure) < 0.05:
                    continue
                
                # Compute cumulative direction through the path
                cumulative_direction = efi.direction * path.cumulative_direction
                net_direction = cumulative_direction * (1 if exposure > 0 else -1)
                
                # Compute impact strength
                path_strength = compute_path_strength(path)
                impact_strength = (
                    efi.strength
                    * path_strength
                    * abs(exposure)
                    * holding.weight
                )
                
                impacts.append(IndirectImpact(
                    event_id=event.event_id,
                    source_factor=source_factor,
                    terminal_factor=terminal_factor,
                    path=path.factors,
                    path_depth=path.depth,
                    security_id=security_id,
                    holding_weight=holding.weight,
                    factor_exposure=exposure,
                    path_strength=path_strength,
                    net_direction=net_direction,
                    impact_strength=impact_strength,
                    confidence=efi.confidence * compute_path_confidence(path),
                    explanation=format_path_explanation(event, path, holding),
                ))
    
    return impacts
```

### Avoiding Double Counting in Direct + Indirect

```python
def deduplicate_impacts(
    direct_impacts: list[DirectImpact],
    indirect_impacts: list[IndirectImpact],
) -> list[Impact]:
    """
    If an event affects a security both directly and indirectly,
    keep the STRONGER path and reduce the weaker one.
    """
    # Group by (event_id, security_id)
    groups = defaultdict(list)
    for impact in direct_impacts + indirect_impacts:
        key = (impact.event_id, impact.security_id)
        groups[key].append(impact)
    
    final_impacts = []
    for key, group_impacts in groups.items():
        if len(group_impacts) == 1:
            final_impacts.append(group_impacts[0])
        else:
            # Sort by impact strength descending
            group_impacts.sort(key=lambda x: abs(x.impact_strength), reverse=True)
            
            # Keep the strongest path at full strength
            strongest = group_impacts[0]
            final_impacts.append(strongest)
            
            # For additional paths: only add if they represent
            # genuinely different causal mechanisms
            seen_terminal_factors = {strongest.terminal_factor if hasattr(strongest, 'terminal_factor') else strongest.factor_id}
            
            for additional in group_impacts[1:]:
                terminal = additional.terminal_factor if hasattr(additional, 'terminal_factor') else additional.factor_id
                if terminal not in seen_terminal_factors:
                    # Different mechanism — add at reduced strength
                    additional.impact_strength *= 0.50  # 50% discount for secondary paths
                    final_impacts.append(additional)
                    seen_terminal_factors.add(terminal)
                # else: skip — this is a duplicate causal mechanism
    
    return final_impacts
```

---

## 10. Security Exposure Model

### Exposure Vector Construction — Tiered Approach

#### Tier 1: Sector-Based Defaults (MVP)

```python
SECTOR_FACTOR_DEFAULTS = {
    "Financial Services": {
        "interest_rates": +0.70,
        "economic_growth": +0.80,
        "credit_growth": +0.85,
        "liquidity": +0.70,
        "inflation_actual": -0.30,
        "fii_fpi_flows": +0.50,
        "market_momentum": +0.60,
        "banking_asset_quality": +0.80,
        "banking_credit_demand": +0.85,
    },
    "Technology": {
        "us_growth": +0.75,
        "it_spending": +0.90,
        "inr_usd": -0.70,  # INR weakness helps (earn in USD)
        "global_risk_sentiment": +0.50,
        "interest_rates": -0.30,
        "dxy": -0.40,
    },
    "Energy": {
        "crude_oil": +0.80,
        "natural_gas": +0.50,
        "economic_growth": +0.60,
        "energy_demand": +0.85,
        "inr_usd": -0.20,
    },
    "Airlines": {
        "crude_oil": -0.90,
        "consumer_demand": +0.70,
        "inr_usd": -0.60,
        "economic_growth": +0.65,
    },
    "FMCG / Consumer Defensive": {
        "consumer_demand": +0.85,
        "inflation_actual": -0.40,
        "input_costs": -0.50,
        "economic_growth": +0.40,
        "interest_rates": -0.20,
        "inr_usd": -0.15,
    },
    "Pharmaceuticals": {
        "pharma_regulation": +0.80,
        "us_growth": +0.50,
        "inr_usd": -0.55,
        "crude_oil": -0.15,
    },
    "Industrials / Infrastructure": {
        "infrastructure_spending": +0.85,
        "government_spending": +0.75,
        "economic_growth": +0.80,
        "interest_rates": -0.40,
        "steel": +0.30,
        "crude_oil": -0.25,
    },
    "Automobiles": {
        "auto_demand": +0.90,
        "consumer_demand": +0.70,
        "interest_rates": -0.50,
        "steel": -0.40,
        "crude_oil": -0.30,
        "economic_growth": +0.75,
    },
    "Real Estate": {
        "real_estate_demand": +0.90,
        "interest_rates": -0.80,
        "economic_growth": +0.70,
        "liquidity": +0.75,
        "inflation_actual": -0.30,
    },
    "Metals & Mining": {
        "steel": +0.85,
        "copper": +0.70,
        "aluminum": +0.75,
        "economic_growth": +0.70,
        "china_growth": +0.65,
        "infrastructure_spending": +0.60,
    },
    "Telecom": {
        "telecom_arpu": +0.90,
        "consumer_demand": +0.50,
        "interest_rates": -0.30,
        "economic_growth": +0.45,
    },
}
```

#### Tier 2: Company-Specific LLM Adjustments

```python
def get_llm_adjusted_exposure(
    security: Security,
    sector_defaults: dict[str, float],
) -> dict[str, float]:
    """
    Use LLM to adjust sector defaults for company-specific characteristics.
    """
    prompt = f"""
    Company: {security.name}
    Sector: {security.sector}
    Industry: {security.industry}
    
    Default sector factor exposures:
    {json.dumps(sector_defaults, indent=2)}
    
    Adjust these exposures for the specific characteristics of {security.name}.
    Consider:
    - Revenue mix (domestic vs export)
    - Cost structure (raw material intensity)
    - Debt level (interest rate sensitivity)
    - Business model specifics
    
    Return adjusted exposures as JSON. Only change values where the company
    is meaningfully different from sector average. Keep values between -1.0 and +1.0.
    """
    # ... LLM call ...
```

#### Tier 3: Statistical Regression (Production)

```python
def compute_statistical_exposure(
    security_ticker: str,
    factor_proxies: dict[str, pd.Series],
    window_days: int = 252,
) -> dict[str, StatisticalExposure]:
    """
    Multi-factor regression of security daily returns against factor proxy returns.
    """
    import statsmodels.api as sm
    
    security_returns = get_daily_returns(security_ticker, window_days)
    
    # Build factor return matrix
    X = pd.DataFrame({
        factor: proxy_returns 
        for factor, proxy_returns in factor_proxies.items()
    }).dropna()
    
    # Align dates
    common_dates = security_returns.index.intersection(X.index)
    y = security_returns.loc[common_dates]
    X = X.loc[common_dates]
    
    # Add constant for intercept (alpha)
    X_with_const = sm.add_constant(X)
    
    # OLS regression
    model = sm.OLS(y, X_with_const).fit()
    
    exposures = {}
    for factor in factor_proxies:
        coef = model.params.get(factor, 0)
        pvalue = model.pvalues.get(factor, 1)
        
        exposures[factor] = StatisticalExposure(
            beta=coef,
            t_stat=model.tvalues.get(factor, 0),
            p_value=pvalue,
            significant=pvalue < 0.05,
        )
    
    return exposures
```

### Exposure Evolution Over Time

- **Sector defaults**: Update annually or when major industry shifts occur
- **LLM adjustments**: Re-run quarterly or when company announces major strategic changes
- **Statistical regression**: Roll window monthly; use 252-day (1-year) or 504-day (2-year) windows
- **Store historical exposures**: Keep an `as_of_date` field so you can compare exposure drift

---

## 11. Mutual Fund Exposure Model

### Basic Fund Exposure Calculation

```python
def compute_fund_factor_exposure(
    holdings: list[FundHolding],
    security_exposures: dict[str, dict[str, float]],
) -> dict[str, float]:
    """
    Fund factor exposure = weighted sum of security factor exposures.
    
    fund_exposure[factor] = Σ (holding_weight × security_exposure[factor])
    """
    fund_exposure = defaultdict(float)
    total_weight_with_exposure = 0.0
    
    for holding in holdings:
        sec_exposures = security_exposures.get(holding.security_id, {})
        if not sec_exposures:
            continue
        
        total_weight_with_exposure += holding.weight
        
        for factor, exposure in sec_exposures.items():
            fund_exposure[factor] += holding.weight * exposure
    
    return dict(fund_exposure)
```

### Handling Special Cases

#### Cash Holdings

```python
def handle_cash(fund: Fund, holdings: list[FundHolding]) -> dict[str, float]:
    """Cash has specific factor exposures."""
    equity_weight = sum(h.weight for h in holdings if h.asset_class == "equity")
    cash_weight = 1.0 - equity_weight
    
    cash_exposure = {
        "interest_rates": +0.30 * cash_weight,     # earns short-term rate
        "market_momentum": -cash_weight,             # cash drag in rising market
        "equity_valuations": 0.0,
        "market_volatility": +0.10 * cash_weight,    # relative benefit in volatile markets
    }
    return cash_exposure
```

#### Stale Portfolio Disclosures

```python
def compute_staleness_penalty(
    disclosure_date: date,
    analysis_date: date,
    fund_turnover_ratio: float,
) -> float:
    """
    How much should we trust the disclosed portfolio?
    """
    days_stale = (analysis_date - disclosure_date).days
    daily_turnover = fund_turnover_ratio / 252
    estimated_change = daily_turnover * days_stale
    confidence = max(1.0 - estimated_change, 0.50)
    return confidence
```

#### Benchmark-Relative Exposure (Active Exposure)

```python
def compute_active_exposure(
    fund_exposure: dict[str, float],
    benchmark_exposure: dict[str, float],
) -> dict[str, float]:
    """
    Active exposure = fund exposure - benchmark exposure.
    """
    all_factors = set(fund_exposure.keys()) | set(benchmark_exposure.keys())
    
    active = {}
    for factor in all_factors:
        fund_val = fund_exposure.get(factor, 0.0)
        bench_val = benchmark_exposure.get(factor, 0.0)
        active[factor] = fund_val - bench_val
    
    return active
```

---

## 12. Historical Sensitivity Model

### Recommended Approach: Rolling Multi-Factor Regression

```python
def estimate_fund_sensitivity(
    fund_nav_series: pd.Series,
    factor_proxy_series: dict[str, pd.Series],
    window: int = 126,               # ~6 months rolling window
    min_observations: int = 60,
) -> dict[str, SensitivityEstimate]:
    """
    Rolling OLS regression of fund daily returns against factor proxy returns.
    """
    import statsmodels.api as sm
    
    fund_returns = fund_nav_series.pct_change().dropna()
    factor_returns = {
        factor: series.pct_change().dropna()
        for factor, series in factor_proxy_series.items()
    }
    
    all_data = pd.DataFrame({"fund": fund_returns})
    for factor, returns in factor_returns.items():
        all_data[factor] = returns
    all_data = all_data.dropna()
    
    if len(all_data) < min_observations:
        return {}
    
    recent_data = all_data.tail(window)
    
    y = recent_data["fund"]
    X = recent_data.drop(columns=["fund"])
    X = sm.add_constant(X)
    
    # Handle multicollinearity
    X_clean = remove_multicollinear_factors(X, vif_threshold=5.0)
    
    model = sm.OLS(y, X_clean).fit()
    
    sensitivities = {}
    for factor in X_clean.columns:
        if factor == "const":
            continue
        
        sensitivities[factor] = SensitivityEstimate(
            factor_id=factor,
            beta=round(model.params[factor], 4),
            t_statistic=round(model.tvalues[factor], 2),
            p_value=round(model.pvalues[factor], 4),
            is_significant=model.pvalues[factor] < 0.05,
            confidence_interval_lower=round(model.conf_int().loc[factor, 0], 4),
            confidence_interval_upper=round(model.conf_int().loc[factor, 1], 4),
            r_squared=round(model.rsquared, 4),
            window_start=recent_data.index[0],
            window_end=recent_data.index[-1],
            n_observations=len(recent_data),
        )
    
    return sensitivities
```

### Handling Multicollinearity

```python
from statsmodels.stats.outliers_influence import variance_inflation_factor

def remove_multicollinear_factors(X: pd.DataFrame, vif_threshold: float = 5.0) -> pd.DataFrame:
    """Iteratively remove the factor with highest VIF until all VIFs < threshold."""
    X_temp = X.copy()
    
    while True:
        vif_data = pd.Series(
            [variance_inflation_factor(X_temp.values, i) 
             for i in range(X_temp.shape[1])],
            index=X_temp.columns
        )
        
        vif_factors = vif_data.drop("const", errors="ignore")
        
        if vif_factors.max() <= vif_threshold:
            break
        
        worst_factor = vif_factors.idxmax()
        X_temp = X_temp.drop(columns=[worst_factor])
    
    return X_temp
```

### Combining Theoretical Exposure with Historical Sensitivity

```python
def combined_exposure_score(
    theoretical_exposure: float,
    historical_beta: float,
    beta_significant: bool,
    beta_confidence: float,
) -> float:
    """
    Blend theoretical and empirical exposure.
    """
    if not beta_significant:
        return theoretical_exposure * 0.70
    
    if abs(theoretical_exposure) > 0.1 and abs(historical_beta) > 0.01:
        empirical_weight = min(beta_confidence * 2, 0.70)
        theoretical_weight = 1.0 - empirical_weight
        
        blended = (
            theoretical_weight * theoretical_exposure +
            empirical_weight * historical_beta
        )
        
        return blended
    
    if abs(historical_beta) > 0.01:
        return historical_beta
    return theoretical_exposure
```

---

## 13. Impact Calculation

### Improved Formula

Your proposed formula:

```
Event Strength × Relationship Strength × Factor Exposure × Historical Sensitivity × Portfolio Weight × Confidence
```

**My improved version** separates the components more clearly and adds uncertainty:

```python
def calculate_impact(
    event_factor_strength: float,
    event_factor_direction: int,
    path_strength: float,
    path_direction: int,
    security_factor_exposure: float,
    holding_weight: float,
    historical_beta: Optional[float],
    confidence: float,
    factor_magnitude: Optional[float],  # Actual observed factor change
) -> ImpactEstimate:
    """
    Calculate the estimated impact of an event on a fund through a specific path.
    """
    
    # Step 1: Determine the effective factor change
    if factor_magnitude is not None:
        # We have actual market data — use it!
        effective_change = factor_magnitude
    else:
        # No market data — use event strength as proxy
        effective_change = event_factor_strength * 5.0  # percent
    
    # Step 2: Propagate through the factor graph
    propagated_change = effective_change * path_strength * path_direction
    
    # Step 3: Apply security exposure
    if historical_beta is not None and abs(historical_beta) > 0.001:
        security_impact_pct = propagated_change * historical_beta
    else:
        security_impact_pct = propagated_change * security_factor_exposure * 0.5
    
    # Step 4: Weight by portfolio allocation
    fund_impact_bps = security_impact_pct * holding_weight * 100
    
    # Step 5: Apply confidence discount
    adjusted_impact_bps = fund_impact_bps * confidence
    
    # Step 6: Compute uncertainty range
    uncertainty_factor = 1.5
    impact_low = adjusted_impact_bps / uncertainty_factor
    impact_high = adjusted_impact_bps * uncertainty_factor
    
    return ImpactEstimate(
        point_estimate_bps=round(adjusted_impact_bps, 1),
        range_low_bps=round(min(impact_low, impact_high), 1),
        range_high_bps=round(max(impact_low, impact_high), 1),
        confidence=confidence,
        direction=event_factor_direction * path_direction * (1 if security_factor_exposure > 0 else -1),
    )
```

### Why This Is Better

1. **Uses actual market data when available** (crude actually moved +4.2%, not just "strength 0.9")
2. **Separates theoretical exposure from empirical beta** (uses beta when available, falls back to exposure)
3. **Reports ranges, not just point estimates** (more honest)
4. **Confidence discount prevents overstatement**

---

## 14. Attribution Methodology

### Attribution Engine Design

```python
def compute_attribution(
    fund_id: str,
    analysis_date: date,
    all_impacts: list[ImpactEstimate],
    actual_return_bps: float,
) -> Attribution:
    """Rank all impact estimates, deduplicate, and produce a ranked list."""
    
    # Step 1: Aggregate impacts by event
    event_impacts = defaultdict(lambda: {
        "total_impact_bps": 0.0,
        "paths": [],
        "securities": set(),
        "factors": set(),
        "min_confidence": 1.0,
    })
    
    for impact in all_impacts:
        eid = impact.event_id
        event_impacts[eid]["total_impact_bps"] += impact.point_estimate_bps
        event_impacts[eid]["paths"].append(impact)
        event_impacts[eid]["securities"].add(impact.security_id)
        event_impacts[eid]["factors"].add(impact.terminal_factor)
        event_impacts[eid]["min_confidence"] = min(
            event_impacts[eid]["min_confidence"],
            impact.confidence
        )
    
    # Step 2: Handle correlated events
    event_impacts = adjust_for_correlated_events(event_impacts)
    
    # Step 3: Rank by absolute impact
    ranked = sorted(
        event_impacts.items(),
        key=lambda x: abs(x[1]["total_impact_bps"]),
        reverse=True,
    )
    
    # Step 4: Classify into categories
    attributions = []
    for rank, (event_id, data) in enumerate(ranked, 1):
        impact_bps = data["total_impact_bps"]
        category = "negative" if impact_bps < 0 else "positive"
        
        if data["min_confidence"] >= 0.80:
            confidence_category = "high"
        elif data["min_confidence"] >= 0.50:
            confidence_category = "medium"
        else:
            confidence_category = "low"
        
        max_depth = max(p.path_depth for p in data["paths"])
        path_type = "direct" if max_depth <= 1 else "indirect"
        
        attributions.append(AttributionItem(
            rank=rank,
            event_id=event_id,
            impact_bps=round(impact_bps, 1),
            impact_pct=round(impact_bps / 100, 3),
            category=category,
            confidence_category=confidence_category,
            path_type=path_type,
            affected_securities=list(data["securities"]),
            affected_factors=list(data["factors"]),
            num_paths=len(data["paths"]),
        ))
    
    # Step 5: Compute explained vs unexplained
    total_explained_bps = sum(a.impact_bps for a in attributions)
    unexplained_bps = actual_return_bps - total_explained_bps
    
    return Attribution(
        fund_id=fund_id,
        analysis_date=analysis_date,
        actual_return_bps=actual_return_bps,
        explained_bps=round(total_explained_bps, 1),
        unexplained_bps=round(unexplained_bps, 1),
        items=attributions,
        top_negative=[a for a in attributions if a.category == "negative"][:5],
        top_positive=[a for a in attributions if a.category == "positive"][:3],
    )
```

### Handling Correlated Events

```python
def adjust_for_correlated_events(
    event_impacts: dict,
    correlation_threshold: float = 0.70,
) -> dict:
    """
    If two events share >70% of the same affected factors,
    discount the weaker event by 50%.
    """
    event_ids = list(event_impacts.keys())
    
    for i, eid1 in enumerate(event_ids):
        for eid2 in event_ids[i+1:]:
            factors1 = event_impacts[eid1]["factors"]
            factors2 = event_impacts[eid2]["factors"]
            
            if not factors1 or not factors2:
                continue
            
            overlap = len(factors1 & factors2) / len(factors1 | factors2)
            
            if overlap > correlation_threshold:
                abs1 = abs(event_impacts[eid1]["total_impact_bps"])
                abs2 = abs(event_impacts[eid2]["total_impact_bps"])
                
                weaker = eid1 if abs1 < abs2 else eid2
                event_impacts[weaker]["total_impact_bps"] *= 0.50
    
    return event_impacts
```

---

## 15. Actual vs Expected Methodology

### Framework

```python
def analyze_actual_vs_expected(
    actual_return_bps: float,
    total_explained_bps: float,
) -> ActualVsExpected:
    """Compare what we predicted with what actually happened."""
    unexplained_bps = actual_return_bps - total_explained_bps
    
    if abs(actual_return_bps) < 5:
        explanation_quality = "trivial_movement"
        explanation_ratio = None
    else:
        explanation_ratio = total_explained_bps / actual_return_bps
        
        if 0.60 <= explanation_ratio <= 1.40:
            explanation_quality = "well_explained"
        elif 0.30 <= explanation_ratio < 0.60 or 1.40 < explanation_ratio <= 2.00:
            explanation_quality = "partially_explained"
        else:
            explanation_quality = "poorly_explained"
    
    direction_match = (actual_return_bps * total_explained_bps) > 0
    
    return ActualVsExpected(
        actual_return_bps=actual_return_bps,
        explained_bps=total_explained_bps,
        unexplained_bps=unexplained_bps,
        explanation_ratio=explanation_ratio,
        explanation_quality=explanation_quality,
        direction_match=direction_match,
        should_caveat=explanation_quality in ["partially_explained", "poorly_explained"],
        caveat_message=generate_caveat(explanation_quality, unexplained_bps),
    )

def generate_caveat(quality: str, unexplained_bps: float) -> Optional[str]:
    if quality == "well_explained":
        return None
    elif quality == "partially_explained":
        return (
            "The identified market events explain a portion of the fund's movement, "
            "but other factors — such as fund flows, trading activity, or factors not "
            "captured in our analysis — may also have contributed."
        )
    elif quality == "poorly_explained":
        return (
            "The identified market events do not fully account for the fund's movement. "
            "The primary drivers may include fund-specific factors (portfolio rebalancing, "
            "large redemptions), market microstructure effects, or events not yet captured "
            "in our analysis."
        )
    elif quality == "trivial_movement":
        return "The fund's movement during this period was minimal."
    return None
```

---

## 16. Benchmark Attribution

### Brinson-Fachler Decomposition

```python
def compute_benchmark_attribution(
    fund_return: float,
    benchmark_return: float,
    fund_sector_weights: dict[str, float],
    benchmark_sector_weights: dict[str, float],
    fund_sector_returns: dict[str, float],
    benchmark_sector_returns: dict[str, float],
) -> BenchmarkAttribution:
    """
    Total Active Return = Allocation Effect + Selection Effect + Interaction Effect
    """
    active_return = fund_return - benchmark_return
    
    sectors = set(fund_sector_weights.keys()) | set(benchmark_sector_weights.keys())
    
    allocation_effects = {}
    selection_effects = {}
    interaction_effects = {}
    
    for sector in sectors:
        w_fund = fund_sector_weights.get(sector, 0)
        w_bench = benchmark_sector_weights.get(sector, 0)
        r_fund = fund_sector_returns.get(sector, 0)
        r_bench = benchmark_sector_returns.get(sector, 0)
        
        allocation_effects[sector] = (w_fund - w_bench) * (r_bench - benchmark_return)
        selection_effects[sector] = w_bench * (r_fund - r_bench)
        interaction_effects[sector] = (w_fund - w_bench) * (r_fund - r_bench)
    
    return BenchmarkAttribution(
        fund_return=fund_return,
        benchmark_return=benchmark_return,
        active_return=active_return,
        allocation_effect=sum(allocation_effects.values()),
        selection_effect=sum(selection_effects.values()),
        interaction_effect=sum(interaction_effects.values()),
        sector_allocation=allocation_effects,
        sector_selection=selection_effects,
    )
```

---

## 17. Time Decay

### Event Half-Life Model

```python
class EventHalfLife:
    HALF_LIVES = {
        EventType.TECHNICAL_MARKET: timedelta(hours=12),
        EventType.EARNINGS: timedelta(days=5),
        EventType.CORPORATE_ACTION: timedelta(days=3),
        EventType.FUND_FLOWS: timedelta(days=3),
        EventType.GEOPOLITICAL: timedelta(days=14),
        EventType.COMMODITY_PRICE: timedelta(days=21),
        EventType.CURRENCY_MOVE: timedelta(days=14),
        EventType.REGULATORY: timedelta(days=30),
        EventType.CREDIT_EVENT: timedelta(days=21),
        EventType.MONETARY_POLICY: timedelta(days=90),
        EventType.FISCAL_POLICY: timedelta(days=90),
        EventType.TRADE_POLICY: timedelta(days=60),
        EventType.SECTOR_DEVELOPMENT: timedelta(days=45),
    }
    
    @classmethod
    def compute_decay(cls, event_type: EventType, hours_elapsed: float) -> float:
        half_life_hours = cls.HALF_LIVES.get(
            event_type, timedelta(days=7)
        ).total_seconds() / 3600
        
        decay = math.exp(-0.693 * hours_elapsed / half_life_hours)
        return max(decay, 0.05)
```

### Factor Response Delay

```python
FACTOR_RESPONSE_LAG = {
    "crude_oil": 0,        # Immediate
    "gold": 0,
    "market_momentum": 0,
    "fii_fpi_flows": 0,
    "inr_usd": 0,
    "equity_valuations": 2,     # 1-5 days
    "bond_yields_domestic": 1,
    "rate_expectations": 1,
    "inflation_expectations": 7,    # 1-4 weeks
    "banking_credit_demand": 14,
    "consumer_demand": 21,
    "input_costs": 7,
    "gdp_growth": 60,          # 1-3 months
    "credit_growth": 30,
    "inflation_actual": 45,
}
```

---

## 18. Market Regimes

### Regime Detection — Hybrid Rule-Based

```python
class MarketRegimeDetector:
    """
    Regime is a VECTOR, not a single label. Multiple regimes
    can be active simultaneously.
    """
    
    def detect(self, market_data: MarketData) -> MarketRegime:
        regimes = {}
        
        if market_data.india_vix > 20:
            regimes["risk"] = "risk_off"
        elif market_data.india_vix < 13:
            regimes["risk"] = "risk_on"
        else:
            regimes["risk"] = "neutral"
        
        if market_data.cpi_yoy > 6.0:
            regimes["inflation"] = "high_inflation"
        elif market_data.cpi_yoy < 4.0:
            regimes["inflation"] = "low_inflation"
        else:
            regimes["inflation"] = "moderate_inflation"
        
        if market_data.repo_rate_change_6m > 0.25:
            regimes["rates"] = "rising_rates"
        elif market_data.repo_rate_change_6m < -0.25:
            regimes["rates"] = "falling_rates"
        else:
            regimes["rates"] = "stable_rates"
        
        if market_data.iip_growth_3m_avg > 5.0:
            regimes["growth"] = "strong_growth"
        elif market_data.iip_growth_3m_avg < 1.0:
            regimes["growth"] = "weak_growth"
        else:
            regimes["growth"] = "moderate_growth"
        
        nifty_return_3m = market_data.nifty_return_3m
        if nifty_return_3m > 10:
            regimes["momentum"] = "strong_bull"
        elif nifty_return_3m > 3:
            regimes["momentum"] = "mild_bull"
        elif nifty_return_3m > -3:
            regimes["momentum"] = "sideways"
        elif nifty_return_3m > -10:
            regimes["momentum"] = "mild_bear"
        else:
            regimes["momentum"] = "strong_bear"
        
        return MarketRegime(as_of=market_data.date, regimes=regimes)
```

---

## 19. News Pipeline

### Complete Pipeline Design

```
Step 1: COLLECT
├── Google News RSS (broad queries)
├── Financial news APIs (MoneyControl, ET, LiveMint, BS)
├── RBI announcements
├── SEBI circulars
└── Global feeds (Reuters)

Step 2: NORMALIZE
├── Clean HTML entities
├── Extract publication date → IST
├── Standardize source names
├── Extract article body (trafilatura)
└── Compute article hash (for dedup)

Step 3: DEDUPLICATE
├── Exact URL deduplication
├── Near-duplicate title detection (Jaccard > 0.75)
├── Content fingerprint deduplication (SimHash)
└── Output: ~40-60% reduction

Step 4: CLUSTER INTO EVENTS
├── Sentence-transformer embeddings
├── Agglomerative clustering (cosine threshold 0.80)
├── Pick primary article per cluster
├── Generate event summary (LLM or extractive)
└── Output: 30-60 events from 200-500 articles

Step 5: SCORE EVENT IMPORTANCE
├── Magnitude (LLM or rule-based)
├── Breadth (how many factors affected)
├── Novelty (is this new or continuation?)
├── Severity (how extreme?)
├── Confidence (source count, credibility, consistency)
└── Output: importance + confidence scores per event

Step 6: FILTER TO TOP EVENTS
├── Keep events with importance > 0.40
├── Keep events with confidence > 0.50
├── Keep events that affect factors in the fund's exposure
├── Limit to top 20 events
└── Output: 10-20 events relevant to analysis

Step 7: EXTRACT FACTOR IMPACTS
├── LLM structured extraction
├── For each event: which factors? direction? strength?
├── Validate against factor taxonomy
├── Cross-reference with actual market data
└── Output: event-factor impact mappings
```

### News Source Credibility Scoring

```python
SOURCE_CREDIBILITY = {
    "Reserve Bank of India": 0.98,
    "SEBI": 0.97,
    "Ministry of Finance": 0.96,
    "Reuters": 0.95,
    "Bloomberg": 0.95,
    "Economic Times": 0.85,
    "Business Standard": 0.85,
    "LiveMint": 0.83,
    "MoneyControl": 0.80,
    "CNBC-TV18": 0.78,
    "Financial Express": 0.78,
    "Hindu BusinessLine": 0.80,
    "Times of India": 0.68,
    "NDTV": 0.70,
    "India Today": 0.65,
    "Investing.com": 0.55,
    "TradingView": 0.50,
}
```

---

## 20. LLM Architecture

### LLM Responsibility Division

```
┌─────────────────────────────────────────────────────────┐
│                 LLM RESPONSIBILITIES                     │
│                                                          │
│  1. Event extraction from articles                       │
│  2. Event → Factor mapping                               │
│  3. Security-specific exposure adjustment                │
│  4. Investor explanation generation                      │
│  5. Relationship hypothesis validation                   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          PYTHON / DETERMINISTIC RESPONSIBILITIES         │
│                                                          │
│  1. News collection and scraping                         │
│  2. URL deduplication                                    │
│  3. Title fuzzy matching                                 │
│  4. Portfolio weight calculations                        │
│  5. Fund factor exposure computation                     │
│  6. Factor graph traversal (BFS/DFS)                     │
│  7. Impact calculation (arithmetic)                      │
│  8. Attribution ranking and deduplication                 │
│  9. Actual vs expected comparison                        │
│  10. Correlated event detection                          │
│  11. Confidence scoring                                  │
│  12. Data validation and output formatting               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          STATISTICAL / MODEL RESPONSIBILITIES            │
│                                                          │
│  1. Rolling multi-factor regression                      │
│  2. Fund NAV sensitivity estimation                      │
│  3. VIF / multicollinearity detection                    │
│  4. Confidence intervals                                 │
│  5. Regime detection (threshold-based)                   │
│  6. Embedding computation (sentence-transformers)        │
│  7. Clustering (agglomerative / DBSCAN)                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          EXTERNAL DATA RESPONSIBILITIES                  │
│                                                          │
│  1. Daily NAV (AMFI API)                                 │
│  2. Fund holdings (AMFI / fund house websites)           │
│  3. Stock prices (Yahoo Finance / NSE Bhavcopy)          │
│  4. Index levels (NSE)                                   │
│  5. Bond yields (RBI / CCIL)                             │
│  6. USDINR rate (RBI reference rate)                     │
│  7. Crude oil prices (commodity feeds)                   │
│  8. FII/FPI flow data (NSDL)                             │
│  9. DII flow data (AMFI)                                 │
│  10. India VIX (NSE)                                     │
│  11. CPI / WPI data (MOSPI)                              │
│  12. Gold prices (MCX / international feeds)             │
└─────────────────────────────────────────────────────────┘
```

### LLM Call Budget Per Analysis Run

| LLM Call | Purpose | Count |
|---|---|---|
| Event extraction + classification | Extract events from article clusters | ~5-10 (batched) |
| Event → Factor mapping | Map events to affected factors | ~2-3 (batched) |
| Security exposure adjustment | Adjust sector defaults | ~3-5 (batched) |
| Relationship validation | Sanity-check impact paths | 1-2 |
| Investor explanation | Generate final narrative | 1 |
| **Total** | | **~12-20 calls** |

---

## 21. LLM Prompts

### Prompt 1: Event Extraction + Classification

```
SYSTEM:
You are a financial market analyst. Extract structured market events from 
news article clusters.

For each article cluster, identify the SINGLE underlying market event:
1. event_type: One of [geopolitical, monetary_policy, fiscal_policy, 
   commodity_price, currency_move, earnings, regulatory, economic_data, 
   global_market, fund_flows, credit_event, trade_policy, 
   sector_development, corporate_action, technical_market]
2. title: Clear, factual 8-15 word title
3. summary: 2-3 sentence factual summary
4. magnitude: 0.0-1.0
5. severity: 0.0-1.0
6. duration_estimate: [flash, short_term, medium_term, structural]

IMPORTANT:
- Be FACTUAL. State what happened, not opinions.
- Distinguish actual events from commentary/opinions.

Return JSON:
{
  "event_type": "...",
  "title": "...",
  "summary": "...",
  "magnitude": 0.0-1.0,
  "severity": 0.0-1.0,
  "duration_estimate": "..."
}
```

### Prompt 2: Event → Factor Mapping

```
SYSTEM:
You are a market economist. For each market event, identify which market 
factors it affects and how.

Available factors (use ONLY these codes):
[List all factor codes from the taxonomy]

For each affected factor, specify:
1. factor: factor code from the list above
2. direction: +1 or -1
3. strength: 0.0-1.0
4. confidence: 0.0-1.0
5. time_horizon: immediate / days / weeks / months
6. evidence: One sentence explaining the mechanism

Rules:
- Only include factors with strength >= 0.3
- Maximum 8 factors per event
- Be specific about mechanisms

Return JSON:
{
  "factor_impacts": [
    {
      "factor": "crude_oil",
      "direction": 1,
      "strength": 0.95,
      "confidence": 0.98,
      "time_horizon": "immediate",
      "evidence": "Direct: Brent crude rose 4.2% to $92/barrel"
    }
  ]
}
```

### Prompt 3: Investor Explanation Generation

```
SYSTEM:
You are writing a market commentary for a retail mutual fund investor.

RULES:
1. NEVER use: factor loading, beta, regression, exposure vector, 
   causal DAG, factor score, basis points, multicollinearity, R-squared
2. Use simple language: "pressure", "headwind", "tailwind", "weakness"
3. Explain MECHANISMS, not just correlations
4. Acknowledge UNCERTAINTY: use "appears to", "may have", "could be"
   NEVER use "caused", "resulted in" unless confidence is very high
5. Structure: big picture → specifics → outlook
6. Length: 150-250 words
7. If unexplained_ratio > 40%, explicitly state that

Return JSON:
{
  "explanation": "Your fund's recent movement...",
  "headline": "...",
  "key_takeaways": ["...", "...", "..."],
  "outlook_note": "...",
  "confidence_disclaimer": "..."
}
```

---

## 22. Python Project Structure

```
fund_intelligence_engine/
│
├── config/
│   ├── __init__.py
│   ├── settings.py              # Environment vars, API keys, model names
│   ├── factors.py               # FACTOR_REGISTRY, complete taxonomy
│   ├── factor_graph.py          # FACTOR_GRAPH_EDGES, curated relationships
│   ├── sector_defaults.py       # SECTOR_FACTOR_DEFAULTS, exposure templates
│   └── sources.py               # SOURCE_CREDIBILITY, RSS URLs, API endpoints
│
├── models/
│   ├── __init__.py
│   ├── news.py                  # NewsArticle, ArticleCluster
│   ├── events.py                # MarketEvent, EventType, EventDuration
│   ├── factors.py               # Factor, EventFactorImpact, FactorRelationship
│   ├── securities.py            # Security, SecurityFactorExposure
│   ├── funds.py                 # Fund, FundHolding, FundFactorExposure
│   ├── sensitivity.py           # SensitivityEstimate
│   ├── impact.py                # ImpactEstimate, DirectImpact, IndirectImpact
│   ├── attribution.py           # Attribution, AttributionItem, ActualVsExpected
│   ├── regimes.py               # MarketRegime, MarketData
│   └── explanation.py           # InvestorExplanation
│
├── news/
│   ├── __init__.py
│   ├── collector.py             # RSS fetching, API calls, parallel scraping
│   ├── scraper.py               # Article text extraction
│   ├── deduplicator.py          # URL dedup, title fuzzy matching
│   ├── clusterer.py             # Sentence-transformer embeddings + clustering
│   └── importance.py            # Event importance, confidence, freshness
│
├── events/
│   ├── __init__.py
│   ├── extractor.py             # LLM-based event extraction
│   ├── normalizer.py            # Event normalization, type classification
│   └── scorer.py                # Event scoring
│
├── factors/
│   ├── __init__.py
│   ├── mapper.py                # LLM-based event → factor mapping
│   ├── graph.py                 # NetworkX factor graph, path finding
│   ├── propagator.py            # BFS/DFS propagation through graph
│   └── regime.py                # Market regime detection
│
├── portfolio/
│   ├── __init__.py
│   ├── holdings.py              # Load fund holdings
│   ├── exposure.py              # Security/fund exposure computation
│   ├── sensitivity.py           # Rolling regression, multi-factor betas
│   ├── benchmark.py             # Brinson attribution
│   └── staleness.py             # Portfolio staleness detection
│
├── attribution/
│   ├── __init__.py
│   ├── direct.py                # Direct impact paths (depth 0-1)
│   ├── indirect.py              # Indirect impact paths (depth 2-3)
│   ├── deduplicator.py          # Correlated event detection
│   ├── calculator.py            # Impact calculation formula
│   ├── ranker.py                # Rank attributions
│   └── actual_vs_expected.py    # Explained vs unexplained
│
├── llm/
│   ├── __init__.py
│   ├── client.py                # LLM API client
│   ├── prompts.py               # All prompt templates
│   ├── event_classifier.py      # Event extraction calls
│   ├── factor_mapper.py         # Factor mapping calls
│   ├── exposure_adjuster.py     # Exposure adjustment calls
│   ├── explanation_generator.py # Explanation generation calls
│   └── validator.py             # Sanity-check LLM outputs
│
├── data/
│   ├── __init__.py
│   ├── nav.py                   # AMFI NAV data fetcher
│   ├── prices.py                # Stock price fetcher
│   ├── market_data.py           # Bond yields, FX, commodities, VIX
│   ├── flows.py                 # FII/DII flow data
│   └── cache.py                 # Data caching layer
│
├── output/
│   ├── __init__.py
│   ├── report.py                # Final report assembly
│   ├── investor_insight.py      # Investor-facing output formatting
│   └── audit_trail.py           # Full audit trail for debugging
│
├── db/
│   ├── __init__.py
│   ├── models.py                # SQLAlchemy ORM models
│   ├── migrations/              # Alembic migrations
│   └── repository.py            # Data access layer
│
├── tests/
│   ├── __init__.py
│   ├── test_deduplication.py
│   ├── test_clustering.py
│   ├── test_factor_mapping.py
│   ├── test_graph_traversal.py
│   ├── test_exposure.py
│   ├── test_impact.py
│   ├── test_attribution.py
│   ├── test_double_counting.py
│   ├── test_actual_vs_expected.py
│   ├── test_explanation.py
│   └── fixtures/
│       ├── sample_articles.json
│       ├── sample_events.json
│       ├── sample_fund.json
│       └── sample_market_data.json
│
├── main.py                      # Entry point, orchestrator
├── pipeline.py                  # End-to-end pipeline definition
├── requirements.txt
└── README.md
```

---

## 23. Database Design

### Recommended: PostgreSQL Only (MVP), + Redis (Production)

```sql
-- ============================================================
-- NEWS & EVENTS
-- ============================================================

CREATE TABLE news_articles (
    id              SERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    canonical_url   TEXT,
    title           TEXT NOT NULL,
    source          VARCHAR(200),
    published_at    TIMESTAMPTZ,
    scraped_at      TIMESTAMPTZ DEFAULT NOW(),
    text_content    TEXT,
    text_length     INTEGER,
    scrape_status   VARCHAR(50),
    content_hash    VARCHAR(64),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_published ON news_articles (published_at);
CREATE INDEX idx_articles_source ON news_articles (source);

CREATE TABLE market_events (
    id              SERIAL PRIMARY KEY,
    event_code      VARCHAR(100) UNIQUE NOT NULL,
    event_type      VARCHAR(50) NOT NULL,
    title           TEXT NOT NULL,
    summary         TEXT,
    importance      DECIMAL(4,3),
    confidence      DECIMAL(4,3),
    freshness       DECIMAL(4,3),
    novelty         DECIMAL(4,3),
    severity        DECIMAL(4,3),
    magnitude       DECIMAL(4,3),
    duration_estimate VARCHAR(50),
    first_seen_at   TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ,
    article_count   INTEGER DEFAULT 0,
    source_count    INTEGER DEFAULT 0,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_importance ON market_events (importance DESC);

CREATE TABLE article_events (
    id              SERIAL PRIMARY KEY,
    article_id      INTEGER REFERENCES news_articles(id),
    event_id        INTEGER REFERENCES market_events(id),
    is_primary      BOOLEAN DEFAULT FALSE,
    UNIQUE(article_id, event_id)
);

-- ============================================================
-- FACTORS
-- ============================================================

CREATE TABLE factors (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(100) UNIQUE NOT NULL,
    name            VARCHAR(200) NOT NULL,
    category        VARCHAR(50) NOT NULL,
    level           VARCHAR(20) NOT NULL,
    parent_code     VARCHAR(100) REFERENCES factors(code),
    proxy_ticker    VARCHAR(50),
    proxy_description TEXT,
    is_observable   BOOLEAN DEFAULT TRUE,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE event_factor_impacts (
    id              SERIAL PRIMARY KEY,
    event_id        INTEGER REFERENCES market_events(id),
    factor_code     VARCHAR(100) REFERENCES factors(code),
    direction       SMALLINT NOT NULL,
    strength        DECIMAL(4,3) NOT NULL,
    confidence      DECIMAL(4,3) NOT NULL,
    time_horizon    VARCHAR(20),
    evidence        TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(event_id, factor_code)
);

CREATE TABLE factor_relationships (
    id                  SERIAL PRIMARY KEY,
    source_factor_code  VARCHAR(100) REFERENCES factors(code),
    target_factor_code  VARCHAR(100) REFERENCES factors(code),
    relationship_type   VARCHAR(20) NOT NULL,
    base_strength       DECIMAL(4,3) NOT NULL,
    confidence          DECIMAL(4,3) NOT NULL,
    lag                 VARCHAR(20),
    regime_condition    TEXT,
    mechanism           TEXT,
    evidence_type       VARCHAR(20),
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_factor_code, target_factor_code)
);

-- ============================================================
-- SECURITIES & FUNDS
-- ============================================================

CREATE TABLE securities (
    id              SERIAL PRIMARY KEY,
    ticker          VARCHAR(50) UNIQUE,
    isin            VARCHAR(12) UNIQUE,
    name            VARCHAR(300) NOT NULL,
    sector          VARCHAR(100),
    industry        VARCHAR(100),
    market_cap_category VARCHAR(20),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE security_factor_exposures (
    id              SERIAL PRIMARY KEY,
    security_id     INTEGER REFERENCES securities(id),
    factor_code     VARCHAR(100) REFERENCES factors(code),
    exposure        DECIMAL(5,3) NOT NULL,
    confidence      DECIMAL(4,3),
    source          VARCHAR(50),
    as_of_date      DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(security_id, factor_code, as_of_date)
);

CREATE TABLE funds (
    id              SERIAL PRIMARY KEY,
    fund_code       VARCHAR(50) UNIQUE,
    name            VARCHAR(300) NOT NULL,
    category        VARCHAR(100),
    benchmark       VARCHAR(200),
    amc             VARCHAR(200),
    fund_type       VARCHAR(50),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE fund_holdings (
    id              SERIAL PRIMARY KEY,
    fund_id         INTEGER REFERENCES funds(id),
    security_id     INTEGER REFERENCES securities(id),
    weight          DECIMAL(6,4) NOT NULL,
    asset_class     VARCHAR(20),
    as_of_date      DATE NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_holdings_fund_date ON fund_holdings (fund_id, as_of_date);

-- ============================================================
-- ANALYSIS & ATTRIBUTION
-- ============================================================

CREATE TABLE fund_analyses (
    id                  SERIAL PRIMARY KEY,
    fund_id             INTEGER REFERENCES funds(id),
    analysis_date       DATE NOT NULL,
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    actual_return_bps   DECIMAL(8,2),
    benchmark_return_bps DECIMAL(8,2),
    explained_bps       DECIMAL(8,2),
    unexplained_bps     DECIMAL(8,2),
    explanation_quality VARCHAR(30),
    regime_snapshot     JSONB,
    portfolio_as_of     DATE,
    staleness_score     DECIMAL(4,3),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fund_id, analysis_date)
);

CREATE TABLE impact_estimates (
    id                  SERIAL PRIMARY KEY,
    analysis_id         INTEGER REFERENCES fund_analyses(id),
    event_id            INTEGER REFERENCES market_events(id),
    factor_code         VARCHAR(100),
    path_type           VARCHAR(20),
    path_depth          SMALLINT,
    path_description    TEXT,
    security_id         INTEGER REFERENCES securities(id),
    holding_weight      DECIMAL(6,4),
    impact_bps          DECIMAL(8,2),
    confidence          DECIMAL(4,3),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE attributions (
    id                  SERIAL PRIMARY KEY,
    analysis_id         INTEGER REFERENCES fund_analyses(id),
    rank                SMALLINT NOT NULL,
    event_id            INTEGER REFERENCES market_events(id),
    impact_bps          DECIMAL(8,2) NOT NULL,
    impact_category     VARCHAR(20),
    confidence_category VARCHAR(20),
    path_type           VARCHAR(20),
    affected_securities TEXT[],
    affected_factors    TEXT[],
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE investor_explanations (
    id                  SERIAL PRIMARY KEY,
    analysis_id         INTEGER REFERENCES fund_analyses(id),
    headline            TEXT,
    explanation_text    TEXT NOT NULL,
    key_takeaways       TEXT[],
    outlook_note        TEXT,
    confidence_disclaimer TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE historical_sensitivities (
    id                  SERIAL PRIMARY KEY,
    fund_id             INTEGER REFERENCES funds(id),
    factor_code         VARCHAR(100) REFERENCES factors(code),
    beta                DECIMAL(8,4),
    t_statistic         DECIMAL(6,2),
    p_value             DECIMAL(6,4),
    is_significant      BOOLEAN,
    r_squared           DECIMAL(6,4),
    ci_lower            DECIMAL(8,4),
    ci_upper            DECIMAL(8,4),
    window_start        DATE,
    window_end          DATE,
    n_observations      INTEGER,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(fund_id, factor_code, window_end)
);
```

---

## 24. Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional
from enum import Enum


class EventType(str, Enum):
    GEOPOLITICAL = "geopolitical"
    MONETARY_POLICY = "monetary_policy"
    FISCAL_POLICY = "fiscal_policy"
    COMMODITY_PRICE = "commodity_price"
    CURRENCY_MOVE = "currency_move"
    EARNINGS = "earnings"
    REGULATORY = "regulatory"
    ECONOMIC_DATA = "economic_data"
    GLOBAL_MARKET = "global_market"
    FUND_FLOWS = "fund_flows"
    CREDIT_EVENT = "credit_event"
    TRADE_POLICY = "trade_policy"
    SECTOR_DEVELOPMENT = "sector_development"
    CORPORATE_ACTION = "corporate_action"
    TECHNICAL_MARKET = "technical_market"

class EventDuration(str, Enum):
    FLASH = "flash"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    STRUCTURAL = "structural"

class TimeHorizon(str, Enum):
    IMMEDIATE = "immediate"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"
    QUARTERS = "quarters"

class ConfidenceCategory(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class ExplanationQuality(str, Enum):
    WELL_EXPLAINED = "well_explained"
    PARTIALLY_EXPLAINED = "partially_explained"
    POORLY_EXPLAINED = "poorly_explained"
    TRIVIAL_MOVEMENT = "trivial_movement"


class NewsArticle(BaseModel):
    id: Optional[int] = None
    url: str
    canonical_url: Optional[str] = None
    title: str
    source: Optional[str] = None
    published_at: Optional[datetime] = None
    text_content: Optional[str] = None
    text_length: Optional[int] = None
    scrape_status: Optional[str] = None
    content_hash: Optional[str] = None

class MarketEvent(BaseModel):
    event_id: str
    event_type: EventType
    title: str
    summary: str
    importance: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    freshness: float = Field(ge=0.0, le=1.0)
    novelty: float = Field(ge=0.0, le=1.0)
    severity: float = Field(ge=0.0, le=1.0)
    magnitude: float = Field(ge=0.0, le=1.0)
    duration_estimate: EventDuration
    first_seen_at: datetime
    last_seen_at: datetime
    article_count: int = 0
    source_count: int = 0

class EventFactorImpact(BaseModel):
    event_id: str
    factor_id: str
    direction: int = Field(ge=-1, le=1)
    strength: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: TimeHorizon
    evidence: str

class FactorPath(BaseModel):
    factors: list[str]
    depth: int
    cumulative_strength: float
    cumulative_direction: int

class FundHolding(BaseModel):
    security_id: str
    security_name: str
    weight: float = Field(ge=0.0, le=1.0)
    sector: Optional[str] = None
    asset_class: str = "equity"
    as_of_date: date

class Fund(BaseModel):
    fund_id: str
    name: str
    category: Optional[str] = None
    benchmark: Optional[str] = None
    holdings: list[FundHolding] = Field(default_factory=list)
    portfolio_as_of: Optional[date] = None

class SensitivityEstimate(BaseModel):
    factor_id: str
    beta: float
    t_statistic: float = 0.0
    p_value: float = 1.0
    is_significant: bool = False
    r_squared: Optional[float] = None
    window_start: Optional[date] = None
    window_end: Optional[date] = None
    n_observations: int = 0

class ImpactEstimate(BaseModel):
    event_id: str
    factor_id: str
    terminal_factor: str
    security_id: str
    path_type: str
    path_depth: int
    path_description: str
    holding_weight: float
    factor_exposure: float
    point_estimate_bps: float
    range_low_bps: float
    range_high_bps: float
    confidence: float
    direction: int

class AttributionItem(BaseModel):
    rank: int
    event_id: str
    event_title: str
    event_summary: str
    impact_bps: float
    impact_pct: float
    category: str
    confidence_category: ConfidenceCategory
    path_type: str
    affected_securities: list[str]
    affected_factors: list[str]
    mechanism_description: str
    num_paths: int

class ActualVsExpected(BaseModel):
    actual_return_bps: float
    explained_bps: float
    unexplained_bps: float
    explanation_ratio: Optional[float] = None
    explanation_quality: ExplanationQuality
    direction_match: bool
    should_caveat: bool
    caveat_message: Optional[str] = None

class Attribution(BaseModel):
    fund_id: str
    analysis_date: date
    period_start: date
    period_end: date
    actual_return_bps: float
    explained_bps: float
    unexplained_bps: float
    explanation_quality: ExplanationQuality
    items: list[AttributionItem]
    top_negative: list[AttributionItem]
    top_positive: list[AttributionItem]
    actual_vs_expected: ActualVsExpected

class InvestorExplanation(BaseModel):
    fund_id: str
    analysis_date: date
    headline: str
    explanation: str
    key_takeaways: list[str]
    outlook_note: Optional[str] = None
    confidence_disclaimer: Optional[str] = None
    portfolio_disclosure_note: str

class MarketRegime(BaseModel):
    as_of: date
    regimes: dict[str, str]
```

---

## 25. Core Python Pseudocode

### Main Pipeline Orchestrator

```python
# pipeline.py

async def run_analysis(fund_id: str, analysis_date: date) -> InvestorExplanation:
    """Complete end-to-end analysis pipeline."""
    
    # === PHASE 1: DATA COLLECTION ===
    fund = load_fund_with_holdings(fund_id)
    nav_return = get_nav_return(fund_id, period_days=7)
    benchmark_return = get_benchmark_return(fund.benchmark, period_days=7)
    market_data = get_current_market_data()
    regime = detect_market_regime(market_data)
    
    # === PHASE 2: NEWS → EVENTS ===
    raw_articles = collect_market_news(days_back=7, queries=build_broad_market_queries())
    unique_articles = deduplicate(raw_articles)
    article_clusters = cluster_into_events(unique_articles)
    
    events = []
    for cluster in article_clusters:
        event = await extract_event(cluster)
        event.importance = score_event_importance(event)
        event.confidence = score_event_confidence(event)
        event.freshness = compute_freshness(event, analysis_date)
        events.append(event)
    
    important_events = [
        e for e in events 
        if e.importance >= 0.40 and e.confidence >= 0.50
    ][:20]
    
    # === PHASE 3: EVENTS → FACTORS ===
    event_factor_map = {}
    for event in important_events:
        impacts = await map_event_to_factors(event)
        event_factor_map[event.event_id] = impacts
    
    # === PHASE 4: FACTOR GRAPH ===
    factor_graph = build_factor_graph(regime)
    
    # === PHASE 5: EXPOSURE & SENSITIVITY ===
    security_exposures = {}
    for holding in fund.holdings:
        exposure = get_security_exposure(holding.security_id, holding.sector)
        security_exposures[holding.security_id] = exposure
    
    fund_exposure = compute_fund_factor_exposure(fund.holdings, security_exposures)
    sensitivities = get_historical_sensitivities(fund_id)
    
    # === PHASE 6: IMPACT CALCULATION ===
    all_impacts = []
    for event in important_events:
        event_factors = event_factor_map.get(event.event_id, [])
        direct = find_direct_impacts(event, event_factors, fund.holdings, security_exposures)
        indirect = find_indirect_impacts(event, event_factors, factor_graph, 
                                         fund.holdings, security_exposures, max_depth=3)
        all_impacts.extend(direct)
        all_impacts.extend(indirect)
    
    all_impacts = deduplicate_impacts(
        [i for i in all_impacts if isinstance(i, DirectImpact)],
        [i for i in all_impacts if isinstance(i, IndirectImpact)],
    )
    
    # === PHASE 7: ATTRIBUTION ===
    attribution = compute_attribution(fund_id, analysis_date, all_impacts, nav_return * 100)
    
    # === PHASE 8: EXPLANATION ===
    explanation = await generate_investor_explanation(fund, attribution, regime, benchmark_return)
    
    # === PHASE 9: PERSIST ===
    save_analysis(attribution, explanation)
    
    return explanation
```

---

## 26. Example End-to-End Calculation

### Fund: Hypothetical Flexi-Cap Fund

**Holdings** (as of August 31, 2026):

| Security | Sector | Weight |
|---|---|---|
| HDFC Bank | Financial Services | 8.0% |
| Infosys | Technology | 6.0% |
| Reliance | Energy | 5.5% |
| IndiGo | Airlines | 3.0% |
| HUL | FMCG | 4.0% |
| TCS | Technology | 5.0% |
| ICICI Bank | Financial Services | 5.5% |
| L&T | Industrials | 4.0% |
| Other holdings | Various | 59.0% |

**Period**: September 8–14, 2026  
**Fund NAV Return**: -1.10%  
**Benchmark (Nifty 500) Return**: -0.70%

### Step 1: Event Extraction

```json
[
  {"event_id": "EV001", "title": "Crude oil surges 4.2% on Middle East escalation", "importance": 0.88},
  {"event_id": "EV002", "title": "Geopolitical tensions escalate in Middle East", "importance": 0.82},
  {"event_id": "EV003", "title": "US 10-year yield rises to 4.8% on strong jobs data", "importance": 0.79},
  {"event_id": "EV004", "title": "INR weakens to 84.5 against USD", "importance": 0.71},
  {"event_id": "EV005", "title": "IT spending expectations cut by Gartner", "importance": 0.68},
  {"event_id": "EV006", "title": "RBI injects Rs 50,000 crore via OMO", "importance": 0.65}
]
```

### Step 2: Factor Extraction

```
EV001 (Crude surge) → crude_oil +0.90, inflation_expectations +0.60, input_costs +0.75
EV003 (US yields)   → us_interest_rates +0.80, global_risk_sentiment -0.50
EV004 (INR weakness) → inr_usd -0.70
EV005 (IT spending)  → it_spending -0.80
EV006 (RBI OMO)      → liquidity +0.70, rate_expectations -0.40
```

### Step 3: Direct Relationships

```
crude_oil ↑ → IndiGo (exposure: -0.90, weight: 3%) = -2.43 bps
crude_oil ↑ → Reliance (exposure: +0.80, weight: 5.5%) = +3.96 bps
input_costs ↑ → HUL (exposure: -0.50, weight: 4%) = -1.50 bps
it_spending ↓ → Infosys (exposure: +0.95, weight: 6%) = -4.56 bps
it_spending ↓ → TCS (exposure: +0.90, weight: 5%) = -3.60 bps
liquidity ↑ → HDFC Bank (exposure: +0.70, weight: 8%) = +3.92 bps
liquidity ↑ → ICICI Bank (exposure: +0.70, weight: 5.5%) = +2.70 bps
```

### Step 4: Indirect Relationships

```
crude → inflation → rate_expectations → equity_valuations
  path_strength = 0.192
  → HDFC Bank (equity_valuations exposure: +0.50) = -0.69 bps

us_interest_rates → fii_fpi_flows → market_momentum
  path_strength = 0.211
  → Broad market impact = -8.11 bps
  
inr_usd ↓ → Infosys (inr_usd exposure: -0.70) = +2.94 bps [INR weakness helps IT]
inr_usd ↓ → TCS (inr_usd exposure: -0.65) = +2.28 bps
```

### Step 5: Attribution Ranking

| Rank | Event | Impact (bps) | Category | Confidence |
|---|---|---|---|---|
| 1 | US yields rise / FII risk | -8.1 | Negative | Medium |
| 2 | IT spending cut | -8.2 | Negative | High |
| 3 | Crude oil surge | -0.7 (net) | Negative | High |
| 4 | RBI liquidity injection | +6.6 | Positive | High |
| 5 | INR depreciation | +5.2 | Positive | High |

### Step 6: Actual vs Expected

```
Actual return: -110 bps
Factor-driven attribution: -5.2 bps (net)
Market beta effect (0.85 × -70bps): -59.5 bps
Total explained: -64.7 bps (~59%)
Unexplained: -45.3 bps (~41%)

Quality: PARTIALLY_EXPLAINED
```

---

## 27. Example Investor Output

```json
{
  "fund_name": "ABC Flexi Cap Fund",
  "period": "September 8-14, 2026",
  "fund_return": "-1.10%",
  "benchmark_return": "-0.70%",
  "underperformance": "-0.40%",
  
  "headline": "Broad market weakness and sector-specific headwinds weighed on the fund",
  
  "explanation": "Your fund declined 1.10% over the past week, slightly more than the broader market's 0.70% decline. Most of this movement appears to be driven by the overall market environment rather than issues with any single holding.\n\nThe global backdrop was challenging. Rising US bond yields, driven by stronger-than-expected US economic data, appear to have reduced foreign investor appetite for Indian equities. This broad risk-off sentiment likely contributed to the overall market decline.\n\nWithin the fund, two specific headwinds stood out. The fund's technology holdings (Infosys, TCS) faced pressure as global IT spending expectations were cut by a leading research firm. Additionally, a sharp rise in crude oil prices created cost concerns for several portfolio companies, though the fund's energy holding (Reliance) partially offset this.\n\nOn the positive side, the RBI's decision to inject liquidity supported the fund's banking holdings, and the weaker rupee actually helped IT companies through favorable currency conversion.\n\nThe fund's slight underperformance versus the benchmark appears to be partly due to its higher-than-benchmark exposure to IT companies and the specific mix of holdings affected by crude oil price movements.",
  
  "key_takeaways": [
    "Market-wide factors drove most of the decline — this is not a stock-specific issue",
    "IT spending outlook weakness specifically affected the fund's tech holdings",
    "Rising crude oil prices created mixed effects: hurt some holdings, helped others",
    "Banking holdings received some support from RBI liquidity measures"
  ],
  
  "confidence_disclaimer": "This analysis is based on portfolio holdings disclosed as of August 31, 2026. Actual current holdings may differ. The identified market factors explain a portion of the fund's movement; other factors may also have contributed."
}
```

---

## 28. Testing Strategy

### Unit Test Categories

```python
# 1. Event Deduplication Tests
def test_exact_url_dedup():
    articles = [NewsArticle(url="u1", title="T1"), NewsArticle(url="u1", title="T1")]
    assert len(deduplicate_urls(articles)) == 1

def test_fuzzy_title_dedup():
    articles = [
        NewsArticle(url="u1", title="HDFC Bank Q4 profit rises 9% to Rs 17616 crore"),
        NewsArticle(url="u2", title="HDFC Bank Q4 net profit jumps 9% to 17616 crore"),
    ]
    assert len(deduplicate_titles(articles)) == 1

# 2. Graph Traversal Tests
def test_no_cycles():
    graph = build_factor_graph()
    paths = graph.find_all_paths("crude_oil", max_depth=5)
    for path in paths:
        assert len(path.factors) == len(set(path.factors))

def test_max_depth_respected():
    paths = graph.find_all_paths("crude_oil", max_depth=3)
    for path in paths:
        assert path.depth <= 3

# 3. Exposure Tests
def test_fund_exposure_weighted_sum():
    holdings = [
        FundHolding(security_id="HDFC", weight=0.08, security_name="HDFC Bank"),
        FundHolding(security_id="INFY", weight=0.06, security_name="Infosys"),
    ]
    exposures = {
        "HDFC": {"interest_rates": 0.70},
        "INFY": {"interest_rates": -0.30},
    }
    result = compute_fund_factor_exposure(holdings, exposures)
    assert abs(result["interest_rates"] - 0.038) < 0.001

# 4. Impact Direction Tests
def test_crude_up_hurts_airline():
    impact = calculate_direct_impact(
        event_strength=0.90, event_direction=+1,
        security_exposure=-0.90, holding_weight=0.03
    )
    assert impact.direction == -1  # Negative

def test_crude_up_helps_energy():
    impact = calculate_direct_impact(
        event_strength=0.90, event_direction=+1,
        security_exposure=+0.80, holding_weight=0.055
    )
    assert impact.direction == +1  # Positive

# 5. Double Counting Tests
def test_correlated_events_discounted():
    # Two events with 80% factor overlap should have weaker one discounted
    ...

# 6. Causal Language Tests
def test_explanation_uses_hedged_language():
    explanation = generate_explanation(...)
    hedged = ["appears to", "may have", "could be"]
    assert any(phrase in explanation.lower() for phrase in hedged)

# 7. Unexplained Return Tests
def test_large_unexplained_generates_caveat():
    attribution = compute_attribution(fund_id="F1", all_impacts=[], actual_return_bps=-110)
    assert attribution.explanation_quality == ExplanationQuality.POORLY_EXPLAINED
    assert attribution.actual_vs_expected.should_caveat == True
```

### Synthetic Test Dataset

```json
{
  "test_fund": {
    "name": "Test Flexi Cap Fund",
    "holdings": [
      {"security": "BANK_A", "sector": "Financial Services", "weight": 0.10},
      {"security": "IT_A", "sector": "Technology", "weight": 0.08},
      {"security": "ENERGY_A", "sector": "Energy", "weight": 0.06},
      {"security": "AIRLINE_A", "sector": "Airlines", "weight": 0.03},
      {"security": "FMCG_A", "sector": "FMCG", "weight": 0.05}
    ],
    "nav_return_bps": -85
  },
  "test_events": [
    {"id": "TEST_EV1", "type": "commodity_price", "title": "Crude oil rises 5%",
     "factors": [{"factor": "crude_oil", "direction": 1, "strength": 0.90}]},
    {"id": "TEST_EV2", "type": "sector_development", "title": "IT spending forecast cut",
     "factors": [{"factor": "it_spending", "direction": -1, "strength": 0.80}]}
  ],
  "expected_outcomes": {
    "AIRLINE_A_crude_impact": "negative",
    "IT_A_spending_impact": "negative",
    "ENERGY_A_crude_impact": "positive",
    "total_explained_direction": "negative"
  }
}
```

---

## 29. MVP Architecture

### What to Build First (Weeks 1-4)

```
✅ INCLUDE:
├── News collection (Google News RSS, 5-6 broad queries)
├── Article deduplication (URL + fuzzy title)
├── LLM-based event extraction (batched)
├── Event importance scoring (simple)
├── LLM-based event → factor mapping
├── Static factor graph (30-40 curated edges)
├── Direct relationships only (depth 0-1)
├── Sector-based default exposures (Tier 1)
├── Simple impact calculation
├── Basic attribution ranking
├── LLM investor explanation
├── CLI-based output
└── SQLite or JSON file storage

❌ EXCLUDE (Phase 2+):
├── Embedding-based clustering (use LLM for MVP)
├── Historical sensitivity (regression)
├── Indirect relationships (depth 2-3)
├── Market regime detection
├── Benchmark attribution (Brinson)
├── Time decay modeling
├── Statistical exposure (Tier 3)
├── PostgreSQL / Redis
├── Web API / dashboard
└── Production monitoring
```

### MVP LLM Calls: ~8-12 total

---

## 30. Production Architecture

```
┌────────────────────────────────────────────────────────┐
│                 PRODUCTION ARCHITECTURE                 │
│                                                         │
│  Scheduler (Celery/APScheduler, runs daily)             │
│         ↓                                               │
│  News Collector (async) + Market Data Fetcher           │
│         ↓                                               │
│  PostgreSQL (articles, events, factors, analyses)       │
│  Redis (cache: embeddings, LLM responses, data)        │
│         ↓                                               │
│  Analysis Engine (pipeline.py)                          │
│  + LLM Service (rate-limited)                           │
│         ↓                                               │
│  FastAPI REST Endpoints                                 │
│         ↓                                               │
│  Web Dashboard / Mobile App / Email Reports             │
└────────────────────────────────────────────────────────┘
```

| Component | MVP | Production |
|---|---|---|
| Storage | SQLite / JSON | PostgreSQL + Redis |
| Scheduling | Manual CLI | APScheduler / Celery |
| Exposure | Sector defaults | Sector + LLM + regression |
| Factor graph | Direct only | Direct + indirect (depth 0-3) |
| Sensitivity | None | Rolling multi-factor regression |
| Regimes | None | Rule-based regime detection |
| Benchmark | None | Brinson attribution |
| API | None | FastAPI REST endpoints |
| Monitoring | None | Prometheus, error alerting |

---

## 31. Major Failure Modes

| # | Failure Mode | Probability | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **False causal attribution** | HIGH | HIGH | Always report large unexplained component |
| 2 | **Stale portfolio** | HIGH | MEDIUM | Display "as of" date; compute staleness |
| 3 | **LLM hallucination** | MEDIUM | HIGH | Validate against curated factor taxonomy |
| 4 | **Exposure vector errors** | MEDIUM | HIGH | Statistical regression to validate |
| 5 | **Double counting** | MEDIUM | MEDIUM | Correlated event detection; path dedup |
| 6 | **Missing events** | MEDIUM | MEDIUM | Multiple news sources; monitor unexplained spikes |
| 7 | **Regime misclassification** | LOW | MEDIUM | Multiple indicators; default to neutral |
| 8 | **Regression instability** | MEDIUM | LOW | Robust regression; confidence intervals |
| 9 | **Graph explosion** | LOW | LOW | Cap on max paths; strength threshold |
| 10 | **Overconfident explanations** | MEDIUM | HIGH | Enforce hedged language; confidence thresholds |

---

## 32. Recommended Implementation Roadmap

### Phase 1: Foundation (Weeks 1-3)

```
Week 1:
  ├── Set up project structure
  ├── Define all Pydantic models
  ├── Implement factor taxonomy
  ├── Implement sector default exposures
  └── Build factor graph with 30-40 curated edges

Week 2:
  ├── Build news collector (Google News RSS)
  ├── Implement URL + title deduplication
  ├── Build LLM event extraction (batched)
  ├── Build LLM event → factor mapping
  └── Implement event importance scoring

Week 3:
  ├── Build direct impact calculator
  ├── Build basic attribution ranker
  ├── Build LLM explanation generator
  ├── Wire up end-to-end pipeline
  └── Test with 2-3 real mutual funds
```

### Phase 2: Depth (Weeks 4-6)

```
Week 4:
  ├── Implement embedding-based article clustering
  ├── Add indirect relationship engine (depth 2-3)
  ├── Implement path decay and strength computation
  └── Add double-counting prevention

Week 5:
  ├── Implement historical sensitivity regression
  ├── Add market data fetchers
  ├── Build combined exposure scoring
  └── Add actual vs expected framework

Week 6:
  ├── Set up PostgreSQL database
  ├── Implement data persistence layer
  ├── Add Redis caching for LLM responses
  └── Comprehensive unit testing
```

### Phase 3: Polish (Weeks 7-9)

```
Week 7:
  ├── Implement market regime detection
  ├── Add regime-conditional edge strengths
  ├── Build benchmark attribution (Brinson)
  └── Add time decay modeling

Week 8:
  ├── Build FastAPI REST endpoints
  ├── Implement scheduled daily runs
  ├── Add error handling and retry logic
  └── Build audit trail logging

Week 9:
  ├── Backtesting framework
  ├── Run on 3 months of historical data
  ├── Tune parameters
  └── Documentation
```

### Phase 4: Production (Weeks 10-12)

```
Week 10-12:
  ├── Production deployment
  ├── Monitoring and alerting
  ├── A/B test explanation quality
  ├── Expand to 50+ mutual funds
  ├── Add more news sources
  └── Iterate on factor graph from backtest results
```

---

## Final Recommendations

### The Single Most Important Design Decision

> **Use ordinal/qualitative impact categories ("strong negative", "moderate positive") instead of precise percentages for investor-facing output.**

The precision of "-0.28% impact from crude oil" is an illusion. The system cannot reliably estimate impact to 2 decimal places. But it CAN reliably say "rising crude oil was a moderate headwind for this fund through its cost-sensitive holdings." This qualitative statement is defensible; the precise number is not.

Reserve the numbers for internal ranking and debugging. Present the investor with a narrative that honestly conveys what the system knows, what it suspects, and what it cannot determine.
