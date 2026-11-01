"""
CricEngine AI Configuration Settings
"""
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_CRICSHEET_DIR = DATA_DIR / "raw_cricsheet"
DATALAKE_DIR = DATA_DIR / "datalake"

# Raw Cricsheet Ingestion Subdirectories
CRICSHEET_ARCHIVES_DIR = RAW_CRICSHEET_DIR / "archives"
CRICSHEET_EXTRACTED_DIR = RAW_CRICSHEET_DIR / "extracted"
CRICSHEET_REGISTERS_DIR = RAW_CRICSHEET_DIR / "registers"
MANIFEST_PATH = RAW_CRICSHEET_DIR / "manifest.json"

# Datalake Tier Paths
DATALAKE_RAW_DIR = DATALAKE_DIR / "raw"
DATALAKE_CURATED_DIR = DATALAKE_DIR / "curated"
DATALAKE_FEATURE_STORE_DIR = DATALAKE_DIR / "feature_store"

# Database Configuration
DUCKDB_PATH = DATALAKE_CURATED_DIR / "cricengine.duckdb"

# Ensure runtime directories exist
for path in [
    RAW_CRICSHEET_DIR,
    CRICSHEET_ARCHIVES_DIR,
    CRICSHEET_EXTRACTED_DIR,
    CRICSHEET_REGISTERS_DIR,
    DATALAKE_RAW_DIR,
    DATALAKE_CURATED_DIR,
    DATALAKE_FEATURE_STORE_DIR,
]:
    path.mkdir(parents=True, exist_ok=True)

