@echo off
setlocal
cd /d "%~dp0"

set "PROFILE=%~dp0chrome_profile"
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
  echo [ERROR] Google Chrome was not found.
  pause
  exit /b 1
)

if not exist "%PROFILE%" mkdir "%PROFILE%"

echo [INFO] Starting Chrome remote debugging on port 9222.
start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%PROFILE%"
echo [INFO] Log in to Naver, open Naver Real Estate, and show the search results.
echo [INFO] Keep this Chrome window open, then run local_collect.bat.
pause
exit /b 0
