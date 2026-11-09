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

.PHONY: help install up down status reset migrate migrate-down lint typecheck test \
        migration-check secret-scan check

help:
	@grep -E '^[a-z-]+:' Makefile | cut -d: -f1 | sort | tr '\n' ' '; echo

install:
	@echo "==> install"
	uv sync --locked

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

test:
	@echo "==> test"
	$(UV) pytest

migration-check:
	@echo "==> migration-check"
	@echo "not implemented yet"; exit 1

secret-scan:
	@echo "==> secret-scan"
	@echo "not implemented yet"; exit 1

check:
	@echo "==> check"
	@echo "not implemented yet"; exit 1
