#!/usr/bin/env python3
"""Run DataPilot with one command.

python run.py          sample data, no accounts needed
python run.py --real   downloads real Vélib' history first (needs internet)
"""
import argparse
import os
import shutil
import subprocess
import sys
import venv
import webbrowser
from pathlib import Path
from threading import Timer

ROOT = Path(__file__).parent.resolve()
VENV = ROOT / ".venv"
PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(*command, cwd=ROOT):
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def prepare_python():
    if sys.version_info < (3, 10):
        sys.exit("DataPilot needs Python 3.10 or newer.")
    if not PYTHON.exists():
        print("Creating .venv ...")
        venv.create(VENV, with_pip=True)
    marker = VENV / ".installed"
    if not marker.exists():
        print("Installing packages. This takes a few minutes the first time ...")
        run(PYTHON, "-m", "pip", "install", "-q", "-r", "api/requirements.txt", "-r", "data/requirements.txt")
        marker.touch()


def prepare_llm():
    env_file = ROOT / ".env"
    marker = VENV / ".cloud-installed"
    if env_file.exists() and "LLM_MODEL=" in env_file.read_text(encoding="utf-8") and not marker.exists():
        print("Installing LLM packages ...")
        run(PYTHON, "-m", "pip", "install", "-q", "-r", "api/requirements-cloud.txt")
        marker.touch()


def prepare_web():
    if (ROOT / "api/static/index.html").exists():
        return
    npm = shutil.which("npm")
    if not npm:
        sys.exit("The web build is missing and npm isn't installed. Install Node LTS, then run this again.")
    run(npm, "ci", cwd=ROOT / "web")
    run(npm, "run", "build", cwd=ROOT / "web")
    shutil.copytree(ROOT / "web/dist/web/browser", ROOT / "api/static")


def prepare_data(real: bool) -> str:
    wanted = "real" if real else "sample"
    if real:
        if not (ROOT / "data/local/snapshots.parquet").exists():
            run(PYTHON, "data/ingest.py", "--local")
    else:
        os.environ["DATA_BACKEND"] = "demo"
        if not (ROOT / "data/demo/snapshots.parquet").exists():
            print("Generating sample data ...")
            run(PYTHON, "make_demo_data.py", cwd=ROOT / "data")
    trained_on = ROOT / "api/model.data"
    if not (ROOT / "api/model.joblib").exists() or not trained_on.exists() or trained_on.read_text() != wanted:
        print("Training the model ...")
        run(PYTHON, "ml/train.py")
        trained_on.write_text(wanted)
    return wanted


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", action="store_true", help="use real Vélib' history")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    prepare_python()
    prepare_llm()
    prepare_web()
    data = prepare_data(args.real)
    url = f"http://127.0.0.1:{args.port}"
    print(f"\nParis Pulse is running on {data} data at {url}\nPress Ctrl+C to stop.\n")
    Timer(2.5, lambda: webbrowser.open(url)).start()
    try:
        run(PYTHON, "-m", "uvicorn", "main:app", "--port", args.port, cwd=ROOT / "api")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
