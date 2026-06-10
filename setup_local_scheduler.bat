@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=FactoryManagerAutoCollect"
set "RUNNER=%~dp0local_collect.bat"
set "PYTHON_SCRIPT=%~dp0local_collect.py"

if not exist "%RUNNER%" (
  echo [ERROR] local_collect.bat was not found.
  pause
  exit /b 1
)
if not exist "%PYTHON_SCRIPT%" (
  echo [ERROR] local_collect.py was not found.
  pause
  exit /b 1
)

echo Registering Windows scheduled task: %TASK_NAME%
echo Runner: %RUNNER%
echo Schedule: every 3 hours

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$arguments = '/c """"%RUNNER%"" --scheduled""';" ^
  "$action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument $arguments -WorkingDirectory '%~dp0';" ^
  "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 3);" ^
  "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30);" ^
  "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited;" ^
  "Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Factory Manager visible-browser Naver listing collection every 3 hours' -Force | Out-Null"

if errorlevel 1 (
  echo [ERROR] Scheduled task registration failed.
  echo Right-click this file and select Run as administrator.
  pause
  exit /b 1
)

echo [SUCCESS] Scheduled task registration completed.
echo Collection will run every 3 hours while the PC is on and the user is logged in.
pause
exit /b 0
