param(
    [string]$Message = "Update real estate manager"
)

$ErrorActionPreference = "Stop"
$git = "C:\Program Files\Git\cmd\git.exe"
$remoteUrl = "https://github.com/Sugoil/factory-manager"

if (-not (Test-Path $git)) {
    throw "Git을 찾을 수 없습니다: $git"
}

Set-Location $PSScriptRoot

if (-not (Test-Path ".git")) {
    & $git init -b main
}

$origin = & $git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0) {
    & $git remote add origin $remoteUrl
} elseif ($origin -ne $remoteUrl) {
    & $git remote set-url origin $remoteUrl
}

& $git fetch origin main 2>$null
$remoteMain = & $git rev-parse --verify origin/main 2>$null
$localHead = & $git rev-parse --verify HEAD 2>$null

if ($remoteMain -and -not $localHead) {
    # 원격 이력을 기준으로 시작하되 현재 작업 파일은 그대로 유지합니다.
    & $git reset --mixed origin/main
} elseif ($remoteMain -and $localHead) {
    & $git pull --rebase --autostash origin main
}

& $git add app.py naver_collector.py requirements.txt README.md .gitignore listings.csv sync-github.ps1
& $git add .github/workflows/daily-naver-watch.yml logs/.gitkeep
& $git add -f .streamlit/secrets.toml.example

$changes = & $git status --porcelain
if ($changes) {
    & $git commit -m $Message
} else {
    Write-Host "커밋할 변경사항이 없습니다."
}

& $git push -u origin main
Write-Host "GitHub 반영 완료: $remoteUrl"
