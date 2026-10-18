[CmdletBinding()]
param(
    [string]$PythonPath = "D:\python\python.exe",
    [int]$Port = 8010,
    [string]$ProjectRoot = ""
)

$ProjectRoot = if ($ProjectRoot) { $ProjectRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ServiceUrl = "http://127.0.0.1:$Port"
$LogDir = Join-Path $ProjectRoot "outputs\service_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-Ts($Msg, $Color = "White") {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $Msg" -ForegroundColor $Color
}

function Test-Health {
    $homeOk = $false
    $titleOk = $false
    try {
        $resp = Invoke-WebRequest -Uri "$ServiceUrl/" -TimeoutSec 5 -UseBasicParsing
        $homeOk = $resp.StatusCode -eq 200
    } catch {}
    try {
        $api = Invoke-RestMethod -Uri "$ServiceUrl/openapi.json" -TimeoutSec 5
        if ($api.info.title -eq "us_ratchet") { $titleOk = $true }
    } catch {}
    return ($homeOk -and $titleOk)
}

# Step 1: Health check
Write-Ts "Checking if service is already running..." Cyan

if (Test-Health) {
    Write-Ts "us_ratchet is already running ($ServiceUrl)" Green
    Write-Host "RESULT=already_running"
    Write-Host "URL=$ServiceUrl"
    exit 0
}

# Step 2: Port check
Write-Ts "Health check failed, checking port $Port..." Yellow

try {
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listeners) {
        $ownerPids = @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)
        $ownerProcs = @(Get-CimInstance Win32_Process -Filter "ProcessId IN ($($ownerPids -join ','))" -ErrorAction SilentlyContinue)
        $known = $false
        foreach ($proc in $ownerProcs) {
            if ($proc.Name -match '^python(?:w)?\.exe$' -and $proc.CommandLine -match 'api\.server') {
                $known = $true
            }
        }
        if (-not $known) {
            Write-Ts "Port $Port occupied by unknown process (PID: $($ownerPids -join ','))" Red
            Write-Host "RESULT=port_conflict"
            Write-Host "OWNER_PIDS=$($ownerPids -join ',')"
            exit 1
        }
        Write-Ts "Port owned by known process but health check failed. Restarting..." Yellow
        $ownerPids | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
    }
} catch {
    Write-Ts "Port check error: $($_.Exception.Message)" Yellow
}

# Step 3: Start service
Write-Ts "Starting us_ratchet service..." Cyan

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$stdoutLog = Join-Path $LogDir "server_${ts}.stdout.log"
$stderrLog = Join-Path $LogDir "server_${ts}.stderr.log"
$pidFile = Join-Path $LogDir "server_${ts}.pid"

$python = (Get-Command $PythonPath -ErrorAction Stop).Source

try {
    $process = Start-Process -FilePath $python `
        -ArgumentList @('-B', '-m', 'api.server', '--host', '127.0.0.1', '--port', "$Port") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru

    $process.Id | Out-File -FilePath $pidFile -Encoding ascii
    Write-Ts "Process started, PID: $($process.Id)" Cyan

    # Step 4: Wait and verify
    Start-Sleep -Seconds 5

    if (Test-Health) {
        Write-Ts "us_ratchet started successfully" Green
        Write-Host "RESULT=started"
        Write-Host "PID=$($process.Id)"
        Write-Host "URL=$ServiceUrl"
        Write-Host "LOG_DIR=$LogDir"
        Write-Host "STDOUT=$stdoutLog"
        Write-Host "STDERR=$stderrLog"
        Write-Host "TIME=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
        exit 0
    } else {
        Write-Ts "Health check failed after startup" Red
        $tail = if (Test-Path -LiteralPath $stderrLog) {
            (Get-Content -Tail 30 -LiteralPath $stderrLog) -join "`n"
        } else { "(no stderr log)" }
        Write-Host "RESULT=start_failed"
        Write-Host "STDERR_TAIL=$tail"
        exit 1
    }
} catch {
    Write-Ts "Startup exception: $($_.Exception.Message)" Red
    Write-Host "RESULT=fatal_error"
    Write-Host "ERROR=$($_.Exception.Message)"
    exit 1
}
