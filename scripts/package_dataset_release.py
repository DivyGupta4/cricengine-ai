#!/usr/bin/env python3
"""
package_dataset_release.py — Packages and Prepares the CricEngine AI Dataset Release.

Creates the official release layout for Hugging Face Hub:
    cricengine-ai-dataset/
        README.md
        dataset_manifest.json
        SHA256SUMS
        canonical_database/
            cricengine.duckdb
        feature_store/
            feature_store_v3b/
        rating_store/
            rating_store_v4/
        predictive_store/
            predictive_store_v4c/
        raw_data/
            README.md
        schemas/
            database_schema.json
            feature_store_schema.json
            rating_store_schema.json
            predictive_store_schema.json
        documentation/
            DATA_DICTIONARY.md
            DATASET_CARD.md
            DATA_LINEAGE.md
            KNOWN_LIMITATIONS.md
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_OUT_DIR = os.path.join(PROJECT_ROOT, "distribution", "cricengine-ai-dataset")


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def copy_or_link(src, dst, use_hardlink=True):
    """Copy or hardlink a file/directory to preserve disk space."""
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src)
            target_dir = os.path.join(dst, rel)
            os.makedirs(target_dir, exist_ok=True)
            for f in files:
                s_file = os.path.join(root, f)
                d_file = os.path.join(target_dir, f)
                if os.path.exists(d_file):
                    os.remove(d_file)
                try:
                    if use_hardlink:
                        os.link(s_file, d_file)
                    else:
                        shutil.copy2(s_file, d_file)
                except Exception:
                    shutil.copy2(s_file, d_file)
    else:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            os.remove(dst)
        try:
            if use_hardlink:
                os.link(src, dst)
            else:
                shutil.copy2(src, dst)
        except Exception:
            shutil.copy2(src, dst)


def build_release_package(output_dir, copy_mode=False):
    """Assemble the complete dataset release tree."""
    print("\n" + "=" * 70)
    print(f"  BUILDING DATASET RELEASE BUNDLE (v1.0.0)")
    print("=" * 70)
    print(f"  Target Destination: {output_dir}")
    print(f"  Mode:               {'Copy' if copy_mode else 'Hardlink (Zero-Storage Duplication)'}")
    print("-" * 70)

    os.makedirs(output_dir, exist_ok=True)

    # 1. Root Readme (Dataset Card)
    print("[1/8] Installing Dataset Card (README.md)...")
    shutil.copy2(os.path.join(PROJECT_ROOT, "DATASET_CARD.md"), os.path.join(output_dir, "README.md"))

    # 2. Manifest and Checksums
    print("[2/8] Installing manifests and SHA256SUMS...")
    shutil.copy2(os.path.join(PROJECT_ROOT, "dataset_manifest.json"), os.path.join(output_dir, "dataset_manifest.json"))
    shutil.copy2(os.path.join(PROJECT_ROOT, "SHA256SUMS"), os.path.join(output_dir, "SHA256SUMS"))

    # 3. Canonical Database
    print("[3/8] Linking Canonical DuckDB database (cricengine.duckdb)...")
    db_src = os.path.join(PROJECT_ROOT, "data", "datalake", "curated", "cricengine.duckdb")
    db_dst = os.path.join(output_dir, "canonical_database", "cricengine.duckdb")
    copy_or_link(db_src, db_dst, use_hardlink=not copy_mode)

    # 4. Feature Store
    print("[4/8] Linking Feature Store v3b (1,164 Parquet files)...")
    fs_src = os.path.join(PROJECT_ROOT, "data", "datalake", "feature_store_v3b")
    fs_dst = os.path.join(output_dir, "feature_store", "feature_store_v3b")
    copy_or_link(fs_src, fs_dst, use_hardlink=not copy_mode)

    # 5. Rating Store
    print("[5/8] Linking Rating Store v4 (145 Parquet files)...")
    rs_src = os.path.join(PROJECT_ROOT, "data", "datalake", "rating_store_v4")
    rs_dst = os.path.join(output_dir, "rating_store", "rating_store_v4")
    copy_or_link(rs_src, rs_dst, use_hardlink=not copy_mode)

    # 6. Predictive Store
    print("[6/8] Linking Predictive Store v4c (86 Parquet files)...")
    ps_src = os.path.join(PROJECT_ROOT, "data", "datalake", "predictive_store_v4c")
    ps_dst = os.path.join(output_dir, "predictive_store", "predictive_store_v4c")
    copy_or_link(ps_src, ps_dst, use_hardlink=not copy_mode)

    # 7. Raw Data Notice
    print("[7/8] Installing raw data acquisition instructions...")
    raw_dir = os.path.join(output_dir, "raw_data")
    os.makedirs(raw_dir, exist_ok=True)
    with open(os.path.join(raw_dir, "README.md"), "w") as f:
        f.write("""# Raw Cricsheet Data Acquisition

Raw match archives are governed by the Open Data Commons Open Database License (ODbL) v1.0 and CC BY-SA 4.0.
To respect source provenance and avoid distribution bloat, raw JSON archives are not bundled directly.

To download original raw Cricsheet data directly from the official source, run from the repository root:
    python etl/download_cricsheet.py

Source: https://cricsheet.org
""")

    # 8. Schemas and Documentation
    print("[8/8] Installing Schemas and Technical Documentation...")
    schemas_dst = os.path.join(output_dir, "schemas")
    os.makedirs(schemas_dst, exist_ok=True)
    for s_file in os.listdir(os.path.join(PROJECT_ROOT, "schemas")):
        if s_file.endswith(".json"):
            shutil.copy2(os.path.join(PROJECT_ROOT, "schemas", s_file), os.path.join(schemas_dst, s_file))

    doc_dst = os.path.join(output_dir, "documentation")
    os.makedirs(doc_dst, exist_ok=True)
    for doc in ["DATA_DICTIONARY.md", "DATASET_CARD.md", "DATA_LINEAGE.md", "KNOWN_LIMITATIONS.md"]:
        shutil.copy2(os.path.join(PROJECT_ROOT, doc), os.path.join(doc_dst, doc))

    print("-" * 70)
    print("  [SUCCESS] Release bundle assembled successfully at:")
    print(f"  {output_dir}")
    print("=" * 70 + "\n")


def check_hf_auth():
    """Check whether Hugging Face CLI is authenticated."""
    try:
        res = subprocess.run(["hf", "auth", "whoami"], capture_output=True, text=True)
        if res.returncode == 0 and "Not logged in" not in res.stderr and "Not logged in" not in res.stdout:
            return True, res.stdout.strip()
    except Exception:
        pass
    return False, None


def upload_to_huggingface(release_dir, repo_id="cricengine-ai/cricengine-ai-dataset"):
    """Upload release directory to Hugging Face Hub."""
    is_auth, user = check_hf_auth()
    if not is_auth:
        print("\n" + "!" * 70)
        print("  HUGGING FACE AUTHENTICATION REQUIRED FOR REMOTE UPLOAD")
        print("!" * 70)
        print("""
Your Hugging Face CLI is not currently authenticated.
To upload the prepared dataset release, follow these steps:

1. Obtain a Write Access Token from:
   https://huggingface.co/settings/tokens

2. Log in from your terminal:
   hf auth login

3. Upload the prepared dataset bundle:
   hf upload cricengine-ai/cricengine-ai-dataset ./distribution/cricengine-ai-dataset . --repo-type dataset

The release bundle has been fully assembled, verified, and staged locally at:
   ./distribution/cricengine-ai-dataset
""")
        print("!" * 70 + "\n")
        return False

    print(f"\nAuthenticated as Hugging Face user: {user}")
    print(f"Uploading {release_dir} to {repo_id}...")
    cmd = ["hf", "upload", repo_id, release_dir, ".", "--repo-type", "dataset"]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"\n[SUCCESS] Upload complete! View dataset at: https://huggingface.co/datasets/{repo_id}")
        return True
    else:
        print(f"\n[ERROR] Upload failed with exit code {res.returncode}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Package CricEngine AI Dataset Release (v1.0.0)")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_OUT_DIR, help="Output staging directory")
    parser.add_argument("--copy", action="store_true", help="Copy files instead of hardlinking")
    parser.add_argument("--upload", action="store_true", help="Attempt upload to Hugging Face Hub after assembly")
    parser.add_argument("--repo-id", type=str, default="cricengine-ai/cricengine-ai-dataset", help="Target Hugging Face Hub repo")
    args = parser.parse_args()

    build_release_package(args.out_dir, copy_mode=args.copy)

    if args.upload:
        upload_to_huggingface(args.out_dir, repo_id=args.repo_id)


if __name__ == "__main__":
    main()
