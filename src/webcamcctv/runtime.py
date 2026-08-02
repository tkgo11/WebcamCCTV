"""Resolve companion processes in source and frozen distributions."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def companion_command(name: str, module: str) -> list[str]:
    """Return a command for a bundled companion or its Python module."""
    if not getattr(sys, "frozen", False):
        return [sys.executable, "-m", module]

    suffix = ".exe" if os.name == "nt" else ""
    executable = Path(sys.executable).resolve()
    roots = [executable.parent]
    # A macOS GUI executable lives at App.app/Contents/MacOS/<name>.
    if ".app" in executable.as_posix() and len(executable.parents) > 3:
        roots.append(executable.parents[3])
    for root in roots:
        candidate = root / f"{name}{suffix}"
        if candidate.is_file():
            return [str(candidate)]
    raise FileNotFoundError(f"Bundled companion executable not found: {name}{suffix}")
