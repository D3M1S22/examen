# EXAMEN Python Backend - Dockerfile
# Optimized for AWS ECS Fargate
# Multistage build for minimal footprint

# Stage 1: Builder
FROM python:3.11-slim-bookworm as builder

# Set env variables to avoid interactive prompts & optimize python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install build dependencies if needed (e.g. gcc for certain python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies into a virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt


# Stage 2: Runner
FROM python:3.11-slim-bookworm as runner

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

WORKDIR /app

# Only copy the built virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY src/ /app/src/
# Copy the static exported UI (assuming it's built to src/web_ui/out)
COPY src/web_ui/out/ /app/src/web_ui/out/ 

# Expose the FastMCP port
EXPOSE 8000

# Run the MCP Server module directly
CMD ["python", "-m", "src.serving.mcp_server", "--host", "0.0.0.0", "--port", "8000"]
