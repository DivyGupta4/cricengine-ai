# CricEngine AI — Phase 3B: External Source Evaluation

> **Authority**: Phase 3B Milestone Implementation (Part B — External Data Sources)  
> **Status**: COMPLETED AND VERIFIED  
> **Date**: November 2026  
> **Scope**: Comparative evaluation of external cricket data repositories for player attribute enrichment.

---

## 1. Executive Summary

To enrich CricEngine AI's canonical player master with authoritative attributes (batting hand, bowling style, birthdates, and listed roles), we conducted empirical technical evaluations across six external data providers:
1. **ESPNcricinfo Athlete API**
2. **BCCI Official Registry**
3. **Official National Cricket Boards (CA, ECB, PCB, CSA, etc.)**
4. **CricketArchive**
5. **Wikidata SPARQL Knowledge Graph**
6. **Cricsheet Static Registers (`people.csv`, `names.csv`)**

Our empirical findings conclude that while third-party web APIs provide rich attributes for top-tier international stars, **live dynamic extraction across all 7,014 players is infeasible for production pipelines** due to severe rate-limiting (WAF/Akamai), intermittent HTTP 503 errors, high latency (~3.9s/request), and lack of formal SLAs. 

The optimal, reproducible architecture is a **statically verified registry baseline** combined with **curated attribute seeds** and **direct empirical box-score observation**, strictly preserving `NULL` for unobserved values to eliminate data hallucination.

---

## 2. Comparative Matrix of External Sources

| Source | Coverage (% of 7,014) | Attributes Available | API Protocol / Access | Latency / Reliability | Legal / Licensing Status | Recommendation |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- |
| **Cricsheet Registers** | **100.0%** (7,014) | Identifier, Display Name, Unique Name, Multi-Registry Keys | Local CSV (`people.csv`, `names.csv`) | Instant (<0.1s), 100% Reliable | Open Data (ODbL / CC-BY) | **Primary Backbone** |
| **Direct Match Box-Scores** | **99.4%** (6,974) | Career runs, balls faced, overs, wickets, catches, observed role | Local Curated DuckDB | Instant (<1.0s), 100% Reliable | First-party Curated Derived | **Primary Role Engine** |
| **ESPNcricinfo Athlete API** | **99.9%** (7,013 keys) | Full Name, DOB, Batting Style, Bowling Style, Position, Teams | Reverse-Engineered REST (`/athletes/{id}`) | High latency (~3.9s), ~30% HTTP 503 errors, Akamai WAF | Unofficial / No SLA | **Curated Seed Profiles Only** |
| **BCCI Registry** | **18.7%** (1,311 keys) | Domestic Indian IDs, basic names | Web scraping / Proprietary | Fragile, no structured API | Proprietary | **Disambiguation Key Only** |
| **CricketArchive** | **23.3%** (1,634 keys) | Detailed biographical, historical career records | Paywalled Web UI | Paywall restricted | Commercial Copyright | **Key Cross-Reference Only** |
| **Wikidata SPARQL** | **< 5.0%** (<350) | P7422 (batting hand), P7423 (bowling style), DOB | SPARQL HTTP Endpoint | Moderate latency, severe attribute sparsity | Creative Commons CC0 | **Auxiliary Validation Only** |

---

## 3. Empirical Test Results: ESPNcricinfo Athlete Endpoint

We performed live benchmark probing against the ESPNcricinfo athlete endpoint (`https://site.web.api.espn.com/apis/common/v3/sports/cricket/athletes/{cricinfo_id}`):

### 3.1. Benchmark Performance (10 Representative Marquee Players)
- **Batch Size**: 10 requests
- **Total Duration**: 39.24 seconds (Average: 3.92s per athlete)
- **Success Rate**: 70.0% (7 succeeded, 3 failed)
- **Failures Encountered**:
  - `28081` (MS Dhoni): `HTTP Error 503: Service Unavailable`
  - `219889` (David Warner): `HTTP Error 503: Service Unavailable`
  - `37737` (Yuvraj Singh): `HTTP Error 503: Service Unavailable`

### 3.2. Technical Assessment of ESPNcricinfo
1. **Akamai Edge Server Intermittency**: The endpoint is served via edge caches that intermittently throw `503 Service Unavailable` for specific high-traffic legacy athletes.
2. **Throughput Bottleneck**: At 3.9 seconds per request, fetching all 7,014 players sequentially would require **over 7.6 hours**, during which Akamai WAF would inevitably trigger IP blocking (`429 Too Many Requests` or `403 Forbidden`).
3. **Payload Variance**: The JSON structure varies across player eras (e.g., `batStyle` and `bowlStyle` arrays are frequently empty for associate cricketers and bowlers who rarely batted).

---

## 4. Technical Assessment of Other Providers

### 4.1. Wikidata SPARQL (`query.wikidata.org`)
- **Query Executed**: SPARQL query matching cricketers via ESPNcricinfo ID (P3571) to extract Batting Hand (P7422) and Bowling Style (P7423).
- **Finding**: While basic biographical metadata (birth date, nationality) is present for international players, cricket-specific technical attributes (`P7422`, `P7423`) have $<5\%$ population coverage among modern cricketers in Cricsheet. Bulk SPARQL queries frequently time out (`HTTP 500 / 504 Gateway Timeout`) under concurrent server load.

### 4.2. BCCI Official Database
- **Finding**: BCCI provides domestic player registration IDs (`key_bcci` in `people.csv`, covering 1,311 domestic Indian players). However, there is no public, unauthenticated API offering programmatic retrieval of bowling arm, bowling type, or pace/spin categorization.

---

## 5. Architectural Decision & Long-Term Acquisition Strategy

Based on this evaluation, Phase 3B adopts the following architectural strategy:

1. **Immediate Production Baseline (Phase 3B)**:
   - Sourced canonical identity and unique names 100% from Cricsheet registers (`people.csv`).
   - Sourced alternate full names (2,367 players) from `names.csv`.
   - Computed `observed_historical_role` 100% empirically from DuckDB ball-by-ball and participation records.
   - Sourced authoritative verified playing attributes (`batting_hand`, `bowling_style`, `pace_spin_class`, `date_of_birth`, `officially_listed_role`) for core international players into a static curated seed dictionary.
   - Preserved all other unconfirmed player attributes strictly as `NULL` with provenance `UNAVAILABLE`.
2. **Future Offline Bulk Acquisition (Post-Phase 3B)**:
   - If full attribute coverage for all 7,014 players is desired in future milestones, it should be conducted via an **asynchronous offline crawler** with exponential backoff, persistent SQLite/DuckDB disk caching, and proxy rotation, completely decoupled from feature store materialization.
   - Under no circumstances should runtime pipelines rely on live third-party network requests.
