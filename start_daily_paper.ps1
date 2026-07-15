$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerScript = Join-Path $Root "scripts\local_server.py"
$Url = "http://127.0.0.1:8766/"
$StatusUrl = "http://127.0.0.1:8766/api/status"

function Test-DailyPaperApi {
    try {
        $status = Invoke-RestMethod -Uri $StatusUrl -TimeoutSec 1
        return $null -ne $status.state
    } catch {
        return $false
    }
}

if (-not (Test-DailyPaperApi)) {
    $listener = Get-NetTCPConnection -LocalPort 8766 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        $isOldDailyPaperServer = $process.CommandLine -match '-m\s+http\.server\s+8766(?:\s|$)'
        if (-not $isOldDailyPaperServer) {
            throw "Port 8766 is occupied by another program. Close process $($listener.OwningProcess) and try again."
        }
        Stop-Process -Id $listener.OwningProcess -Force
        Start-Sleep -Milliseconds 500
    }

    $pythonw = Get-Command pythonw -ErrorAction SilentlyContinue
    $pythonExecutable = if ($pythonw) { $pythonw.Source } else { (Get-Command python).Source }
    Start-Process -FilePath $pythonExecutable -ArgumentList @($ServerScript) -WorkingDirectory $Root -WindowStyle Hidden

    $ready = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 250
        if (Test-DailyPaperApi) {
            $ready = $true
            break
        }
    }
    if (-not $ready) {
        throw "Daily Paper local server did not start."
    }
}

Start-Process $Url
