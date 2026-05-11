param(
    [int[]]$AppPorts = @(3000, 8000),
    [int]$DatabasePort = 5432
)

$ErrorActionPreference = "Stop"

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Warn($Message) {
    Write-Host "WARNING: $Message" -ForegroundColor Yellow
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
Set-Location -LiteralPath $Root

Write-Step "Stopping Docker stack"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    & docker compose down
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "docker compose down failed. Continuing with direct port cleanup."
    }
} else {
    Write-Warn "docker command not found. Skipping docker compose down."
}

Write-Step "Stopping existing project runtime processes"
Stop-ProjectRuntimeProcesses -ProjectRoot $Root

Write-Step "Stopping processes occupying local ports"
Stop-PortProcesses -LocalPorts $AppPorts

if (-not (Wait-PortsReleased -LocalPorts $AppPorts -TimeoutSeconds 30)) {
    Show-PortOccupants -LocalPorts $AppPorts -Prefix "App ports still occupied after cleanup"
    Write-Warn "Some app ports are still busy after cleanup."
} else {
    Write-Host "App ports released: $($AppPorts -join ', ')." -ForegroundColor Green
}

Write-Step "Checking database port"
if (-not (Wait-PortsReleased -LocalPorts @($DatabasePort) -TimeoutSeconds 15)) {
    Show-PortOccupants -LocalPorts @($DatabasePort) -Prefix "Database port still occupied"
    Write-Warn "Port $DatabasePort is still busy after docker compose down. This is likely an external PostgreSQL or another service."
} else {
    Write-Host "Database port released: $DatabasePort." -ForegroundColor Green
}

Write-Host ""
Write-Host "Stop complete." -ForegroundColor Green
