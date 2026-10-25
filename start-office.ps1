# Open the AI Office (after setup.ps1 has run once). Easiest: double-click start-office.cmd.
# On your phone too: set OFFICE_PHONE in .env to wifi or anywhere (setup.ps1 asks), or run
#   .\start-office.ps1 -Phone      (same Wi-Fi)      .\start-office.ps1 -Anywhere   (anywhere)
param([switch]$Phone, [switch]$Anywhere)
Set-Location $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$py = ".\.venv\Scripts\python.exe"
if (-not (& $py -m local_env get GEMINI_API_KEY)) {  # the local AI needs Ollama running
    try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null }
    catch { Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
}
$flags = @()
if ($Phone) { $flags += "--phone" }
if ($Anywhere) { $flags += "--anywhere" }
& $py -m office @flags
