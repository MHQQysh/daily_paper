param(
    [string]$StartDate = "",
    [string]$EndDate = "",
    [int]$PapersPerTopic = 5,
    [switch]$NoDeepSeek
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $StartDate) {
    $StartDate = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
}
if (-not $EndDate) {
    $EndDate = (Get-Date).AddDays(-1).ToString("yyyy-MM-dd")
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
    "--start-date", $StartDate,
    "--end-date", $EndDate,
    "--papers-per-topic", "$PapersPerTopic"
)

Write-Host "Running local date-range update..."
Write-Host "StartDate=$StartDate EndDate=$EndDate PapersPerTopic=$PapersPerTopic Mode=append-only"
python @argsList

Write-Host ""
Write-Host "Done. Open local site:"
Write-Host "  http://127.0.0.1:8766/"
Write-Host ""
Write-Host "If the server is not running, start it with:"
Write-Host "  python -m http.server 8766 --directory docs"
