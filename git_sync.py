# -*- coding: utf-8 -*-
"""Commit and push only locally collected data files."""

import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_FILES = ("listings.db", "listings.csv", "collect_logs.csv")


def find_git():
    git = shutil.which("git")
    if git:
        return git
    installed = Path(r"C:\Program Files\Git\cmd\git.exe")
    return str(installed) if installed.exists() else ""


def run_git(git, *args):
    command = [git, *args]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if output:
        print(output)
    return result


def push_current_branch(git):
    branch_result = run_git(git, "branch", "--show-current")
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "main"
    branch = branch or "main"
    push_result = run_git(git, "push", "origin", branch)
    if push_result.returncode:
        return False, "GitHub push에 실패했습니다."
    return True, "GitHub 데이터 반영이 완료되었습니다."


def sync_collected_data():
    git = find_git()
    if not git:
        return False, "Git을 찾을 수 없습니다."
    if not (ROOT / ".git").exists():
        return False, "현재 프로젝트가 Git 저장소가 아닙니다."

    existing_files = [name for name in DATA_FILES if (ROOT / name).exists()]
    if not existing_files:
        return False, "GitHub에 반영할 데이터 파일이 없습니다."

    add_result = run_git(git, "add", "--", *existing_files)
    if add_result.returncode:
        return False, "데이터 파일 git add에 실패했습니다."

    changed = run_git(git, "diff", "--cached", "--quiet", "--", *existing_files)
    if changed.returncode == 0:
        return push_current_branch(git)
    if changed.returncode != 1:
        return False, "Git 변경사항 확인에 실패했습니다."

    message = f"Auto update collected listings {datetime.now():%Y-%m-%d %H:%M}"
    commit_result = run_git(git, "commit", "-m", message, "--", *existing_files)
    if commit_result.returncode:
        return False, "데이터 파일 자동 커밋에 실패했습니다."

    success, message = push_current_branch(git)
    if not success:
        return False, f"자동 커밋은 생성됐지만 {message}"
    return success, message


if __name__ == "__main__":
    success, detail = sync_collected_data()
    print(detail)
    raise SystemExit(0 if success else 1)
