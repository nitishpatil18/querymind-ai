-- Creates the read-only application role used for query execution and schema inspection.
-- Runs once on first container start (docker-entrypoint-initdb.d). Plain SQL on purpose:
-- it needs no executable bit, so it works on bind mounts that do not allow execution.
-- Credentials come from the container environment through psql's \getenv (psql 15+).
\getenv ro_user QUERYMIND_RO_USER
\getenv ro_pass QUERYMIND_RO_PASSWORD
\if :{?ro_user}
\else
  \set ro_user querymind_ro
\endif
\if :{?ro_pass}
\else
  DO $$ BEGIN RAISE EXCEPTION 'QUERYMIND_RO_PASSWORD must be set'; END $$;
\endif

SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'ro_user', :'ro_pass')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'ro_user') \gexec

SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'ro_user') \gexec
SELECT format('ALTER ROLE %I SET statement_timeout = ''15s''', :'ro_user') \gexec
SELECT format('ALTER ROLE %I SET idle_in_transaction_session_timeout = ''30s''', :'ro_user') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'ro_user') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('REVOKE CREATE ON SCHEMA public FROM %I', :'ro_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'ro_user') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'ro_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO %I', :'ro_user') \gexec
