"""Build demo.db (SQLite) from the synthetic submissions in make_sample_repo.py.

    python make_demo_db.py            # writes demo.db
    python make_demo_db.py --out x.db
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from db_adapter import create_schema, insert_submission
from make_sample_repo import all_submissions


def build(out: Path) -> Path:
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    try:
        create_schema(conn)
        for sub in all_submissions():
            insert_submission(conn, sub)
    finally:
        conn.close()
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the synthetic demo database.")
    ap.add_argument("--out", type=Path, default=Path("demo.db"))
    path = build(ap.parse_args().out)
    print(f"wrote {path}")
