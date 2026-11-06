FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY skills/ ./skills/

RUN pip install --no-cache-dir .

EXPOSE 8080

CMD ["sh", "-c", "uvicorn mbooks.studio.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
