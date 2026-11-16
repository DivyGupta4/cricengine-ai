#!/usr/bin/env python3
"""
explore_database.py — Interactive and Scriptable DuckDB Database Explorer for CricEngine AI.

Designed for professor demonstration and dataset inspection.
Strictly read-only access to canonical data.
"""

import os
import sys
import argparse

# Ensure soft limit on open file descriptors is increased on macOS
try:
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft < 4096:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, hard), hard))
except Exception:
    pass

try:
    import duckdb
except ImportError:
    print("[ERROR] duckdb is not installed in the active Python environment.")
    print("Please run this script using the project's virtual environment:")
    print("    .venv/bin/python professor_demo/explore_database.py")
    sys.exit(1)


def find_database_path():
    """Locate the canonical database path reliably."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, ".."))
    
    candidates = [
        os.path.join(project_root, "data", "datalake", "curated", "cricengine.duckdb"),
        os.path.join(os.getcwd(), "data", "datalake", "curated", "cricengine.duckdb"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_read_only_connection(db_path):
    """Open DuckDB strictly in read-only mode."""
    try:
        return duckdb.connect(database=db_path, read_only=True)
    except Exception as e:
        print(f"[FATAL] Failed to open DuckDB database in read-only mode: {e}")
        sys.exit(1)


def get_tables(conn):
    """Retrieve all table names in main schema."""
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


def show_table_counts(conn):
    """Display all tables and exact row counts."""
    tables = get_tables(conn)
    print("\n" + "=" * 70)
    print("  CANONICAL DUCKDB DATABASE: TABLE INVENTORY & ROW COUNTS")
    print("=" * 70)
    print(f" {'#':<3} | {'Table Name':<32} | {'Row Count':>15} | {'Type':<10}")
    print("-" * 70)
    total_rows = 0
    for idx, table in enumerate(tables, 1):
        count = conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        total_rows += count
        tbl_type = "Dimension" if table.startswith("dim_") else ("Fact" if table.startswith("fact_") else "Metadata/Audit")
        print(f" {idx:<3} | {table:<32} | {count:>15,d} | {tbl_type:<10}")
    print("-" * 70)
    print(f" Total Tables: {len(tables)} | Total Rows: {total_rows:,d}")
    print("=" * 70 + "\n")


def show_schema(conn, table_name):
    """Show detailed schema for a table."""
    tables = get_tables(conn)
    if table_name not in tables:
        print(f"[ERROR] Table '{table_name}' does not exist.")
        print(f"Available tables: {', '.join(tables)}")
        return

    columns = conn.execute(f'DESCRIBE "{table_name}"').fetchall()
    print("\n" + "=" * 70)
    print(f"  SCHEMA: {table_name}")
    print("=" * 70)
    print(f" {'#':<3} | {'Column Name':<30} | {'Data Type':<16} | {'Null?':<6}")
    print("-" * 70)
    for idx, col in enumerate(columns, 1):
        cname, ctype, cnull = col[0], col[1], col[2]
        print(f" {idx:<3} | {cname:<30} | {ctype:<16} | {str(cnull):<6}")
    print("=" * 70 + "\n")


def sample_table(conn, table_name, limit=5):
    """Display sample rows from a table."""
    tables = get_tables(conn)
    if table_name not in tables:
        print(f"[ERROR] Table '{table_name}' does not exist.")
        print(f"Available tables: {', '.join(tables)}")
        return

    print("\n" + "=" * 70)
    print(f"  SAMPLE RECORDS: {table_name} (LIMIT {limit})")
    print("=" * 70)
    df = conn.execute(f'SELECT * FROM "{table_name}" LIMIT {limit}').df()
    print(df.to_string(index=False))
    print("=" * 70 + "\n")


EXAMPLE_QUERIES = [
    {
        "name": "Match Overview & Result (Match 1389392: IND vs AUS)",
        "sql": """
SELECT 
    m.match_id,
    m.competition_name,
    m.match_format,
    m.season,
    m.start_date,
    m.team_1,
    m.team_2,
    c.venue_name,
    c.outcome_winner,
    c.win_by_type,
    c.win_by_margin
FROM dim_match m
JOIN dim_match_context c ON m.match_id = c.match_id
WHERE m.match_id = '1389392';
"""
    },
    {
        "name": "Ball-by-Ball First Over Deliveries (Match 1389392)",
        "sql": """
SELECT 
    b.innings_num,
    b.over_num,
    b.delivery_num,
    bat.canonical_name AS batter,
    bowl.canonical_name AS bowler,
    b.runs_batter,
    b.runs_extras,
    b.runs_total,
    b.is_wicket
FROM fact_ball_by_ball b
JOIN dim_player_master bat ON b.batter_id = bat.player_id
JOIN dim_player_master bowl ON b.bowler_id = bowl.player_id
WHERE b.match_id = '1389392' AND b.innings_num = 1 AND b.over_num = 0
ORDER BY b.delivery_num;
"""
    },
    {
        "name": "Match Participation & Starting XI (Match 1389392)",
        "sql": """
SELECT 
    p.team_name,
    pm.canonical_name AS player_name,
    p.participation_role,
    p.in_starting_xi,
    p.batted_flag,
    p.bowled_flag,
    p.fielded_flag
FROM fact_match_participation p
JOIN dim_player_master pm ON p.player_id = pm.player_id
WHERE p.match_id = '1389392'
ORDER BY p.team_name, pm.canonical_name
LIMIT 12;
"""
    },
    {
        "name": "Dismissal Breakdown with Bowler & Fielder Attribution",
        "sql": """
SELECT 
    d.innings_num,
    out_p.canonical_name AS player_out,
    d.dismissal_kind,
    bowl_p.canonical_name AS bowler,
    COALESCE(f_p.canonical_name, 'None / Unassisted') AS fielder
FROM fact_delivery_dismissal d
JOIN dim_player_master out_p ON d.player_out_id = out_p.player_id
JOIN fact_ball_by_ball b ON d.ball_id = b.ball_id
JOIN dim_player_master bowl_p ON b.bowler_id = bowl_p.player_id
LEFT JOIN fact_dismissal_fielder f ON d.dismissal_id = f.dismissal_id
LEFT JOIN dim_player_master f_p ON f.fielder_id = f_p.player_id
WHERE d.match_id = '1389392'
ORDER BY d.innings_num, d.dismissal_seq
LIMIT 10;
"""
    },
    {
        "name": "Top All-Time Run Scorers in Curated Database",
        "sql": """
SELECT 
    pm.canonical_name,
    COUNT(DISTINCT b.match_id) AS matches_batted,
    SUM(b.runs_batter) AS total_runs,
    COUNT(CASE WHEN b.is_legal_delivery THEN 1 END) AS balls_faced,
    ROUND(SUM(b.runs_batter) * 100.0 / NULLIF(COUNT(CASE WHEN b.is_legal_delivery THEN 1 END), 0), 2) AS career_strike_rate
FROM fact_ball_by_ball b
JOIN dim_player_master pm ON b.batter_id = pm.player_id
GROUP BY pm.canonical_name
HAVING total_runs > 4000
ORDER BY total_runs DESC
LIMIT 10;
"""
    },
    {
        "name": "Top All-Time Wicket Takers in Curated Database",
        "sql": """
SELECT 
    pm.canonical_name,
    COUNT(DISTINCT b.match_id) AS matches_bowled,
    COUNT(d.dismissal_id) AS total_wickets,
    ROUND(SUM(b.runs_total) * 6.0 / NULLIF(COUNT(CASE WHEN b.is_legal_delivery THEN 1 END), 0), 2) AS career_economy
FROM fact_ball_by_ball b
JOIN dim_player_master pm ON b.bowler_id = pm.player_id
LEFT JOIN fact_delivery_dismissal d ON b.ball_id = d.ball_id AND d.bowler_credited = TRUE
GROUP BY pm.canonical_name
HAVING total_wickets > 150
ORDER BY total_wickets DESC
LIMIT 10;
"""
    }
]


def run_example_queries(conn, index=None):
    """Execute pre-built verified queries."""
    if index is not None:
        if 1 <= index <= len(EXAMPLE_QUERIES):
            queries = [EXAMPLE_QUERIES[index - 1]]
        else:
            print(f"[ERROR] Invalid query index. Choose 1 to {len(EXAMPLE_QUERIES)}.")
            return
    else:
        queries = EXAMPLE_QUERIES

    for idx, q in enumerate(queries, 1):
        print("\n" + "=" * 70)
        print(f"  EXAMPLE QUERY {idx if index is None else index}: {q['name']}")
        print("=" * 70)
        print(q["sql"].strip())
        print("-" * 70)
        df = conn.execute(q["sql"]).df()
        print(df.to_string(index=False))
        print("=" * 70 + "\n")


def execute_custom_query(conn, query_str):
    """Execute arbitrary SQL in read-only mode."""
    print("\n" + "=" * 70)
    print("  EXECUTING QUERY (READ-ONLY)")
    print("=" * 70)
    print(query_str.strip())
    print("-" * 70)
    try:
        df = conn.execute(query_str).df()
        print(df.to_string(index=False))
        print(f"\n({len(df)} rows returned)")
    except Exception as e:
        print(f"[ERROR] Query execution failed: {e}")
    print("=" * 70 + "\n")


def interactive_menu(conn):
    """Display interactive CLI menu."""
    tables = get_tables(conn)
    while True:
        print("\n" + "#" * 50)
        print("   CRICENGINE DUCKDB EXPLORER (READ-ONLY)")
        print("#" * 50)
        print("  [1] List all 14 tables and exact row counts")
        print("  [2] View table schema")
        print("  [3] View sample records from a table")
        print("  [4] Run pre-verified example queries (1-6)")
        print("  [5] Execute custom read-only SQL query")
        print("  [0] Exit")
        print("#" * 50)
        
        choice = input("Enter choice (0-5): ").strip()
        if choice == "0":
            print("\nExiting. Good luck with your demonstration!\n")
            break
        elif choice == "1":
            show_table_counts(conn)
        elif choice == "2":
            print("\nAvailable tables:")
            for i, t in enumerate(tables, 1):
                print(f"  {i}. {t}")
            t_choice = input("Enter table name or number: ").strip()
            if t_choice.isdigit() and 1 <= int(t_choice) <= len(tables):
                t_name = tables[int(t_choice) - 1]
            else:
                t_name = t_choice
            show_schema(conn, t_name)
        elif choice == "3":
            print("\nAvailable tables:")
            for i, t in enumerate(tables, 1):
                print(f"  {i}. {t}")
            t_choice = input("Enter table name or number: ").strip()
            if t_choice.isdigit() and 1 <= int(t_choice) <= len(tables):
                t_name = tables[int(t_choice) - 1]
            else:
                t_name = t_choice
            lim = input("Enter number of rows to sample [default 5]: ").strip()
            limit = int(lim) if lim.isdigit() else 5
            sample_table(conn, t_name, limit)
        elif choice == "4":
            print("\nAvailable Example Queries:")
            for i, q in enumerate(EXAMPLE_QUERIES, 1):
                print(f"  [{i}] {q['name']}")
            print("  [A] Run All Queries")
            q_choice = input("Select query (1-6 or A): ").strip().upper()
            if q_choice == "A":
                run_example_queries(conn)
            elif q_choice.isdigit():
                run_example_queries(conn, int(q_choice))
        elif choice == "5":
            print("\nEnter SQL query (type ';' and press Enter to execute):")
            lines = []
            while True:
                line = input()
                lines.append(line)
                if ";" in line:
                    break
            execute_custom_query(conn, "\n".join(lines))
        else:
            print("[!] Invalid selection. Please choose an option from the menu.")


def main():
    parser = argparse.ArgumentParser(description="CricEngine AI - DuckDB Database Explorer (Read-Only)")
    parser.add_argument("--list", action="store_true", help="List all tables and row counts")
    parser.add_argument("--schema", type=str, help="Show schema of specified table")
    parser.add_argument("--sample", type=str, help="Sample records from specified table")
    parser.add_argument("--limit", type=int, default=5, help="Sample limit (default: 5)")
    parser.add_argument("--example", type=int, help="Run specific example query (1 to 6)")
    parser.add_argument("--examples-all", action="store_true", help="Run all example queries")
    parser.add_argument("--query", type=str, help="Run custom read-only SQL query")
    args = parser.parse_args()

    db_path = find_database_path()
    if not db_path:
        print("[FATAL] Could not find cricengine.duckdb at data/datalake/curated/cricengine.duckdb")
        sys.exit(1)

    conn = get_read_only_connection(db_path)

    # If flags passed, run non-interactively
    if args.list:
        show_table_counts(conn)
    elif args.schema:
        show_schema(conn, args.schema)
    elif args.sample:
        sample_table(conn, args.sample, args.limit)
    elif args.example:
        run_example_queries(conn, args.example)
    elif args.examples_all:
        run_example_queries(conn)
    elif args.query:
        execute_custom_query(conn, args.query)
    else:
        # If no flags passed and interactive terminal
        if sys.stdin.isatty():
            interactive_menu(conn)
        else:
            show_table_counts(conn)

    conn.close()


if __name__ == "__main__":
    main()
