@echo off
setlocal

cd /d "%~dp0"
set "GIT=C:\Program Files\Git\cmd\git.exe"
set "REMOTE=https://github.com/Sugoil/factory-manager"

if not exist "%GIT%" (
    echo [ERROR] Git not found: %GIT%
    pause
    exit /b 1
)

if not exist ".git" (
    echo [INFO] Initializing Git repository...
    "%GIT%" init -b main
    if errorlevel 1 goto :error
)

"%GIT%" remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [INFO] Adding GitHub remote...
    "%GIT%" remote add origin "%REMOTE%"
    if errorlevel 1 goto :error
) else (
    "%GIT%" remote set-url origin "%REMOTE%"
    if errorlevel 1 goto :error
)

echo [INFO] Current changes:
"%GIT%" status --short

set "COMMIT_MESSAGE=%~1"
if "%COMMIT_MESSAGE%"=="" (
    set /p "COMMIT_MESSAGE=Commit message: "
)
if "%COMMIT_MESSAGE%"=="" (
    set "COMMIT_MESSAGE=Update real estate manager"
)

echo [INFO] Adding changes...
"%GIT%" add --all
if errorlevel 1 goto :error

"%GIT%" diff --cached --quiet
if not errorlevel 1 (
    echo [INFO] No changes to commit.
) else (
    echo [INFO] Creating commit...
    "%GIT%" commit -m "%COMMIT_MESSAGE%"
    if errorlevel 1 goto :error
)

echo [INFO] Pushing to GitHub...
"%GIT%" push -u origin main
if errorlevel 1 goto :error

echo.
echo [SUCCESS] GitHub push completed.
pause
exit /b 0

:error
echo.
echo [ERROR] GitHub push failed. Check the error message above.
pause
exit /b 1
