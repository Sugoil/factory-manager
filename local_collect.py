"""Run the visible-browser collector from a local Windows PC."""

from pathlib import Path

from browser_collect import main
from git_sync import sync_collected_data


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    print(f"Local low-volume collection started: {project_dir}")
    try:
        exit_code = main()
        if exit_code:
            raise SystemExit(exit_code)
    except Exception as error:
        print(f"Local collection failed: {type(error).__name__}: {error}")
        raise
    else:
        print("Local low-volume collection finished.")
        sync_success, sync_message = sync_collected_data()
        print(sync_message)
        if sync_success:
            print("수집 완료 및 GitHub 반영 완료")
        else:
            print("수집 완료, GitHub 반영 실패")
            raise SystemExit(3)
