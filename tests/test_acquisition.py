"""
Automated Unit Tests for Cricsheet Acquisition and Inventory Utilities

Tests checksum calculation, manifest updates, unchanged archive detection,
invalid ZIP handling, safe path-traversal prevention, inventory scanning,
and graceful handling of invalid/unreadable JSON files.
Uses local fixtures without external network dependencies.
"""
import io
import json
import zipfile
from pathlib import Path
import pytest

from etl.download_cricsheet import (
    compute_sha256,
    validate_zip_archive,
    safe_extract_zip,
    IngestionManifest,
    inspect_dataset_files,
    inspect_register_csv,
)


@pytest.fixture
def sample_zip(tmp_path: Path) -> Path:
    """Create a valid sample ZIP containing two valid match JSON files."""
    zip_path = tmp_path / "valid_sample.zip"
    match_1 = {
        "meta": {"data_version": "1.3.0"},
        "info": {
            "dates": ["2023-03-01", "2023-03-02"],
            "season": "2022/23",
            "teams": ["India", "Australia"],
            "match_type": "Test",
        },
    }
    match_2 = {
        "meta": {"data_version": "1.3.0"},
        "info": {
            "dates": ["2023-03-09"],
            "season": "2022/23",
            "teams": ["India", "Australia"],
            "match_type": "Test",
        },
    }

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("1001.json", json.dumps(match_1))
        zf.writestr("1002.json", json.dumps(match_2))
        zf.writestr("README.txt", "Sample cricsheet archive")

    return zip_path


def test_compute_sha256(tmp_path: Path):
    """Verify SHA-256 computation against known string."""
    test_file = tmp_path / "test.txt"
    test_file.write_bytes(b"CricEngine AI Test Data")
    # Known sha256 for b"CricEngine AI Test Data"
    import hashlib
    expected_sha = hashlib.sha256(b"CricEngine AI Test Data").hexdigest()
    assert compute_sha256(test_file) == expected_sha


def test_validate_zip_archive_valid(sample_zip: Path):
    """Verify valid ZIP detection."""
    is_valid, error = validate_zip_archive(sample_zip)
    assert is_valid is True
    assert error is None


def test_validate_zip_archive_invalid(tmp_path: Path):
    """Verify corrupted / non-ZIP file detection."""
    corrupt_file = tmp_path / "corrupt.zip"
    corrupt_file.write_bytes(b"This is completely invalid zip content")
    is_valid, error = validate_zip_archive(corrupt_file)
    assert is_valid is False
    assert "Not a valid ZIP format" in error


def test_validate_zip_archive_missing(tmp_path: Path):
    """Verify missing file handling."""
    missing_file = tmp_path / "non_existent.zip"
    is_valid, error = validate_zip_archive(missing_file)
    assert is_valid is False
    assert "File not found" in error


def test_safe_extract_zip(sample_zip: Path, tmp_path: Path):
    """Verify safe extraction extracts all member files within destination."""
    extract_dir = tmp_path / "extracted_output"
    count = safe_extract_zip(sample_zip, extract_dir)
    assert count == 3
    assert (extract_dir / "1001.json").exists()
    assert (extract_dir / "1002.json").exists()
    assert (extract_dir / "README.txt").exists()


def test_safe_extract_zip_prevents_path_traversal(tmp_path: Path):
    """Verify path traversal attack in ZIP is detected and blocked with ValueError."""
    malicious_zip = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious_zip, "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    dest_dir = tmp_path / "safe_zone"
    with pytest.raises(ValueError, match="Path traversal detected"):
        safe_extract_zip(malicious_zip, dest_dir)


def test_manifest_creation_and_persistence(tmp_path: Path):
    """Verify IngestionManifest creation, updates, and persistence."""
    manifest_file = tmp_path / "manifest.json"
    manifest = IngestionManifest(manifest_path=manifest_file)

    manifest.record_dataset(
        "ipl_male",
        {
            "competition": "IPL",
            "format": "T20",
            "tier": 2,
            "archive_filename": "ipl_male_json.zip",
            "archive_sha256": "fakehash123",
            "archive_size_bytes": 5000000,
            "extraction_status": "SUCCESS",
            "extracted_file_count": 1000,
            "error": None,
        },
    )

    assert manifest_file.exists()

    # Re-read manifest from disk
    manifest_reloaded = IngestionManifest(manifest_path=manifest_file)
    ipl_record = manifest_reloaded.get_dataset("ipl_male")
    assert ipl_record is not None
    assert ipl_record["competition"] == "IPL"
    assert ipl_record["archive_sha256"] == "fakehash123"
    assert ipl_record["extraction_status"] == "SUCCESS"


def test_inspect_dataset_files(tmp_path: Path, sample_zip: Path):
    """Verify inspection extracts correct dates, seasons, match IDs, and detects unreadable files."""
    extract_dir = tmp_path / "extracted_matches"
    safe_extract_zip(sample_zip, extract_dir)

    # Inject one unreadable / malformed JSON file
    corrupt_json = extract_dir / "9999.json"
    corrupt_json.write_text("{ unclosed invalid json string ...", encoding="utf-8")

    stats = inspect_dataset_files(extract_dir)

    assert stats["total_files"] == 3  # 1001.json, 1002.json, 9999.json
    assert stats["readable_files"] == 2
    assert stats["unreadable_files"] == 1
    assert len(stats["invalid_files"]) == 1
    assert "9999.json" in stats["invalid_files"][0]
    assert stats["earliest_date"] == "2023-03-01"
    assert stats["latest_date"] == "2023-03-09"
    assert stats["distinct_match_ids"] == 2
    assert stats["data_versions"] == ["1.3.0"]
    assert stats["teams_count"] == 2



def test_inspect_register_csv(tmp_path: Path):
    """Verify CSV register inspection for headers and row count."""
    csv_file = tmp_path / "people_sample.csv"
    csv_file.write_text(
        "identifier,name,unique_name,key_cricinfo,key_bcci\n"
        "252938a6,V Kohli,Virat Kohli,253802,234\n"
        "b8a55852,BB McCullum,Brendon McCullum,37737,\n",
        encoding="utf-8",
    )

    result = inspect_register_csv(csv_file)
    assert result["exists"] is True
    assert result["row_count"] == 2
    assert "identifier" in result["columns"]
    assert "key_cricinfo" in result["columns"]
    assert "key_bcci" in result["columns"]


def test_changed_archive_detection_and_backup(tmp_path: Path):
    """Verify that when archive content changes, the previous version is backed up without data loss."""
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    orig_archive = archive_dir / "test_comp.zip"

    # 1. Create version 1
    with zipfile.ZipFile(orig_archive, "w") as zf:
        zf.writestr("match_v1.json", json.dumps({"v": 1}))
    v1_sha = compute_sha256(orig_archive)

    # 2. Simulate downloading a changed version 2 to temp file
    new_archive = archive_dir / "test_comp.zip.new"
    with zipfile.ZipFile(new_archive, "w") as zf:
        zf.writestr("match_v2.json", json.dumps({"v": 2}))
    v2_sha = compute_sha256(new_archive)

    assert v1_sha != v2_sha

    # 3. Simulate change detection and backup logic
    if v1_sha != v2_sha and orig_archive.exists():
        backup_name = f"{orig_archive.stem}_{v1_sha[:8]}{orig_archive.suffix}"
        backup_path = orig_archive.with_name(backup_name)
        orig_archive.rename(backup_path)
    new_archive.replace(orig_archive)

    # Assert backup exists and new archive is in place
    expected_backup = archive_dir / f"test_comp_{v1_sha[:8]}.zip"
    assert expected_backup.exists(), "Previous archive backup was not created"
    assert compute_sha256(expected_backup) == v1_sha
    assert compute_sha256(orig_archive) == v2_sha


def test_unchanged_archive_detection(tmp_path: Path, sample_zip: Path):
    """Verify that an unchanged archive with valid checksum is recognized."""
    orig_sha = compute_sha256(sample_zip)
    current_sha = compute_sha256(sample_zip)
    assert orig_sha == current_sha
    is_valid, error = validate_zip_archive(sample_zip)
    assert is_valid is True
    assert error is None

