"""
CricEngine AI — Phase 3B: Comprehensive Validation & Regression Test Suite
Validates Player Identity Disambiguation, Player Master Enrichment,
Historical Roster Classification, Feature Store v3b, and Database Immutability.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow.parquet as pq
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
DUCKDB_PATH = ROOT_DIR / "data/datalake/curated/cricengine.duckdb"
EXPECTED_DUCKDB_SHA256 = "a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae"
EXPECTED_DUCKDB_SIZE = 401616896


def calculate_file_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


# -----------------------------------------------------------------------------
# Workstream 1: Player Identity Disambiguation Tests
# -----------------------------------------------------------------------------

def test_player_identity_disambiguation_artifacts():
    parquet_path = ROOT_DIR / "data/datalake/metadata_v3b/player_identity_resolution.parquet"
    csv_path = ROOT_DIR / "data/datalake/metadata_v3b/player_identity_resolution.csv"
    evidence_path = ROOT_DIR / "data/datalake/metadata_v3b/player_identity_evidence_table.json"
    collisions_path = ROOT_DIR / "data/datalake/metadata_v3b/remaining_collisions.json"

    assert parquet_path.exists(), "Missing player_identity_resolution.parquet"
    assert csv_path.exists(), "Missing player_identity_resolution.csv"
    assert evidence_path.exists(), "Missing player_identity_evidence_table.json"
    assert collisions_path.exists(), "Missing remaining_collisions.json"

    df = pd.read_parquet(parquet_path)
    assert len(df) == 7029, f"Expected 7029 rows, got {len(df)}"

    # Check standalone status
    standalone_counts = df["standalone_name_status"].value_counts().to_dict()
    assert standalone_counts.get("AMBIGUOUS") == 152, f"Expected 152 AMBIGUOUS, got {standalone_counts.get('AMBIGUOUS')}"
    assert standalone_counts.get("VERIFIED") == 6876, f"Expected 6876 VERIFIED, got {standalone_counts.get('VERIFIED')}"
    assert standalone_counts.get("PROBABLE") == 1, f"Expected 1 PROBABLE, got {standalone_counts.get('PROBABLE')}"
    assert standalone_counts.get("UNRESOLVED", 0) == 0, "UNRESOLVED should be 0"

    # Check contextual resolution status
    contextual_counts = df["contextual_resolution_status"].value_counts().to_dict()
    assert contextual_counts.get("VERIFIED") == 7028, f"Expected 7028 VERIFIED, got {contextual_counts.get('VERIFIED')}"
    assert contextual_counts.get("PROBABLE") == 1, f"Expected 1 PROBABLE, got {contextual_counts.get('PROBABLE')}"
    assert contextual_counts.get("AMBIGUOUS", 0) == 0, "Contextual AMBIGUOUS should be 0"
    assert contextual_counts.get("UNRESOLVED", 0) == 0, "Contextual UNRESOLVED should be 0"

    # Check evidence table covers all 71 colliding names
    with open(evidence_path, "r") as f:
        evidence = json.load(f)
    assert len(evidence) == 71, f"Expected 71 colliding names in evidence table, got {len(evidence)}"


# -----------------------------------------------------------------------------
# Workstream 2: Player Master Enrichment Tests
# -----------------------------------------------------------------------------

def test_player_master_enrichment_artifacts():
    enriched_parquet = ROOT_DIR / "data/datalake/enrichment_v3b/dim_player_master_enriched.parquet"
    provenance_parquet = ROOT_DIR / "data/datalake/enrichment_v3b/player_attribute_provenance.parquet"
    missing_file = ROOT_DIR / "data/datalake/metadata_v3b/missing_attributes.json"
    conflicts_file = ROOT_DIR / "data/datalake/metadata_v3b/attribute_conflicts.json"

    assert enriched_parquet.exists(), "Missing dim_player_master_enriched.parquet"
    assert provenance_parquet.exists(), "Missing player_attribute_provenance.parquet"
    assert missing_file.exists(), "Missing missing_attributes.json"
    assert conflicts_file.exists(), "Missing attribute_conflicts.json"

    df_enriched = pd.read_parquet(enriched_parquet)
    assert len(df_enriched) == 7014, f"Expected 7014 canonical players, got {len(df_enriched)}"

    # Verify column existence
    expected_cols = [
        "player_id", "canonical_name", "full_name", "unique_name", "date_of_birth",
        "nationality", "batting_hand", "bowling_style", "bowling_arm", "bowling_type",
        "pace_spin_class", "officially_listed_role", "observed_historical_role",
        "derived_statistical_role", "current_role"
    ]
    for col in expected_cols:
        assert col in df_enriched.columns, f"Missing expected column: {col}"

    # Verify unmodelled statistical role is 100% NULL
    assert df_enriched["derived_statistical_role"].isna().all(), "derived_statistical_role must be 100% NULL"

    # Verify provenance table
    df_prov = pd.read_parquet(provenance_parquet)
    assert len(df_prov) == 7014 * 12, f"Expected {7014*12} provenance rows, got {len(df_prov)}"
    valid_categories = {"DIRECTLY OBSERVED", "AUTHORITATIVELY SOURCED", "DERIVED", "UNAVAILABLE", "CONFLICTING"}
    assert set(df_prov["provenance_category"].unique()).issubset(valid_categories)


# -----------------------------------------------------------------------------
# Workstream 3: Historical Match Roster Classification Tests
# -----------------------------------------------------------------------------

def test_historical_match_roster_classification():
    class_parquet = ROOT_DIR / "data/datalake/enrichment_v3b/historical_roster_classifications.parquet"
    part_parquet = ROOT_DIR / "data/datalake/enrichment_v3b/fact_match_participation_v3b.parquet"
    coverage_file = ROOT_DIR / "data/datalake/metadata_v3b/match_roster_coverage.json"

    assert class_parquet.exists(), "Missing historical_roster_classifications.parquet"
    assert part_parquet.exists(), "Missing fact_match_participation_v3b.parquet"
    assert coverage_file.exists(), "Missing match_roster_coverage.json"

    df_class = pd.read_parquet(class_parquet)
    assert len(df_class) == 9085, f"Expected 9085 matches, got {len(df_class)}"

    counts = df_class["roster_classification"].value_counts().to_dict()
    assert counts.get("LEGITIMATELY_STANDARD_22") == 4945, f"LEGITIMATELY_STANDARD_22: {counts.get('LEGITIMATELY_STANDARD_22')}"
    assert counts.get("INACTIVE_STARTING_XI_PLAYERS") == 2664, f"INACTIVE_STARTING_XI_PLAYERS: {counts.get('INACTIVE_STARTING_XI_PLAYERS')}"
    assert counts.get("MISSING_SUBSTITUTE_OR_REPLACEMENT_INFO") == 993, f"MISSING_SUBSTITUTE_OR_REPLACEMENT_INFO: {counts.get('MISSING_SUBSTITUTE_OR_REPLACEMENT_INFO')}"
    assert counts.get("IMPACT_PLAYER_ERA") == 371, f"IMPACT_PLAYER_ERA: {counts.get('IMPACT_PLAYER_ERA')}"
    assert counts.get("LEGITIMATELY_MORE_THAN_22") == 105, f"LEGITIMATELY_MORE_THAN_22: {counts.get('LEGITIMATELY_MORE_THAN_22')}"
    assert counts.get("LEGITIMATELY_FEWER_THAN_22") == 5, f"LEGITIMATELY_FEWER_THAN_22: {counts.get('LEGITIMATELY_FEWER_THAN_22')}"
    assert counts.get("SOURCE_METADATA_INCONSISTENCY") == 2, f"SOURCE_METADATA_INCONSISTENCY: {counts.get('SOURCE_METADATA_INCONSISTENCY')}"
    assert counts.get("UNCERTAIN_CLASSIFICATION", 0) == 0, "UNCERTAIN_CLASSIFICATION must be 0"

    # Verify participation v3b restoration
    df_part = pd.read_parquet(part_parquet)
    assert len(df_part) == 200709, f"Expected 200709 participation rows, got {len(df_part)}"

    # Inactive starting players must be restored with in_starting_xi = True and STARTING_XI_INACTIVE
    inactive_starting = df_part[df_part["participation_role"] == "STARTING_XI_INACTIVE"]
    assert len(inactive_starting) > 0, "Expected inactive starting XI players to be present"
    assert (inactive_starting["in_starting_xi"] == True).all(), "All STARTING_XI_INACTIVE must have in_starting_xi = True"


# -----------------------------------------------------------------------------
# Feature Store v3b Integration Tests
# -----------------------------------------------------------------------------

def test_feature_store_v3b_integrity():
    fs_dir = ROOT_DIR / "data/datalake/feature_store_v3b"
    manifest_path = fs_dir / "_manifest.json"
    checksums_path = ROOT_DIR / "docs/feature_store_v3b_checksums.json"

    assert manifest_path.exists(), "Missing feature_store_v3b/_manifest.json"
    assert checksums_path.exists(), "Missing docs/feature_store_v3b_checksums.json"

    with open(manifest_path, "r") as f:
        manifest = json.load(f)
    assert manifest["feature_store_version"] == "3.1.0-phase3b"

    # Read dataset schema using hive partitioning
    import pyarrow.dataset as ds
    dataset = ds.dataset(fs_dir / "player_match", partitioning="hive")
    assert len(dataset.schema) == 51, f"Expected 51 fields in player_match v3b dataset, got {len(dataset.schema)}"
    schema = dataset.schema

    # Check newly added fields
    enriched_fields = ["batting_hand", "bowling_style", "pace_spin_class", "primary_role", "player_age_at_match"]
    for field in enriched_fields:
        assert field in schema.names, f"Missing enriched field {field} in player_match"

    # Verify age sanity (when present, age should be between 14 and 65)
    pm_files = list((fs_dir / "player_match").rglob("*.parquet"))
    sample_df = pd.read_parquet(pm_files[0])
    valid_ages = sample_df["player_age_at_match"].dropna()
    if len(valid_ages) > 0:
        assert (valid_ages > 14).all() and (valid_ages < 65).all(), "Invalid player age range detected"


# -----------------------------------------------------------------------------
# Curated Database Immutability Check
# -----------------------------------------------------------------------------

def test_curated_duckdb_immutability():
    actual_sha256 = calculate_file_sha256(DUCKDB_PATH)
    actual_size = DUCKDB_PATH.stat().st_size
    assert actual_sha256 == EXPECTED_DUCKDB_SHA256, (
        f"Database modified! Checksum mismatch: {actual_sha256} != {EXPECTED_DUCKDB_SHA256}"
    )
    assert actual_size == EXPECTED_DUCKDB_SIZE, (
        f"Database modified! Size mismatch: {actual_size} != {EXPECTED_DUCKDB_SIZE}"
    )
