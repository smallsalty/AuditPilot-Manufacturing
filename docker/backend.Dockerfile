FROM python:3.11-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/apps/backend

COPY apps/backend/pyproject.toml /app/apps/backend/pyproject.toml

RUN python -m pip install --no-cache-dir --upgrade pip && \
    python -c "import subprocess, sys, tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--no-cache-dir', *deps])"

COPY apps/backend/app /app/apps/backend/app
COPY data /app/data

EXPOSE 8000

CMD ["sh", "-c", "python -m app.scripts.init_db && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
