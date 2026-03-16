-- QueryMind role initialization for defense-in-depth.
-- Creates separate users:
-- 1) querymind_admin    : infrastructure/migrations/seeding
-- 2) querymind_app      : application user (separate from agent)
-- 3) querymind_readonly : strict SELECT-only user for all agent queries

DO
$$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'querymind_app') THEN
        CREATE ROLE querymind_app LOGIN PASSWORD 'querymind_app_password';
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'querymind_readonly') THEN
        CREATE ROLE querymind_readonly LOGIN PASSWORD 'querymind_readonly_password';
    END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO querymind_app;
GRANT USAGE ON SCHEMA public TO querymind_readonly;

-- Default privileges for tables/sequences created by the bootstrap admin role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO querymind_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO querymind_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO querymind_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT USAGE, SELECT ON SEQUENCES TO querymind_readonly;

-- Existing objects grants (safe if none exist yet).
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO querymind_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO querymind_readonly;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO querymind_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO querymind_readonly;

-- Ensure querymind_readonly cannot create/modify schema objects.
REVOKE CREATE ON SCHEMA public FROM querymind_readonly;
REVOKE CREATE ON SCHEMA public FROM querymind_app;
