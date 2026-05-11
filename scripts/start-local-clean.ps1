param(
    [int[]]$AppPorts = @(3000, 8000),
    [int]$DatabasePort = 5432,
    [switch]$BackendReload,
    [int]$DockerWaitSeconds = 180,
    [int]$PostgresWaitSeconds = 180
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

function Test-DockerReady {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & docker info 1>$null 2>$null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previous
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

function Get-BlockedPorts([int[]]$LocalPorts) {
    $blockedPorts = @()
    foreach ($port in $LocalPorts) {
        if (-not (Test-PortBindable -Port $port)) {
            $blockedPorts += $port
        }
    }
    return @($blockedPorts | Sort-Object -Unique)
}

function Test-PortBindable([int]$Port) {
    $listener = $null
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Any, $Port)
        $listener.Server.ExclusiveAddressUse = $true
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        if ($listener) {
            $listener.Stop()
        }
    }
}

function Test-BackendHealthy($TimeoutSeconds = 5) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2
            if ($response.status -eq "ok") {
                return $true
            }
        } catch {}
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Get-ListeningPortEntries([int[]]$LocalPorts) {
    $entries = @()
    foreach ($port in $LocalPorts) {
        $connections = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
        foreach ($connection in $connections) {
            $ownerPid = [int]$connection.OwningProcess
            if ($ownerPid -le 0) {
                continue
            }
            $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
            $entries += [PSCustomObject]@{
                Port = $port
                PID = $ownerPid
                ProcessName = if ($process) { $process.ProcessName } else { "unknown" }
            }
        }
    }
    return @($entries | Sort-Object Port, PID -Unique)
}

function Get-PortProcessMap([int[]]$LocalPorts) {
    $result = @{}

    foreach ($entry in Get-ListeningPortEntries -LocalPorts $LocalPorts) {
        $ownerPid = [int]$entry.PID
        if ($ownerPid -eq $PID) {
            continue
        }
        if (-not $result.ContainsKey($ownerPid)) {
            $result[$ownerPid] = @()
        }
        $result[$ownerPid] = @($result[$ownerPid]) + [int]$entry.Port
    }

    return $result
}

function Stop-PortProcesses([int[]]$LocalPorts) {
    $processMap = Get-PortProcessMap -LocalPorts $LocalPorts
    if ($processMap.Count -eq 0) {
        Write-Host "No running process is occupying ports $($LocalPorts -join ', ')."
        return
    }

    foreach ($entry in $processMap.GetEnumerator() | Sort-Object Name) {
        $ownerPid = [int]$entry.Key
        $portList = @($entry.Value | Sort-Object -Unique)
        $process = Get-Process -Id $ownerPid -ErrorAction SilentlyContinue
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        Write-Host "Stopping PID $ownerPid ($processName) on ports $($portList -join ', ')..."
        try {
            Stop-Process -Id $ownerPid -Force -ErrorAction Stop
        } catch {
            Write-Warn "Failed to stop PID $ownerPid ($processName): $($_.Exception.Message)"
        }
    }
}

function Wait-PortsReleased([int[]]$LocalPorts, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $blockedPorts = @()
        foreach ($port in $LocalPorts) {
            if (-not (Test-PortBindable -Port $port)) {
                $blockedPorts += $port
            }
        }
        if ($blockedPorts.Count -eq 0) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-PortOccupants([int[]]$LocalPorts, [string]$Prefix = "Port occupants") {
    $entries = @(Get-ListeningPortEntries -LocalPorts $LocalPorts)
    if ($entries.Count -eq 0) {
        Write-Host "${Prefix}: none."
        return
    }

    Write-Host "${Prefix}:"
    foreach ($entry in $entries) {
        Write-Host "  Port $($entry.Port) -> PID $($entry.PID) ($($entry.ProcessName))"
    }
}

function Wait-ContainerHealthy($ContainerName, $TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $status = (& docker inspect --format "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}" $ContainerName 2>$null)
        if ($LASTEXITCODE -eq 0) {
            $trimmed = [string]::Join("", $status).Trim()
            if ($trimmed -eq "healthy" -or $trimmed -eq "running") {
                return $true
            }
        }
        Start-Sleep -Seconds 3
    }
    return $false
}

function Quote-ForPowerShell($Value) {
    return "'" + ($Value -replace "'", "''") + "'"
}

function Stop-ProjectRuntimeProcesses([string]$ProjectRoot) {
    $normalizedRoot = $ProjectRoot.ToLowerInvariant()
    $patterns = @(
        "uvicorn app.main:app",
        "npm run dev:frontend",
        "next dev",
        "next\\dist\\server\\lib\\start-server.js"
    )

    $processes = @(Get-CimInstance Win32_Process | Where-Object {
        $commandLine = [string]($_.CommandLine)
        if ([string]::IsNullOrWhiteSpace($commandLine)) {
            return $false
        }
        $normalizedCommandLine = $commandLine.ToLowerInvariant()
        if ($normalizedCommandLine -notlike "*$normalizedRoot*") {
            return $false
        }
        foreach ($pattern in $patterns) {
            if ($normalizedCommandLine -like "*$pattern*") {
                return $true
            }
        }
        return $false
    })

    if ($processes.Count -eq 0) {
        Write-Host "No existing project runtime process matched command-line cleanup."
        return
    }

    foreach ($process in $processes | Sort-Object ProcessId -Unique) {
        Write-Host "Stopping runtime PID $($process.ProcessId) ($($process.Name))..."
        try {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-Warn "Failed to stop runtime PID $($process.ProcessId) ($($process.Name)): $($_.Exception.Message)"
        }
    }
}

$Root = Split-Path -Parent $PSScriptRoot
$BackendDir = Join-Path $Root "apps\backend"
$QuotedRoot = Quote-ForPowerShell $Root
$QuotedBackendDir = Quote-ForPowerShell $BackendDir

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
        Fail "Docker daemon is still not ready. Open Docker Desktop and check pending prompts."
    }
}
Write-Host "Docker daemon is ready." -ForegroundColor Green

Write-Step "Stopping existing Docker stack"
& docker compose down
if ($LASTEXITCODE -ne 0) {
    Fail "docker compose down failed."
}

Write-Step "Stopping existing project runtime processes"
Stop-ProjectRuntimeProcesses -ProjectRoot $Root

Write-Step "Stopping processes occupying app ports"
Stop-PortProcesses -LocalPorts $AppPorts
if (-not (Wait-PortsReleased -LocalPorts $AppPorts -TimeoutSeconds 30)) {
    Show-PortOccupants -LocalPorts $AppPorts -Prefix "App ports still occupied after cleanup"
    $blockedPorts = @(Get-BlockedPorts -LocalPorts $AppPorts)
    if ($blockedPorts.Count -eq 1 -and $blockedPorts[0] -eq 8000 -and (Test-BackendHealthy -TimeoutSeconds 5)) {
        $reuseExistingBackend = $true
        Write-Warn "Port 8000 is still occupied by a healthy backend listener that could not be reaped. Reusing it for this run."
    } else {
        Fail "Ports $($AppPorts -join ', ') are still occupied after cleanup."
    }
} else {
    $reuseExistingBackend = $false
}
Write-Host "App ports released: $($AppPorts -join ', ')." -ForegroundColor Green

Write-Step "Checking database port"
if (-not (Wait-PortsReleased -LocalPorts @($DatabasePort) -TimeoutSeconds 15)) {
    Show-PortOccupants -LocalPorts @($DatabasePort) -Prefix "Database port still occupied"
    Fail "Port $DatabasePort is still occupied after docker compose down. Refusing to kill a non-Docker database process."
}
Write-Host "Database port released: $DatabasePort." -ForegroundColor Green

Write-Step "Starting PostgreSQL container"
& docker compose up -d postgres
if ($LASTEXITCODE -ne 0) {
    & docker compose ps
    & docker compose logs --tail 80 postgres
    Fail "docker compose up -d postgres failed."
}

Write-Step "Waiting for PostgreSQL to become healthy"
if (-not (Wait-ContainerHealthy -ContainerName "auditpilot-postgres" -TimeoutSeconds $PostgresWaitSeconds)) {
    & docker compose ps
    & docker compose logs --tail 120 postgres
    Fail "PostgreSQL did not become healthy in time."
}
Write-Host "PostgreSQL is ready on port 5432." -ForegroundColor Green

if (-not $reuseExistingBackend) {
    Write-Step "Starting backend in a new PowerShell window"
    $reloadArg = if ($BackendReload) { " --reload" } else { "" }
    $backendCommand = "Set-Location -LiteralPath $QuotedBackendDir; python -m uvicorn app.main:app$reloadArg --host 0.0.0.0 --port 8000"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCommand | Out-Null
} else {
    Write-Step "Reusing existing healthy backend listener"
}

Write-Step "Starting frontend in a new PowerShell window"
$frontendCommand = "Set-Location -LiteralPath $QuotedRoot; npm run dev:frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCommand | Out-Null

Write-Host ""
Write-Host "Startup complete." -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/docs"
