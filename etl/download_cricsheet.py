"""
CricEngine AI — Cricsheet Data Acquisition & Verification Pipeline

Handles atomic downloads, cryptographic checksums (SHA-256), zip archive
integrity verification, path-traversal-safe extraction, and manifest tracking.
"""
from __future__ import annotations
import csv
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import zipfile
import requests

from config.settings import (
    CRICSHEET_ARCHIVES_DIR,
    CRICSHEET_EXTRACTED_DIR,
    CRICSHEET_REGISTERS_DIR,
    MANIFEST_PATH,
)

logger = logging.getLogger(__name__)

# Approved Initial Acquisition Targets
APPROVED_DATASETS: List[Dict[str, Any]] = [
    {
        "key": "tests_male",
        "competition": "Test Matches",
        "format": "Test",
        "tier": 1,
        "archive_filename": "tests_male_json.zip",
        "url": "https://cricsheet.org/downloads/tests_male_json.zip",
        "extract_subdir": "tests_male",
        "reported_match_count": 897,
    },
    {
        "key": "odis_male",
        "competition": "One-Day Internationals",
        "format": "ODI",
        "tier": 1,
        "archive_filename": "odis_male_json.zip",
        "url": "https://cricsheet.org/downloads/odis_male_json.zip",
        "extract_subdir": "odis_male",
        "reported_match_count": 2607,
    },
    {
        "key": "t20s_male",
        "competition": "T20 Internationals",
        "format": "T20I",
        "tier": 1,
        "archive_filename": "t20s_male_json.zip",
        "url": "https://cricsheet.org/downloads/t20s_male_json.zip",
        "extract_subdir": "t20s_male",
        "reported_match_count": 3646,
    },
    {
        "key": "ipl_male",
        "competition": "Indian Premier League",
        "format": "T20",
        "tier": 2,
        "archive_filename": "ipl_male_json.zip",
        "url": "https://cricsheet.org/downloads/ipl_male_json.zip",
        "extract_subdir": "ipl_male",
        "reported_match_count": 1095,
    },
    {
        "key": "sma_male",
        "competition": "Syed Mushtaq Ali Trophy",
        "format": "T20",
        "tier": 3,
        "archive_filename": "sma_male_json.zip",
        "url": "https://cricsheet.org/downloads/sma_male_json.zip",
        "extract_subdir": "sma_male",
        "reported_match_count": 695,
    },
]

APPROVED_REGISTERS: List[Dict[str, Any]] = [
    {
        "key": "people",
        "filename": "people.csv",
        "url": "https://cricsheet.org/register/people.csv",
        "description": "People Register mapping Cricsheet IDs to external registries (BCCI, Cricinfo, Cricbuzz, etc.)",
    },
    {
        "key": "names",
        "filename": "names.csv",
        "url": "https://cricsheet.org/register/names.csv",
        "description": "Name alias mappings to Cricsheet identifiers",
    },
    {
        "key": "venues",
        "filename": "venues.csv",
        "url": "https://cricsheet.org/register/venues.csv",
        "description": "Venue names mapped to Cricinfo venue identifiers",
    },
]


def compute_sha256(filepath: Path) -> str:
    """Compute the SHA-256 hash of a file reading in 64KB chunks."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def download_file(
    url: str,
    dest_path: Path,
    timeout: int = 60,
    max_retries: int = 3,
    chunk_size: int = 65536,
) -> Dict[str, Any]:
    """
    Download a file atomically using a temporary .part file and retries.
    Returns download metadata including checksum and retrieval timestamp.
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_name(f"{dest_path.name}.part")

    session = requests.Session()
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Downloading %s (attempt %d/%d)...", url, attempt, max_retries)
            with session.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with open(temp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)

            # Atomic rename on complete download
            temp_path.replace(dest_path)
            retrieval_ts = datetime.now(timezone.utc).isoformat()
            sha256 = compute_sha256(dest_path)
            file_size = dest_path.stat().st_size

            return {
                "status": "SUCCESS",
                "retrieval_timestamp": retrieval_ts,
                "sha256": sha256,
                "size_bytes": file_size,
                "error": None,
            }
        except Exception as exc:  # pylint: disable=broad-except
            last_error = exc
            logger.warning("Download attempt %d failed for %s: %s", attempt, url, exc)
            if temp_path.exists():
                temp_path.unlink()

    return {
        "status": "FAILED",
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "sha256": None,
        "size_bytes": 0,
        "error": str(last_error),
    }


def validate_zip_archive(zip_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate that a file is a valid, uncorrupted ZIP archive.
    Returns (is_valid, error_message).
    """
    if not zip_path.exists():
        return False, f"File not found: {zip_path}"

    if not zipfile.is_zipfile(zip_path):
        return False, f"Not a valid ZIP format: {zip_path}"

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            bad_file = zf.testzip()
            if bad_file is not None:
                return False, f"Corrupted file inside archive: {bad_file}"
        return True, None
    except Exception as exc:  # pylint: disable=broad-except
        return False, f"Archive validation exception: {exc}"


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> int:
    """
    Extract a ZIP archive safely preventing path traversal attacks.
    Returns count of extracted files.
    """
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted_count = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            # Resolve destination target path
            target_path = (extract_dir / member.filename).resolve()

            # Security check: ensure target path is within extract_dir
            if not target_path.is_relative_to(extract_dir):
                raise ValueError(
                    f"Path traversal detected in archive member: {member.filename}"
                )

            # Prevent directory extraction issues
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, open(target_path, "wb") as target:
                while chunk := source.read(65536):
                    target.write(chunk)
            extracted_count += 1

    return extracted_count


class IngestionManifest:
    """Manages the structured acquisition manifest file."""

    def __init__(self, manifest_path: Path = MANIFEST_PATH):
        self.manifest_path = manifest_path
        self.data: Dict[str, Any] = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Could not read existing manifest: %s", exc)
        return {
            "version": "1.0.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "datasets": {},
            "registers": {},
        }

    def record_dataset(self, key: str, record: Dict[str, Any]) -> None:
        """Record or update a dataset entry."""
        self.data["datasets"][key] = record
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def record_register(self, key: str, record: Dict[str, Any]) -> None:
        """Record or update a register entry."""
        self.data["registers"][key] = record
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.save()

    def get_dataset(self, key: str) -> Optional[Dict[str, Any]]:
        """Get dataset entry if present."""
        return self.data.get("datasets", {}).get(key)

    def save(self) -> None:
        """Atomically persist manifest to JSON."""
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        temp_manifest = self.manifest_path.with_suffix(".json.tmp")
        with open(temp_manifest, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)
        temp_manifest.replace(self.manifest_path)


def acquire_approved_datasets(
    force_redownload: bool = False,
) -> Tuple[IngestionManifest, Dict[str, Any]]:
    """
    Acquire, validate, extract, and record all approved Cricsheet datasets.
    Rerunning does not redownload unless force_redownload=True or archive is missing/invalid.
    """
    manifest = IngestionManifest()
    results: Dict[str, Any] = {}

    for target in APPROVED_DATASETS:
        key = target["key"]
        archive_path = CRICSHEET_ARCHIVES_DIR / target["archive_filename"]
        extract_dir = CRICSHEET_EXTRACTED_DIR / target["extract_subdir"]

        existing_record = manifest.get_dataset(key)
        existing_sha = (
            compute_sha256(archive_path)
            if archive_path.exists()
            else (existing_record.get("archive_sha256") if existing_record else None)
        )
        need_download = force_redownload or not archive_path.exists()

        if not need_download and archive_path.exists():
            # Validate existing archive integrity
            is_valid, error_msg = validate_zip_archive(archive_path)
            if not is_valid:
                logger.warning("Existing archive for %s invalid: %s. Redownloading.", key, error_msg)
                need_download = True

        version_changed = False
        previous_sha = existing_sha
        download_status = "UNCHANGED"

        if need_download:
            # Download to a temporary location first
            temp_download_target = archive_path.with_name(f"{archive_path.name}.new")
            download_meta = download_file(target["url"], temp_download_target)
            if download_meta["status"] != "SUCCESS":
                manifest.record_dataset(
                    key,
                    {
                        "competition": target["competition"],
                        "format": target["format"],
                        "tier": target["tier"],
                        "url": target["url"],
                        "archive_filename": target["archive_filename"],
                        "archive_sha256": existing_sha,
                        "previous_archive_sha256": None,
                        "version_changed": False,
                        "archive_size_bytes": archive_path.stat().st_size if archive_path.exists() else 0,
                        "retrieval_timestamp": download_meta["retrieval_timestamp"],
                        "download_status": "DOWNLOAD_FAILED",
                        "extraction_status": "DOWNLOAD_FAILED",
                        "extracted_file_count": 0,
                        "error": download_meta["error"],
                    },
                )
                results[key] = {"status": "DOWNLOAD_FAILED", "error": download_meta["error"]}
                continue

            new_sha = download_meta["sha256"]
            # Check if archive content changed
            if existing_sha and new_sha != existing_sha and archive_path.exists():
                version_changed = True
                backup_name = f"{archive_path.stem}_{existing_sha[:8]}{archive_path.suffix}"
                backup_path = archive_path.with_name(backup_name)
                archive_path.rename(backup_path)
                logger.info("Preserved previous archive as %s", backup_name)

            temp_download_target.replace(archive_path)
            archive_sha256 = new_sha
            archive_size = download_meta["size_bytes"]
            retrieval_ts = download_meta["retrieval_timestamp"]
            download_status = "DOWNLOADED"
        else:
            archive_sha256 = existing_sha or compute_sha256(archive_path)
            archive_size = archive_path.stat().st_size
            retrieval_ts = (
                existing_record.get("retrieval_timestamp")
                if existing_record
                else datetime.now(timezone.utc).isoformat()
            )

        # Validate ZIP
        is_valid, error_msg = validate_zip_archive(archive_path)
        if not is_valid:
            manifest.record_dataset(
                key,
                {
                    "competition": target["competition"],
                    "format": target["format"],
                    "tier": target["tier"],
                    "url": target["url"],
                    "archive_filename": target["archive_filename"],
                    "archive_sha256": archive_sha256,
                    "previous_archive_sha256": previous_sha if version_changed else None,
                    "version_changed": version_changed,
                    "archive_size_bytes": archive_size,
                    "retrieval_timestamp": retrieval_ts,
                    "download_status": download_status,
                    "extraction_status": "ARCHIVE_INVALID",
                    "extracted_file_count": 0,
                    "error": error_msg,
                },
            )
            results[key] = {"status": "ARCHIVE_INVALID", "error": error_msg}
            continue

        # Safe extraction
        try:
            extracted_count = safe_extract_zip(archive_path, extract_dir)
            manifest.record_dataset(
                key,
                {
                    "competition": target["competition"],
                    "format": target["format"],
                    "tier": target["tier"],
                    "url": target["url"],
                    "archive_filename": target["archive_filename"],
                    "archive_sha256": archive_sha256,
                    "previous_archive_sha256": previous_sha if version_changed else None,
                    "version_changed": version_changed,
                    "archive_size_bytes": archive_size,
                    "retrieval_timestamp": retrieval_ts,
                    "extract_subdir": target["extract_subdir"],
                    "download_status": download_status,
                    "extraction_status": "SUCCESS",
                    "extracted_file_count": extracted_count,
                    "reported_match_count": target["reported_match_count"],
                    "error": None,
                },
            )

            results[key] = {
                "status": "SUCCESS",
                "sha256": archive_sha256,
                "size_bytes": archive_size,
                "extracted_count": extracted_count,
            }
        except Exception as exc:  # pylint: disable=broad-except
            manifest.record_dataset(
                key,
                {
                    "competition": target["competition"],
                    "format": target["format"],
                    "tier": target["tier"],
                    "url": target["url"],
                    "archive_filename": target["archive_filename"],
                    "archive_sha256": archive_sha256,
                    "archive_size_bytes": archive_size,
                    "retrieval_timestamp": retrieval_ts,
                    "extraction_status": "EXTRACTION_FAILED",
                    "extracted_file_count": 0,
                    "error": str(exc),
                },
            )
            results[key] = {"status": "EXTRACTION_FAILED", "error": str(exc)}

    # Acquire Approved Registers
    for reg in APPROVED_REGISTERS:
        key = reg["key"]
        reg_path = CRICSHEET_REGISTERS_DIR / reg["filename"]
        need_download = force_redownload or not reg_path.exists()

        if need_download:
            meta = download_file(reg["url"], reg_path)
            if meta["status"] == "SUCCESS":
                manifest.record_register(
                    key,
                    {
                        "filename": reg["filename"],
                        "url": reg["url"],
                        "sha256": meta["sha256"],
                        "size_bytes": meta["size_bytes"],
                        "retrieval_timestamp": meta["retrieval_timestamp"],
                        "status": "SUCCESS",
                        "error": None,
                    },
                )
            else:
                manifest.record_register(
                    key,
                    {
                        "filename": reg["filename"],
                        "url": reg["url"],
                        "sha256": None,
                        "size_bytes": 0,
                        "retrieval_timestamp": meta["retrieval_timestamp"],
                        "status": "DOWNLOAD_FAILED",
                        "error": meta["error"],
                    },
                )
        else:
            sha256 = compute_sha256(reg_path)
            manifest.record_register(
                key,
                {
                    "filename": reg["filename"],
                    "url": reg["url"],
                    "sha256": sha256,
                    "size_bytes": reg_path.stat().st_size,
                    "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "SUCCESS",
                    "error": None,
                },
            )

    return manifest, results


def inspect_dataset_files(extract_dir: Path) -> Dict[str, Any]:
    """
    Perform a complete readability scan of all JSON files in extract_dir.
    Extracts match count, dates, seasons, match IDs, and validates JSON syntax.
    """
    json_files = sorted(extract_dir.glob("*.json"))
    readable_count = 0
    unreadable_count = 0
    invalid_files: List[str] = []
    dates: List[str] = []
    seasons: set[str] = set()
    match_ids: set[str] = set()
    data_versions: set[str] = set()
    teams: set[str] = set()

    for jf in json_files:
        try:
            with open(jf, "r", encoding="utf-8") as f:
                data = json.load(f)

            readable_count += 1
            stem_id = jf.stem
            match_ids.add(stem_id)

            meta = data.get("meta", {})
            if "data_version" in meta:
                data_versions.add(str(meta["data_version"]))

            info = data.get("info", {})
            if "dates" in info and isinstance(info["dates"], list):
                dates.extend(str(d) for d in info["dates"])
            if "season" in info:
                seasons.add(str(info["season"]))
            if "teams" in info and isinstance(info["teams"], list):
                teams.update(info["teams"])

        except Exception as exc:  # pylint: disable=broad-except
            unreadable_count += 1
            invalid_files.append(f"{jf.name}: {exc}")

    dates.sort()
    earliest_date = dates[0] if dates else None
    latest_date = dates[-1] if dates else None

    return {
        "total_files": len(json_files),
        "readable_files": readable_count,
        "unreadable_files": unreadable_count,
        "invalid_files": invalid_files,
        "distinct_match_ids": len(match_ids),
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "seasons_count": len(seasons),
        "seasons_sample": sorted(list(seasons))[:5] + (["..."] if len(seasons) > 5 else []),
        "data_versions": sorted(list(data_versions)),
        "teams_count": len(teams),
    }


def inspect_register_csv(csv_path: Path) -> Dict[str, Any]:
    """Inspect CSV header, total rows, and non-empty columns."""
    if not csv_path.exists():
        return {"exists": False, "row_count": 0, "columns": []}

    row_count = 0
    columns: List[str] = []
    sample_row: Dict[str, str] = {}

    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        for i, row in enumerate(reader):
            row_count += 1
            if i == 0:
                sample_row = dict(row)

    return {
        "exists": True,
        "row_count": row_count,
        "columns": columns,
        "sample_keys": list(sample_row.keys()),
    }
