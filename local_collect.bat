@echo off
setlocal
cd /d "%~dp0"
set "SCHEDULED_MODE=0"
if /I "%~1"=="--scheduled" set "SCHEDULED_MODE=1"

where python >nul 2>nul
if not errorlevel 1 (
  python local_collect.py
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    echo Python을 찾을 수 없습니다. Python 설치 후 다시 실행해주세요.
    pause
    exit /b 1
  )
  py -3 local_collect.py
)
if errorlevel 1 (
  echo 로컬 자동수집 실행 중 오류가 발생했습니다.
  if "%SCHEDULED_MODE%"=="0" pause
  exit /b 1
)

echo 로컬 자동수집이 완료되었습니다.
if "%SCHEDULED_MODE%"=="0" pause
exit /b 0
