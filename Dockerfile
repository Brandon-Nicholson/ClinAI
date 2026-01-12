# Stage 1: Build React frontend
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python application
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml poetry.lock* ./

RUN pip install --no-cache-dir poetry \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY . .

# Copy React build from frontend stage
COPY --from=frontend-builder /app/static/dist /app/app/static/dist

CMD ["bash", "-lc", "exec poetry run uvicorn app.clinai_web:app --host 0.0.0.0 --port ${PORT:-8000}"]
