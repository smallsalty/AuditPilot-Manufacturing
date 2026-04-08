#!/usr/bin/env bash

set -euo pipefail

SEED=false
if [[ "${1:-}" == "--seed" ]]; then
  SEED=true
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_PATH="$ROOT_DIR/.env"
ENV_EXAMPLE_PATH="$ROOT_DIR/.env.example"
BACKEND_DIR="$ROOT_DIR/apps/backend"
VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

step() {
  echo
  echo "==> $1"
}

fail() {
  echo
  echo "ERROR: $1" >&2
  exit 1
}

read_env_value() {
  local key="$1"
  python3 - "$ENV_PATH" "$key" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
key = sys.argv[2]
if not env_path.exists():
    sys.exit(0)
for line in env_path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    k, v = stripped.split("=", 1)
    if k.strip() == key:
        print(v.strip())
        break
PY
}

step "检查 .env"
if [[ ! -f "$ENV_PATH" ]]; then
  if [[ ! -f "$ENV_EXAMPLE_PATH" ]]; then
    fail "未找到 .env 和 .env.example"
  fi
  cp "$ENV_EXAMPLE_PATH" "$ENV_PATH"
  echo ".env 不存在，已从 .env.example 复制。请确认 DATABASE_URL 和 LLM_* 配置。"
fi

DATABASE_URL_VALUE="$(read_env_value DATABASE_URL)"
if [[ -z "$DATABASE_URL_VALUE" ]]; then
  fail ".env 中缺少 DATABASE_URL"
fi

LLM_API_KEY_VALUE="$(read_env_value LLM_API_KEY)"
if [[ -z "$LLM_API_KEY_VALUE" ]]; then
  echo "警告: LLM_API_KEY 未配置，系统将以 Mock 模式运行。"
fi

step "检查 docker 与 Python 3.11"
command -v docker >/dev/null 2>&1 || fail "未找到 docker"
docker compose version >/dev/null 2>&1 || fail "未找到 docker compose"
command -v python3.11 >/dev/null 2>&1 || fail "未找到 python3.11"

step "启动 PostgreSQL 容器"
cd "$ROOT_DIR"
docker compose up -d postgres

step "准备后端虚拟环境"
if [[ ! -x "$VENV_PYTHON" ]]; then
  cd "$BACKEND_DIR"
  python3.11 -m venv .venv
fi

step "按需安装后端依赖"
NEED_BACKEND_INSTALL=false
if [[ ! -x "$VENV_PYTHON" ]]; then
  NEED_BACKEND_INSTALL=true
else
  cd "$BACKEND_DIR"
  if ! "$VENV_PYTHON" -c "import uvicorn,pytest,fastapi,sqlalchemy,app.main" >/dev/null 2>&1; then
    NEED_BACKEND_INSTALL=true
  fi
fi
if [[ "$NEED_BACKEND_INSTALL" == "true" ]]; then
  cd "$BACKEND_DIR"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -e .[dev]
else
  echo "后端依赖已存在，跳过安装。"
fi

step "数据库 ready 检查"
DB_READY=false
for _ in $(seq 1 30); do
  cd "$BACKEND_DIR"
  if "$VENV_PYTHON" -c "from sqlalchemy import create_engine, text; from app.core.config import settings; engine=create_engine(settings.database_url, future=True, pool_pre_ping=True); conn=engine.connect(); conn.execute(text('SELECT 1')); conn.close()" >/dev/null 2>&1; then
    DB_READY=true
    break
  fi
  sleep 2
done

if [[ "$DB_READY" != "true" ]]; then
  fail "数据库未就绪或无法连接，请检查 DATABASE_URL 与 postgres 容器状态。"
fi

if [[ "$SEED" == "true" ]]; then
  step "执行 seed_demo"
  cd "$BACKEND_DIR"
  "$VENV_PYTHON" -m app.scripts.seed_demo
fi

step "启动 FastAPI"
cd "$BACKEND_DIR"
echo "Backend: http://localhost:8000/docs"
if [[ "$SEED" != "true" ]]; then
  echo "本次未执行 seed_demo；如需初始化 demo 数据，请使用: bash scripts/server-run.sh --seed"
fi
"$VENV_PYTHON" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
