# CricEngine AI — Data Dictionary

This document provides a comprehensive technical data dictionary for all components of the CricEngine AI data lake and lakehouse release (`v1.0.0`).

---

## 1. Canonical Relational Database (`cricengine.duckdb`)

### 1.1 `dim_match` (Dimension, 9,085 rows)
Normalized metadata describing every ingested cricket match.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `match_id` | VARCHAR | NO | **Primary Key**. Cricsheet unique match identifier (e.g., `'1389392'`). |
| `competition_name` | VARCHAR | NO | Name of tournament (e.g., `'Indian Premier League'`, `'T20 Internationals'`). |
| `competition_tier` | INTEGER | NO | Competition tier: 1 (International), 2 (Major Franchise / IPL), 3 (Domestic / SMAT). |
| `match_format` | VARCHAR | NO | Format enum: `'TEST'`, `'ODI'`, `'T20'`. |
| `match_type_number`| INTEGER | YES | Sequential international match type number if applicable. |
| `season` | VARCHAR | NO | Match season string (e.g., `'2023/24'`, `'2024'`). |
| `start_date` | DATE | NO | Match commencement date (YYYY-MM-DD). |
| `end_date` | DATE | NO | Match conclusion date (YYYY-MM-DD). |
| `team_1` | VARCHAR | NO | Name of first listed team. |
| `team_2` | VARCHAR | NO | Name of second listed team. |
| `gender` | VARCHAR | NO | Player gender designation (`'male'`). |
| `balls_per_over` | INTEGER | NO | Scheduled legal deliveries per over (standard: 6). |
| `source_archive` | VARCHAR | NO | Ingestion source zip archive name. |
| `source_file_path` | VARCHAR | NO | Relative path of original raw JSON file. |
| `source_file_hash` | VARCHAR | NO | Cryptographic SHA-256 hash of original raw JSON file. |
| `revision_number` | INTEGER | NO | Cricsheet file revision number. |

### 1.2 `dim_match_context` (Dimension, 9,085 rows)
Environmental and match outcome details.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `match_id` | VARCHAR | NO | **Foreign Key** referencing `dim_match.match_id`. |
| `venue_name` | VARCHAR | NO | Stadium name as recorded by source. |
| `city` | VARCHAR | YES | City location of stadium. |
| `toss_winner` | VARCHAR | YES | Team winning the pre-match coin toss. |
| `toss_decision` | VARCHAR | YES | Coin toss decision (`'bat'` or `'field'`). |
| `outcome_winner` | VARCHAR | YES | Match winning team (NULL if draw, tie, or no result). |
| `outcome_result` | VARCHAR | YES | Result descriptor (`'draw'`, `'tie'`, `'no result'`, NULL if winner). |
| `win_by_type` | VARCHAR | YES | Victory margin unit (`'runs'`, `'wickets'`, `'innings'`). |
| `win_by_margin` | INTEGER | YES | Numeric victory margin. |
| `method` | VARCHAR | YES | Interrupted match adjustment method (e.g., `'D/L'`). |
| `balls_per_over` | INTEGER | NO | Legal balls per over. |
| `event_name` | VARCHAR | YES | Broader series/tournament name. |
| `match_number` | VARCHAR | YES | Match number in tournament sequence (e.g., `'Final'`, `'3rd Match'`). |

### 1.3 `dim_player_master` (Dimension, 7,014 rows)
Canonical deduplicated player entities.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `player_id` | VARCHAR | NO | **Primary Key**. 8-character hexadecimal player ID. |
| `canonical_name` | VARCHAR | NO | Standardized display name (e.g., `'V Kohli'`, `'JJ Bumrah'`). |
| `is_active` | BOOLEAN | NO | True if player was active in professional cricket on/after 2020-01-01. |
| `created_at` | TIMESTAMP | NO | Ingestion timestamp. |

### 1.4 `fact_innings` (Fact, 19,697 rows)
Aggregated team performance per innings.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `innings_id` | VARCHAR | NO | **Primary Key**. Format: `{match_id}_{innings_num}`. |
| `match_id` | VARCHAR | NO | Foreign Key referencing `dim_match.match_id`. |
| `innings_num` | INTEGER | NO | Innings sequence (1, 2, 3, 4). |
| `batting_team` | VARCHAR | NO | Name of batting team. |
| `bowling_team` | VARCHAR | NO | Name of bowling team. |
| `is_super_over` | BOOLEAN | NO | True if tie-breaker super over. |
| `total_runs_scored` | INTEGER | NO | Total runs scored in innings. |
| `total_wickets_lost` | INTEGER | NO | Total dismissals in innings. |
| `total_deliveries` | INTEGER | NO | Total balls bowled (legal + extras). |
| `total_legal_deliveries`| INTEGER | NO | Total legal balls bowled. |
| `penalty_runs_pre` | INTEGER | NO | Penalty runs before innings. |
| `penalty_runs_post` | INTEGER | NO | Penalty runs during innings. |
| `target_runs` | INTEGER | YES | Chased target runs if 2nd/4th innings. |
| `target_overs` | FLOAT | YES | Allocated target overs. |

### 1.5 `fact_ball_by_ball` (Fact, 4,383,700 rows)
Core ball-by-ball event log.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `ball_id` | VARCHAR | NO | **Primary Key**. Format: `{match_id}_{innings_num}_{over_num}_{delivery_num}`. |
| `match_id` | VARCHAR | NO | Foreign Key referencing `dim_match.match_id`. |
| `innings_id` | VARCHAR | NO | Foreign Key referencing `fact_innings.innings_id`. |
| `innings_num` | INTEGER | NO | Innings index. |
| `over_num` | INTEGER | NO | 0-indexed over number (0 = 1st over). |
| `delivery_num` | INTEGER | NO | 1-indexed delivery within over. |
| `is_legal_delivery` | BOOLEAN | NO | True if ball counts towards over (excludes wides and no-balls). |
| `match_phase` | VARCHAR | NO | Game phase: `'powerplay'`, `'middle'`, `'death'`. |
| `batter_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id` (striker). |
| `bowler_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id`. |
| `non_striker_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id`. |
| `runs_batter` | INTEGER | NO | Runs scored off the bat. |
| `runs_extras` | INTEGER | NO | Total extras conceded on delivery. |
| `runs_total` | INTEGER | NO | Combined runs (`runs_batter + runs_extras`). |
| `wides` | INTEGER | NO | Wide runs on delivery. |
| `noballs` | INTEGER | NO | No-ball runs on delivery. |
| `byes` | INTEGER | NO | Bye runs on delivery. |
| `legbyes` | INTEGER | NO | Leg-bye runs on delivery. |
| `penalty` | INTEGER | NO | Penalty runs on delivery. |
| `is_wicket` | BOOLEAN | NO | True if a dismissal occurred on this delivery. |
| `wicket_count` | INTEGER | NO | Number of dismissals on delivery (usually 1, rarely 0). |

### 1.6 `fact_delivery_dismissal` (Fact, 136,691 rows)
Wicket dismissal event details.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `dismissal_id` | VARCHAR | NO | **Primary Key**. Format: `{ball_id}_{dismissal_seq}`. |
| `ball_id` | VARCHAR | NO | Foreign Key referencing `fact_ball_by_ball.ball_id`. |
| `match_id` | VARCHAR | NO | Foreign Key referencing `dim_match.match_id`. |
| `innings_num` | INTEGER | NO | Innings number. |
| `dismissal_seq` | INTEGER | NO | Sequence of dismissal on delivery (typically 1). |
| `player_out_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id` (dismissed batter). |
| `player_out_name_raw`| VARCHAR | NO | Raw source string of dismissed batter. |
| `dismissal_kind` | VARCHAR | NO | Classification (`'bowled'`, `'caught'`, `'lbw'`, `'run out'`, `'stumped'`). |
| `bowler_credited` | BOOLEAN | NO | True if wicket is credited to the bowler's bowling statistics. |

### 1.7 `fact_dismissal_fielder` (Fact, 94,926 rows)
Fielder attribution for dismissals.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `dismissal_fielder_id`| VARCHAR | NO | **Primary Key**. Format: `{dismissal_id}_{fielder_seq}`. |
| `dismissal_id` | VARCHAR | NO | Foreign Key referencing `fact_delivery_dismissal.dismissal_id`. |
| `fielder_seq` | INTEGER | NO | Sequence of fielder involvement (1 for catch/stumping, 1 or 2 for run-outs). |
| `fielder_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id`. |
| `fielder_name_raw` | VARCHAR | NO | Raw source name of fielder. |
| `is_substitute` | BOOLEAN | NO | True if fielder was a substitute. |

### 1.8 `fact_match_participation` (Fact, 200,709 rows)
Roster participation records.

| Column | Type | Nullable | Description |
| :--- | :--- | :--- | :--- |
| `participation_id` | VARCHAR | NO | **Primary Key**. Format: `{match_id}_{player_id}`. |
| `match_id` | VARCHAR | NO | Foreign Key referencing `dim_match.match_id`. |
| `player_id` | VARCHAR | NO | Foreign Key referencing `dim_player_master.player_id`. |
| `team_name` | VARCHAR | NO | Team represented in match. |
| `participation_role`| VARCHAR | NO | Playing role (e.g. `'player'`, `'captain'`, `'keeper'`). |
| `in_starting_xi` | BOOLEAN | NO | True if member of designated Starting XI. |
| `batted_flag` | BOOLEAN | NO | True if player batted during match. |
| `bowled_flag` | BOOLEAN | NO | True if player bowled at least one delivery. |
| `fielded_flag` | BOOLEAN | NO | True if player participated in fielding. |
| `evidence_confidence`| VARCHAR | NO | Validation confidence level (`'HIGH'`, `'CONFIRMED'`). |

---

## 2. Feature Store (`feature_store_v3b`)

### 2.1 `player_match` (200,709 rows, 51 columns)
Single-match transformed player performance metrics.

- **Partitioning:** `match_format={TEST,ODI,T20}`, `season={season_id}`.
- **Key Columns:**
  - `player_id`, `match_id`: Primary composite entity keys.
  - `batting_position`: Numerical order of entry (1 to 11).
  - `runs_scored`, `balls_faced`, `strike_rate`: Batting volume and velocity.
  - `boundary_fours`, `boundary_sixes`, `dot_balls_faced`: Boundary and dot percentages.
  - `overs_bowled`, `runs_conceded`, `wickets_credited`, `economy_rate`: Bowling volume and efficiency.
  - `batting_load`, `bowling_load`: Normalized situational load metrics.
  - `allrounder_balance_index`: Degree of dual-skill participation.

### 2.2 `rolling_match` (602,127 rows, 34 columns)
Trailing multi-window moving statistics ($w \in \{5, 10, 20\}$ matches).

- **Partitioning:** `match_format`, `window_size={5,10,20}`, `season`.
- **Key Columns:**
  - `matches_in_window`: Number of observed matches within trailing window.
  - `rolling_runs_scored`, `rolling_batting_avg`, `rolling_batting_sr`: Batting form metrics.
  - `rolling_wickets_taken`, `rolling_economy_rate`, `rolling_bowling_sr`: Bowling form metrics.
  - `decayed_batting_sr`, `decayed_economy_rate`: Exponentially weighted recency decay.
  - `shrunk_batting_sr`, `shrunk_economy_rate`: Empirical Bayes shrinkage towards cohort priors.
  - `days_since_last_match`: Inter-match inactivity gap.

### 2.3 `rolling_time` (602,127 rows, 19 columns)
Trailing calendar-time moving statistics ($w \in \{30, 90, 365\}$ days).

- **Partitioning:** `match_format`, `window_days={30,90,365}`, `season`.
- **Key Columns:**
  - `rolling_runs_scored`, `rolling_batting_avg`, `rolling_wickets_taken`.
  - Recency-decayed velocity indicators.

### 2.4 `contextual_features` (200,709 rows, 18 columns)
- **Key Columns:**
  - `venue_historical_park_factor`: Venue scoring inflation/deflation factor (1.0 = neutral).
  - `opposition_bowling_quality_index`: Latent bowling difficulty presented by opposing attack.
  - `opposition_batting_quality_index`: Strength of opposing batting lineup.
  - `is_home_match`, `is_neutral_match`: Location context.

---

## 3. Player Rating Store (`rating_store_v4`)

### 3.1 `pre_match_snapshots` (19,642 rows, 12 columns)
Point-in-time latent ability ratings frozen strictly prior to match start (**D-1 guarantee**).

| Column | Type | Description |
| :--- | :--- | :--- |
| `player_id` | VARCHAR | Canonical player ID. |
| `match_id` | VARCHAR | Match ID for which rating is snapshotted. |
| `match_date` | VARCHAR | Match date (YYYY-MM-DD). |
| `inferred_role` | VARCHAR | Categorical role archetype (`'R1_OPENER'`, `'R8_PACE_SPECIALIST'`). |
| `pre_r_bat` | FLOAT | Pre-match batting latent rating (Glicko-scale, prior mean: 1500). |
| `pre_rd_bat` | FLOAT | Pre-match batting rating deviation (uncertainty). |
| `pre_r_bowl` | FLOAT | Pre-match bowling latent rating. |
| `pre_rd_bowl`| FLOAT | Pre-match bowling rating deviation (uncertainty). |
| `pre_r_field`| FLOAT | Pre-match fielding rating. |
| `pre_rd_field`| FLOAT | Pre-match fielding rating deviation. |
| `pre_vorp` | FLOAT | Expected Value Over Replacement Player baseline prior to toss. |

### 3.2 `player_rating_current` (9,406 active format states, 33 columns)
Latest active latent ratings representing current player skill profiles.

- `theta_bat_rate`, `theta_bat_surv`: Decoupled scoring rate and survival hazard parameters.
- `theta_bowl_haz`, `theta_bowl_econ`: Decoupled wicket hazard and economy rate parameters.
- `r_bat`, `r_bowl`, `r_field`, `r_allround`: Composite ratings.
- `vorp_rating`: Modern marginal replacement surplus.

---

## 4. Predictive Store (`predictive_store_v4c`)

### 4.1 `player_match_vorp` (9,708 rows, 13 columns)
Post-match realized value added over replacement player baseline.

| Column | Type | Description |
| :--- | :--- | :--- |
| `player_id` | VARCHAR | Canonical player ID. |
| `match_id` | VARCHAR | Match ID. |
| `match_date` | VARCHAR | Match date. |
| `inferred_role` | VARCHAR | Player role archetype. |
| `vorp_bat` | DOUBLE | Realized batting marginal runs over replacement. |
| `vorp_bowl` | DOUBLE | Realized bowling marginal runs over replacement. |
| `vorp_field` | DOUBLE | Realized fielding marginal runs over replacement. |
| `vorp_total` | DOUBLE | Net match VORP (`vorp_bat + vorp_bowl + vorp_field`). |
| `is_above_replacement`| BOOLEAN | True if net VORP > 0.0. |

### 4.2 `batting_predictions` (9,708 rows, 25 columns)
Probabilistic expectations and confidence intervals for batting outcomes.

- `expected_runs`, `expected_balls_faced`, `expected_boundary_rate`.
- `runs_interval_50_low / high`: 50% central credible interval.
- `runs_interval_90_low / high`: 90% central credible interval.
- `actual_runs_scored`: Realized actual runs (for calibration validation).
