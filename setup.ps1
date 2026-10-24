# AI Office: one-time setup for Windows, then it starts the office.
#
# In the repo folder, right-click this file > "Run with PowerShell", or in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# It installs (only what's missing): Python, ffmpeg and Git. It asks for your free Gemini key (the
# team's brain) and your free Cloudflare keys (AI pictures for the videos), and whether you want the
# office on your phone. Without a Gemini key it installs Ollama and a local AI model instead.
# Keys are saved in .env (never committed). Safe to run again; it skips what's already done.

# "Continue": tools like winget and ollama print progress to stderr, which "Stop" would treat as a
# failure in Windows PowerShell 5.1. Real failures are checked explicitly below.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function WingetInstall($id) {
    if (-not (Have winget)) { throw "winget is missing. Install 'App Installer' from the Microsoft Store, then run this again." }
    winget install -e --id $id --accept-package-agreements --accept-source-agreements
}
function Check($what) { if ($LASTEXITCODE) { throw "$what failed (exit code $LASTEXITCODE). Fix the message above and run this again." } }
function RefreshPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}

Step "Python"
$python = $null
foreach ($candidate in @("py", "python")) {
    if (Have $candidate) {
        $version = try { & $candidate --version 2>&1 } catch { "" }
        if ("$version" -match "Python 3\.(1[0-9])") { $python = $candidate; break }
    }
}
if (-not $python) {
    WingetInstall "Python.Python.3.12"
    RefreshPath
    $python = if (Have py) { "py" } else { "python" }
}
Write-Host "Using $(& $python --version)"
if (-not (Test-Path ".venv")) { & $python -m venv .venv; Check "Creating .venv" }
$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r requirements.txt; Check "Installing the Python packages"

Step "ffmpeg (joins video clips)"
if (-not (Have ffmpeg)) { WingetInstall "Gyan.FFmpeg"; RefreshPath }
if (Have ffmpeg) { Write-Host "ffmpeg is ready" } else { Write-Host "ffmpeg installed; it will be found after you reopen PowerShell." }

Step "Gemini (the team's free AI brain)"
$gemini = & $venvPython -m local_env get GEMINI_API_KEY
while (-not $gemini) {
    Write-Host "Opening Google AI Studio: sign in with your Google account and click 'Create API key' (free, no card)."
    Start-Process "https://aistudio.google.com/apikey"
    $gemini = (Read-Host "Paste your Gemini API key (or press Enter to use a local AI on this computer instead)").Trim()
    if (-not $gemini) { break }
    try {
        Invoke-RestMethod "https://generativelanguage.googleapis.com/v1beta/models?key=$gemini" -ErrorAction Stop | Out-Null
        & $venvPython -m local_env set GEMINI_API_KEY $gemini
        Write-Host "Gemini works and the key is saved in .env" -ForegroundColor Green
    } catch {
        Write-Host "Google didn't accept that key. Copy it again from aistudio.google.com/apikey." -ForegroundColor Yellow
        $gemini = $null
    }
}

if (-not $gemini) {
    Step "Ollama (a free local AI, instead of Gemini)"
    $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollama) {
        WingetInstall "Ollama.Ollama"
        RefreshPath
        $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
        if (-not $ollama) { $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
    }
    function OllamaUp { try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null; $true } catch { $false } }
    if (-not (OllamaUp)) {
        Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
        foreach ($i in 1..30) { if (OllamaUp) { break }; Start-Sleep 1 }
    }
    if (-not (OllamaUp)) { throw "Ollama didn't start. Open the Ollama app from the Start menu, then run this again." }

    $ramGB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    $model = if ($ramGB -ge 15) { "qwen3:8b" } elseif ($ramGB -ge 7) { "qwen3:4b" } else { "qwen3:1.7b" }
    $saved = & $venvPython -m local_env get OLLAMA_MODEL
    if ($saved) { $model = $saved }
    Write-Host "This computer has $ramGB GB of RAM: using $model (download once, a few GB)"
    & $ollama pull $model; Check "Downloading $model"
    & $venvPython -m local_env set OLLAMA_MODEL $model
}

Step "Cloudflare (free AI pictures for the videos)"
$cfAccount = & $venvPython -m local_env get CLOUDFLARE_ACCOUNT_ID
$cfToken = & $venvPython -m local_env get CLOUDFLARE_API_TOKEN
while (-not ($cfAccount -and $cfToken)) {
    Write-Host "Opening Cloudflare: sign up or log in (free, no card). Then:"
    Write-Host "  1. In the left menu open 'AI' > 'Workers AI' and click 'Use REST API'."
    Write-Host "  2. Copy the Account ID shown there."
    Write-Host "  3. Click 'Create a Workers AI API Token', then 'Create API Token', and copy the token."
    Start-Process "https://dash.cloudflare.com/sign-up"
    $cfAccount = (Read-Host "Paste your Account ID (or press Enter to skip and use stock clips)").Trim()
    if (-not $cfAccount) { break }
    $cfToken = (Read-Host "Paste your Workers AI API token").Trim()
    try {
        Invoke-RestMethod "https://api.cloudflare.com/client/v4/accounts/$cfAccount/ai/models/search?per_page=1" -Headers @{ Authorization = "Bearer $cfToken" } -ErrorAction Stop | Out-Null
        & $venvPython -m local_env set CLOUDFLARE_ACCOUNT_ID $cfAccount
        & $venvPython -m local_env set CLOUDFLARE_API_TOKEN $cfToken
        Write-Host "Cloudflare works: videos will be drawn as AI pictures (about 60 free pictures a day)." -ForegroundColor Green
    } catch {
        Write-Host "Cloudflare didn't accept those. Check the Account ID and that the token has the Workers AI permission." -ForegroundColor Yellow
        $cfAccount = $null; $cfToken = $null
    }
}

if (-not ($cfAccount -and $cfToken)) {
    Step "Pixabay (free stock video clips)"
    $key = & $venvPython -m local_env get PIXABAY_API_KEY
    if (-not $key) { $key = & $venvPython -m local_env get PEXELS_API_KEY }  # an older Pexels key still works
    while (-not $key) {
        Write-Host "Opening Pixabay: sign up or log in (free). Then open pixabay.com/api/docs and find"
        Write-Host "'key (required)' under Parameters: your key is shown right there (green text)."
        Start-Process "https://pixabay.com/accounts/register/"
        Start-Process "https://pixabay.com/api/docs/#api_search_videos"
        $key = (Read-Host "Paste your Pixabay API key (or press Enter to skip for now)").Trim()
        if (-not $key) { Write-Host "Skipped. Video rendering needs it; run this script again any time."; break }
        try {
            Invoke-RestMethod "https://pixabay.com/api/videos/?key=$key&q=cat&per_page=3" -ErrorAction Stop | Out-Null
            & $venvPython -m local_env set PIXABAY_API_KEY $key
            Write-Host "Key works and is saved in .env" -ForegroundColor Green
            $ghStatus = if (Have gh) { try { "$(gh auth status 2>&1)" } catch { "" } } else { "" }
            if ($ghStatus -match "Logged in") {
                if ((Read-Host "Also save it as a GitHub secret for the daily video runs? (y/n)") -eq "y") {
                    $key | gh secret set PIXABAY_API_KEY
                }
            }
        } catch {
            Write-Host "Pixabay didn't accept that key. Copy it again from pixabay.com/api/docs." -ForegroundColor Yellow
            $key = $null
        }
    }
}

Step "Your phone"
$phoneMode = & $venvPython -m local_env get OFFICE_PHONE
if (-not $phoneMode) {
    Write-Host "You can open the office on your phone too (this computer has to stay on):"
    Write-Host "  wifi     - when your phone is on the same Wi-Fi"
    Write-Host "  anywhere - from anywhere, even on mobile data (a free Cloudflare tunnel)"
    Write-Host "  no       - only on this computer"
    $phoneMode = (Read-Host "Which one? (wifi / anywhere / no)").Trim().ToLower()
    if ($phoneMode -notin @("wifi", "anywhere")) { $phoneMode = "no" }
    & $venvPython -m local_env set OFFICE_PHONE $phoneMode
}
if ($phoneMode -eq "anywhere" -and -not (Have cloudflared)) { WingetInstall "Cloudflare.cloudflared"; RefreshPath }
if ($phoneMode -ne "no") { Write-Host "When the office opens, click 'Phone' at the top and scan the QR code with your phone." }

Step "GitHub link (Sync with GitHub, and updates)"
$repo = "https://github.com/Daniel766hi/kaggle-compe.git"
if (-not (Have git)) { WingetInstall "Git.Git"; RefreshPath }
if (-not (Have git)) { Write-Host "Git installed; it will be found after you reopen PowerShell. Run this script again then." }
elseif (-not (Test-Path ".git")) {
    # A folder from a ZIP: make it a GitHub copy in place. Your .env, plans, chats and videos stay.
    git init --quiet
    git remote add origin $repo
    $branch = (git ls-remote --symref origin HEAD | Select-String "ref: refs/heads/(\S+)").Matches[0].Groups[1].Value
    git fetch --quiet origin $branch; Check "Downloading from GitHub"
    git symbolic-ref HEAD "refs/heads/$branch"
    git reset --quiet --mixed "origin/$branch"
    # The ZIP may be older than GitHub: take the latest code, keep your own plans in content/.
    git restore --source=HEAD --worktree -- . ":(exclude)content"
    git branch --quiet --set-upstream-to="origin/$branch"
    Write-Host "This folder is now linked to GitHub ($branch)." -ForegroundColor Green
}
if ((Have git) -and (Test-Path ".git") -and -not (git config user.email)) {
    git config user.name "AI Office"
    git config user.email "ai-office@users.noreply.github.com"
}
if (Test-Path ".git") {
    Write-Host "'Sync with GitHub' in the office now works. The first time it pushes, a GitHub login window opens: sign in."
}

Step "Starting the AI Office"
Write-Host "Next time, just run .\start-office.ps1"
& $venvPython -m office
