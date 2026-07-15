param(
    [string]$Date = "",
    [int]$PapersPerTopic = 5,
    [switch]$NoDeepSeek
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Date) {
    $Date = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
}

if (-not $NoDeepSeek -and -not $env:DEEPSEEK_API_KEY) {
    $secure = Read-Host "DeepSeek API key (input hidden, Enter to skip)" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    if ($plain) {
        $env:DEEPSEEK_API_KEY = $plain
    }
}

$argsList = @(
    "scripts\fetch_papers.py",
    "--date", $Date,
    "--papers-per-topic", "$PapersPerTopic"
)

Write-Host "Running local one-day update..."
Write-Host "Date=$Date PapersPerTopic=$PapersPerTopic Mode=append-only"
python @argsList

Write-Host ""
Write-Host "Done. Open local site:"
Write-Host "  http://127.0.0.1:8766/"
Write-Host ""
Write-Host "If the server is not running, start it with:"
Write-Host "  python -m http.server 8766 --directory docs"
