@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=FactoryManagerAutoCollect"
set "RUNNER=%~dp0local_collect.bat"
set "PYTHON_SCRIPT=%~dp0local_collect.py"

if not exist "%RUNNER%" (
  echo local_collect.bat 파일을 찾을 수 없습니다.
  pause
  exit /b 1
)
if not exist "%PYTHON_SCRIPT%" (
  echo local_collect.py 파일을 찾을 수 없습니다.
  pause
  exit /b 1
)

echo Windows 작업 스케줄러에 %TASK_NAME% 작업을 등록합니다.
echo 실행 파일: %RUNNER%
echo 실행 주기: 3시간마다

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$python = Get-Command python -ErrorAction SilentlyContinue;" ^
  "$arguments = '""%PYTHON_SCRIPT%""';" ^
  "if (-not $python) { $python = Get-Command py -ErrorAction Stop; $arguments = '-3 ""%PYTHON_SCRIPT%""'; }" ^
  "$action = New-ScheduledTaskAction -Execute $python.Source -Argument $arguments -WorkingDirectory '%~dp0';" ^
  "$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 3);" ^
  "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30);" ^
  "Register-ScheduledTask -TaskName '%TASK_NAME%' -Action $action -Trigger $trigger -Settings $settings -Description 'Factory Manager local Naver listing collection every 3 hours' -Force | Out-Null"
if errorlevel 1 (
  echo 작업 스케줄러 등록에 실패했습니다.
  echo 이 파일을 마우스 오른쪽 버튼으로 클릭한 뒤 관리자 권한으로 실행해주세요.
  pause
  exit /b 1
)

echo 작업 스케줄러 등록이 완료되었습니다.
echo PC가 켜져 있을 때 3시간마다 로컬 자동수집이 실행됩니다.
pause
exit /b 0
