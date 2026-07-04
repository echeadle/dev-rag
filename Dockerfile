FROM python:3.12-slim

WORKDIR /app

RUN pip install uv --no-cache-dir

COPY pyproject.toml ./
COPY src/ ./src/

RUN uv pip install --system -e .

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "dev_rag.api:app", "--host", "0.0.0.0", "--port", "8000"]
