@echo off
setlocal
cd /d "%~dp0"

set "SCHEDULED_MODE=0"
if /I "%~1"=="--scheduled" set "SCHEDULED_MODE=1"
if "%SCHEDULED_MODE%"=="0" (
  echo [INFO] Reading the currently open Naver Real Estate Chrome tab.
  echo [INFO] Run start_chrome_debug.bat first and keep the results tab open.
) else (
  echo [INFO] Scheduled CDP collection mode is enabled.
)

where python >nul 2>nul
if not errorlevel 1 (
  python -c "import playwright" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Playwright is not installed.
    echo Run these commands once:
    echo python -m pip install -r requirements.txt
    echo python -m playwright install chromium
    if "%SCHEDULED_MODE%"=="0" pause
    exit /b 1
  )
  python local_collect.py
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python and try again.
    if "%SCHEDULED_MODE%"=="0" pause
    exit /b 1
  )
  py -3 -c "import playwright" >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] Playwright is not installed.
    echo Run these commands once:
    echo py -3 -m pip install -r requirements.txt
    echo py -3 -m playwright install chromium
    if "%SCHEDULED_MODE%"=="0" pause
    exit /b 1
  )
  py -3 local_collect.py
)

if errorlevel 1 (
  echo [ERROR] Local collection failed.
  if "%SCHEDULED_MODE%"=="0" pause
  exit /b 1
)

echo [SUCCESS] Collection completed and GitHub sync completed.
if "%SCHEDULED_MODE%"=="0" pause
exit /b 0
