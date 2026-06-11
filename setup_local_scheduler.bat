@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=FactoryManagerAutoCollect"
set "RUNNER=%~dp0local_collect.bat"
set "PYTHON_SCRIPT=%~dp0local_collect.py"
set "INTERVAL_MINUTES=10"
for /f %%I in ('python -c "from collection_settings import COLLECT_INTERVAL_MINUTES; print(COLLECT_INTERVAL_MINUTES)" 2^>nul') do set "INTERVAL_MINUTES=%%I"

net session >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Administrator permission is required.
  echo [ERROR] Please run this file again as administrator.
  echo Right-click setup_local_scheduler.bat and select Run as administrator.
  pause
  exit /b 1
)

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
echo Schedule: every %INTERVAL_MINUTES% minutes

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$taskName = '%TASK_NAME%';" ^
  "$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue;" ^
  "if ($existing) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false; Write-Host '[INFO] Existing task removed.' };" ^
  "$arguments = '/c """"%RUNNER%"" --scheduled""';" ^
  "$action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument $arguments -WorkingDirectory '%~dp0';" ^
  "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes %INTERVAL_MINUTES%);" ^
  "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 9) -MultipleInstances IgnoreNew;" ^
  "$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited;" ^
  "Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Factory Manager visible-browser Naver listing collection every 10 minutes' -Force | Out-Null;" ^
  "$registered = Get-ScheduledTask -TaskName $taskName;" ^
  "$info = Get-ScheduledTaskInfo -TaskName $taskName;" ^
  "$interval = $registered.Triggers[0].Repetition.Interval;" ^
  "Write-Host '';" ^
  "Write-Host 'Task Name:';" ^
  "Write-Host $taskName;" ^
  "Write-Host '';" ^
  "Write-Host 'Interval:';" ^
  "Write-Host ('%INTERVAL_MINUTES% minutes (Windows value: ' + $interval + ')');" ^
  "Write-Host '';" ^
  "Write-Host 'Next Run Time:';" ^
  "Write-Host $info.NextRunTime"

if errorlevel 1 (
  echo [ERROR] Scheduled task registration failed.
  echo [ERROR] Please run this file again as administrator.
  echo Right-click setup_local_scheduler.bat and select Run as administrator.
  pause
  exit /b 1
)

echo [SUCCESS] Scheduled task registration completed.
echo Registration Result: SUCCESS
echo Task Name: %TASK_NAME%
echo Interval: %INTERVAL_MINUTES% minutes
echo Runner: %RUNNER%
pause
exit /b 0
