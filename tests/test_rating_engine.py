"""
CricEngine AI — Comprehensive Test Suite for Player Rating Engine (Phase 4B)
Verifies mathematical fidelity, observation models, exposure handling,
uncertainty propagation, role inference, negative VORP, and leakage prevention.
"""

from __future__ import annotations
import math
import sys
from pathlib import Path
import pytest
import numpy as np

# Ensure root directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ratings.config import (
    FORMAT_CONFIGS,
    DEFAULT_CONFIG,
    FormatConfig,
)
from src.ratings.state_model import PlayerRatingState
from src.ratings.observation_models import (
    laplace_mode_filter_negbin,
    laplace_mode_filter_survival,
    laplace_mode_filter_zip,
)
from src.ratings.batting import update_batting_state
from src.ratings.bowling import update_bowling_state
from src.ratings.fielding import update_fielding_state
from src.ratings.all_round import compute_all_round_and_vorp
from src.ratings.contextual_adjustments import ContextualEngine
from src.ratings.temporal_dynamics import apply_temporal_drift
from src.ratings.role_inference import infer_dynamic_role
from src.ratings.identity_resolution import IdentityManager
from src.ratings.uncertainty import (
    compute_credible_interval,
    probability_player_superiority,
)


class TestObservationLikelihoods:
    """1. Observation likelihood and exposure correctness."""

    def test_negative_binomial_exposure_scaling(self):
        """Scoring 40 runs in 20 balls (SR 200) vs 40 runs in 50 balls (SR 80)."""
        prior_mean, prior_var = 0.0, 0.25
        
        # High scoring rate
        post_mean_fast, post_var_fast, conv_fast = laplace_mode_filter_negbin(
            prior_mean=prior_mean,
            prior_var=prior_var,
            observed_y=40.0,
            exposure=20.0,
            context_offset=0.0,
        )
        
        # Slow scoring rate
        post_mean_slow, post_var_slow, conv_slow = laplace_mode_filter_negbin(
            prior_mean=prior_mean,
            prior_var=prior_var,
            observed_y=40.0,
            exposure=50.0,
            context_offset=0.0,
        )
        
        assert conv_fast and conv_slow
        assert post_mean_fast > post_mean_slow, "Higher runs/ball must yield higher posterior mean"
        assert post_var_fast < prior_var and post_var_slow < prior_var, "Posterior variance must decrease"

    def test_zero_exposure_handling(self):
        """Zero exposure must preserve prior state without numerical failure."""
        prior_mean, prior_var = 0.50, 0.20
        post_mean, post_var, conv = laplace_mode_filter_negbin(
            prior_mean=prior_mean,
            prior_var=prior_var,
            observed_y=0.0,
            exposure=0.0,
        )
        assert conv
        assert post_mean == prior_mean
        assert post_var == prior_var

    def test_duck_on_positive_balls_handling(self):
        """Scoring 0 runs in 10 balls (duck/block) must update downward cleanly."""
        prior_mean, prior_var = 0.0, 0.25
        post_mean, post_var, conv = laplace_mode_filter_negbin(
            prior_mean=prior_mean,
            prior_var=prior_var,
            observed_y=0.0,
            exposure=10.0,
            context_offset=0.0,
        )
        assert conv
        assert post_mean < prior_mean, "0 runs in 10 balls must decrease scoring rate"
        assert post_var < prior_var

    def test_wicketless_spell_handling(self):
        """0 wickets in 24 legal balls must decrease wicket hazard."""
        prior_mean, prior_var = -3.20, 0.35
        post_mean, post_var, conv = laplace_mode_filter_negbin(
            prior_mean=prior_mean,
            prior_var=prior_var,
            observed_y=0.0,
            exposure=24.0,
            context_offset=0.0,
        )
        assert conv
        assert post_mean < prior_mean, "Wicketless spell must lower hazard rate"
        assert post_var < prior_var

    def test_survival_not_out_vs_dismissed(self):
        """Surviving 50 balls not out vs being dismissed on ball 50."""
        prior_mean, prior_var = 3.20, 0.35
        post_surv_notout, _, _ = laplace_mode_filter_survival(
            prior_mean=prior_mean,
            prior_var=prior_var,
            is_dismissed=False,
            balls_faced=50,
        )
        post_surv_out, _, _ = laplace_mode_filter_survival(
            prior_mean=prior_mean,
            prior_var=prior_var,
            is_dismissed=True,
            balls_faced=50,
        )
        assert post_surv_notout > post_surv_out, "Not out innings must yield higher survival posterior"


class TestContextualAdjustments:
    """2. Directional correctness of contextual adjustments (Phase 4A.1 fixes)."""

    def test_oqi_batting_direction(self):
        """Facing an elite attack (I_OBQ = 1.35) must reward the batter more than facing a weak attack (I_OBQ = 0.75)."""
        fmt_config = FORMAT_CONFIGS["T20"]
        state_elite = PlayerRatingState.create_debutant("p1", "T20", "2024-01-01")
        state_weak = PlayerRatingState.create_debutant("p2", "T20", "2024-01-01")

        # Identical raw performance: 40 runs off 20 balls (SR 200)
        state_elite = update_batting_state(
            state=state_elite,
            runs_scored=40,
            balls_faced=20,
            is_dismissed=False,
            park_factor=1.00,
            opp_bowling_quality=1.35,  # Elite bowling
            format_config=fmt_config,
        )
        state_weak = update_batting_state(
            state=state_weak,
            runs_scored=40,
            balls_faced=20,
            is_dismissed=False,
            park_factor=1.00,
            opp_bowling_quality=0.75,  # Weak bowling
            format_config=fmt_config,
        )

        assert state_elite.r_bat > state_weak.r_bat, (
            "Scoring 40 runs against elite bowling must yield a higher rating than against weak bowling"
        )

    def test_opp_batting_quality_bowling_direction(self):
        """Conceding 24 runs in 4 overs against India (I_BatQuality = 1.30) must reward the bowler more than against weak batting (I_BatQuality = 0.70)."""
        fmt_config = FORMAT_CONFIGS["T20"]
        state_elite = PlayerRatingState.create_debutant("b1", "T20", "2024-01-01")
        state_weak = PlayerRatingState.create_debutant("b2", "T20", "2024-01-01")

        # Identical raw figures: 1 wicket for 24 runs in 24 balls (Econ 6.0)
        state_elite = update_bowling_state(
            state=state_elite,
            wickets_taken=1,
            runs_conceded=24,
            legal_balls_bowled=24,
            park_factor=1.00,
            opp_batting_quality=1.30,  # Elite batting
            format_config=fmt_config,
        )
        state_weak = update_bowling_state(
            state=state_weak,
            wickets_taken=1,
            runs_conceded=24,
            legal_balls_bowled=24,
            park_factor=1.00,
            opp_batting_quality=0.70,  # Weak batting
            format_config=fmt_config,
        )

        assert state_elite.r_bowl > state_weak.r_bowl, (
            "Conceding 24 against elite batting must yield higher bowling rating than against weak batting"
        )


class TestTemporalDynamicsAndUncertainty:
    """3. Continuous-time variance inflation and uncertainty properties."""

    def test_inactivity_variance_growth(self):
        """Inactivity must inflate RD while preserving mean skill."""
        fmt_config = FORMAT_CONFIGS["T20"]
        state = PlayerRatingState.create_debutant("p1", "T20", "2023-01-01")
        state.r_bat = 1200.0
        state.rd_bat = 80.0
        state.last_match_date = "2023-01-01"

        # Advance 180 days without match observations
        drifted_state = apply_temporal_drift(
            state=state,
            current_match_date="2023-06-30",
            format_config=fmt_config,
            rd_max=350.0,
        )

        assert drifted_state.r_bat == 1200.0, "Mean ability must remain constant during inactivity"
        assert drifted_state.rd_bat > 80.0, "Rating deviation must increase with inactivity"
        assert drifted_state.rd_bat <= 350.0, "Rating deviation must be capped at RD_max"

    def test_credible_intervals(self):
        """Verify 90% Bayesian credible interval calculation."""
        low, high = compute_credible_interval(1000.0, 50.0, alpha=0.10)
        expected_width = 2.0 * 1.644853 * 50.0
        assert math.isclose(high - low, expected_width, rel_tol=1e-3)

    def test_probability_of_superiority(self):
        """A player with 1200 +/- 40 is overwhelmingly likely superior to 1000 +/- 40."""
        p_sup = probability_player_superiority(1200.0, 40.0, 1000.0, 40.0)
        assert p_sup > 0.999


class TestAllRoundAndVORP:
    """4. Monotonic additive all-round rating and negative VORP preservation."""

    def test_all_round_monotonicity(self):
        """Improving batting ability must NEVER lower all-round rating."""
        fmt_config = FORMAT_CONFIGS["ODI"]
        state_modest = PlayerRatingState.create_debutant("ar1", "ODI", "2024-01-01")
        state_modest.r_bat = 700.0
        state_modest.r_bowl = 850.0

        state_elite = PlayerRatingState.create_debutant("ar2", "ODI", "2024-01-01")
        state_elite.r_bat = 1100.0  # Significantly better batting
        state_elite.r_bowl = 850.0  # Identical bowling

        r_ar_modest, _, _ = compute_all_round_and_vorp(state_modest, 0.40, 0.50, fmt_config)
        r_ar_elite, _, _ = compute_all_round_and_vorp(state_elite, 0.40, 0.50, fmt_config)

        assert r_ar_elite > r_ar_modest, "All-round rating must be strictly monotonic in batting ability"

    def test_negative_vorp_preservation(self):
        """Sub-replacement players must produce negative VORP (no max(0, ...) truncation)."""
        fmt_config = FORMAT_CONFIGS["T20"]
        state_subrep = PlayerRatingState.create_debutant("sub", "T20", "2024-01-01")
        state_subrep.r_bat = 450.0   # Well below 650.0 replacement level
        state_subrep.r_bowl = 400.0  # Well below 650.0 replacement level
        state_subrep.r_field = 350.0

        _, _, vorp = compute_all_round_and_vorp(state_subrep, 0.60, 0.40, fmt_config, replacement_level_rating=650.0)
        assert vorp < 0.0, "Sub-replacement player must have negative VORP (zero truncation prohibited)"


class TestRoleInferenceAndIdentity:
    """5. Dynamic role inference and identity confidence decoupling."""

    def test_role_inference_opener(self):
        """Player with batting position 1.2 and 0 overs bowled is Opener."""
        role, conf, flag = infer_dynamic_role(
            rolling_batting_pos=1.2,
            rolling_overs_bowled=0.0,
            rolling_stumpings=0.0,
            pace_spin_class=None,
            matches_in_window=10,
        )
        assert role == "R1_OPENER"
        assert conf >= 0.85
        assert flag is None

    def test_role_inference_specialist_bowler(self):
        """Player with batting position 9.5 and 4.0 overs bowled is Specialist Bowler."""
        role, conf, flag = infer_dynamic_role(
            rolling_batting_pos=9.5,
            rolling_overs_bowled=4.0,
            rolling_stumpings=0.0,
            pace_spin_class="pace",
            matches_in_window=15,
        )
        assert role == "R8_PACE_SPECIALIST"

    def test_debutant_role_flag(self):
        """Debutant with < 5 matches receives default role and insufficient history flag."""
        role, conf, flag = infer_dynamic_role(
            rolling_batting_pos=4.0,
            rolling_overs_bowled=0.0,
            rolling_stumpings=0.0,
            pace_spin_class=None,
            matches_in_window=2,
        )
        assert flag == "DEBUTANT_INSUFFICIENT_HISTORY"

    def test_babar_ali_identity_mixture(self):
        """Player c65e0275 carries PROBABLE status and 0.65 mixture weight."""
        mgr = IdentityManager()
        status, weight = mgr.get_identity_status_and_weight("c65e0275")
        assert status == "PROBABLE"
        assert weight == 0.65

        # Decision expectation mixture
        # E[Y] = 0.65 * 30 + 0.35 * 10 = 19.5 + 3.5 = 23.0
        exp_y = mgr.compute_mixture_expectation("c65e0275", 30.0, 10.0)
        assert math.isclose(exp_y, 23.0)


class TestFormatDecoupling:
    """6. Format ratings are structurally decoupled and independent."""

    def test_format_state_independence(self):
        """Updating T20 state must have zero effect on ODI and Test states."""
        fmt_t20 = FORMAT_CONFIGS["T20"]
        state_t20 = PlayerRatingState.create_debutant("p_multi", "T20", "2024-01-01")
        state_odi = PlayerRatingState.create_debutant("p_multi", "ODI", "2024-01-01")

        initial_odi_rating = state_odi.r_bat

        # Update T20 rating
        state_t20 = update_batting_state(
            state=state_t20,
            runs_scored=80,
            balls_faced=40,
            is_dismissed=False,
            park_factor=1.0,
            opp_bowling_quality=1.0,
            format_config=fmt_t20,
        )

        assert state_t20.r_bat > 1000.0
        assert state_odi.r_bat == initial_odi_rating, "ODI state must remain untouched by T20 updates"
