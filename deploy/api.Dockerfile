# Platform API image (also used by the one-shot `migrate` service).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, for layer caching.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY db ./db
COPY alembic.ini ./
COPY adlc-specs ./adlc-specs
RUN uv sync --locked --no-dev

RUN useradd --system --uid 10001 --no-create-home adlc
USER adlc

EXPOSE 8000
CMD ["adlc-api"]
