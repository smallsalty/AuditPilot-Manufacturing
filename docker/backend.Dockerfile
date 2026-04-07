FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

COPY apps/backend /app/apps/backend
COPY data /app/data

WORKDIR /app/apps/backend

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["sh", "-c", "python -m app.scripts.seed_demo && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

