"""
Environment and Infrastructure Smoke Tests

Verifies Python version, critical package imports, DuckDB database creation,
Parquet file serialization/deserialization, and interoperability between
DuckDB, PyArrow, and Pandas.
"""
import sys
from pathlib import Path
import pytest
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pandas as pd
import requests


def test_python_version():
    """Verify runtime is Python 3.12 or higher."""
    assert sys.version_info >= (3, 12), f"Expected Python >= 3.12, got {sys.version}"


def test_core_package_versions():
    """Verify core packages are available with non-empty version strings."""
    assert duckdb.__version__, "DuckDB version missing"
    assert pa.__version__, "PyArrow version missing"
    assert pd.__version__, "Pandas version missing"
    assert requests.__version__, "Requests version missing"
    assert pytest.__version__, "pytest version missing"


def test_duckdb_in_memory_query():
    """Verify DuckDB in-memory query execution."""
    conn = duckdb.connect(":memory:")
    result = conn.execute("SELECT 42 AS answer, 'CricEngine' AS system").fetchall()
    assert result == [(42, "CricEngine")]
    conn.close()


def test_duckdb_parquet_roundtrip(tmp_path: Path):
    """
    Verify DuckDB writing Parquet, reading Parquet back via DuckDB,
    reading via PyArrow, and reading via Pandas.
    """
    parquet_file = tmp_path / "test_deliveries.parquet"

    # 1. Create table in DuckDB and write Parquet
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE sample_deliveries (
            match_id VARCHAR,
            innings INTEGER,
            over_num INTEGER,
            batter VARCHAR,
            bowler VARCHAR,
            runs_batter INTEGER,
            is_wicket BOOLEAN
        )
    """)
    conn.execute("""
        INSERT INTO sample_deliveries VALUES
            ('IND_AUS_2023_01', 1, 0, 'RG Sharma', 'MA Starc', 4, FALSE),
            ('IND_AUS_2023_01', 1, 0, 'RG Sharma', 'MA Starc', 0, FALSE),
            ('IND_AUS_2023_01', 1, 0, 'RG Sharma', 'MA Starc', 6, FALSE),
            ('IND_AUS_2023_01', 1, 1, 'V Kohli', 'JR Hazlewood', 1, FALSE),
            ('IND_AUS_2023_01', 1, 1, 'RG Sharma', 'JR Hazlewood', 0, TRUE)
    """)

    conn.execute(f"COPY sample_deliveries TO '{parquet_file}' (FORMAT PARQUET)")
    assert parquet_file.exists(), "Parquet file was not created"
    assert parquet_file.stat().st_size > 0, "Parquet file is empty"

    # 2. Read back via DuckDB read_parquet
    duckdb_df = conn.execute(f"SELECT * FROM read_parquet('{parquet_file}')").df()
    assert len(duckdb_df) == 5
    assert list(duckdb_df.columns) == [
        "match_id", "innings", "over_num", "batter", "bowler", "runs_batter", "is_wicket"
    ]
    conn.close()

    # 3. Read back via PyArrow
    arrow_table = pq.read_table(str(parquet_file))
    assert arrow_table.num_rows == 5
    assert arrow_table.num_columns == 7
    schema_names = arrow_table.schema.names
    assert "batter" in schema_names
    assert "runs_batter" in schema_names

    # 4. Read back via Pandas
    pandas_df = pd.read_parquet(parquet_file)
    assert len(pandas_df) == 5
    assert pandas_df["runs_batter"].sum() == 11
    assert pandas_df["is_wicket"].sum() == 1


def test_duckdb_persistent_database(tmp_path: Path):
    """Verify DuckDB persistent file creation, insertion, persistence across reconnections."""
    db_file = tmp_path / "cricengine_test.duckdb"

    # Create and write
    conn1 = duckdb.connect(str(db_file))
    conn1.execute("CREATE TABLE dim_player (player_id VARCHAR PRIMARY KEY, full_name VARCHAR)")
    conn1.execute("INSERT INTO dim_player VALUES ('252938a6', 'Virat Kohli'), ('b8a55852', 'Brendon McCullum')")
    conn1.close()

    # Reconnect and verify persistence
    conn2 = duckdb.connect(str(db_file))
    records = conn2.execute("SELECT player_id, full_name FROM dim_player ORDER BY full_name").fetchall()
    assert records == [('b8a55852', 'Brendon McCullum'), ('252938a6', 'Virat Kohli')]
    conn2.close()


def test_config_paths():
    """Verify configuration settings paths exist."""
    from config.settings import (
        BASE_DIR,
        DATA_DIR,
        RAW_CRICSHEET_DIR,
        CRICSHEET_ARCHIVES_DIR,
        CRICSHEET_EXTRACTED_DIR,
        CRICSHEET_REGISTERS_DIR,
        DATALAKE_DIR,
        DATALAKE_RAW_DIR,
        DATALAKE_CURATED_DIR,
        DATALAKE_FEATURE_STORE_DIR,
    )
    assert BASE_DIR.exists()
    assert DATA_DIR.exists()
    assert RAW_CRICSHEET_DIR.exists()
    assert CRICSHEET_ARCHIVES_DIR.exists()
    assert CRICSHEET_EXTRACTED_DIR.exists()
    assert CRICSHEET_REGISTERS_DIR.exists()
    assert DATALAKE_DIR.exists()
    assert DATALAKE_RAW_DIR.exists()
    assert DATALAKE_CURATED_DIR.exists()
    assert DATALAKE_FEATURE_STORE_DIR.exists()

