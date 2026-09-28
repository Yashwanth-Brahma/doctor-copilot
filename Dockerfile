# Backend for Railway: FastAPI + briefing graph + Q&A agent + MCP server (spawned per question).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# dependencies first, so code changes don't reinstall them
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# Railway sets PORT; shell form so ${PORT} is expanded
CMD uvicorn copilot.api:default_app --factory --host 0.0.0.0 --port ${PORT:-8000}
