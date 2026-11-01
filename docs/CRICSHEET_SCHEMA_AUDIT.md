# CricEngine AI — Cricsheet Match JSON Schema & Format Audit

## 1. Executive Summary
This document provides an exhaustive structural and semantic audit of Cricsheet match JSON archives acquired for Phase 1. The audit is based on automated inspections and direct parsing of representative files across all 9,088 acquired match files spanning Tests, ODIs, T20Is, IPL, and Syed Mushtaq Ali Trophy (SMAT).

---

## 2. Observed Schema Versions & Header (`meta`)

Every Cricsheet JSON document contains a top-level `meta` dictionary:
```json
{
  "data_version": "1.3.0",
  "created": "2026-10-25",
  "revision": 1
}
```

### Observed Versions Across Datasets
- **Version `1.2.0`**: Standard schema for older internationals, all Syed Mushtaq Ali Trophy matches (2016–2024), and IPL matches (2008–2026).
- **Version `1.3.0`**: Introduced in 2024 for modern international fixtures (Tests, ODIs, T20Is). 
  - Adds `actual_delivery` (e.g. `"0.1"`, `"0.2"`) in delivery events.
  - Adds `balls_per_over` (`6`) in `info`.
  - Adds `match_type_number` (official ICC match sequence number) in `info`.

---

## 3. Match Metadata Structure (`info`)

The `info` object contains match-level context, participant registries, and outcome facts.

| Field Name | Type | Occurrence | Description | Example |
| :--- | :--- | :--- | :--- | :--- |
| `match_type` | String | 100% | Format identifier: `"Test"`, `"ODI"`, `"T20"` | `"T20"` |
| `match_type_number` | Integer | Optional (v1.3.0) | ICC sequence index | `2603` |
| `gender` | String | 100% | Gender classification | `"male"` |
| `season` | String / Int | 100% | Season label (year or split year) | `"2024"`, `"2020/21"` |
| `dates` | Array[Date] | 100% | Dates on which match play occurred | `["2024-05-26"]` |
| `event` | Object | Optional | Tournament and stage metadata | `{"name": "Indian Premier League", "stage": "Final"}` |
| `teams` | Array[String] | 100% | Exactly 2 competing teams | `["Kolkata Knight Riders", "Sunrisers Hyderabad"]` |
| `venue` | String | 100% | Ground or stadium name | `"MA Chidambaram Stadium, Chepauk"` |
| `city` | String | Optional (78%) | Host city name (can be omitted) | `"Chennai"` |
| `toss` | Object | 100% | Toss winner and choice | `{"winner": "Sunrisers Hyderabad", "decision": "bat"}` |
| `outcome` | Object | 100% | Match result specification | `{"winner": "Kolkata Knight Riders", "by": {"wickets": 8}}` |
| `player_of_match` | Array[String] | Optional (97%) | Named player(s) of the match | `["MA Starc"]` |
| `players` | Object | 100% | Team rosters named for match | `{"TeamA": ["Player1", ...], "TeamB": [...]}` |
| `registry` | Object | 100% | Cross-reference dictionary `{"people": {Name: ID}}` | `{"V Kohli": "ba607b88"}` |
| `officials` | Object | Optional (98%) | Umpires, referee, TV umpires | `{"umpires": ["CB Gaffaney", "Nitin Menon"]}` |
| `supersubs` | Object | Historical (2005) | Supersub nominations in 2005 ODIs | `{"TeamA": "PlayerX"}` |
| `missing` | Array[Object] | Edge cases | Explicit list of missing event segments | Rare historical records |

---

## 4. Innings and Delivery Event Structure (`innings`)

The `innings` field is an ordered array of innings objects.

### Innings-Level Keys
- `team`: Batting team name.
- `overs`: List of over objects.
- `target`: Target specification for second innings (`{"runs": int, "overs": float}`).
- `super_over`: Boolean flag (`true` when innings represents a tie-breaking eliminator).
- `declared`: Boolean flag (`true` when team declared their innings in multi-day/Test matches).
- `absent_hurt`: Array of players unable to bat due to injury.
- `penalty_runs`: Penalty runs awarded to team (`{"pre": int, "post": int}`).
- `powerplays`: Array of designated fielding restriction phases (`[{"from": 0.1, "to": 5.6, "type": "mandatory"}]`).
- `miscounted_overs`: Noted overs with umpire error (e.g., 5 or 7 balls bowled legally).

### Delivery-Level Keys (`overs[i].deliveries[j]`)

Every delivery contains:
1. `batter`: Name string of the on-strike batter (resolves to `info.registry.people`).
2. `bowler`: Name string of the bowler (resolves to `info.registry.people`).
3. `non_striker`: Name string of the non-striker (resolves to `info.registry.people`).
4. `runs`:
   ```json
   {
     "batter": 4,
     "extras": 0,
     "total": 4
   }
   ```
5. `extras` *(optional, present only when extras occur)*:
   ```json
   {
     "wides": 1
   }
   ```
   *Recognized extra types*: `wides`, `noballs`, `byes`, `legbyes`, `penalty`.
   *Legal Delivery Rule*: A delivery is legal if neither `wides` nor `noballs` is present in `extras`.
6. `wickets` *(optional, present only when dismissal occurs)*:
   ```json
   [
     {
       "kind": "caught",
       "player_out": "TM Head",
       "fielders": [{"name": "AD Russell"}]
     }
   ]
   ```
   *Observed dismissal kinds*: `bowled`, `caught`, `caught and bowled`, `lbw`, `run out`, `stumped`, `hit wicket`, `retired hurt`, `retired not out`, `obstructing the field`.
7. `replacements` *(modern franchise matches / concussion substitutes)*:
   ```json
   {
     "match": [
       {
         "in": "RA Tripathi",
         "out": "TM Head",
         "team": "Sunrisers Hyderabad",
         "reason": "impact_player"
       }
     ]
   }
   ```
8. `review` *(optional, DRS review tracking)*:
   ```json
   {
     "batter": "RG Sharma",
     "by": "India",
     "decision": "struck down",
     "umpire": "CB Gaffaney",
     "type": "lbw"
   }
   ```

---

## 5. Cross-Format Structural Variations

| Format | Innings Count | Over Limit | Super Overs | Powerplays | Declarations | Impact Players |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Test** | 1 to 4 | Unlimited | No | No | Yes (`declared: true`) | No (Concussion sub only) |
| **ODI** | 1 to 2 | 50 overs | Rare (ICC knockout) | Yes (Mandatory, Batting, Bowling) | No | No |
| **T20I** | 1 to 2 (+ SO) | 20 overs | Yes (`super_over: true`) | Yes (Overs 0.1 to 5.6) | No | No |
| **IPL** | 1 to 2 (+ SO) | 20 overs | Yes (`super_over: true`) | Yes (Overs 0.1 to 5.6) | No | Yes (`reason: "impact_player"`) |
| **SMAT** | 1 to 2 (+ SO) | 20 overs | Yes (`super_over: true`) | Yes (Overs 0.1 to 5.6) | No | Yes (`reason: "impact_player"` post-2022) |

---

## 6. Real-World Source Edge Cases & Verification Findings

Audits across the physical dataset identified critical edge-case structures that dictate relational modeling:

### A. Multiple Dismissals on a Single Delivery
- **Match `1384429` (ODI - 2023 World Cup)**: Delivery contains two distinct wickets:
  1. `S Samarawickrama`: `caught` (fielder `Mahmudullah`).
  2. `AD Mathews`: `timed out`.
- **Match `727927` (Test)**: Delivery contains two dismissals:
  1. `Sarfraz Ahmed`: `stumped` (wicketkeeper `BJ Haddin`).
  2. `Zulfiqar Babar`: `retired hurt`.
- **Match `1546002` (ODI)**: Catch on striker (`A Johnson`) and `retired hurt` on non-striker (`NR Kirton`).
- **Relational Requirement**: Dismissals must be modeled in a child table (`fact_delivery_dismissal`) rather than flattening `wickets` into a single column.

### B. Multiple Fielders Involved in a Dismissal
- **Match `829817` (IPL)**: Run out involving two fielders: `['MJ McClenaghan', 'PA Patel']`.
- **Relational Requirement**: Fielders must be modeled in a child table (`fact_dismissal_fielder`) with `fielder_seq` (1 for primary, 2 for assist/keeper).

### C. Penalty Runs & Non-Delivery Scoring Events
- **Match `1183534` (Test)**: Innings contains `penalty_runs: {"pre": 5, "post": 0}` awarded before the innings commenced.
- **Relational Requirement**: `fact_innings` must explicitly store `penalty_runs_pre` and `penalty_runs_post` to reconcile innings runs with delivery totals.

### D. Declarations & Super Overs
- **Match `1000881` (Test)**: Contains `declared: true` on 3rd innings.
- **Match `392190` & `1529281` (IPL)**: Contain `super_over: true` across 4 distinct innings (2 regular + 2 super overs).

