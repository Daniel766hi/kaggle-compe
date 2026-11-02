# Hermes Agent setup for this repo on Windows. In PowerShell, from the repo folder:
#
#   powershell -ExecutionPolicy Bypass -File .\hermes\install.ps1
#
# Installs only what's missing: Hermes Agent, the GitHub CLI and the Python packages (Kaggle CLI).
# Logs you in to GitHub and Kaggle, installs the persona (SOUL.md) and this repo's skills, and can
# add a daily 09:00 WIB health check. Safe to run again: it updates the skills and skips the rest.

# "Continue": winget and pip print progress to stderr, which "Stop" would treat as a failure.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Repo = Split-Path $PSScriptRoot -Parent
Set-Location $Repo
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA "hermes" }

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Have($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Ask($q) { (Read-Host "$q [y/N]") -match '^[Yy]' }
function RefreshPath {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
}
function WingetInstall($id) {
    if (-not (Have winget)) { throw "winget is missing. Install 'App Installer' from the Microsoft Store, then run this again." }
    winget install -e --id $id --accept-package-agreements --accept-source-agreements
    RefreshPath
}

Step "Hermes Agent"
if (-not (Have hermes)) {
    Invoke-Expression (Invoke-RestMethod https://hermes-agent.nousresearch.com/install.ps1)
    RefreshPath
    if (-not (Have hermes)) { Write-Host "Hermes is installed. Open a new PowerShell window and run this script again."; exit 0 }
}
hermes --version

Step "GitHub CLI"
if (-not (Have gh)) { WingetInstall "GitHub.cli" }
if (-not (Have git)) { WingetInstall "Git.Git" }
gh auth status *> $null
if ($LASTEXITCODE) { gh auth login --web --git-protocol https }
gh auth setup-git
gh auth status

Step "Python packages (includes the Kaggle CLI)"
if (-not (Have python)) { WingetInstall "Python.Python.3.12" }
if (-not (Test-Path ".venv")) { python -m venv .venv }
$Py = Join-Path $Repo ".venv\Scripts\python.exe"
& $Py -m pip install --quiet --upgrade pip
& $Py -m pip install --quiet -r requirements.txt
$Kaggle = Join-Path $Repo ".venv\Scripts\kaggle.exe"

Step "Kaggle login"
& $Kaggle datasets list -m *> $null
if ($LASTEXITCODE) {
    Write-Host "kaggle.com -> Settings -> API -> Generate New Token, then copy the token."
    Start-Process "https://www.kaggle.com/settings"
    $secure = Read-Host "Paste your Kaggle API token (hidden)" -AsSecureString
    $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    $dir = Join-Path $env:USERPROFILE ".kaggle"
    New-Item -ItemType Directory -Force $dir | Out-Null
    [IO.File]::WriteAllText((Join-Path $dir "access_token"), $token)
    Remove-Variable token, secure
}
& $Kaggle datasets list -m *> $null
if ($LASTEXITCODE) { Write-Host "Kaggle didn't accept the token. Generate a new one and run this again." -ForegroundColor Yellow }
else { Write-Host "Kaggle works." -ForegroundColor Green }

Step "Persona (SOUL.md) and skills"
New-Item -ItemType Directory -Force (Join-Path $HermesHome "skills") | Out-Null
$soul = Join-Path $HermesHome "SOUL.md"
if ((Test-Path $soul) -and ((Get-FileHash $soul).Hash -ne (Get-FileHash "hermes\SOUL.md").Hash)) {
    Copy-Item $soul "$soul.bak" -Force
    Write-Host "Your previous SOUL.md is saved as SOUL.md.bak"
}
Copy-Item "hermes\SOUL.md" $soul -Force
$skills = Join-Path $HermesHome "skills\kaggle-compe"
if (Test-Path $skills) { Remove-Item $skills -Recurse -Force }
Copy-Item "hermes\skills" $skills -Recurse
Write-Host ("Installed skills: " + ((Get-ChildItem "hermes\skills" -Directory).Name -join " "))

Step "Safety settings"
hermes config set approvals.mode manual
hermes config set approvals.cron_mode deny
Write-Host "For the force-push deny list, paste the approvals block from hermes\config-snippet.yaml into 'hermes config edit'."

Step "AI model (the agent's brain)"
Write-Host "Closest to Claude Code: Anthropic with an API key (console.anthropic.com). Free option: Gemini."
if (Ask "Choose the model now?") { hermes model }

Step "Daily health check (optional)"
if (Ask "Add a 09:00 WIB check of GitHub Actions and Kaggle datasets?") {
    hermes cron create "0 9 * * *" --timezone Asia/Jakarta `
        "Run the daily-repo-check skill for this repository and report the result." `
        --skill daily-repo-check --name "kaggle-compe morning check" --workdir "$Repo"
    Write-Host "Scheduled jobs run inside the Hermes gateway. Keeping it running in the background:"
    hermes gateway install
    if ($LASTEXITCODE) { Write-Host "Run 'hermes gateway' yourself when you want the jobs to run." }
}

Step "Done"
Write-Host "Start Hermes from the repo so it reads AGENTS.md:"
Write-Host "  cd `"$Repo`"; hermes"
Write-Host "Then try:  /careful-engineer run the tests and tell me what's failing"
