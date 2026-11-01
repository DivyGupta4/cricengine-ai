"""
CricEngine AI — Cricsheet Parser Core Specification & Entity Extraction Functions

Implements modular parsing helpers for schema extraction, delivery ordering,
legal ball tracking, format-specific match phases (decoupling over number,
ball changes, and ball age), innings reconciliation with quality severity tiers,
player participation evidence classification, and 1-to-many child table
transformations (dismissals, fielders, replacements, officials).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple, Set


def calculate_match_phase(
    match_format: str,
    over_num: int,
    is_super_over: bool = False,
    scheduled_overs: int = 20,
    ball_age_overs: Optional[int] = None,
    new_ball_taken_over: Optional[int] = None,
) -> str:
    """
    Format-specific match phase calculation.
    
    Decouples raw over number, ball age, and ball change events:
    - Does NOT apply T20 boundaries to Tests or ODIs.
    - In Test cricket, does NOT assume an automatic new ball reset every 80 overs.
      80 overs is the earliest a captain *may* take a new ball, but Cricsheet does
      not record ball changes. Overs >= 80 remain 'OLD_BALL_UNCONFIRMED_NEW' unless
      explicit evidence of a new ball is provided via new_ball_taken_over.
    """
    if is_super_over:
        return "SUPER_OVER"

    format_upper = match_format.upper()

    if "T20" in format_upper:
        if scheduled_overs >= 20:
            if over_num <= 5:
                return "POWERPLAY"
            elif over_num <= 14:
                return "MIDDLE"
            else:
                return "DEATH"
        else:
            # Proportional scaling for shortened T20s
            pp_cutoff = max(0, round(scheduled_overs * 0.3) - 1)
            death_cutoff = scheduled_overs - max(1, round(scheduled_overs * 0.25))
            if over_num <= pp_cutoff:
                return "POWERPLAY"
            elif over_num < death_cutoff:
                return "MIDDLE"
            else:
                return "DEATH"

    elif "ODI" in format_upper or "ONE-DAY" in format_upper:
        if scheduled_overs >= 50:
            if over_num <= 9:
                return "POWERPLAY_1"
            elif over_num <= 39:
                return "MIDDLE"
            else:
                return "DEATH"
        else:
            # Proportional scaling for shortened ODIs
            pp_cutoff = max(0, round(scheduled_overs * 0.2) - 1)
            death_cutoff = scheduled_overs - max(2, round(scheduled_overs * 0.2))
            if over_num <= pp_cutoff:
                return "POWERPLAY_1"
            elif over_num < death_cutoff:
                return "MIDDLE"
            else:
                return "DEATH"

    elif "TEST" in format_upper or "MULTI-DAY" in format_upper:
        # If an explicit new ball over was recorded/provided
        if new_ball_taken_over is not None and over_num >= new_ball_taken_over:
            effective_age = over_num - new_ball_taken_over
            if effective_age <= 19:
                return "SECOND_NEW_BALL"
            elif effective_age <= 59:
                return "SECOND_NEW_BALL_MIDDLE"
            else:
                return "OLD_BALL_80_PLUS"
                
        # If caller explicitly provided an already-calculated ball age (e.g. from commentary)
        effective_ball_age = ball_age_overs if ball_age_overs is not None else over_num
        
        if effective_ball_age <= 19:
            return "INITIAL_NEW_BALL"
        elif effective_ball_age <= 79:
            return "WORN_BALL_MIDDLE"
        else:
            # Overs 80+ without verified new ball event
            return "OLD_BALL_UNCONFIRMED_NEW"

    return "UNKNOWN"


def parse_delivery_extras(extras_dict: Optional[Dict[str, int]]) -> Tuple[int, int, int, int, int, bool]:
    """
    Extract exact extras breakdown and determine legal delivery status.
    Returns (wides, noballs, byes, legbyes, penalty, is_legal).
    """
    if not extras_dict:
        return 0, 0, 0, 0, 0, True

    wides = extras_dict.get("wides", 0)
    noballs = extras_dict.get("noballs", 0)
    byes = extras_dict.get("byes", 0)
    legbyes = extras_dict.get("legbyes", 0)
    penalty = extras_dict.get("penalty", 0)

    is_legal = (wides == 0 and noballs == 0)
    return wides, noballs, byes, legbyes, penalty, is_legal


def parse_dismissals_and_fielders(
    wickets_list: Optional[List[Dict[str, Any]]],
    ball_id: str,
    match_id: str,
    innings_num: int,
    registry_people: Dict[str, str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Extract dismissals and associated fielders into relational child table records.
    Supports multiple dismissals per delivery and multiple fielders per dismissal.
    """
    if not wickets_list:
        return [], []

    dismissals: List[Dict[str, Any]] = []
    fielders: List[Dict[str, Any]] = []

    for seq, w in enumerate(wickets_list, start=1):
        dismissal_id = f"{ball_id}_{seq}"
        player_out_name = w.get("player_out", "")
        player_out_id = registry_people.get(player_out_name)
        kind = w.get("kind", "unknown")

        bowler_credited = kind in {
            "bowled",
            "caught",
            "caught and bowled",
            "lbw",
            "stumped",
            "hit wicket",
        }

        dismissals.append({
            "dismissal_id": dismissal_id,
            "ball_id": ball_id,
            "match_id": match_id,
            "innings_num": innings_num,
            "dismissal_seq": seq,
            "player_out_id": player_out_id,
            "player_out_name_raw": player_out_name,
            "dismissal_kind": kind,
            "bowler_credited": bowler_credited,
        })

        for f_seq, fld in enumerate(w.get("fielders", []), start=1):
            fld_id = f"{dismissal_id}_{f_seq}"
            fld_name = fld.get("name", "")
            fld_player_id = registry_people.get(fld_name) if fld_name else None
            is_sub = bool(fld.get("substitute", False))

            fielders.append({
                "dismissal_fielder_id": fld_id,
                "dismissal_id": dismissal_id,
                "fielder_seq": f_seq,
                "fielder_id": fld_player_id,
                "fielder_name_raw": fld_name,
                "is_substitute": is_sub,
            })

    return dismissals, fielders


def parse_replacements(
    deliv_dict: Dict[str, Any],
    ball_id: str,
    match_id: str,
    registry_people: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Extract replacement events (impact players, concussion substitutes)."""
    replacements_data = deliv_dict.get("replacements", {}).get("match", [])
    records: List[Dict[str, Any]] = []

    for seq, rep in enumerate(replacements_data, start=1):
        in_name = rep.get("in", "")
        out_name = rep.get("out", "")
        records.append({
            "replacement_id": f"{ball_id}_rep_{seq}",
            "match_id": match_id,
            "ball_id": ball_id,
            "team_name": rep.get("team"),
            "in_player_id": registry_people.get(in_name),
            "out_player_id": registry_people.get(out_name),
            "in_player_name": in_name,
            "out_player_name": out_name,
            "replacement_reason": rep.get("reason", "unknown"),
        })

    return records


def parse_officials(
    info_officials: Optional[Dict[str, Any]],
    match_id: str,
    registry_people: Dict[str, str],
) -> List[Dict[str, Any]]:
    """Extract match officials into relational records."""
    if not info_officials or not isinstance(info_officials, dict):
        return []

    records: List[Dict[str, Any]] = []
    role_mapping = {
        "umpires": "onfield_umpire",
        "tv_umpires": "tv_umpire",
        "match_referees": "match_referee",
        "reserve_umpires": "reserve_umpire",
    }

    for source_role, canonical_role in role_mapping.items():
        people = info_officials.get(source_role, [])
        if isinstance(people, str):
            people = [people]
        for p in people:
            pid = registry_people.get(p)
            records.append({
                "official_assignment_id": f"{match_id}_{pid}_{canonical_role}",
                "match_id": match_id,
                "official_id": pid,
                "official_name": p,
                "official_role": canonical_role,
            })

    return records


def classify_player_participation(
    player_id: str,
    player_name: str,
    team_name: str,
    info_players: Dict[str, List[str]],
    match_replacements: List[Dict[str, Any]],
    active_batters: Set[str],
    active_bowlers: Set[str],
    active_fielders: Set[str],
) -> Dict[str, Any]:
    """
    Classify player participation evidence to separate Starting XI,
    Tactical Substitutes (Impact Players), Concussion Substitutes,
    Substitute Fielders, and Unconfirmed Bench Roster.
    """
    team_squad = info_players.get(team_name, [])
    in_team_squad = player_name in team_squad

    # Check replacements
    impact_sub_in = any(
        r.get("in_player_name") == player_name and r.get("replacement_reason") == "impact_player"
        for r in match_replacements
    )
    concussion_sub_in = any(
        r.get("in_player_name") == player_name and r.get("replacement_reason") == "concussion_substitute"
        for r in match_replacements
    )

    has_batted = player_name in active_batters
    has_bowled = player_name in active_bowlers
    has_fielded = player_name in active_fielders
    active_on_field = has_batted or has_bowled or has_fielded

    if impact_sub_in:
        participation_role = "IMPACT_PLAYER"
        confidence = "IMPACT_PLAYER"
        is_starting_xi = False
    elif concussion_sub_in:
        participation_role = "CONCUSSION_SUB"
        confidence = "SUBSTITUTE_CONFIRMED"
        is_starting_xi = False
    elif in_team_squad and active_on_field:
        participation_role = "STARTING_XI"
        confidence = "CONFIRMED_PLAYING_XI"
        is_starting_xi = True
    elif in_team_squad and not active_on_field:
        # In modern T20/IPL, teams name 12 players (11 + Impact Player)
        # Players who neither batted, bowled, nor fielded remain unconfirmed roster
        participation_role = "BENCH_NOMINATED"
        confidence = "UNCONFIRMED_ROSTER"
        is_starting_xi = False
    elif not in_team_squad and active_on_field:
        # Fielder appeared in dismissals but was not in starting squad
        participation_role = "SUBSTITUTE_FIELDER"
        confidence = "SUBSTITUTE_CONFIRMED"
        is_starting_xi = False
    else:
        participation_role = "UNKNOWN"
        confidence = "UNCONFIRMED_ROSTER"
        is_starting_xi = False

    return {
        "player_id": player_id,
        "player_name": player_name,
        "team_name": team_name,
        "in_team_squad": in_team_squad,
        "is_starting_xi": is_starting_xi,
        "participation_role": participation_role,
        "evidence_confidence": confidence,
        "has_batted": has_batted,
        "has_bowled": has_bowled,
        "has_fielded": has_fielded,
        "active_on_field": active_on_field,
    }


def reconcile_innings_totals(
    innings_data: Dict[str, Any],
    deliveries_list: List[Dict[str, Any]],
    declared_target_runs: Optional[int] = None,
    match_outcome: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Reconcile scoreboard totals against delivery-level events, penalty runs,
    target scores, and match outcome semantics.
    
    Distinguishes:
    - Delivery-derived runs (sum of off-the-bat runs + extras).
    - Administrative pre- and post-innings penalty runs.
    - Final innings total.
    - Target score and runs required before the winning delivery.
    - Result and termination conditions (wickets margin, runs margin, tie, DLS).
    
    Categorizes reconciliation status into PASS, WARNING, or CRITICAL.
    """
    deliv_runs_sum = sum(d.get("runs_total", 0) for d in deliveries_list)
    batter_runs_sum = sum(d.get("runs_batter", 0) for d in deliveries_list)
    extras_runs_sum = sum(d.get("runs_extras", 0) for d in deliveries_list)
    
    # Mathematical balance invariant across delivery events
    math_delivery_balance = (deliv_runs_sum == batter_runs_sum + extras_runs_sum)

    # Administrative penalty runs recorded at innings level
    penalty_runs = innings_data.get("penalty_runs", {})
    penalty_pre = penalty_runs.get("pre", 0)
    penalty_post = penalty_runs.get("post", 0)
    reconciled_total_runs = deliv_runs_sum + penalty_pre + penalty_post

    total_wickets = sum(d.get("wicket_count", 0) for d in deliveries_list)
    legal_deliveries = sum(1 for d in deliveries_list if d.get("is_legal_delivery"))

    status = "PASS"
    discrepancy_reason: Optional[str] = None
    discrepancy_amount = 0
    outcome_consistent = True
    runs_req_before_final_deliv: Optional[int] = None
    final_deliv_runs: Optional[int] = None
    surplus_over_target: Optional[int] = None

    if not math_delivery_balance:
        status = "CRITICAL"
        discrepancy_reason = "DELIVERY_RUN_COMPONENTS_DO_NOT_SUM_TO_TOTAL"
        discrepancy_amount = deliv_runs_sum - (batter_runs_sum + extras_runs_sum)
    elif declared_target_runs is not None:
        target = declared_target_runs
        batting_team = innings_data.get("team")
        num_delivs = len(deliveries_list)
        final_deliv = deliveries_list[-1] if num_delivs > 0 else {}
        final_deliv_runs = final_deliv.get("runs_total", 0)

        # Runs scored off deliveries prior to final delivery
        deliv_runs_before_final = deliv_runs_sum - final_deliv_runs
        score_before_final_deliv = deliv_runs_before_final + penalty_pre
        runs_req_before_final_deliv = target - score_before_final_deliv

        is_dls = (
            (match_outcome and match_outcome.get("method") in {"D/L", "DLS", "Awarded"})
            or (match_outcome and "method" in match_outcome and match_outcome["method"] is not None)
            or (innings_data.get("target", {}).get("overs") is not None and innings_data.get("target", {}).get("overs") < 20)
        )

        if reconciled_total_runs >= target:
            # Successful chase
            surplus_over_target = reconciled_total_runs - target

            # Invariant: Target must NOT have been already reached before the final delivery
            if is_dls:
                # Under DLS rain interruptions, target is a revised par score / guideline
                status = "PASS"
            elif score_before_final_deliv >= target:
                status = "CRITICAL"
                discrepancy_reason = "TARGET_ALREADY_REACHED_BEFORE_FINAL_DELIVERY"
                discrepancy_amount = score_before_final_deliv - target
            else:
                # Under MCC Law 16.6, surplus cannot exceed runs produced on the winning delivery / post-penalty event
                max_allowed_surplus = max(0, (final_deliv_runs + penalty_post) - 1)
                if surplus_over_target > max_allowed_surplus:
                    status = "CRITICAL"
                    discrepancy_reason = "SURPLUS_RUNS_EXCEED_FINAL_DELIVERY_AND_PENALTY_BOUND"
                    discrepancy_amount = surplus_over_target - max_allowed_surplus
                else:
                    status = "PASS"

            # Validate against match outcome if provided
            if match_outcome and status == "PASS":
                winner = match_outcome.get("winner")
                by_info = match_outcome.get("by", {})
                by_wickets = by_info.get("wickets")
                if winner and winner != batting_team:
                    status = "CRITICAL"
                    discrepancy_reason = "OUTCOME_CONTRADICTS_SCORE_BOWLER_DECLARED_WINNER_DESPITE_TARGET_REACHED"
                    outcome_consistent = False
                elif by_wickets is not None:
                    # In standard 11-player cricket, wickets margin is 10 - dismissals_count
                    # (where dismissals excludes retired hurt / retired not out under MCC Law 25.4)
                    dismissals_count = sum(d.get("dismissal_count", d.get("wicket_count", 0)) for d in deliveries_list)
                    expected_wickets_margin = 10 - dismissals_count
                    if expected_wickets_margin != by_wickets:
                        if is_dls or abs(expected_wickets_margin - by_wickets) <= 1:
                            status = "WARNING"
                            discrepancy_reason = "DLS_REVISED_TARGET_DIFFERENCE" if is_dls else "ABSENT_HURT_OR_UNCONFIRMED_RETIREMENT_MARGIN_VARIANCE"
                        else:
                            status = "CRITICAL"
                            discrepancy_reason = f"OUTCOME_WICKETS_MARGIN_MISMATCH_EXPECTED_{expected_wickets_margin}_GOT_{by_wickets}"
                            outcome_consistent = False
        else:
            # Short of target (Defeat, Tie, Rain/DLS, or Unfinished)
            shortfall = target - reconciled_total_runs
            discrepancy_amount = shortfall

            if match_outcome:
                winner = match_outcome.get("winner")
                by_info = match_outcome.get("by", {})
                by_runs = by_info.get("runs")
                result_str = match_outcome.get("result")

                if winner and winner == batting_team:
                    if is_dls:
                        status = "WARNING"
                        discrepancy_reason = "DLS_REVISED_TARGET_DIFFERENCE"
                        outcome_consistent = True
                    else:
                        status = "CRITICAL"
                        discrepancy_reason = "OUTCOME_CONTRADICTS_SCORE_BATTER_DECLARED_WINNER_WITHOUT_REACHING_TARGET"
                        outcome_consistent = False
                elif result_str == "tie":
                    if shortfall == 1:
                        status = "PASS"
                    else:
                        status = "CRITICAL"
                        discrepancy_reason = "TIE_DECLARED_BUT_SCORE_DOES_NOT_MATCH_OPPOSITION"
                        outcome_consistent = False
                elif by_runs is not None:
                    expected_win_by_runs = shortfall - 1
                    if by_runs == expected_win_by_runs:
                        status = "PASS"
                        outcome_consistent = True
                    elif is_dls:
                        status = "WARNING"
                        discrepancy_reason = "DLS_REVISED_TARGET_DIFFERENCE"
                    else:
                        status = "CRITICAL"
                        discrepancy_reason = f"OUTCOME_RUNS_MARGIN_MISMATCH_EXPECTED_{expected_win_by_runs}_GOT_{by_runs}"
                        outcome_consistent = False
                elif is_dls:
                    status = "WARNING"
                    discrepancy_reason = "DLS_REVISED_TARGET_DIFFERENCE"
                elif total_wickets >= 10:
                    status = "PASS"
                else:
                    status = "WARNING"
                    discrepancy_reason = "INNINGS_TERMINATED_SHORT_OF_TARGET_WITHOUT_ALL_OUT"
            elif is_dls:
                status = "WARNING"
                discrepancy_reason = "DLS_REVISED_TARGET_DIFFERENCE"
            elif shortfall <= 5:
                status = "WARNING"
                discrepancy_reason = "MINOR_HISTORICAL_SCORECARD_DISCREPANCY"
            else:
                status = "CRITICAL"
                discrepancy_reason = "SCORECARD_RUN_MISMATCH_EXCEEDS_TOLERANCE"

    return {
        "delivery_runs_sum": deliv_runs_sum,
        "batter_runs_sum": batter_runs_sum,
        "extras_runs_sum": extras_runs_sum,
        "penalty_runs_pre": penalty_pre,
        "penalty_runs_post": penalty_post,
        "reconciled_total_runs": reconciled_total_runs,
        "reconciled_wickets": total_wickets,
        "total_deliveries": len(deliveries_list),
        "total_legal_deliveries": legal_deliveries,
        "math_delivery_balance": math_delivery_balance,
        "target_runs": declared_target_runs,
        "runs_required_before_winning_delivery": runs_req_before_final_deliv,
        "final_delivery_runs": final_deliv_runs,
        "surplus_over_target": surplus_over_target,
        "outcome_consistent": outcome_consistent,
        "reconciliation_status": status,
        "discrepancy_reason": discrepancy_reason,
        "discrepancy_amount": discrepancy_amount,
    }


def validate_match_venue(
    venue: Optional[str],
    city: Optional[str],
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Validate match venue and city according to invariant M4.
    
    Rules:
    - venue is REQUIRED (CRITICAL if None, empty, or whitespace only).
    - city is OPTIONAL (preserved as SQL NULL if missing; WARNING flagged for transparency).
    - Never fabricates city names from venue strings.
    
    Returns:
    (severity, failure_or_warning_reason, clean_venue, clean_city)
    """
    clean_venue = venue.strip() if venue and isinstance(venue, str) else None
    clean_city = city.strip() if city and isinstance(city, str) else None

    if not clean_venue:
        return "CRITICAL", "VENUE_NAME_MISSING_OR_BLANK", None, clean_city

    if not clean_city:
        return "WARNING", "HOST_CITY_IS_NULL_VENUE_PRESENT", clean_venue, None

    return "PASS", None, clean_venue, clean_city

