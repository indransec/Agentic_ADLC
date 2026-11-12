# Pilot image (feature 009): the Incident Triage Assistant's template, fills and tooling.
# A separate project from the platform image; it holds no platform code or secrets.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /pilot

COPY pilot/pyproject.toml pilot/uv.lock pilot/README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY pilot/src ./src
COPY pilot/template ./template
COPY pilot/fills ./fills
COPY pilot/datasets.yaml ./datasets.yaml
RUN uv sync --locked --no-dev

# Package registry, records, generated data and worker scratch; named volumes inherit the owner.
RUN useradd --system --uid 10002 --no-create-home pilot \
    && mkdir -p /packages /records /data /tmp/pilot-work \
    && chown pilot /packages /records /data /tmp/pilot-work
USER pilot

EXPOSE 8100 8200
CMD ["pilot-host", "--env", "dev"]
