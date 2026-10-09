-- One Postgres, two databases, one least-privilege owner role each.
-- Run as an admin user (superuser, or the RDS master user). Safe to re-run.
--   Docker:  runs automatically on first start (postgres/initdb.sh)
--   Other:   psql -h <host> -p <port> -U <admin> -d postgres \
--              -v app_password=... -v keycloak_password=... -f postgres/create-databases.sql
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') \gexec
SELECT format('CREATE ROLE keycloak LOGIN PASSWORD %L', :'keycloak_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'keycloak') \gexec

-- PostgreSQL 16+ (e.g. AWS RDS): a non-superuser admin must be a member of a role to make it a database owner.
GRANT app, keycloak TO CURRENT_USER;

SELECT 'CREATE DATABASE app OWNER app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'app') \gexec
SELECT 'CREATE DATABASE keycloak OWNER keycloak'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak') \gexec

-- Isolation: by default every role may connect to every database. Only each owner may now.
REVOKE CONNECT ON DATABASE app FROM PUBLIC;
REVOKE CONNECT ON DATABASE keycloak FROM PUBLIC;
