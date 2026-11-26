# Starts StudyPilot: backend (port 8000) and frontend (port 5173) in two windows,
# then opens the app in your browser.  Run from the studypilot folder:  .\start.ps1
$root = $PSScriptRoot

# stop any old backend still holding port 8000
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root\backend'; .\.venv\Scripts\uvicorn main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "cd '$root\frontend'; npm run dev"

Start-Sleep -Seconds 6
Start-Process "http://localhost:5173"
Write-Host "StudyPilot is starting. Backend: http://localhost:8000/health  App: http://localhost:5173"
