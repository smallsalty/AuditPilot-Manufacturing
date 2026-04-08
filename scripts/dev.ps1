param(
    [switch]$Seed
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail($Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Read-EnvValue($Path, $Key) {
    if (-not (Test-Path $Path)) {
        return $null
    }
    $line = Get-Content $Path | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
    if (-not $line) {
        return $null
    }
    return ($line -split "=", 2)[1].Trim()
}

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".env"
$EnvExamplePath = Join-Path $Root ".env.example"
$BackendDir = Join-Path $Root "apps\backend"
$FrontendDir = Join-Path $Root "apps\frontend"
$VenvDir = Join-Path $BackendDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$NodeModulesDir = Join-Path $FrontendDir "node_modules"

Write-Step "检查 .env"
if (-not (Test-Path $EnvPath)) {
    if (-not (Test-Path $EnvExamplePath)) {
        Fail "未找到 .env 和 .env.example"
    }
    Copy-Item $EnvExamplePath $EnvPath
    Write-Host ".env 不存在，已从 .env.example 复制。请确认 DATABASE_URL 和 LLM_* 配置。" -ForegroundColor Yellow
}

$DatabaseUrl = Read-EnvValue $EnvPath "DATABASE_URL"
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    Fail ".env 中缺少 DATABASE_URL"
}

$LlmApiKey = Read-EnvValue $EnvPath "LLM_API_KEY"
if ([string]::IsNullOrWhiteSpace($LlmApiKey)) {
    Write-Host "警告: LLM_API_KEY 未配置，系统将以 Mock 模式运行。" -ForegroundColor Yellow
}

Write-Step "检查 Python 和 Node"
$PythonVersionText = & python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "未找到 python 命令"
}
if ($PythonVersionText -notmatch "Python 3\.11") {
    Fail "需要 Python 3.11，当前为: $PythonVersionText"
}
& node --version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "未找到 node 命令"
}
& npm --version *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "未找到 npm 命令"
}

Write-Step "准备后端虚拟环境"
if (-not (Test-Path $VenvPython)) {
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        Fail "创建后端虚拟环境失败"
    }
}

Write-Step "按需安装后端依赖"
$NeedBackendInstall = $false
if (-not (Test-Path $VenvPython)) {
    $NeedBackendInstall = $true
} else {
    Push-Location $BackendDir
    & $VenvPython -c "import uvicorn,pytest,fastapi,sqlalchemy,app.main" *> $null
    if ($LASTEXITCODE -ne 0) {
        $NeedBackendInstall = $true
    }
    Pop-Location
}
if ($NeedBackendInstall) {
    Push-Location $BackendDir
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -e .[dev]
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Fail "后端依赖安装失败"
    }
    Pop-Location
} else {
    Write-Host "后端依赖已存在，跳过安装。"
}

Write-Step "按需安装前端依赖"
if (-not (Test-Path $NodeModulesDir)) {
    Push-Location $FrontendDir
    & npm install
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Fail "前端依赖安装失败"
    }
    Pop-Location
} else {
    Write-Host "前端依赖已存在，跳过安装。"
}

Write-Step "数据库 ready 检查"
$DbCheck = @"
from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
with engine.connect() as conn:
    conn.execute(text('SELECT 1'))
print('DB_READY')
"@

$DbReady = $false
for ($i = 1; $i -le 20; $i++) {
    Push-Location $BackendDir
    & $VenvPython -c $DbCheck *> $null
    $ExitCode = $LASTEXITCODE
    Pop-Location
    if ($ExitCode -eq 0) {
        $DbReady = $true
        break
    }
    Start-Sleep -Seconds 2
}
if (-not $DbReady) {
    Fail "数据库未就绪或无法连接，请检查 DATABASE_URL 与服务器 PostgreSQL 状态。"
}

if ($Seed) {
    Write-Step "执行 seed_demo"
    Push-Location $BackendDir
    & $VenvPython -m app.scripts.seed_demo
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Fail "seed_demo 执行失败"
    }
    Pop-Location
}

Write-Step "启动后端与前端"
$BackendCommand = "Set-Location '$BackendDir'; & '$VenvPython' -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
$FrontendCommand = "Set-Location '$FrontendDir'; npm run dev"

Start-Process powershell -ArgumentList "-NoExit", "-Command", $BackendCommand | Out-Null
Start-Process powershell -ArgumentList "-NoExit", "-Command", $FrontendCommand | Out-Null

Write-Host ""
Write-Host "启动完成:" -ForegroundColor Green
Write-Host "Backend:  http://localhost:8000/docs"
Write-Host "Frontend: http://localhost:3000"
if (-not $Seed) {
    Write-Host "本次未执行 seed_demo；如需初始化 demo 数据，请使用: powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 -Seed" -ForegroundColor Yellow
}

