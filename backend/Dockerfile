FROM python:3.12-slim

WORKDIR /app

# uv for dependency management (single source of truth: pyproject.toml + uv.lock)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies (cached layer — only re-runs when deps change)
COPY pyproject.toml uv.lock ./
RUN UV_HTTP_TIMEOUT=300 uv sync --frozen --no-dev --no-install-project

# Copy source code and install the project itself
COPY . .
RUN uv sync --frozen --no-dev

# Expose port
EXPOSE 8000

# Run the FastAPI application (single canonical async app)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
