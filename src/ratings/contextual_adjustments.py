"""
CricEngine AI — Contextual Adjustments Engine (Phase 4B)
"""

from __future__ import annotations
import math
from typing import Dict, Tuple, Optional
from pathlib import Path
import pyarrow.parquet as pq
import pandas as pd


class ContextualEngine:
    """
    Manages pre-match venue park factors and opposition quality indices.
    Enforces Phase 4A.1 directional conventions and zero-lookahead constraints.
    """

    def __init__(self, venue_park_factors_path: Optional[Path] = None):
        self.venue_cache: Dict[Tuple[str, str], float] = {}
        if venue_park_factors_path and venue_park_factors_path.exists():
            self._load_venue_baselines(venue_park_factors_path)

    def _load_venue_baselines(self, path: Path):
        """Loads and applies Empirical Bayes shrinkage to venue park factors."""
        table = pq.read_table(path)
        pydict = table.to_pydict()
        
        venues = pydict.get("canonical_venue_name", [])
        formats = pydict.get("match_format", [])
        matches = pydict.get("total_matches", [])
        raw_factors = pydict.get("park_factor", [])
        
        for v, f, n, rf in zip(venues, formats, matches, raw_factors):
            # Empirical Bayes shrinkage for venues with < 15 matches (K=10)
            n_val = float(n) if n is not None else 0.0
            rf_val = float(rf) if rf is not None else 1.0
            shrunk_pf = (n_val / (n_val + 10.0)) * rf_val + (10.0 / (n_val + 10.0)) * 1.000
            self.venue_cache[(v, f.upper())] = round(shrunk_pf, 4)

    def get_shrunk_park_factor(self, canonical_venue: str, match_format: str, raw_pf: Optional[float] = None) -> float:
        """
        Retrieves pre-match park factor for a venue. Defaults to 1.0 if unseen.
        """
        key = (canonical_venue, match_format.upper())
        if key in self.venue_cache:
            return self.venue_cache[key]
        if pd.notna(raw_pf):
            return max(0.60, min(1.60, float(raw_pf)))
        return 1.000

    @staticmethod
    def sanitize_opp_bowling_quality(obq: Optional[float]) -> float:
        """
        Sanitizes Opposition Bowling Quality Index (I_OBQ).
        Higher means tougher bowling attack (e.g. 1.25).
        """
        if pd.isna(obq) or float(obq) <= 0.0:
            return 1.000
        return max(0.50, min(2.50, float(obq)))

    @staticmethod
    def sanitize_opp_batting_quality(obq: Optional[float]) -> float:
        """
        Sanitizes Opposition Batting Quality Index (I_BatQuality).
        Higher means stronger batting attack (e.g. 1.25).
        """
        if pd.isna(obq) or float(obq) <= 0.0:
            return 1.000
        return max(0.50, min(2.50, float(obq)))
