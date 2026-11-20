# Trace collector and viewer (Arize Phoenix): OTLP in, REST API and UI out. Python only.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PHOENIX_WORKING_DIR=/var/lib/phoenix \
    PHOENIX_HOST=0.0.0.0 \
    PHOENIX_PORT=6006

WORKDIR /phoenix
COPY deploy/phoenix/pyproject.toml deploy/phoenix/uv.lock deploy/phoenix/README.md ./
RUN uv sync --locked --no-dev

RUN useradd --system --uid 10003 --no-create-home phoenix \
    && mkdir -p /var/lib/phoenix \
    && chown phoenix /var/lib/phoenix

USER phoenix
EXPOSE 6006
CMD ["phoenix", "serve"]
