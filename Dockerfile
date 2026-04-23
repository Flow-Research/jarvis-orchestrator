FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY pyproject.toml uv.lock README.md /app/
COPY cli /app/cli
COPY miner_tools /app/miner_tools
COPY scripts /app/scripts
COPY subnets /app/subnets
COPY workstream /app/workstream

RUN uv sync --frozen --no-dev

ENTRYPOINT ["jarvis-miner"]
CMD ["--help"]
