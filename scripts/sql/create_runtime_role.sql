-- Least-privilege runtime role for Metrik application traffic.
-- Run as a superuser / migration owner after creating the database.
-- Migrations should continue to use an elevated owner role.

-- Example:
--   psql -U postgres -d groundtruth -f scripts/sql/create_runtime_role.sql

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'metrik_runtime') THEN
    CREATE ROLE metrik_runtime LOGIN PASSWORD 'replace-me-runtime';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE groundtruth TO metrik_runtime;
GRANT USAGE ON SCHEMA public TO metrik_runtime;

-- DML for application tables (no DDL).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO metrik_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO metrik_runtime;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO metrik_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO metrik_runtime;

-- Explicitly revoke DDL-capable rights if previously granted.
REVOKE CREATE ON SCHEMA public FROM metrik_runtime;
