param(
    [switch]$NoBuild,
    [switch]$FollowBackendLogs,
    [switch]$SkipFrontend,
    [int]$DockerWaitSeconds = 180,
    [int]$BackendWaitSeconds = 180
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Warn($Message) {
    Write-Host "WARNING: $Message" -ForegroundColor Yellow
}

function Fail($Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Read-EnvValue($Path, $Key) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } |
        Select-Object -First 1

    if (-not $line) {
        return $null
    }

    return ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

function Test-DockerReady {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker info 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Find-DockerDesktop {
    $candidates = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }

    return $null
}

function Wait-DockerReady($TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) {
            return $true
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Wait-BackendReady($Url, $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5
            if ($response.status -eq "ok") {
                return $true
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    return $false
}

function Quote-ForPowerShell($Value) {
    return "'" + ($Value -replace "'", "''") + "'"
}

$Root = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $Root ".env"
$EnvExamplePath = Join-Path $Root ".env.example"
$FrontendEnvPath = Join-Path $Root "apps\frontend\.env.local"
$RootNodeModules = Join-Path $Root "node_modules"
$FrontendNodeModules = Join-Path $Root "apps\frontend\node_modules"
$HealthUrl = "http://localhost:8000/health"

Set-Location -LiteralPath $Root

Write-Step "Checking Docker CLI"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "docker command not found. Install Docker Desktop first."
}

Write-Step "Starting Docker Desktop if needed"
if (-not (Test-DockerReady)) {
    $dockerDesktop = Find-DockerDesktop
    if (-not $dockerDesktop) {
        Fail "Docker Desktop executable was not found. Start Docker Desktop manually, then rerun this script."
    }

    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        Write-Host "Starting Docker Desktop: $dockerDesktop"
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
    } else {
        Write-Host "Docker Desktop process is already running; waiting for daemon..."
    }

    if (-not (Wait-DockerReady -TimeoutSeconds $DockerWaitSeconds)) {
        Fail "Docker Desktop was started, but Docker daemon is still not ready. Open Docker Desktop and check WSL/login/update prompts."
    }
}
Write-Host "Docker daemon is ready." -ForegroundColor Green

Write-Step "Checking environment"
if (-not (Test-Path -LiteralPath $EnvPath)) {
    if (-not (Test-Path -LiteralPath $EnvExamplePath)) {
        Fail ".env and .env.example were not found."
    }
    Copy-Item -LiteralPath $EnvExamplePath -Destination $EnvPath
    Write-Warn ".env was missing and has been copied from .env.example. Configure your DeepSeek API key before using AI features."
}

$anthropicKey = Read-EnvValue -Path $EnvPath -Key "ANTHROPIC_API_KEY"
if ([string]::IsNullOrWhiteSpace($anthropicKey)) {
    Write-Warn "No ANTHROPIC_API_KEY found in .env. Backend can start, but AI calls will fail until a DeepSeek key is configured."
} else {
    Write-Host "LLM API key is configured." -ForegroundColor Green
}

if (Test-Path -LiteralPath $FrontendEnvPath) {
    $frontendApiBase = Read-EnvValue -Path $FrontendEnvPath -Key "NEXT_PUBLIC_API_BASE_URL"
    if ($frontendApiBase -and $frontendApiBase -ne "http://localhost:8000") {
        Write-Warn "apps/frontend/.env.local points to $frontendApiBase. For local Docker backend, set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000."
    }
}

Write-Step "Starting Docker backend stack"
$composeArgs = @("compose", "up", "-d")
if (-not $NoBuild) {
    $composeArgs += "--build"
}
$composeArgs += @("postgres", "backend")

& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    & docker compose ps
    & docker compose logs --tail 80 backend
    Fail "docker compose failed."
}

Write-Step "Waiting for backend healthcheck"
if (-not (Wait-BackendReady -Url $HealthUrl -TimeoutSeconds $BackendWaitSeconds)) {
    & docker compose ps
    & docker compose logs --tail 120 backend
    Fail "Backend did not become healthy at $HealthUrl."
}
Write-Host "Backend is ready: http://localhost:8000/docs" -ForegroundColor Green

if (-not $SkipFrontend) {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        Fail "npm command not found. Install Node.js first."
    }

    Write-Step "Checking frontend dependencies"
    if ((-not (Test-Path -LiteralPath $RootNodeModules)) -and (-not (Test-Path -LiteralPath $FrontendNodeModules))) {
        & npm install
        if ($LASTEXITCODE -ne 0) {
            Fail "npm install failed."
        }
    } else {
        Write-Host "Frontend dependencies appear to be installed."
    }

    Write-Step "Starting frontend dev server"
    $quotedRoot = Quote-ForPowerShell $Root
    $frontendCommand = "Set-Location -LiteralPath $quotedRoot; npm --workspace apps/frontend run dev"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand | Out-Null
    Write-Host "Frontend is starting in a new PowerShell window: http://localhost:3000" -ForegroundColor Green
}

Write-Host ""
Write-Host "Startup complete." -ForegroundColor Green
Write-Host "Backend API:  http://localhost:8000/docs"
if (-not $SkipFrontend) {
    Write-Host "Frontend:     http://localhost:3000"
}

if ($FollowBackendLogs) {
    Write-Step "Following backend logs"
    & docker compose logs -f backend
}
