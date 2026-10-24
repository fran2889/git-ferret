# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""The one seam between git-ferret and the git binary.

Every git invocation in the project goes through this module, and no other
module imports ``subprocess``. Concentrating the calls in a single file is what
makes the report-only safety property auditable: the whole of what git-ferret
can do to a repository is the argv assembled by :func:`run_git`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

TIMEOUT_SECONDS = 120
# A version probe should be immediate. A hang here means a broken installation,
# not a slow repository, so it gets a much shorter rope than a fetch.
PROBE_TIMEOUT_SECONDS = 10

# The shell's convention for a timeout. Git itself reports fatal errors as 128,
# but a git subcommand or alias may use any code, so this value is informational
# rather than a guarantee that git did not run.
TIMEOUT_EXIT = 124

# Re-exported so callers can name this return type without importing
# ``subprocess`` outside this module.
CompletedProcess = subprocess.CompletedProcess[str]


class GitError(Exception):
    """A git command ran and failed, or did not finish within the timeout.

    Carries the code and stderr for reporting. A git that could not be executed
    at all is :class:`GitUnavailable`, not this: that is an environment failure,
    not a repository one.
    """

    def __init__(self, args: list[str], returncode: int, stderr: str):
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr}")
        self.returncode = returncode
        self.stderr = stderr


class GitUnavailable(Exception):
    """git could not be executed, so no repository can be read.

    Deliberately not a :class:`GitError`: per-repository handlers skip a broken
    repository, but a broken environment has to reach the run boundary and stop
    the run instead of producing a report in which every repository is stale.
    """


def require_git() -> str:
    """Prove git can be executed, and return its version line.

    Run rather than look up: ``shutil.which`` finds a shim or a ``git.cmd`` that
    ``subprocess`` cannot actually start, and it cannot see an installation that
    starts and then dies. This is the operation every later call depends on, so
    it is the one to probe.

    Raises :class:`GitUnavailable` with a message fit for one line on stderr.
    """
    try:
        proc = subprocess.run(
            ["git", "--version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise GitUnavailable(f"git did not respond within {PROBE_TIMEOUT_SECONDS}s") from None
    except OSError as exc:
        raise GitUnavailable(f"cannot run git: {exc}") from None
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
        raise GitUnavailable(f"git --version failed: {detail}")
    return proc.stdout.strip()


def run_git(repo: Path, *args: str, check: bool = False) -> CompletedProcess:
    """Run ``git`` in *repo* with captured text output.

    ``-C`` is always passed rather than setting ``cwd``, so no caller can
    accidentally depend on this process's working directory. With the default
    ``check=False`` a non-zero exit is returned rather than raised, which lets
    callers ask git questions whose answer *is* the exit code.

    A git that cannot be executed at all raises :class:`GitUnavailable`, while a
    git that runs past the timeout raises :class:`GitError`. Keeping those apart
    lets a per-repository handler skip a slow repository without swallowing an
    environment failure that makes every repository unreadable.
    """
    # UTF-8 explicitly, not the locale default: on Windows the default is the
    # console code page, which turns a branch name such as "café" into a
    # UnicodeDecodeError even though git wrote valid UTF-8. ``errors="replace"``
    # keeps a genuinely undecodable path from stopping the whole scan.
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise GitError(list(args), TIMEOUT_EXIT, f"timed out after {TIMEOUT_SECONDS}s") from None
    except OSError as exc:
        raise GitUnavailable(f"cannot run git: {exc}") from None
    if check and proc.returncode != 0:
        raise GitError(list(args), proc.returncode, proc.stderr)
    return proc


def run_git_text(repo: Path, *args: str) -> str:
    """Run git, raising :class:`GitError` on failure, and return stdout stripped."""
    return run_git(repo, *args, check=True).stdout.strip()
