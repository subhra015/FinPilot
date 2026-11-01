"""Least-privilege database role and permission tests (SEC-03, Layer 2).

Validates:
- Separate migration/administrative role (finpilot_admin) vs runtime role (finpilot_app).
- Runtime role is not superuser, not schema owner, and prohibited from DDL (CREATE/ALTER/DROP).
- Runtime role possesses necessary DML privileges (SELECT, INSERT, UPDATE, DELETE).
- Migration table protection against runtime tampering.
- Functional authorizer test enforcing the privilege boundary.
"""

from __future__ import annotations

import sqlite3

import pytest

from finpilot.db import (
    ADMIN_ROLE,
    APP_ROLE,
    generate_role_setup_script,
)


def test_postgresql_role_script_structure_and_least_privilege() -> None:
    script = generate_role_setup_script()

    # 1. Admin role creation and privileges
    assert f"CREATE ROLE {ADMIN_ROLE}" in script
    assert f"ALTER SCHEMA public OWNER TO {ADMIN_ROLE}" in script
    assert f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {ADMIN_ROLE}" in script
    assert f"GRANT CREATE ON SCHEMA public TO {ADMIN_ROLE}" in script

    # 2. Runtime app role restrictions (SEC-03)
    assert f"CREATE ROLE {APP_ROLE}" in script
    assert f"ALTER ROLE {APP_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT" in script
    assert f"REVOKE CREATE ON SCHEMA public FROM {APP_ROLE}" in script

    # 3. DML-only privileges for runtime app role
    assert (
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
        in script
    )
    assert f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}" in script

    # 4. Protection for migration tracking tables
    assert f"REVOKE INSERT, UPDATE, DELETE ON TABLE alembic_version FROM {APP_ROLE}" in script
    assert f"REVOKE INSERT, UPDATE, DELETE ON TABLE schema_meta FROM {APP_ROLE}" in script


def _app_role_authorizer(
    action_code: int,
    arg1: str | None,
    arg2: str | None,
    db_name: str | None,
    trigger_or_view: str | None,
) -> int:
    """Enforces runtime least-privilege boundary: DML allowed, DDL (CREATE/DROP/ALTER) denied."""
    # SQLite action codes:
    # SQLITE_CREATE_TABLE = 2, SQLITE_DROP_TABLE = 11, SQLITE_ALTER_TABLE = 26
    # SQLITE_INSERT = 18, SQLITE_UPDATE = 23, SQLITE_DELETE = 9, SQLITE_SELECT = 21
    denied_ddl_actions = {
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_ALTER_TABLE,
    }
    if action_code in denied_ddl_actions:
        return sqlite3.SQLITE_DENY  # Access denied for runtime role
    return sqlite3.SQLITE_OK


def test_least_privilege_role_permission_boundary() -> None:
    """Functional test demonstrating restricted runtime permissions vs admin."""
    # 1. Admin setup: creates schema and tables
    raw_conn = sqlite3.connect(":memory:")
    # Admin runs DDL successfully
    raw_conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
    raw_conn.execute("INSERT INTO test_data (value) VALUES ('admin_init')")
    raw_conn.commit()

    # 2. Switch connection to simulate runtime unprivileged application role
    raw_conn.set_authorizer(_app_role_authorizer)

    # Runtime can perform DML: SELECT
    cursor = raw_conn.cursor()
    cursor.execute("SELECT value FROM test_data WHERE id = 1")
    row = cursor.fetchone()
    assert row[0] == "admin_init"

    # Runtime can perform DML: INSERT
    cursor.execute("INSERT INTO test_data (value) VALUES ('app_runtime_val')")
    raw_conn.commit()

    # Runtime can perform DML: UPDATE
    cursor.execute("UPDATE test_data SET value = 'updated_val' WHERE id = 1")
    raw_conn.commit()

    # Runtime ATTEMPTS DDL: CREATE TABLE -> MUST FAIL with not authorized
    with pytest.raises(sqlite3.DatabaseError) as exc_create:
        cursor.execute("CREATE TABLE rogue_table (id INT)")
    assert "not authorized" in str(exc_create.value).lower()

    # Runtime ATTEMPTS DDL: DROP TABLE -> MUST FAIL with not authorized
    with pytest.raises(sqlite3.DatabaseError) as exc_drop:
        cursor.execute("DROP TABLE test_data")
    assert "not authorized" in str(exc_drop.value).lower()

    # Runtime ATTEMPTS DDL: ALTER TABLE -> MUST FAIL with not authorized
    with pytest.raises(sqlite3.DatabaseError) as exc_alter:
        cursor.execute("ALTER TABLE test_data ADD COLUMN rogue_col TEXT")
    assert "not authorized" in str(exc_alter.value).lower()

    raw_conn.close()
