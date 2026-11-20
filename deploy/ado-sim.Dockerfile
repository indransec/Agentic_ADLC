# ADO simulator image (feature 015): an Azure DevOps Boards REST API 7.1 subset with its own
# SQLite file. A separate project from the platform image; it holds no platform code or secrets.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    ADO_SIM_DB_PATH=/var/lib/ado-sim/ado_sim.db \
    ADO_SIM_SEED_FILE=/ado-sim/seed/demo.yaml \
    ADO_SIM_HOST=0.0.0.0 \
    ADO_SIM_PORT=8600

WORKDIR /ado-sim

COPY ado_sim/pyproject.toml ado_sim/uv.lock ado_sim/README.md ./
RUN uv sync --locked --no-dev --no-install-project

# Only the simulator: its package (with migrations) and the seed file; no tests, no fixtures.
COPY ado_sim/src ./src
COPY ado_sim/seed ./seed
RUN uv sync --locked --no-dev

# The data directory is a named volume in compose; it inherits this owner.
RUN useradd --system --uid 10003 --no-create-home adosim \
    && mkdir -p /var/lib/ado-sim \
    && chown adosim /var/lib/ado-sim
USER adosim

EXPOSE 8600
# Migrate (creates the file on first start), seed only an empty database, then serve.
CMD ["sh", "-c", "ado-sim migrate && ado-sim seed --if-new --file \"$ADO_SIM_SEED_FILE\" && exec ado-sim serve"]
