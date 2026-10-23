# AI Office: one-time setup for Windows, then it starts the office.
#
# In the repo folder, right-click this file > "Run with PowerShell", or in PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#
# It installs (only what's missing): Python, ffmpeg, Git, Ollama and a free local AI model sized for
# this computer. It asks for your free Pixabay key, saves keys in .env (never committed), and
# opens the office. Safe to run again; it skips what's already done.

# "Continue": tools like winget and ollama print progress to stderr, which "Stop" would treat as a
# failure in Windows PowerShell 5.1. Real failures are checked explicitly below.
$ErrorActionPreference = "Continue"
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

Step "Ollama (the free local AI)"
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
