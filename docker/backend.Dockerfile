FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

WORKDIR /app/apps/backend

COPY apps/backend/pyproject.toml /app/apps/backend/pyproject.toml

RUN python -c "import subprocess, sys, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *deps])"

COPY apps/backend/app /app/apps/backend/app
COPY data /app/data

EXPOSE 8000

CMD ["sh", "-c", "python -m app.scripts.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
