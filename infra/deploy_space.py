"""Publish DataPilot to a free Hugging Face Space (Docker).

Run from the project root after `python run.py --real` has downloaded the data:
    .venv/bin/python infra/deploy_space.py

It reads LLM_MODEL, GOOGLE_API_KEY and the LANGFUSE_* values from .env and stores
them as Space secrets, so they never go into any file you upload.
"""
import argparse
import os
import shutil
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
GITHUB_URL = "https://github.com/najeemmd111-cpu/datapilot"
SECRETS = ["GOOGLE_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
VARIABLES = ["LANGFUSE_BASE_URL", "LANGFUSE_HOST", "LLM_MODEL"]
SKIP = shutil.ignore_patterns(
    "node_modules", "dist", ".angular", "static", "__pycache__", ".pytest_cache", "*.joblib", "model.data", ".env",
)


def stage(folder: Path) -> None:
    """Copy only what the image needs into a clean folder."""
    data = ROOT / "data" / "local"
    if not (data / "snapshots.parquet").exists():
        raise SystemExit("Real data is missing. Run: python3 run.py --real")
    shutil.copytree(ROOT / "api", folder / "api", ignore=SKIP)
    shutil.copytree(ROOT / "web", folder / "web", ignore=SKIP)
    shutil.copytree(data, folder / "data" / "local")
    (folder / "ml").mkdir()
    shutil.copy(ROOT / "ml" / "train.py", folder / "ml" / "train.py")
    shutil.copy(ROOT / "infra" / "space" / "Dockerfile", folder / "Dockerfile")
    readme = (ROOT / "infra" / "space" / "README.md").read_text(encoding="utf-8")
    (folder / "README.md").write_text(readme.replace("GITHUB_URL", GITHUB_URL), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="paris-pulse", help="Space name")
    parser.add_argument("--stage-only", metavar="FOLDER", help="only build the upload folder, for checking")
    args = parser.parse_args()
    if args.stage_only:
        stage(Path(args.stage_only))
        print("Staged in", args.stage_only)
        return

    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    api = HfApi()
    user = api.whoami()["name"]
    repo_id = f"{user}/{args.name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    for key in SECRETS:
        if env.get(key):
            api.add_space_secret(repo_id, key, env[key])
    for key in VARIABLES:
        if env.get(key):
            api.add_space_variable(repo_id, key, env[key])
    # Keep public visitors well inside the free Gemini limits.
    api.add_space_variable(repo_id, "ASK_PER_HOUR", "5")
    api.add_space_variable(repo_id, "ASK_PER_DAY", "15")

    with tempfile.TemporaryDirectory() as temp:
        stage(Path(temp))
        api.upload_folder(repo_id=repo_id, repo_type="space", folder_path=temp,
                          commit_message="Deploy DataPilot", delete_patterns=["*"])
    print(f"Uploaded. The Space is building: https://huggingface.co/spaces/{repo_id}")
    print(f"When it says Running, the app is at https://{user}-{args.name}.hf.space")


if __name__ == "__main__":
    main()
