FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
RUN pip install uv --no-cache-dir

COPY pyproject.toml ./
COPY mcp_server.py ./

# Install runtime deps (no dev extras)
RUN uv pip install --system "mcp>=1.0.0" "httpx>=0.27.0" \
    "mcp[http]" "starlette>=0.40.0" "uvicorn>=0.30.0"

ENV PYTHONUNBUFFERED=1

EXPOSE 9000

CMD ["python", "mcp_server.py"]
