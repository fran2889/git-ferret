# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Install the built wheel and run its console script.

Used by ``make smoke`` and the CI build job. It checks the artifact users
install: the console script resolves, the package imports, ``--version``
reports the wheel's metadata version, and ``--help`` exits cleanly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DIST = Path("dist")
DISTRIBUTION = "git-ferret"
ENTRY_POINT = "git-ferret"
IS_WINDOWS = os.name == "nt"


def find_wheel(dist: Path) -> Path:
    """Return the only wheel in *dist*."""
    wheels = sorted(dist.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"smoke_wheel: expected one wheel in {dist}, found {len(wheels)}")
    return wheels[0]


def venv_paths(venv: Path) -> tuple[Path, Path]:
    """Return the venv's Python and console-script paths."""
    if IS_WINDOWS:
        return venv / "Scripts" / "python.exe", venv / "Scripts" / f"{ENTRY_POINT}.exe"
    return venv / "bin" / "python", venv / "bin" / ENTRY_POINT


def _run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run *command*, raising on a non-zero exit."""
    return subprocess.run(
        command,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
    )


def main(argv: list[str]) -> int:
    """Run the smoke test; return 0 on success."""
    if len(argv) > 2:
        raise SystemExit("usage: smoke_wheel.py [WHEEL]")
    if shutil.which("uv") is None:
        raise SystemExit("smoke_wheel: uv is required")
    wheel = Path(argv[1]) if len(argv) == 2 else find_wheel(DIST)
    try:
        with tempfile.TemporaryDirectory(prefix="git-ferret-smoke-") as tmp:
            venv = Path(tmp) / "venv"
            _run(["uv", "venv", "--python", sys.executable, str(venv)])
            python, entry = venv_paths(venv)
            _run(["uv", "pip", "install", "--python", str(python), str(wheel)])
            metadata = _run(
                [
                    str(python),
                    "-c",
                    f"import importlib.metadata as m; print(m.version({DISTRIBUTION!r}))",
                ],
                capture=True,
            ).stdout.strip()
            reported = _run([str(entry), "--version"], capture=True).stdout.strip()
            expected = f"{ENTRY_POINT} {metadata}"
            if reported != expected:
                print(
                    f"smoke_wheel: --version reported {reported!r}, expected {expected!r}",
                    file=sys.stderr,
                )
                return 1
            _run([str(entry), "--help"], capture=True)
            print(f"smoke_wheel: {wheel.name} installed and ran as {reported}")
    except subprocess.CalledProcessError as exc:
        print(
            f"smoke_wheel: command failed with exit code {exc.returncode}: {exc.cmd}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
