@echo off
setlocal enabledelayedexpansion

REM Auralyx One-Click Runner
REM 1) Kill old processes
REM 2) Prepare env
REM 3) Install deps
REM 4) Run bot

set "BOT_DIR=%~dp0"
cd /d "%BOT_DIR%"

if not exist "logs" mkdir logs
if not exist ".cache" mkdir .cache

echo [1/4] Killing old processes...
REM Kill common bot-related processes (ignore errors if not running)
taskkill /F /IM python.exe >nul 2>&1
taskkill /F /IM py.exe >nul 2>&1
taskkill /F /IM ffmpeg.exe >nul 2>&1

REM Remove stale PID lock from previous crash
if exist ".cache\bot.pid" del /f /q ".cache\bot.pid" >nul 2>&1

echo [2/4] Selecting Python...
set "PY_CMD="
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY_CMD=py"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY_CMD=python"
    )
)

if "%PY_CMD%"=="" (
    echo [FAIL] Python not found in PATH.
    pause
    exit /b 1
)

echo [3/4] Installing/updating dependencies...
%PY_CMD% -m pip install --disable-pip-version-check -r requirements.txt > logs\setup.log 2>&1
if %errorlevel% neq 0 (
    echo [WARN] Dependency install had issues. See logs\setup.log
)

echo [4/4] Starting bot from root: %BOT_DIR%
echo --------------------------------------------------

:run
%PY_CMD% main.py
set "EXIT_CODE=%errorlevel%"

if "%EXIT_CODE%"=="0" (
    echo [INFO] Bot exited normally.
    goto :end
)

if "%EXIT_CODE%"=="2" (
    echo [INFO] Restart requested by bot.
    timeout /t 2 /nobreak >nul
    goto :run
)

echo [WARN] Bot crashed with code %EXIT_CODE%. Restarting in 5s...
timeout /t 5 /nobreak >nul
goto :run

:end
echo Done.
pause
exit /b 0
