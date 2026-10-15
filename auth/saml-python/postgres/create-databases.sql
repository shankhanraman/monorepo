-- One Postgres, one app database with a least-privilege owner role.
-- Run as an admin user (superuser, or the RDS master user). Safe to re-run.
--   Docker:  runs automatically on first start (postgres/initdb.sh)
--   Other:   psql -h <host> -p <port> -U <admin> -d postgres -v app_password=... -f postgres/create-databases.sql
\set ON_ERROR_STOP on

SELECT format('CREATE ROLE app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app') \gexec

-- PostgreSQL 16+ (e.g. AWS RDS): a non-superuser admin must be a member of a role to make it a database owner.
GRANT app TO CURRENT_USER;

SELECT 'CREATE DATABASE app OWNER app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'app') \gexec

-- Isolation: by default every role may connect to every database. Only the owner may now.
REVOKE CONNECT ON DATABASE app FROM PUBLIC;
