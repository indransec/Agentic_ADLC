#!/usr/bin/env bash
# Creates the two platform identities and the platform database (data-model.md).
# Runs once, as the container superuser, when the data volume is first created.
# Passwords come from the environment; nothing secret is stored in this file.
set -euo pipefail

: "${ADLC_DB_OWNER_PASSWORD:?ADLC_DB_OWNER_PASSWORD is required}"
: "${ADLC_DB_APP_PASSWORD:?ADLC_DB_APP_PASSWORD is required}"
owner="${ADLC_DB_OWNER_USER:-adlc_owner}"
app="${ADLC_DB_APP_USER:-adlc_app}"
db="${ADLC_DB_NAME:-adlc}"

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname postgres \
  -v owner="$owner" -v app="$app" -v db="$db" \
  -v owner_pw="$ADLC_DB_OWNER_PASSWORD" -v app_pw="$ADLC_DB_APP_PASSWORD" <<'SQL'
CREATE ROLE :"owner" LOGIN PASSWORD :'owner_pw';
CREATE ROLE :"app" LOGIN PASSWORD :'app_pw';
CREATE DATABASE :"db" OWNER :"owner";
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db" TO :"app";
SQL

psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname "$db" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
