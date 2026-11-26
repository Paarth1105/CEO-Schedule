@echo off
:: Check Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges to restart CEO Schedule service...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo ========================================================
echo Updating and Restarting CEO Schedule on Port 5000...
echo ========================================================

echo [1/6] Pulling latest updates from GitHub...
cd /d "C:\Apps\CEO-Schedule"
git pull origin main

echo [2/6] Running automated backup...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe auto_backup.py
) else (
    python auto_backup.py
)

echo [3/6] Running safe database schema migrations...
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe migrations\migrate_multi_role.py upgrade
) else (
    python migrations\migrate_multi_role.py upgrade
)

echo [4/6] Stopping existing services and freeing port 5000...
net stop CEOScheduleApp >nul 2>&1
net stop CEOScheduleService >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo [5/6] Starting CEOScheduleApp service...
net start CEOScheduleApp

timeout /t 3 >nul

echo [6/6] Verifying port 5000 and testing live endpoint...
netstat -ano | findstr :5000
if %errorlevel% neq 0 (
    echo Service port binding pending, starting runner...
    start "" wscript.exe "C:\Apps\CEO-Schedule\run_ceoschedule.vbs"
    timeout /t 3 >nul
)

curl.exe -I http://127.0.0.1:5000

echo ========================================================
echo CEO Schedule is LIVE with all latest updates!
echo Public URL: https://ceoschedule.website
echo Local URL:  http://127.0.0.1:5000
echo ========================================================
pause
