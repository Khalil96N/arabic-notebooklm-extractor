import argparse
import asyncio
import os
import sys
from pathlib import Path


os.environ["PYTHONUTF8"] = "1"
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DATA_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "NotebookLMExtractor"
)
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["NOTEBOOKLM_DATA_DIR"] = str(DATA_ROOT)

from app.config.state import StateManager
from app.workflow import run_workflow


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="default")
    parser.add_argument("--notebook", required=True)
    parser.add_argument("--lecture", required=True)
    args = parser.parse_args()

    os.chdir(DATA_ROOT)
    StateManager.save_state(args.profile, args.notebook)
    output_name = asyncio.run(
        run_workflow(
            args.profile,
            args.notebook,
            args.lecture,
        )
    )
    raise SystemExit(0 if output_name else 1)


if __name__ == "__main__":
    main()
