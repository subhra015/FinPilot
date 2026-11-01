"""PostgreSQL least-privilege role configuration and validation (SEC-03, Layer 2).

Defines separate roles:
1. ``finpilot_admin`` (migration/administrative role): owns database schema,
   runs migrations, creates/alters tables.
2. ``finpilot_app`` (runtime application role): restricted to DML (SELECT, INSERT,
   UPDATE, DELETE) and sequence USAGE. Cannot perform DDL, cannot drop tables,
   is not superuser or schema owner.
"""

from __future__ import annotations

from typing import Final

ADMIN_ROLE: Final[str] = "finpilot_admin"
APP_ROLE: Final[str] = "finpilot_app"
SCHEMA_NAME: Final[str] = "public"

POSTGRES_ROLE_SETUP_TEMPLATE: Final[str] = """\
-- FinPilot AI: PostgreSQL Least-Privilege Role Setup (SEC-03)
-- Execute as PostgreSQL superuser (e.g. postgres) during database provisioning.

-- 1. Create migration/administrative role (owns schema and objects)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{admin_role}') THEN
        CREATE ROLE {admin_role} WITH LOGIN
            ENCRYPTED PASSWORD 'CHANGE_ME_ADMIN_PASSWORD_MIN_32_CHARS';
    END IF;
END
$$;

-- 2. Create runtime application role (unprivileged login role)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{app_role}') THEN
        CREATE ROLE {app_role} WITH LOGIN
            ENCRYPTED PASSWORD 'CHANGE_ME_APP_PASSWORD_MIN_32_CHARS';
    END IF;
END
$$;

-- Ensure runtime role is NOT superuser, cannot create databases, cannot create roles
ALTER ROLE {app_role} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE {admin_role} NOSUPERUSER CREATEDB NOCREATEROLE;

-- 3. Schema ownership and base permissions
ALTER SCHEMA {schema} OWNER TO {admin_role};
REVOKE ALL ON SCHEMA {schema} FROM PUBLIC;
GRANT USAGE ON SCHEMA {schema} TO {admin_role}, {app_role};
GRANT CREATE ON SCHEMA {schema} TO {admin_role};
REVOKE CREATE ON SCHEMA {schema} FROM {app_role};

-- 4. Table permissions: runtime app gets DML only; no DDL / drop
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {app_role};
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {schema} TO {admin_role};

-- 5. Sequence permissions: runtime app needs USAGE and SELECT for autoincrement PKs
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {app_role};
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {schema} TO {admin_role};

-- 6. Default privileges for future tables created by migrations (owned by admin)
ALTER DEFAULT PRIVILEGES FOR ROLE {admin_role} IN SCHEMA {schema}
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_role};

ALTER DEFAULT PRIVILEGES FOR ROLE {admin_role} IN SCHEMA {schema}
    GRANT USAGE, SELECT ON SEQUENCES TO {app_role};

-- Protect migration metadata table from runtime modification if desired
-- (alembic_version and schema_meta should be read-only for runtime)
REVOKE INSERT, UPDATE, DELETE ON TABLE alembic_version FROM {app_role};
REVOKE INSERT, UPDATE, DELETE ON TABLE schema_meta FROM {app_role};
"""


def generate_role_setup_script(
    *,
    admin_role: str = ADMIN_ROLE,
    app_role: str = APP_ROLE,
    schema: str = SCHEMA_NAME,
) -> str:
    """Generate PostgreSQL least-privilege role setup script with custom names."""
    return POSTGRES_ROLE_SETUP_TEMPLATE.format(
        admin_role=admin_role,
        app_role=app_role,
        schema=schema,
    )
