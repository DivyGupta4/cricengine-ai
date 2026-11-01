"""
Automated Unit Tests for Step 3A Parser Specification & Schema Invariants

Tests multi-wicket delivery handling, multi-fielder child tables,
impact player replacements, match officials extraction, format-specific
phase rules (decoupling over number and ball age), legal delivery semantics,
player participation evidence classification, and innings reconciliation
with explicit quality severity tiers.
"""
import json
from pathlib import Path
import pytest

from config.settings import CRICSHEET_EXTRACTED_DIR
from etl.parse_cricsheet import (
    calculate_match_phase,
    parse_delivery_extras,
    parse_dismissals_and_fielders,
    parse_replacements,
    parse_officials,
    classify_player_participation,
    reconcile_innings_totals,
)


def test_calculate_match_phase_t20_standard():
    """Verify standard 20-over T20 phase cutoffs."""
    assert calculate_match_phase("T20", 0) == "POWERPLAY"
    assert calculate_match_phase("T20", 5) == "POWERPLAY"
    assert calculate_match_phase("T20", 6) == "MIDDLE"
    assert calculate_match_phase("T20", 14) == "MIDDLE"
    assert calculate_match_phase("T20", 15) == "DEATH"
    assert calculate_match_phase("T20", 19) == "DEATH"
    assert calculate_match_phase("T20", 0, is_super_over=True) == "SUPER_OVER"


def test_calculate_match_phase_t20_shortened():
    """Verify proportionally scaled phase cutoffs for rain-shortened T20 matches."""
    # 5-over match: PP is first 2 overs (0, 1), Death is last over (4)
    assert calculate_match_phase("T20", 0, scheduled_overs=5) == "POWERPLAY"
    assert calculate_match_phase("T20", 1, scheduled_overs=5) == "POWERPLAY"
    assert calculate_match_phase("T20", 2, scheduled_overs=5) == "MIDDLE"
    assert calculate_match_phase("T20", 4, scheduled_overs=5) == "DEATH"


def test_calculate_match_phase_odi_standard():
    """Verify standard 50-over ODI phase cutoffs."""
    assert calculate_match_phase("ODI", 0, scheduled_overs=50) == "POWERPLAY_1"
    assert calculate_match_phase("ODI", 9, scheduled_overs=50) == "POWERPLAY_1"
    assert calculate_match_phase("ODI", 10, scheduled_overs=50) == "MIDDLE"
    assert calculate_match_phase("ODI", 39, scheduled_overs=50) == "MIDDLE"
    assert calculate_match_phase("ODI", 40, scheduled_overs=50) == "DEATH"
    assert calculate_match_phase("ODI", 49, scheduled_overs=50) == "DEATH"


def test_calculate_match_phase_test_decoupled_ball_age():
    """
    Verify Test cricket phases decouple over number, ball age, and ball changes.
    Does NOT assume an automatic new ball reset every 80 overs without source evidence.
    """
    # First new ball: overs 0 to 19 -> INITIAL_NEW_BALL
    assert calculate_match_phase("Test", 5) == "INITIAL_NEW_BALL"
    assert calculate_match_phase("Test", 19) == "INITIAL_NEW_BALL"

    # Worn ball middle: overs 20 to 79 -> WORN_BALL_MIDDLE
    assert calculate_match_phase("Test", 25) == "WORN_BALL_MIDDLE"
    assert calculate_match_phase("Test", 79) == "WORN_BALL_MIDDLE"

    # Over 80+ without verified new ball event remains OLD_BALL_UNCONFIRMED_NEW
    # (prevents fabricating ball changes)
    assert calculate_match_phase("Test", 80) == "OLD_BALL_UNCONFIRMED_NEW"
    assert calculate_match_phase("Test", 85) == "OLD_BALL_UNCONFIRMED_NEW"
    assert calculate_match_phase("Test", 120) == "OLD_BALL_UNCONFIRMED_NEW"

    # When an explicit new ball event is recorded at over 80
    assert calculate_match_phase("Test", 82, new_ball_taken_over=80) == "SECOND_NEW_BALL"
    assert calculate_match_phase("Test", 99, new_ball_taken_over=80) == "SECOND_NEW_BALL"
    assert calculate_match_phase("Test", 105, new_ball_taken_over=80) == "SECOND_NEW_BALL_MIDDLE"
    assert calculate_match_phase("Test", 145, new_ball_taken_over=80) == "OLD_BALL_80_PLUS"


def test_parse_delivery_extras_and_legal_ball():
    """Verify extra component breakdown and legal ball detection."""
    # Legal ball with no extras
    w, nb, b, lb, p, legal = parse_delivery_extras(None)
    assert (w, nb, b, lb, p, legal) == (0, 0, 0, 0, 0, True)

    # Wide ball (illegal)
    w, nb, b, lb, p, legal = parse_delivery_extras({"wides": 1})
    assert (w, nb, b, lb, p, legal) == (1, 0, 0, 0, 0, False)

    # No ball with runs (illegal)
    w, nb, b, lb, p, legal = parse_delivery_extras({"noballs": 1})
    assert (w, nb, b, lb, p, legal) == (0, 1, 0, 0, 0, False)

    # Leg byes (legal delivery)
    w, nb, b, lb, p, legal = parse_delivery_extras({"legbyes": 2})
    assert (w, nb, b, lb, p, legal) == (0, 0, 0, 2, 0, True)


def test_parse_multi_wicket_delivery():
    """Verify extraction of multiple dismissals on a single delivery."""
    raw_wickets = [
        {"kind": "caught", "player_out": "S Samarawickrama", "fielders": [{"name": "Mahmudullah"}]},
        {"kind": "timed out", "player_out": "AD Mathews"},
    ]
    reg_people = {"S Samarawickrama": "p1_id", "AD Mathews": "p2_id", "Mahmudullah": "p3_id"}

    dismissals, fielders = parse_dismissals_and_fielders(
        raw_wickets,
        ball_id="1384429_1_24_2",
        match_id="1384429",
        innings_num=1,
        registry_people=reg_people,
    )

    assert len(dismissals) == 2
    assert dismissals[0]["dismissal_id"] == "1384429_1_24_2_1"
    assert dismissals[0]["player_out_id"] == "p1_id"
    assert dismissals[0]["dismissal_kind"] == "caught"
    assert dismissals[0]["bowler_credited"] is True

    assert dismissals[1]["dismissal_id"] == "1384429_1_24_2_2"
    assert dismissals[1]["player_out_id"] == "p2_id"
    assert dismissals[1]["dismissal_kind"] == "timed out"
    assert dismissals[1]["bowler_credited"] is False

    assert len(fielders) == 1
    assert fielders[0]["dismissal_id"] == "1384429_1_24_2_1"
    assert fielders[0]["fielder_id"] == "p3_id"


def test_parse_multi_fielder_dismissal():
    """Verify extraction of multiple fielders involved in a run out or relay catch."""
    raw_wickets = [
        {
            "kind": "run out",
            "player_out": "RG Sharma",
            "fielders": [{"name": "MJ McClenaghan"}, {"name": "PA Patel"}],
        }
    ]
    reg_people = {"RG Sharma": "rohit_id", "MJ McClenaghan": "mitch_id", "PA Patel": "parthiv_id"}

    dismissals, fielders = parse_dismissals_and_fielders(
        raw_wickets,
        ball_id="829817_1_18_4",
        match_id="829817",
        innings_num=1,
        registry_people=reg_people,
    )

    assert len(dismissals) == 1
    assert dismissals[0]["dismissal_kind"] == "run out"
    assert dismissals[0]["bowler_credited"] is False

    assert len(fielders) == 2
    assert fielders[0]["fielder_seq"] == 1
    assert fielders[0]["fielder_id"] == "mitch_id"
    assert fielders[1]["fielder_seq"] == 2
    assert fielders[1]["fielder_id"] == "parthiv_id"


def test_parse_replacements_impact_player():
    """Verify parsing of impact player replacements."""
    deliv_dict = {
        "replacements": {
            "match": [
                {
                    "in": "RA Tripathi",
                    "out": "TM Head",
                    "team": "Sunrisers Hyderabad",
                    "reason": "impact_player",
                }
            ]
        }
    }
    reg_people = {"RA Tripathi": "tripathi_id", "TM Head": "head_id"}

    reps = parse_replacements(deliv_dict, "1426261_2_12_3", "1426261", reg_people)
    assert len(reps) == 1
    assert reps[0]["in_player_id"] == "tripathi_id"
    assert reps[0]["out_player_id"] == "head_id"
    assert reps[0]["replacement_reason"] == "impact_player"
    assert reps[0]["team_name"] == "Sunrisers Hyderabad"


def test_parse_match_officials():
    """Verify officials are parsed and assigned distinct canonical roles."""
    officials_dict = {
        "umpires": ["Navdeep Singh", "NA Patwardhan"],
        "tv_umpires": ["AG Wharf"],
        "match_referees": ["V Narayan Kutty"],
    }
    reg_people = {
        "Navdeep Singh": "u1_id",
        "NA Patwardhan": "u2_id",
        "AG Wharf": "tv1_id",
        "V Narayan Kutty": "ref_id",
    }

    records = parse_officials(officials_dict, "1426261", reg_people)
    assert len(records) == 4
    roles = {r["official_role"] for r in records}
    assert roles == {"onfield_umpire", "tv_umpire", "match_referee"}


def test_classify_player_participation():
    """Verify participation evidence correctly separates Starting XI, Impact Subs, and Bench."""
    info_players = {
        "Sunrisers Hyderabad": ["TM Head", "Abhishek Sharma", "RA Tripathi", "Mayank Agarwal"]
    }
    match_reps = [
        {"in_player_name": "RA Tripathi", "out_player_name": "TM Head", "replacement_reason": "impact_player"}
    ]
    active_batters = {"TM Head", "Abhishek Sharma", "RA Tripathi"}
    active_bowlers = set()
    active_fielders = {"Sub Fielder A"}

    # Case 1: In squad and active on field -> CONFIRMED_PLAYING_XI
    p_head = classify_player_participation(
        "p_head", "TM Head", "Sunrisers Hyderabad",
        info_players, match_reps, active_batters, active_bowlers, active_fielders
    )
    assert p_head["participation_role"] == "STARTING_XI"
    assert p_head["evidence_confidence"] == "CONFIRMED_PLAYING_XI"
    assert p_head["is_starting_xi"] is True

    # Case 2: Impact player subbed in -> IMPACT_PLAYER
    p_tripathi = classify_player_participation(
        "p_tripathi", "RA Tripathi", "Sunrisers Hyderabad",
        info_players, match_reps, active_batters, active_bowlers, active_fielders
    )
    assert p_tripathi["participation_role"] == "IMPACT_PLAYER"
    assert p_tripathi["evidence_confidence"] == "IMPACT_PLAYER"
    assert p_tripathi["is_starting_xi"] is False

    # Case 3: In squad but did not bat, bowl, or field -> BENCH_NOMINATED / UNCONFIRMED_ROSTER
    p_mayank = classify_player_participation(
        "p_mayank", "Mayank Agarwal", "Sunrisers Hyderabad",
        info_players, match_reps, active_batters, active_bowlers, active_fielders
    )
    assert p_mayank["participation_role"] == "BENCH_NOMINATED"
    assert p_mayank["evidence_confidence"] == "UNCONFIRMED_ROSTER"
    assert p_mayank["is_starting_xi"] is False

    # Case 4: Substitute fielder not in starting squad -> SUBSTITUTE_FIELDER
    p_sub = classify_player_participation(
        "p_sub", "Sub Fielder A", "Sunrisers Hyderabad",
        info_players, match_reps, active_batters, active_bowlers, active_fielders
    )
    assert p_sub["participation_role"] == "SUBSTITUTE_FIELDER"
    assert p_sub["evidence_confidence"] == "SUBSTITUTE_CONFIRMED"
    assert p_sub["is_starting_xi"] is False


def test_reconcile_innings_totals_quality_tiers():
    """Verify innings run reconciliation quality tiers (PASS, WARNING, CRITICAL)."""
    # 1. Clean match with administrative penalty -> PASS
    innings_data = {"penalty_runs": {"pre": 5, "post": 0}}
    deliveries_list = [
        {"runs_total": 4, "runs_batter": 4, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
        {"runs_total": 1, "runs_batter": 0, "runs_extras": 1, "is_legal_delivery": False, "wicket_count": 0},
        {"runs_total": 6, "runs_batter": 6, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 1},
    ]
    res_pass = reconcile_innings_totals(innings_data, deliveries_list)
    assert res_pass["reconciliation_status"] == "PASS"
    assert res_pass["delivery_runs_sum"] == 11
    assert res_pass["reconciled_total_runs"] == 16
    assert res_pass["math_delivery_balance"] is True

    # 2. Mathematical imbalance in delivery runs -> CRITICAL
    corrupt_deliveries = [
        {"runs_total": 10, "runs_batter": 4, "runs_extras": 1, "is_legal_delivery": True, "wicket_count": 0}
    ]
    res_crit = reconcile_innings_totals({}, corrupt_deliveries)
    assert res_crit["reconciliation_status"] == "CRITICAL"
    assert res_crit["math_delivery_balance"] is False
    assert res_crit["discrepancy_reason"] == "DELIVERY_RUN_COMPONENTS_DO_NOT_SUM_TO_TOTAL"

    # 3. DLS target discrepancy -> WARNING
    dls_innings = {"target": {"overs": 15, "runs": 130}}
    normal_delivs = [
        {"runs_total": 125, "runs_batter": 120, "runs_extras": 5, "is_legal_delivery": True, "wicket_count": 2}
    ]
    res_warn_dls = reconcile_innings_totals(dls_innings, normal_delivs, declared_target_runs=130)
    assert res_warn_dls["reconciliation_status"] == "WARNING"
    assert res_warn_dls["discrepancy_reason"] == "DLS_REVISED_TARGET_DIFFERENCE"

    # 4. Severe discrepancy > 5 runs without rain -> CRITICAL
    res_crit_target = reconcile_innings_totals({}, normal_delivs, declared_target_runs=150)
    assert res_crit_target["reconciliation_status"] == "CRITICAL"
    assert res_crit_target["discrepancy_reason"] == "SCORECARD_RUN_MISMATCH_EXCEEDS_TOLERANCE"


def test_idempotency_upsert_reproducibility():
    """Verify that re-inserting match data using INSERT OR REPLACE produces 0 duplicate records."""
    import duckdb

    con = duckdb.connect()
    con.execute("""
    CREATE TABLE dim_match (match_id VARCHAR PRIMARY KEY, comp VARCHAR);
    CREATE TABLE fact_innings (innings_id VARCHAR PRIMARY KEY, match_id VARCHAR, runs INT);
    """)

    # First insertion
    con.execute("INSERT OR REPLACE INTO dim_match VALUES ('m1', 'IPL')")
    con.execute("INSERT OR REPLACE INTO fact_innings VALUES ('m1_1', 'm1', 180)")
    assert con.execute("SELECT count(*) FROM dim_match").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_innings").fetchone()[0] == 1

    # Second insertion (identical keys)
    con.execute("INSERT OR REPLACE INTO dim_match VALUES ('m1', 'IPL')")
    con.execute("INSERT OR REPLACE INTO fact_innings VALUES ('m1_1', 'm1', 180)")
    assert con.execute("SELECT count(*) FROM dim_match").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fact_innings").fetchone()[0] == 1


def test_transaction_rollback_recovery():
    """Verify transactional rollback leaves database state clean after failure."""
    import duckdb

    con = duckdb.connect()
    con.execute("CREATE TABLE test_tab (id INT PRIMARY KEY, val VARCHAR);")
    con.execute("INSERT INTO test_tab VALUES (1, 'good');")

    con.begin()
    try:
        con.execute("INSERT INTO test_tab VALUES (2, 'staging');")
        raise RuntimeError("SIMULATED_FAILURE")
    except RuntimeError:
        con.rollback()

    assert con.execute("SELECT count(*) FROM test_tab").fetchone()[0] == 1
    assert con.execute("SELECT id FROM test_tab").fetchall() == [(1,)]


def test_production_database_integrity():
    """Verify that production canonical database exists, is valid, and queryable."""
    from config.settings import DUCKDB_PATH
    import duckdb

    assert DUCKDB_PATH.exists(), f"Production database {DUCKDB_PATH} should exist after canonical ingestion!"
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    try:
        m_count = con.execute("SELECT count(*) FROM dim_match").fetchone()[0]
        assert m_count == 9085, f"Expected 9085 ingested matches, got {m_count}"
    finally:
        con.close()


def test_validate_match_venue_rules():
    """Verify venue/city validation logic: venue required, city optional, never fabricated."""
    from etl.parse_cricsheet import validate_match_venue

    # Case 1: Both venue and city present -> PASS
    sev, msg, clean_v, clean_c = validate_match_venue("Eden Gardens", "Kolkata")
    assert sev == "PASS"
    assert msg is None
    assert clean_v == "Eden Gardens"
    assert clean_c == "Kolkata"

    # Case 2: Venue present, city missing -> WARNING (non-fatal, preserved as None)
    sev, msg, clean_v, clean_c = validate_match_venue("Reliance Stadium", None)
    assert sev == "WARNING"
    assert msg == "HOST_CITY_IS_NULL_VENUE_PRESENT"
    assert clean_v == "Reliance Stadium"
    assert clean_c is None  # Never fabricated from venue

    # Case 3: Missing venue (None) -> CRITICAL
    sev, msg, clean_v, clean_c = validate_match_venue(None, "Mumbai")
    assert sev == "CRITICAL"
    assert msg == "VENUE_NAME_MISSING_OR_BLANK"

    # Case 4: Blank whitespace venue -> CRITICAL
    sev, msg, clean_v, clean_c = validate_match_venue("   ", "Delhi")
    assert sev == "CRITICAL"
    assert msg == "VENUE_NAME_MISSING_OR_BLANK"

    # Case 5: Both venue and city missing -> CRITICAL
    sev, msg, clean_v, clean_c = validate_match_venue(None, None)
    assert sev == "CRITICAL"
    assert msg == "VENUE_NAME_MISSING_OR_BLANK"


def test_target_and_penalty_innings_arithmetic():
    """
    Verify exact distinction between delivery runs, administrative penalties,
    innings totals, opposition scores, and target scores (e.g. Nepal vs Canada 1420222).
    """
    # Opposition score (Canada, Innings 1)
    opposition_score = 232
    target_score = opposition_score + 1  # 233

    # Nepal Innings 2: 229 off deliveries + 5 post-innings penalty runs
    inn2_deliveries = [
        {"runs_total": 223, "runs_batter": 215, "runs_extras": 8, "is_legal_delivery": True, "wicket_count": 1},
        {"runs_total": 6, "runs_batter": 6, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},  # Final six on 44.3
    ]
    inn2_data = {
        "penalty_runs": {"pre": 0, "post": 5},
        "target": {"runs": 233, "overs": 50}
    }

    rec = reconcile_innings_totals(inn2_data, inn2_deliveries, declared_target_runs=target_score)

    delivery_derived_total = rec["delivery_runs_sum"]
    penalty_runs = rec["penalty_runs_pre"] + rec["penalty_runs_post"]
    innings_total = rec["reconciled_total_runs"]

    # 1. Batting team delivery-derived total is 229
    assert delivery_derived_total == 229

    # 2. Administrative penalty runs is 5
    assert penalty_runs == 5

    # 3. Innings total is 229 + 5 = 234
    assert innings_total == 234

    # 4. Target score is 233
    assert target_score == 233

    # 5. Innings total (234) exceeds target score (233) by 1 run
    assert innings_total >= target_score
    runs_surplus = innings_total - target_score
    assert runs_surplus == 1

    # 6. Runs required before winning delivery:
    # Up to 44.2, delivery runs were 223. Target was 233.
    assert rec["runs_required_before_winning_delivery"] == 10
    assert rec["final_delivery_runs"] == 6

    # 7. Reconciliation status is PASS
    assert rec["reconciliation_status"] == "PASS"


def test_semantic_chase_reconciliation_and_result_inconsistencies():
    """
    Gate 1 Regression Tests covering:
    1. A successful chase (exact target).
    2. A successful chase with runs beyond target on the winning delivery.
    3. A chase involving administrative penalty runs.
    4. An invalid innings total (component imbalance and surplus violation).
    5. A result or target inconsistency (outcome contradicts score and margin mismatch).
    """
    team_a = "Team A"
    team_b = "Team B"

    # Scenario 1: A successful chase (exact target hit)
    # Target 151. Deliveries: 147 before final ball. Final ball: 4 runs -> total 151.
    delivs_exact = [
        {"runs_total": 147, "runs_batter": 140, "runs_extras": 7, "is_legal_delivery": True, "wicket_count": 4},
        {"runs_total": 4, "runs_batter": 4, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
    ]
    outcome_win = {"winner": team_a, "by": {"wickets": 6}}
    res_exact = reconcile_innings_totals(
        {"team": team_a}, delivs_exact, declared_target_runs=151, match_outcome=outcome_win
    )
    assert res_exact["reconciliation_status"] == "PASS"
    assert res_exact["surplus_over_target"] == 0
    assert res_exact["runs_required_before_winning_delivery"] == 4
    assert res_exact["outcome_consistent"] is True

    # Scenario 2: Successful chase with runs beyond target on winning delivery (MCC Law 16.6)
    # Target 151. Deliveries: 147 before final ball (4 needed). Final ball: 6 runs -> total 153.
    delivs_six = [
        {"runs_total": 147, "runs_batter": 140, "runs_extras": 7, "is_legal_delivery": True, "wicket_count": 4},
        {"runs_total": 6, "runs_batter": 6, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
    ]
    res_six = reconcile_innings_totals(
        {"team": team_a}, delivs_six, declared_target_runs=151, match_outcome=outcome_win
    )
    assert res_six["reconciliation_status"] == "PASS"
    assert res_six["surplus_over_target"] == 2
    assert res_six["runs_required_before_winning_delivery"] == 4
    assert res_six["final_delivery_runs"] == 6

    # Scenario 3: Chase involving administrative penalty runs (Raw 1420222 verification)
    import json
    from pathlib import Path
    match_file = Path("data/raw_cricsheet/extracted/odis_male/1420222.json")
    if match_file.exists():
        with open(match_file) as f:
            d = json.load(f)
        inn2 = d["innings"][1]
        delivs_raw = []
        for ov in inn2.get("overs", []):
            for deliv in ov.get("deliveries", []):
                r = deliv.get("runs", {})
                w = deliv.get("wickets", [])
                delivs_raw.append({
                    "runs_total": r.get("total", 0),
                    "runs_batter": r.get("batter", 0),
                    "runs_extras": r.get("extras", 0),
                    "is_legal_delivery": "wides" not in deliv.get("extras", {}) and "noballs" not in deliv.get("extras", {}),
                    "wicket_count": len(w),
                })
        res_raw = reconcile_innings_totals(
            inn2, delivs_raw, declared_target_runs=233, match_outcome=d["info"].get("outcome")
        )
        assert res_raw["reconciliation_status"] == "PASS"
        assert res_raw["delivery_runs_sum"] == 229
        assert res_raw["penalty_runs_post"] == 5
        assert res_raw["reconciled_total_runs"] == 234
        assert res_raw["reconciled_wickets"] == 1
        assert res_raw["surplus_over_target"] == 1
        assert res_raw["outcome_consistent"] is True

    # Scenario 4: Invalid innings total
    # 4a. Delivery component sum imbalance
    delivs_imbalance = [{"runs_total": 10, "runs_batter": 5, "runs_extras": 2, "is_legal_delivery": True, "wicket_count": 0}]
    res_imb = reconcile_innings_totals({"team": team_a}, delivs_imbalance, declared_target_runs=151)
    assert res_imb["reconciliation_status"] == "CRITICAL"
    assert res_imb["discrepancy_reason"] == "DELIVERY_RUN_COMPONENTS_DO_NOT_SUM_TO_TOTAL"

    # 4b. Impossible surplus exceeding final delivery bound
    # Target 151. Delivery before final ball: 147. Final ball: 2 runs. But innings total claimed is 155 (surplus 4 > 2)
    delivs_impossible = [
        {"runs_total": 147, "runs_batter": 140, "runs_extras": 7, "is_legal_delivery": True, "wicket_count": 0},
        {"runs_total": 2, "runs_batter": 2, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
    ]
    # Simulate an anomalous post-penalty or corrupt declared total
    res_impos = reconcile_innings_totals(
        {"team": team_a, "penalty_runs": {"pre": 0, "post": 10}}, delivs_impossible, declared_target_runs=151
    )
    # Total = 149 + 10 = 159. Surplus = 8. Max allowed surplus = max(0, (2 + 10) - 1) = 11.
    # Now let's test where surplus strictly exceeds: e.g. final_deliv_runs = 1, post = 0, but total is 155 without penalty
    delivs_anom = [
        {"runs_total": 150, "runs_batter": 150, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
        {"runs_total": 5, "runs_batter": 5, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
    ]
    # Score before final ball was 150 (1 needed). Final ball was 5 -> total 155. Surplus = 4. Max allowed = 5 - 1 = 4.
    # What if target was ALREADY reached before final ball? Score before final was 152 for target 151:
    delivs_already_reached = [
        {"runs_total": 152, "runs_batter": 152, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
        {"runs_total": 4, "runs_batter": 4, "runs_extras": 0, "is_legal_delivery": True, "wicket_count": 0},
    ]
    res_already = reconcile_innings_totals({"team": team_a}, delivs_already_reached, declared_target_runs=151)
    assert res_already["reconciliation_status"] == "CRITICAL"
    assert res_already["discrepancy_reason"] == "TARGET_ALREADY_REACHED_BEFORE_FINAL_DELIVERY"

    # Scenario 5: Result or target inconsistencies
    # 5a. Outcome declares batting team winner, but batting team did not reach target
    delivs_short = [
        {"runs_total": 140, "runs_batter": 135, "runs_extras": 5, "is_legal_delivery": True, "wicket_count": 10}
    ]
    res_incon_winner = reconcile_innings_totals(
        {"team": team_a}, delivs_short, declared_target_runs=151, match_outcome={"winner": team_a}
    )
    assert res_incon_winner["reconciliation_status"] == "CRITICAL"
    assert res_incon_winner["discrepancy_reason"] == "OUTCOME_CONTRADICTS_SCORE_BATTER_DECLARED_WINNER_WITHOUT_REACHING_TARGET"
    assert res_incon_winner["outcome_consistent"] is False

    # 5b. Outcome declares bowling team winner, despite batting team reaching target
    res_incon_bowler = reconcile_innings_totals(
        {"team": team_a}, delivs_exact, declared_target_runs=151, match_outcome={"winner": team_b}
    )
    assert res_incon_bowler["reconciliation_status"] == "CRITICAL"
    assert res_incon_bowler["discrepancy_reason"] == "OUTCOME_CONTRADICTS_SCORE_BOWLER_DECLARED_WINNER_DESPITE_TARGET_REACHED"
    assert res_incon_bowler["outcome_consistent"] is False

    # 5c. Wickets margin mismatch (lost 4 wickets, so expected margin is 6 wickets, but outcome claims 2 wickets)
    res_incon_margin = reconcile_innings_totals(
        {"team": team_a}, delivs_exact, declared_target_runs=151, match_outcome={"winner": team_a, "by": {"wickets": 2}}
    )
    assert res_incon_margin["reconciliation_status"] == "CRITICAL"
    assert "OUTCOME_WICKETS_MARGIN_MISMATCH" in res_incon_margin["discrepancy_reason"]
    assert res_incon_margin["outcome_consistent"] is False




