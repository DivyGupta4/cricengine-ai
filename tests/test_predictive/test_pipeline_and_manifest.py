"""
Integration tests for predictive pipeline outputs and manifest verification (Phase 4C).
"""

import json
from pathlib import Path
import pytest
from src.predictive.config import PREDICTIVE_STORE_V4C_DIR, ANALYSIS_DIR


def test_manifest_existence_and_schema():
    """Verify _manifest.json exists, contains valid SHA-256 hashes, and correct summary fields."""
    manifest_path = PREDICTIVE_STORE_V4C_DIR / "_manifest.json"
    assert manifest_path.exists(), "Manifest file must exist"
    
    with open(manifest_path, "r") as f:
        manifest = json.load(f)
        
    assert manifest["version"] == "4.3.0-phase4c"
    assert manifest["total_files"] >= 80
    assert "summary" in manifest
    summary = manifest["summary"]
    assert summary["total_batting_predictions"] > 0
    assert summary["d_minus_1_verified"] is True
    
    # Check that each file in the manifest actually exists on disk
    for rel_path, file_meta in manifest["files"].items():
        full_path = PREDICTIVE_STORE_V4C_DIR / rel_path
        assert full_path.exists(), f"Materialized file {rel_path} must exist on disk"
        assert len(file_meta["sha256"]) == 64
        assert file_meta["bytes"] > 0


def test_analysis_artifacts_existence():
    """Verify analytical summary JSON artifacts are exported."""
    bm_path = ANALYSIS_DIR / "benchmark_comparison.json"
    cal_path = ANALYSIS_DIR / "calibration_diagnostics.json"
    summary_path = ANALYSIS_DIR / "pipeline_summary.json"
    
    assert bm_path.exists(), "benchmark_comparison.json must exist"
    assert cal_path.exists(), "calibration_diagnostics.json must exist"
    assert summary_path.exists(), "pipeline_summary.json must exist"
    
    with open(bm_path, "r") as f:
        benchmarks = json.load(f)
    assert len(benchmarks) >= 5
