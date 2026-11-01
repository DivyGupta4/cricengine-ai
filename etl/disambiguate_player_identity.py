"""
CricEngine AI — Phase 3A: Player Identity Disambiguation Engine
Resolves PID-01 and PID-03.

Enriches player_source_identity with authoritative external registry keys
from registers/people.csv (unique_name, key_cricinfo, key_bcci), identifies
all 71 display-name collisions (152 rows), assigns 4-tier confidence status
(VERIFIED, PROBABLE, AMBIGUOUS, UNRESOLVED), and outputs versioned artifacts.
"""
from __future__ import annotations

import json
from pathlib import Path
import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def disambiguate_player_identities(
    db_path: Path = Path("data/datalake/curated/cricengine.duckdb"),
    people_csv_path: Path = Path("data/raw_cricsheet/registers/people.csv"),
    output_meta_dir: Path = Path("data/datalake/metadata"),
) -> pd.DataFrame:
    """Extract and disambiguate all player identity mappings."""
    output_meta_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read curated source mappings (Strictly READ-ONLY)
    conn = duckdb.connect(str(db_path), read_only=True)
    psi_df = conn.execute("""
        SELECT 
            identity_mapping_id,
            player_id,
            source_system,
            source_identifier,
            confidence_status AS raw_confidence_status
        FROM player_source_identity
        ORDER BY source_identifier, player_id
    """).df()
    conn.close()

    # 2. Read authoritative people.csv registry
    people_df = pd.read_csv(people_csv_path, dtype=str)

    # 3. Merge authoritative keys
    merged = psi_df.merge(
        people_df[["identifier", "unique_name", "key_cricinfo", "key_bcci"]],
        left_on="player_id",
        right_on="identifier",
        how="left"
    )

    # 4. Identify colliding source_identifier display names
    collision_counts = psi_df.groupby("source_identifier")["player_id"].nunique()
    colliding_names = set(collision_counts[collision_counts > 1].index)

    # 5. Assign 4-tier confidence status and explanatory evidence notes
    statuses = []
    notes = []
    for _, row in merged.iterrows():
        s_id = row["source_identifier"]
        p_id = row["player_id"]
        u_name = row["unique_name"]
        cricinfo_id = row["key_cricinfo"]
        bcci_id = row["key_bcci"]

        if s_id in colliding_names:
            statuses.append("AMBIGUOUS")
            notes.append(
                f"Display name string '{s_id}' collides with {collision_counts[s_id]} distinct canonical cricketers. "
                f"Disambiguated as '{u_name}' via Cricsheet ID {p_id} and Cricinfo ID {cricinfo_id}."
            )
        elif pd.notna(u_name) and pd.notna(cricinfo_id):
            statuses.append("VERIFIED")
            notes.append(f"Authoritatively verified via ESPNcricinfo ID {cricinfo_id} and unique_name '{u_name}'.")
        elif pd.notna(u_name):
            statuses.append("PROBABLE")
            notes.append(f"Unique registry entry '{u_name}' verified in people.csv; external key_cricinfo absent.")
        else:
            statuses.append("UNRESOLVED")
            notes.append("No authoritative registry match found in people.csv.")

    merged["confidence_status"] = statuses
    merged["disambiguation_notes"] = notes

    # Clean schema
    output_cols = [
        "identity_mapping_id",
        "player_id",
        "source_system",
        "source_identifier",
        "unique_name",
        "key_cricinfo",
        "key_bcci",
        "confidence_status",
        "disambiguation_notes"
    ]
    df_clean = merged[output_cols].copy()

    # 6. Save Parquet and CSV artifacts in data/datalake/metadata
    parquet_path = output_meta_dir / "player_identity_disambiguation.parquet"
    csv_path = output_meta_dir / "player_identity_disambiguation.csv"
    
    table = pa.Table.from_pandas(df_clean)
    pq.write_table(table, parquet_path, compression="SNAPPY")
    df_clean.to_csv(csv_path, index=False)

    # 7. Generate Collision Report JSON
    collision_report = {
        "report_name": "CricEngine AI — Player Display Name Collision Report",
        "total_mappings": len(df_clean),
        "total_colliding_names": len(colliding_names),
        "total_affected_rows": len(df_clean[df_clean["confidence_status"] == "AMBIGUOUS"]),
        "status_distribution": df_clean["confidence_status"].value_counts().to_dict(),
        "collisions": {}
    }

    for name in sorted(colliding_names):
        subset = df_clean[df_clean["source_identifier"] == name]
        collision_report["collisions"][name] = {
            "candidate_count": len(subset),
            "candidates": [
                {
                    "player_id": r["player_id"],
                    "unique_name": r["unique_name"],
                    "key_cricinfo": r["key_cricinfo"] if pd.notna(r["key_cricinfo"]) else None,
                    "key_bcci": r["key_bcci"] if pd.notna(r["key_bcci"]) else None,
                    "identity_mapping_id": r["identity_mapping_id"]
                }
                for _, r in subset.iterrows()
            ]
        }

    json_path = output_meta_dir / "player_identity_collisions.json"
    with open(json_path, "w") as fp:
        json.dump(collision_report, fp, indent=2)

    return df_clean


if __name__ == "__main__":
    df = disambiguate_player_identities()
    print("Disambiguation complete. Total rows:", len(df))
    print(df["confidence_status"].value_counts())
