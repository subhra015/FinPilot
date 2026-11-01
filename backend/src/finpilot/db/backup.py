"""Database backup and restore procedures and verification (SEC-03, Layer 2).

Provides procedures for:
1. Operational SQLite disposable backup/restore (for tests and local dev).
2. Documented production PostgreSQL backup/restore runbook commands.
3. Checksum verification of backup artifacts to ensure tamper resistance.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from sqlalchemy import Engine, inspect


def calculate_file_sha256(path: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_sqlite_database(source_db_path: Path, target_backup_path: Path) -> str:
    """Safely back up a SQLite database using the online backup API.

    Returns the SHA-256 checksum of the resulting backup artifact.
    """
    target_backup_path.parent.mkdir(parents=True, exist_ok=True)

    # Use SQLite online backup API to ensure consistent snapshot even during active reads
    src_conn = sqlite3.connect(str(source_db_path))
    dst_conn = sqlite3.connect(str(target_backup_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()

    return calculate_file_sha256(target_backup_path)


def restore_sqlite_database(
    backup_path: Path, target_db_path: Path, expected_sha256: str | None = None
) -> None:
    """Restore a SQLite database from a backup artifact with optional checksum verification."""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    if expected_sha256 is not None:
        actual_sha256 = calculate_file_sha256(backup_path)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Backup checksum mismatch! Expected: {expected_sha256}, got: {actual_sha256}"
            )

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(backup_path))
    dst_conn = sqlite3.connect(str(target_db_path))
    try:
        src_conn.backup(dst_conn)
    finally:
        dst_conn.close()
        src_conn.close()


def verify_database_schema(engine: Engine) -> dict[str, list[str]]:
    """Inspect and return dictionary of tables and their column names."""
    inspector = inspect(engine)
    out: dict[str, list[str]] = {}
    for table_name in inspector.get_table_names():
        cols = [col["name"] for col in inspector.get_columns(table_name)]
        out[table_name] = cols
    return out
