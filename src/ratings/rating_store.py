"""
CricEngine AI — Materialized Rating Store Management (Phase 4B)
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from src.ratings.state_model import PlayerRatingState


def sha256_file(filepath: Path) -> str:
    """Computes SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class RatingStore:
    """
    Manages parquet materialization, directory partitioning, and manifest generation
    for data/datalake/rating_store_v4/.
    """

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.current_dir = output_dir / "player_rating_current"
        self.history_dir = output_dir / "player_rating_history"
        self.pre_match_dir = output_dir / "pre_match_snapshots"
        self.metadata_dir = output_dir / "rating_metadata"
        self.audit_dir = output_dir / "audit_records"

        for d in [self.current_dir, self.history_dir, self.pre_match_dir, self.metadata_dir, self.audit_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_current_states(self, states_by_format: Dict[str, List[PlayerRatingState]]) -> Dict[str, int]:
        """
        Saves latest player rating states partitioned by match_format.
        """
        counts = {}
        for fmt, states in states_by_format.items():
            fmt_dir = self.current_dir / f"match_format={fmt.upper()}"
            fmt_dir.mkdir(parents=True, exist_ok=True)
            
            data = [s.to_dict() for s in states]
            df = pd.DataFrame(data)
            
            out_file = fmt_dir / "current_ratings.parquet"
            # Drop match_format from file schema since it is the directory partition
            cols_to_drop = [c for c in ["match_format"] if c in df.columns]
            table = pa.Table.from_pandas(df.drop(columns=cols_to_drop))
            pq.write_table(table, out_file, compression="SNAPPY")
            counts[fmt] = len(df)
            
        return counts

    def save_history_checkpoints(self, history_records: List[Dict[str, Any]]) -> int:
        """
        Saves historical checkpoints partitioned by match_format and year.
        """
        if not history_records:
            return 0
            
        df = pd.DataFrame(history_records)
        df["year"] = df["as_of_date"].str[:4]
        
        total_rows = len(df)
        for (fmt, year), group in df.groupby(["match_format", "year"]):
            part_dir = self.history_dir / f"match_format={fmt.upper()}" / f"year={year}"
            part_dir.mkdir(parents=True, exist_ok=True)
            
            cols_to_drop = [c for c in ["year", "match_format"] if c in group.columns]
            table = pa.Table.from_pandas(group.drop(columns=cols_to_drop))
            pq.write_table(table, part_dir / "history.parquet", compression="SNAPPY")
            
        return total_rows

    def save_pre_match_snapshots(self, snapshot_records: List[Dict[str, Any]]) -> int:
        """
        Saves pre-match snapshots for validation and backtesting.
        """
        if not snapshot_records:
            return 0
            
        df = pd.DataFrame(snapshot_records)
        df["year"] = df["match_date"].str[:4]
        
        for (fmt, year), group in df.groupby(["match_format", "year"]):
            part_dir = self.pre_match_dir / f"match_format={fmt.upper()}" / f"year={year}"
            part_dir.mkdir(parents=True, exist_ok=True)
            
            cols_to_drop = [c for c in ["year", "match_format"] if c in group.columns]
            table = pa.Table.from_pandas(group.drop(columns=cols_to_drop))
            pq.write_table(table, part_dir / "pre_match.parquet", compression="SNAPPY")
            
        return len(df)

    def write_metadata_and_manifest(
        self,
        config: Any,
        input_provenance: Dict[str, Any],
        run_stats: Dict[str, Any],
        audit_records: Dict[str, Any],
    ) -> Path:
        """
        Generates _manifest.json and checksums for the entire rating store.
        """
        # Save audit records
        audit_file = self.audit_dir / "audit_log.json"
        with open(audit_file, "w") as f:
            json.dump(audit_records, f, indent=2)

        # Compute file checksums
        file_manifest = {}
        total_bytes = 0
        total_files = 0
        
        for file in self.output_dir.rglob("*.parquet"):
            rel_path = str(file.relative_to(self.output_dir))
            size = file.stat().st_size
            file_manifest[rel_path] = {
                "sha256": sha256_file(file),
                "bytes": size,
            }
            total_bytes += size
            total_files += 1

        manifest = {
            "rating_engine_version": config.version,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "MATERIALIZED_AND_VERIFIED",
            "total_files": total_files,
            "total_bytes": total_bytes,
            "input_provenance": input_provenance,
            "run_statistics": run_stats,
            "file_checksums": file_manifest,
        }

        manifest_path = self.output_dir / "_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        return manifest_path
