# Open the AI Office (after setup.ps1 has run once). Right-click > "Run with PowerShell".
Set-Location $PSScriptRoot
try { Invoke-RestMethod "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null }
catch { Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
& ".\.venv\Scripts\python.exe" -m office
