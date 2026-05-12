"""Codex bridge helpers for LifeOps intervention dispatch."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .paths import repo_root


@dataclass(frozen=True)
class CodexLaunch:
    prompt_path: Path
    title: str
    command: str
    process_id: int | None = None
    terminal: str | None = None


def read_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def find_codex_command() -> str | None:
    for name in ("codex", "codex.exe"):
        found = shutil.which(name)
        if found:
            return found

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidate = Path(local_app_data) / "OpenAI" / "Codex" / "bin" / "codex.exe"
        if candidate.exists():
            return str(candidate)
    return None


def find_powershell_command() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")


def _quote_ps(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _console_creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return 0


def build_codex_intervention_command(prompt_path: Path, root: Path | None = None) -> str:
    base = root or repo_root()
    codex = find_codex_command()
    if not codex:
        raise FileNotFoundError("Codex CLI not found. Ensure codex is installed and available on PATH.")

    src = base / "src"
    return "; ".join(
        [
            f"$env:LIFEOPS_REPO_ROOT = {_quote_ps(base)}",
            f"$env:PYTHONPATH = {_quote_ps(src)}",
            f"$prompt = Get-Content -LiteralPath {_quote_ps(prompt_path)} -Raw -Encoding UTF8",
            f"& {_quote_ps(codex)} --cd {_quote_ps(base)} --profile lifeops $prompt",
        ]
    )


def launch_codex_intervention(prompt_path: Path, title: str = "LifeOps Codex Intervention") -> CodexLaunch:
    ps = find_powershell_command()
    if not ps:
        raise FileNotFoundError("PowerShell executable not found.")

    command = build_codex_intervention_command(prompt_path)
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt:
        args = [wt, "new-tab", "--title", title, ps, "-NoExit", "-Command", command]
        process = subprocess.Popen(args)
        return CodexLaunch(prompt_path=prompt_path, title=title, command=command, process_id=process.pid, terminal="Windows Terminal")

    titled_command = f"$Host.UI.RawUI.WindowTitle = {_quote_ps(title)}; {command}"
    args = [ps, "-NoExit", "-Command", titled_command]
    process = subprocess.Popen(args, creationflags=_console_creation_flags())
    return CodexLaunch(prompt_path=prompt_path, title=title, command=titled_command, process_id=process.pid, terminal="PowerShell")