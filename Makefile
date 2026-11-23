# Single entry point for developers and CI (contracts/make-targets.md).
# Every target echoes "==> <target>" first, so a failure names its step.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# Host-side settings come from .env when present (contracts/settings.md).
-include .env
export

COMPOSE := docker compose -f deploy/compose.yaml --env-file .env
UV := uv run
GITLEAKS_IMAGE := ghcr.io/gitleaks/gitleaks:v8.30.1

.PHONY: help install up down status reset local local-setup migrate migrate-down phoenix lint typecheck test \
        migration-check secret-scan check spec-validate spec-register \
        demo demo-auto demo-live demo-reset resilience trace \
        web-install web-browsers web-build web-dev web-lint web-typecheck web-test web-e2e web-check openapi api-docs

# L5 spec validation compares with this git ref (override in the environment).
ADLC_SPEC_BASELINE_REF ?= origin/main

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | sort | tr '\n' ' '; echo

install:
	@echo "==> install"
	uv sync --locked
	@$(MAKE) --no-print-directory web-install

up: .env
	@echo "==> up"
	$(COMPOSE) up -d --build --wait

down: .env
	@echo "==> down"
	$(COMPOSE) down

status: .env
	@echo "==> status"
	$(COMPOSE) ps -a

reset: .env
	@echo "==> reset"
	@deploy/confirm-env.sh "Reset removes the data volume and wipes ALL data"
	$(COMPOSE) down -v
	$(MAKE) up

.env:
	@echo "missing .env: copy .env.example to .env and fill in every REPLACE_ME" >&2; exit 1

# ------------------------------------------------------------------ without Docker
# docs/run-without-docker.md. Settings: .env, then deploy/local.env (localhost values).
LOCAL_ENV := set -a; source .env; source deploy/local.env; set +a
HONCHO := uvx honcho==2.0.0

# Migrate the database file and register the specs (idempotent).
local-setup: .env
	@echo "==> local-setup"
	@$(LOCAL_ENV); mkdir -p data/local/pilot/packages; \
	  env -u VIRTUAL_ENV uv run alembic upgrade head && \
	  env -u VIRTUAL_ENV uv run adlc-spec register adlc-specs && \
	  (cd pilot && env -u VIRTUAL_ENV uv sync --locked -q) && \
	  (cd deploy/phoenix && env -u VIRTUAL_ENV uv sync --locked -q)
	@$(MAKE) --no-print-directory web-build

# Every process of deploy/Procfile.local in the foreground; Ctrl-C stops them all.
local: local-setup
	@echo "==> local"
	$(HONCHO) -f deploy/Procfile.local -e .env,deploy/local.env -d . start

# The trace collector without Docker (deploy/phoenix, its own uv project): UI and OTLP on :6006.
phoenix:
	@echo "==> phoenix"
	cd deploy/phoenix && env -u VIRTUAL_ENV PHOENIX_WORKING_DIR=$(CURDIR)/data/local/phoenix uv run phoenix serve

migrate:
	@echo "==> migrate"
	$(UV) alembic upgrade head

migrate-down:
	@echo "==> migrate-down"
	@deploy/confirm-env.sh "Rolling back ALL migrations wipes ALL data"
	$(UV) alembic downgrade base

lint:
	@echo "==> lint"
	$(UV) ruff check .
	$(UV) ruff format --check .

typecheck:
	@echo "==> typecheck"
	$(UV) mypy

# Whole-package coverage is reported; the core modules (constitution IX) are gated at 80%.
CORE_MODULES := */adlc/config/*,*/adlc/identity/*,*/adlc/db/*,*/adlc/spec_toolkit/*,*/adlc/orchestration/*,*/adlc/policy/*,*/adlc/ledger/*,*/adlc/agents/*,*/adlc/inbox/*,*/adlc/api/*,*/adlc/knowledge/*

test:
	@echo "==> test"
	$(UV) pytest
	@echo "core-module coverage (gate 80%):"
	$(UV) coverage report --include='$(CORE_MODULES)' --skip-covered --fail-under=80

# The pilot (feature 009) is its own uv project: lint, types and tests, with an 80% coverage gate.
pilot-check:
	@echo "==> pilot-check"
	cd pilot && env -u VIRTUAL_ENV $(UV) ruff check . && env -u VIRTUAL_ENV $(UV) ruff format --check .
	cd pilot && env -u VIRTUAL_ENV $(UV) mypy
	cd pilot && env -u VIRTUAL_ENV $(UV) pytest
	cd pilot && env -u VIRTUAL_ENV $(UV) coverage report --skip-covered --fail-under=80

spec-validate:
	@echo "==> spec-validate"
	$(UV) adlc-spec validate adlc-specs --baseline-ref $(ADLC_SPEC_BASELINE_REF)

# Registers adlc-specs into the ADLC_DB_PATH data store, host side.
spec-register: .env
	@echo "==> spec-register"
	$(UV) adlc-spec register adlc-specs

migration-check:
	@echo "==> migration-check"
	$(UV) python -m scripts.migration_check

secret-scan:
	@echo "==> secret-scan"
	docker run --rm -v "$(CURDIR):/repo" $(GITLEAKS_IMAGE) dir /repo \
		--config /repo/.gitleaks.toml --redact --no-banner

# Runs every check in order and stops at the first failure; the failing step is the last
# "==> <target>" line printed.
check:
	@echo "==> check"
	@$(MAKE) --no-print-directory lint
	@$(MAKE) --no-print-directory typecheck
	@$(MAKE) --no-print-directory spec-validate
	@$(MAKE) --no-print-directory test
	@$(MAKE) --no-print-directory pilot-check
	@$(MAKE) --no-print-directory web-check
	@$(MAKE) --no-print-directory migration-check
	@$(MAKE) --no-print-directory secret-scan
	@echo "==> check passed"

# ------------------------------------------------------------------ web application (feature 022)
# The browser application in web/ (Node 24 with corepack; pnpm version pinned in package.json).
# Node is needed to build and check it only: adlc-web, a Python process, serves web/dist.
PNPM := pnpm -C web

web-install:
	@echo "==> web-install"
	corepack enable
	$(PNPM) install --frozen-lockfile

# The browser the end-to-end tests drive (CI and first-time setup; with its system libraries)
web-browsers:
	@echo "==> web-browsers"
	$(PNPM) exec playwright install --with-deps chromium

web-build:
	@echo "==> web-build"
	$(PNPM) build

# Vite on :5173, forwarding /api and /config.json to adlc-web on ADLC_UI_PORT
web-dev:
	@echo "==> web-dev"
	$(PNPM) dev

web-lint:
	@echo "==> web-lint"
	$(PNPM) lint
	$(PNPM) format:check

# Type check, then the contract types must match the committed OpenAPI document (FR-021)
web-typecheck:
	@echo "==> web-typecheck"
	$(PNPM) typecheck
	@tmp=$$(mktemp -d); \
	  $(PNPM) exec openapi-typescript src/api/openapi.json -o $$tmp/schema.d.ts >/dev/null; \
	  diff -q web/src/api/schema.d.ts $$tmp/schema.d.ts >/dev/null \
	    || { echo "web/src/api/schema.d.ts is stale: run make openapi" >&2; rm -rf $$tmp; exit 1; }; \
	  rm -rf $$tmp

web-test:
	@echo "==> web-test"
	$(PNPM) test

# Always against a fresh build: the end-to-end stack serves web/dist
web-e2e: web-build
	@echo "==> web-e2e"
	$(PNPM) e2e

web-check:
	@echo "==> web-check"
	@$(MAKE) --no-print-directory web-lint
	@$(MAKE) --no-print-directory web-typecheck
	@$(MAKE) --no-print-directory web-test
	@$(MAKE) --no-print-directory web-e2e

# The platform contract: the API's OpenAPI document, the web application's types from it, and
# the API reference (docs/api-reference.md)
openapi:
	@echo "==> openapi"
	$(UV) python -m scripts.export_openapi web/src/api/openapi.json
	$(PNPM) exec openapi-typescript src/api/openapi.json -o src/api/schema.d.ts
	@$(MAKE) --no-print-directory api-docs

# The API reference, generated from the API's own OpenAPI document (never edited by hand)
api-docs:
	@echo "==> api-docs"
	$(UV) python -m scripts.api_docs docs/api-reference.md

# ------------------------------------------------------------------ demo (feature 014)
FROM_STEP ?= 1

demo: .env
	@echo "==> demo"
	$(UV) python -m scripts.demo --from-step $(FROM_STEP)

demo-auto: .env
	@echo "==> demo-auto"
	$(UV) python -m scripts.demo --auto --from-step $(FROM_STEP)

demo-live: .env
	@echo "==> demo-live"
	$(UV) python -m scripts.demo --live --from-step $(FROM_STEP)

demo-reset: .env
	@echo "==> demo-reset"
	@deploy/require-env.sh demo
	@deploy/confirm-env.sh "Demo reset removes the platform and pilot data volumes"
	$(COMPOSE) down -v
	$(MAKE) up

resilience: .env
	@echo "==> resilience"
	@deploy/require-env.sh demo
	$(UV) python -m scripts.resilience

trace: .env
	@echo "==> trace"
	$(COMPOSE) run --rm -T orchestrator adlc-ledger trace $(USECASE)

