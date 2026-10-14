@echo off
:: Check Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator privileges to restart CEO Schedule service...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process cmd.exe -ArgumentList '/c \"\"%~f0\"\"' -Verb RunAs"
    exit /b
)

echo ========================================================
echo Updating and Restarting CEO Schedule on Port 5005...
echo ========================================================

echo [1/5] Pulling latest updates from GitHub...
cd /d "C:\Apps\CEO-Schedule"
git pull origin main

echo [2/5] Stopping existing services and freeing port 5005...
net stop CEOScheduleApp >nul 2>&1
net stop CEOScheduleService >nul 2>&1
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 5005 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo [3/5] Starting CEOScheduleApp service...
net start CEOScheduleApp

timeout /t 3 >nul

echo [4/5] Verifying port 5005...
netstat -ano | findstr :5005
if %errorlevel% neq 0 (
    echo Service port binding pending, starting runner...
    start "" wscript.exe "C:\Apps\CEO-Schedule\run_ceoschedule.vbs"
    timeout /t 3 >nul
)

echo [5/5] Testing live HTTP endpoint...
curl.exe -I http://127.0.0.1:5005

echo ========================================================
echo CEO Schedule is LIVE with all latest updates!
echo Public URL: https://ceoschedule.website
echo Local URL:  http://127.0.0.1:5005
echo ========================================================
pause
