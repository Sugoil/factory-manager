"""Run the same low-volume collector from a local Windows PC."""

from pathlib import Path

from auto_collect import main


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    print(f"Local low-volume collection started: {project_dir}")
    try:
        main()
    except Exception as error:
        print(f"Local collection failed: {type(error).__name__}: {error}")
        raise
    else:
        print("Local low-volume collection finished.")
