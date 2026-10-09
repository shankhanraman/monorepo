#!/bin/sh
# First start of the Docker `db` container only (/docker-entrypoint-initdb.d). Passwords come from .env.
set -e
psql -U "$POSTGRES_USER" -d postgres \
  -v app_password="$APP_DB_PASSWORD" -v keycloak_password="$KEYCLOAK_DB_PASSWORD" \
  -f /db/create-databases.sql
