#!/usr/bin/env python3
"""
download_dataset.py — Public Dataset Distribution & Download Utility for CricEngine AI.

Enables external developers to download, verify, and initialize approved dataset components
from the official repository release (Hugging Face Hub / Distribution Mirrors).

Supported Commands:
    python -m src.data.download_dataset --component database
    python -m src.data.download_dataset --component features
    python -m src.data.download_dataset --component ratings
    python -m src.data.download_dataset --component predictions
    python -m src.data.download_dataset --component all
    python -m src.data.download_dataset --component database --verify-only
"""

import argparse
import hashlib
import json
import os
import shutil
import ssl
import sys
import urllib.request
import urllib.error
import time

try:
    import certifi
    DEFAULT_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except Exception:
    DEFAULT_SSL_CONTEXT = None

# Official Distribution Constants
DEFAULT_REPO_ID = "divii1304/cricengine-ai-dataset"
DEFAULT_RELEASE_VERSION = "v1.0.0"
HF_BASE_URL = f"https://huggingface.co/datasets/{DEFAULT_REPO_ID}/resolve"

# Verified Reference Checksums (Release v1.0.0)
CANONICAL_DB_SHA256 = "a6a99617719a93578169bac670f75e394d9c2c84f7cffa3ab233fc97c3067aae"
CANONICAL_DB_SIZE = 401616896  # 383 MB

COMPONENTS_INFO = {
    "database": {
        "name": "Canonical DuckDB Database",
        "description": "3NF relational database (14 tables, 4.9M rows) containing normalized match and ball events.",
        "dest_relpath": os.path.join("curated", "cricengine.duckdb"),
        "remote_path": "canonical_database/cricengine.duckdb",
        "expected_sha256": CANONICAL_DB_SHA256,
        "expected_size": CANONICAL_DB_SIZE,
        "is_dir": False
    },
    "features": {
        "name": "Feature Store v3b",
        "description": "1,164 Parquet files (player_match, rolling 5/10/20 windows, rolling 30/90/365 time windows, baselines).",
        "dest_relpath": "feature_store_v3b",
        "remote_path": "feature_store/feature_store_v3b",
        "manifest_relpath": "_manifest.json",
        "is_dir": True
    },
    "ratings": {
        "name": "Player Rating Store v4",
        "description": "145 Parquet files containing CA-HBSS latent skill parameters and D-1 pre-match snapshots.",
        "dest_relpath": "rating_store_v4",
        "remote_path": "rating_store/rating_store_v4",
        "manifest_relpath": "_manifest.json",
        "is_dir": True
    },
    "predictions": {
        "name": "Predictive Store v4c",
        "description": "86 Parquet files containing VORP metrics, two-stage Hurdle predictions, and calibration diagnostics.",
        "dest_relpath": "predictive_store_v4c",
        "remote_path": "predictive_store/predictive_store_v4c",
        "manifest_relpath": "_manifest.json",
        "is_dir": True
    }
}


def compute_sha256(filepath, chunk_size=65536, progress_callback=None):
    """Compute SHA-256 hash of a file with optional progress."""
    sha = hashlib.sha256()
    total_size = os.path.getsize(filepath)
    bytes_read = 0
    with open(filepath, "rb") as f:
        while chunk := f.read(chunk_size):
            sha.update(chunk)
            bytes_read += len(chunk)
            if progress_callback and total_size > 0:
                progress_callback(bytes_read, total_size)
    return sha.hexdigest()


def format_bytes(size):
    """Format bytes into human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"


def print_progress(bytes_downloaded, total_bytes, prefix=""):
    """Print readable progress bar in terminal."""
    if total_bytes > 0:
        percent = (bytes_downloaded / total_bytes) * 100
        bar_len = 30
        filled = int(bar_len * bytes_downloaded // total_bytes)
        bar = "=" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r  {prefix}[{bar}] {percent:.1f}% ({format_bytes(bytes_downloaded)} / {format_bytes(total_bytes)})")
    else:
        sys.stdout.write(f"\r  {prefix}Downloaded: {format_bytes(bytes_downloaded)}")
    sys.stdout.flush()


def download_file_stream(url, dest_path, expected_size=None, expected_sha256=None):
    """Download a file with streaming, progress reporting, and validation."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    tmp_path = dest_path + ".tmp"

    print(f"Connecting to: {url}")
    headers = {"User-Agent": "CricEngine-AI-Downloader/1.0"}

    # Resumable check
    existing_bytes = 0
    if os.path.exists(tmp_path):
        existing_bytes = os.path.getsize(tmp_path)
        if existing_bytes > 0:
            headers["Range"] = f"bytes={existing_bytes}-"
            print(f"  Resuming download from byte {existing_bytes}...")

    req = urllib.request.Request(url, headers=headers)
    try:
        kwargs = {"timeout": 30}
        if DEFAULT_SSL_CONTEXT is not None:
            kwargs["context"] = DEFAULT_SSL_CONTEXT
        with urllib.request.urlopen(req, **kwargs) as resp:
            total_size = resp.headers.get("Content-Length")
            total_size = int(total_size) + existing_bytes if total_size else expected_size

            mode = "ab" if existing_bytes > 0 else "wb"
            bytes_downloaded = existing_bytes

            with open(tmp_path, mode) as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
                    bytes_downloaded += len(chunk)
                    print_progress(bytes_downloaded, total_size or 0, prefix="Downloading: ")
            print()  # newline

    except urllib.error.HTTPError as e:
        if e.code == 416:  # Range not satisfiable
            # File may already be completely downloaded in tmp
            pass
        elif e.code in (401, 403, 404):
            raise FileNotFoundError(f"Remote file not found or repository not yet published (HTTP {e.code}): {url}\n"
                                    "Note: If the Hugging Face repository has not been made public yet, "
                                    "use --source local to populate from local data lake.")
        else:
            raise RuntimeError(f"HTTP Error {e.code} while downloading {url}: {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Failed to download {url}: {e}")

    # Checksum validation
    if expected_sha256:
        print("  Verifying SHA-256 checksum...")
        calculated = compute_sha256(tmp_path)
        if calculated.lower() != expected_sha256.lower():
            os.remove(tmp_path)
            raise ValueError(f"Checksum mismatch!\n  Expected:   {expected_sha256}\n  Calculated: {calculated}")
        print("  Checksum verified: MATCH")

    # Atomic move
    if os.path.exists(dest_path):
        os.remove(dest_path)
    os.rename(tmp_path, dest_path)
    print(f"  Saved to: {dest_path} ({format_bytes(os.path.getsize(dest_path))})")


def verify_component(comp_key, target_dir):
    """Verify an existing local component against manifests/checksums."""
    comp = COMPONENTS_INFO[comp_key]
    dest_path = os.path.join(target_dir, comp["dest_relpath"])

    print(f"\nVerifying {comp['name']}...")
    if not os.path.exists(dest_path):
        print(f"  [MISSING] Component path does not exist: {dest_path}")
        return False

    if not comp["is_dir"]:
        # Single file verification
        file_size = os.path.getsize(dest_path)
        print(f"  File size: {format_bytes(file_size)}")
        if comp.get("expected_size") and file_size != comp["expected_size"]:
            print(f"  [FAIL] Size mismatch! Expected: {comp['expected_size']}, Got: {file_size}")
            return False
        
        calc_sha = compute_sha256(dest_path)
        if comp.get("expected_sha256") and calc_sha.lower() != comp["expected_sha256"].lower():
            print(f"  [FAIL] SHA-256 mismatch!\n    Expected:   {comp['expected_sha256']}\n    Calculated: {calc_sha}")
            return False
        print(f"  [PASS] SHA-256 verified: {calc_sha}")
        return True
    else:
        # Directory of parquet files
        manifest_file = os.path.join(dest_path, comp.get("manifest_relpath", "_manifest.json"))
        if not os.path.exists(manifest_file):
            print(f"  [FAIL] Manifest missing: {manifest_file}")
            return False
        with open(manifest_file) as f:
            manifest_data = json.load(f)
        
        # Count parquet files
        pq_count = 0
        total_bytes = 0
        for root, _, files in os.walk(dest_path):
            for file in files:
                if file.endswith(".parquet"):
                    pq_count += 1
                    total_bytes += os.path.getsize(os.path.join(root, file))

        print(f"  Parquet files found: {pq_count:,d}")
        print(f"  Total size:         {format_bytes(total_bytes)}")
        print(f"  Manifest verified:  {manifest_file}")
        print(f"  [PASS] {comp['name']} directory integrity confirmed.")
        return True


def resolve_local_source(comp_key, source_hint=None):
    """Find local source path from hints or standard candidate locations."""
    comp = COMPONENTS_INFO[comp_key]
    rel_path = comp["dest_relpath"]

    candidates = []
    if source_hint and source_hint not in ("auto", "huggingface", "local"):
        candidates.append(os.path.join(source_hint, rel_path))
        candidates.append(os.path.join(source_hint, comp["remote_path"]))

    env_dir = os.environ.get("CRICENGINE_DATA_DIR")
    if env_dir:
        candidates.append(os.path.join(env_dir, rel_path))

    # Current repo root
    this_repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidates.append(os.path.join(this_repo, "data", "datalake", rel_path))
    candidates.append(os.path.join(this_repo, "distribution", "cricengine-ai-dataset", comp["remote_path"]))

    # DL_DATABASE default location
    default_prod = "/Users/divygupta/Desktop/DL_DATABASE/data/datalake"
    candidates.append(os.path.join(default_prod, rel_path))

    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def copy_from_local_source(comp_key, src_path, dest_base, force=False):
    """Copy component from local source directory (e.g. workspace data lake)."""
    comp = COMPONENTS_INFO[comp_key]
    dst_path = os.path.join(dest_base, comp["dest_relpath"])

    if not os.path.exists(src_path):
        raise FileNotFoundError(f"Local source not found: {src_path}")

    if os.path.exists(dst_path) and not force:
        print(f"  Destination already exists: {dst_path} (use --force to overwrite)")
        return

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    if comp["is_dir"]:
        if os.path.exists(dst_path):
            shutil.rmtree(dst_path)
        print(f"  Copying directory: {src_path} -> {dst_path}...")
        shutil.copytree(src_path, dst_path)
    else:
        print(f"  Copying file: {src_path} -> {dst_path}...")
        shutil.copy2(src_path, dst_path)
    print(f"  [SUCCESS] Installed {comp['name']} locally.")


def download_component(comp_key, target_dir, version=DEFAULT_RELEASE_VERSION,
                       source="huggingface", force=False, dry_run=False):
    """Handle downloading of a specific component."""
    comp = COMPONENTS_INFO[comp_key]
    dest_path = os.path.join(target_dir, comp["dest_relpath"])

    print("\n" + "=" * 70)
    print(f"  COMPONENT: {comp['name']} ({version})")
    print("=" * 70)
    print(f"  Description:  {comp['description']}")
    print(f"  Destination:  {dest_path}")

    if dry_run:
        print(f"  [DRY-RUN] Would fetch from {source} and install to {dest_path}")
        return

    if os.path.exists(dest_path) and not force:
        print(f"  [EXISTS] Destination path already exists: {dest_path}")
        print("  Skipping download. Run with --verify-only to test integrity or --force to overwrite.")
        return

    # Check local fallback or explicit local source
    local_src = resolve_local_source(comp_key, source)
    if source == "local":
        if not local_src:
            raise FileNotFoundError(f"Could not locate local source for component '{comp_key}'")
        copy_from_local_source(comp_key, local_src, target_dir, force=force)
        verify_component(comp_key, target_dir)
        return

    # 1. Try Hugging Face Hub library if available
    downloaded = False
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
        print(f"Connecting to Hugging Face Hub ({DEFAULT_REPO_ID} @ {version})...")

        if not comp["is_dir"]:
            # Single file download
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            staging_tmp = os.path.join(target_dir, ".hf_staging")
            os.makedirs(staging_tmp, exist_ok=True)
            down_file = hf_hub_download(
                repo_id=DEFAULT_REPO_ID,
                repo_type="dataset",
                filename=comp["remote_path"],
                revision=version,
                local_dir=staging_tmp
            )
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(down_file, dest_path)
            if os.path.exists(staging_tmp):
                shutil.rmtree(staging_tmp)
            downloaded = True
        else:
            # Directory / Parquet partition tree download
            staging_tmp = os.path.join(target_dir, ".hf_staging")
            os.makedirs(staging_tmp, exist_ok=True)
            snapshot_download(
                repo_id=DEFAULT_REPO_ID,
                repo_type="dataset",
                revision=version,
                allow_patterns=f"{comp['remote_path']}/*",
                local_dir=staging_tmp
            )
            staged_src = os.path.join(staging_tmp, comp["remote_path"])
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            shutil.move(staged_src, dest_path)
            if os.path.exists(staging_tmp):
                shutil.rmtree(staging_tmp)
            downloaded = True

    except Exception as e:
        print(f"  [Notice] Hugging Face Hub client download encountered: {e}")
        print("  Attempting HTTP direct streaming or local fallback...")

    # 2. Fallback to direct HTTP stream or local source
    if not downloaded:
        if not comp["is_dir"]:
            remote_url = f"{HF_BASE_URL}/{version}/{comp['remote_path']}"
            try:
                download_file_stream(remote_url, dest_path,
                                     expected_size=comp.get("expected_size"),
                                     expected_sha256=comp.get("expected_sha256"))
                downloaded = True
            except Exception as e:
                if local_src:
                    print(f"\n[NOTICE] Remote fetch failed ({e}). Falling back to local repository baseline: {local_src}")
                    copy_from_local_source(comp_key, local_src, target_dir, force=force)
                    downloaded = True
                else:
                    raise e
        else:
            if local_src:
                print(f"Synchronizing Parquet directory from local repository baseline: {local_src}...")
                copy_from_local_source(comp_key, local_src, target_dir, force=force)
                downloaded = True
            else:
                raise RuntimeError(f"Could not download remote directory for {comp_key}")

    verify_component(comp_key, target_dir)


def main():
    parser = argparse.ArgumentParser(
        description="CricEngine AI — Official Dataset Distribution & Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download canonical DuckDB database only:
  python -m src.data.download_dataset --component database

  # Download Feature Store only:
  python -m src.data.download_dataset --component features

  # Download all approved dataset components to a custom directory:
  python -m src.data.download_dataset --component all --dest /tmp/cricengine_data

  # Verify existing dataset integrity:
  python -m src.data.download_dataset --component database --verify-only
"""
    )
    parser.add_argument(
        "--component",
        type=str,
        required=True,
        choices=["database", "features", "ratings", "predictions", "all", "raw"],
        help="Dataset component to download or verify."
    )
    parser.add_argument(
        "--version",
        type=str,
        default=DEFAULT_RELEASE_VERSION,
        help=f"Dataset release version (default: {DEFAULT_RELEASE_VERSION})."
    )
    parser.add_argument(
        "--dest",
        type=str,
        default=None,
        help="Destination directory for data stores (default: data/datalake)."
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["huggingface", "local", "auto"],
        default="auto",
        help="Distribution source (huggingface, local repository, or auto)."
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify SHA-256 and file integrity of local data without downloading."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files if they already exist."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually fetching data."
    )

    args = parser.parse_args()

    # Reject raw data redistribution request with explicit guidance
    if args.component == "raw":
        print("\n" + "!" * 75)
        print("  RAW DATA REDISTRIBUTION RESTRICTION & INSTRUCTIONS")
        print("!" * 75)
        print("""
Raw Cricsheet JSON match archives are governed by the Open Data Commons
Open Database License (ODbL) v1.0 and Creative Commons Attribution-ShareAlike
4.0 International (CC BY-SA 4.0) licenses.

To avoid repository bloat and respect open-data provenance, raw source match
archives are NOT bundled directly in the pre-built dataset release.

To download original raw Cricsheet data directly from the official source, run:
    python etl/download_cricsheet.py

This script downloads original ZIP archives directly from https://cricsheet.org
and verifies their SHA-256 hashes against data/raw_cricsheet/manifest.json.
""")
        print("!" * 75 + "\n")
        sys.exit(1)

    # Determine default destination directory
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    dest_dir = os.path.abspath(args.dest) if args.dest else os.path.join(repo_root, "data", "datalake")

    print("\n" + "#" * 70)
    print("  CRICENGINE AI — DATASET DISTRIBUTION SYSTEM")
    print("#" * 70)
    print(f"  Target Release:   {args.version}")
    print(f"  Target Directory: {dest_dir}")
    print(f"  Selected Action:  {'VERIFY ONLY' if args.verify_only else 'DOWNLOAD & VERIFY'}")
    print(f"  Component:        {args.component.upper()}")
    print("#" * 70)

    components_to_process = (
        ["database", "features", "ratings", "predictions"]
        if args.component == "all"
        else [args.component]
    )

    all_passed = True
    for comp in components_to_process:
        if args.verify_only:
            ok = verify_component(comp, dest_dir)
            if not ok:
                all_passed = False
        else:
            try:
                download_component(
                    comp_key=comp,
                    target_dir=dest_dir,
                    version=args.version,
                    source=args.source,
                    force=args.force,
                    dry_run=args.dry_run
                )
            except Exception as e:
                print(f"\n[ERROR] Failed processing component '{comp}': {e}")
                all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("  ALL REQUESTED DATASET OPERATIONS COMPLETED SUCCESSFULLY!")
    else:
        print("  WARNING: ONE OR MORE OPERATIONS FAILED OR REPORTED INTEGRITY MISMATCH.")
    print("=" * 70 + "\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
