# Paper-trading bot (Freqtrade) for Windows. Easiest: double-click trading.cmd, or in PowerShell:
#   .\trading.ps1 setup      once: checks Docker, makes the dashboard password, downloads price history
#   .\trading.ps1 backtest   tests the strategy on the last year of prices and prints the results
#   .\trading.ps1 start      starts paper trading (fake money, live prices) and the dashboard
#   .\trading.ps1 stop       stops it
#   .\trading.ps1 status     is it running? the last lines of its log
param([string]$Command = "menu")
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$ft = "/freqtrade/user_data/config.json"
# The strategy the trading lab picked, at the exact version it tested (NostalgiaForInfinity, GPL-3.0).
$nfiCommit = "c2e427d354131833ddacd1203b06166a959d30ad"
$nfiFile = "user_data\strategies\NostalgiaForInfinityX8.py"

function GetStrategy {
    $stamp = "user_data\strategies\.nfi-version"
    if ((Test-Path $nfiFile) -and (Test-Path $stamp) -and ((Get-Content $stamp) -eq $nfiCommit)) { return }
    Write-Host "Downloading the NostalgiaForInfinity X8 strategy (the version the lab tested)..."
    Invoke-WebRequest "https://raw.githubusercontent.com/iterativv/NostalgiaForInfinity/$nfiCommit/NostalgiaForInfinityX8.py" -OutFile $nfiFile -ErrorAction Stop
    Set-Content $stamp $nfiCommit
}

function NeedDocker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "Freqtrade runs in Docker Desktop (free). Installing it now; afterwards restart the computer," -ForegroundColor Cyan
        Write-Host "open Docker Desktop once (accept its terms), then run this again."
        winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
        exit 1
    }
    docker info *> $null
    if ($LASTEXITCODE) { Write-Host "Open Docker Desktop and wait until it says 'Engine running', then try again." -ForegroundColor Yellow; exit 1 }
}

function NewSecret($bytes) {
    $b = New-Object byte[] $bytes
    [System.Security.Cryptography.RNGCryptoServiceProvider]::new().GetBytes($b)
    ([BitConverter]::ToString($b) -replace "-", "").ToLower()
}

function Password { ((Get-Content .env | Select-String "^FREQTRADE__API_SERVER__PASSWORD=(.*)").Matches[0].Groups[1].Value) }

function Setup {
    NeedDocker
    if (-not (Test-Path .env)) {
        @(
            "FREQTRADE__API_SERVER__JWT_SECRET_KEY=$(NewSecret 32)",
            "FREQTRADE__API_SERVER__WS_TOKEN=$(NewSecret 16)",
            "FREQTRADE__API_SERVER__PASSWORD=$(NewSecret 8)"
        ) | Set-Content .env -Encoding ascii
        Write-Host "Made the dashboard password (kept in trading\.env)."
    }
    GetStrategy
    docker compose pull
    Write-Host "Downloading a year of prices (public data, no account needed; takes a while)..." -ForegroundColor Cyan
    docker compose run --rm freqtrade download-data --config $ft --timeframes 5m --days 380
    docker compose run --rm freqtrade download-data --config $ft --timeframes 15m 1h 4h 1d --days 600
    if ($LASTEXITCODE) {
        Write-Host "The download failed. If the exchange is blocked on your network, open user_data\config.json," -ForegroundColor Yellow
        Write-Host "change ""name"": ""binance"" to ""okx"" or ""kucoin"", and run setup again."
        exit 1
    }
    Write-Host "Ready. Next: .\trading.ps1 backtest   then   .\trading.ps1 start" -ForegroundColor Green
}

function Backtest {
    NeedDocker
    GetStrategy
    $from = (Get-Date).AddDays(-365).ToString("yyyyMMdd")
    Write-Host "Backtesting the last year. NostalgiaForInfinity is heavy: this can take 30-60 minutes." -ForegroundColor Cyan
    docker compose run --rm freqtrade backtesting --config $ft --strategy NostalgiaForInfinityX8 --timerange "$from-" --export trades
    Write-Host "`nRead it like this: 'Tot Profit %' is the result, 'Max Drawdown' the worst fall on the way, 'Win%' the share of"
    Write-Host "winning trades. Compare with simply holding BTC ('Market change'). Past results don't promise future ones."
}

function Start-Bot {
    NeedDocker
    if (-not (Test-Path .env)) { Setup }
    GetStrategy
    docker compose up -d
    Write-Host "Paper trading is running (fake money, real prices). It keeps running in Docker until you stop it." -ForegroundColor Green
    Write-Host "Dashboard: http://127.0.0.1:8080   user: freqtrader   password: $(Password)"
    Start-Process "http://127.0.0.1:8080"
}

switch ($Command) {
    "setup" { Setup }
    "backtest" { Backtest }
    "start" { Start-Bot }
    "stop" { docker compose down; Write-Host "Stopped." }
    "status" { docker compose ps; docker compose logs --tail 20 }
    default {
        Write-Host "Paper-trading bot (Freqtrade): fake money, real prices."
        Write-Host "  1  Set up (first time)     2  Backtest the last year     3  Start paper trading"
        Write-Host "  4  Stop                    5  Status"
        switch (Read-Host "Choose 1-5") { "1" { Setup } "2" { Backtest } "3" { Start-Bot } "4" { docker compose down } "5" { docker compose ps; docker compose logs --tail 20 } }
    }
}
