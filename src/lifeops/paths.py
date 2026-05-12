from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env_root = os.environ.get("LIFEOPS_REPO_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_dir(root: Path | None = None) -> Path:
    return (root or repo_root()) / "data"


def db_path(root: Path | None = None) -> Path:
    return data_dir(root) / "state.db"


def ensure_dirs(root: Path | None = None) -> None:
    base = root or repo_root()
    for rel in [
        "data",
        "data/events",
        "data/daily",
        "data/weekly",
        "data/proposals",
        "data/exports",
        "data/runtime",
        "config",
        "prompts",
        "scripts",
    ]:
        (base / rel).mkdir(parents=True, exist_ok=True)


def default_output_path(name: str, root: Path | None = None) -> Path:
    return data_dir(root) / "exports" / name
