# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""End-to-end tests for the checked-in git hooks.

The hooks are shell scripts, so these tests run them in a real repository with
a real ``git``: the same approach the rest of the suite takes. They skip when
no usable bash is available, because a hook cannot run without its interpreter.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from git_ferret.gitcmd import run_git
from tests.helpers import make_repo, run

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS = REPO_ROOT / ".githooks"
CHECK_COMMIT_MSG = REPO_ROOT / "scripts" / "check_commit_msg.py"


def _usable_bash(path: Path) -> bool:
    """Whether *path* runs a shell that can execute the hooks."""
    try:
        result = subprocess.run(
            [str(path), "-c", "exit 0"], check=False, capture_output=True, timeout=10
        )
    except OSError, subprocess.SubprocessError:
        return False
    return result.returncode == 0


def _find_bash() -> str | None:
    """A bash that can run the hooks, preferring Git for Windows' own.

    ``shutil.which("bash")`` can find the Windows Subsystem for Linux launcher
    on a Windows runner before Git's bash, and WSL cannot run a hook whose
    interpreter is a Windows path. Probe the candidates rather than trusting
    the first name on PATH.
    """
    candidates: list[Path] = []
    if sys.platform == "win32":
        git = shutil.which("git")
        if git is not None:
            git_path = Path(git).resolve()
            for root in (git_path.parent.parent, git_path.parent.parent.parent):
                candidates += [
                    root / "bin" / "bash.exe",
                    root / "usr" / "bin" / "bash.exe",
                ]
    found = shutil.which("bash")
    if found is not None:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file() and _usable_bash(candidate):
            return str(candidate)
    return None


BASH = _find_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="no usable bash")


def _bash() -> str:
    """The bash used to run the hooks; the module is skipped without one."""
    assert BASH is not None
    return BASH


def _make_executable(path: Path) -> None:
    """Mark *path* executable for the bash that runs the hooks.

    ``Path.chmod`` cannot set the execute bit on Windows; Git Bash's own
    ``chmod`` records it where Git Bash looks for it.
    """
    subprocess.run(
        [_bash(), "-c", 'chmod +x "$1"', "_", path.as_posix()],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _ruff_available() -> bool:
    return importlib.util.find_spec("ruff") is not None


requires_ruff = pytest.mark.skipif(not _ruff_available(), reason="ruff is not installed")


def _isolated_env(tmp_path: Path) -> dict[str, str]:
    """An environment with a private global git config and the test interpreter."""
    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("", encoding="utf-8")
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = str(global_config)
    env["PYTHON"] = sys.executable
    return env


def _repo_with_hooks(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """A repository whose hooks are the checked-in scripts, plus an isolated env."""
    repo = make_repo(tmp_path / "repo")
    run(repo, "config", "core.hooksPath", str(HOOKS))
    scripts = repo / "scripts"
    scripts.mkdir()
    shutil.copyfile(CHECK_COMMIT_MSG, scripts / CHECK_COMMIT_MSG.name)
    return repo, _isolated_env(tmp_path)


def _commit(repo: Path, env: dict[str, str], message: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_pre_commit_refuses_to_stage_unstaged_changes(tmp_path: Path) -> None:
    repo, env = _repo_with_hooks(tmp_path)
    sample = repo / "sample.py"
    sample.write_text("value = 1\n", encoding="utf-8")
    run(repo, "add", "sample.py")
    sample.write_text("value = 2\n", encoding="utf-8")

    result = _commit(repo, env, "feat: add sample")

    assert result.returncode != 0
    assert "unstaged changes" in result.stderr
    assert run_git(repo, "show", ":sample.py").stdout == "value = 1\n"
    assert run_git(repo, "rev-parse", "--verify", "HEAD", check=False).returncode != 0


@requires_ruff
def test_pre_commit_formats_a_fully_staged_file(tmp_path: Path) -> None:
    repo, env = _repo_with_hooks(tmp_path)
    sample = repo / "sample.py"
    sample.write_text("value=1\n", encoding="utf-8")
    run(repo, "add", "sample.py")

    result = _commit(repo, env, "feat: add sample")

    assert result.returncode == 0, result.stderr
    assert run_git(repo, "show", "HEAD:sample.py").stdout == "value = 1\n"


@requires_ruff
def test_pre_commit_handles_a_non_ascii_path(tmp_path: Path) -> None:
    repo, env = _repo_with_hooks(tmp_path)
    run(repo, "config", "core.quotePath", "true")
    sample = repo / "café.py"
    sample.write_text("value=1\n", encoding="utf-8")
    run(repo, "add", "café.py")

    result = _commit(repo, env, "feat: add café")

    assert result.returncode == 0, result.stderr
    assert run_git(repo, "show", "HEAD:café.py").stdout == "value = 1\n"


@pytest.mark.parametrize(
    ("message", "expected"),
    [("feat: add sample", 0), ("feat: Add sample", 1)],
)
def test_commit_msg_hook_checks_the_subject(tmp_path: Path, message: str, expected: int) -> None:
    repo, env = _repo_with_hooks(tmp_path)
    (repo / "note.txt").write_text("x\n", encoding="utf-8")
    run(repo, "add", "note.txt")

    result = _commit(repo, env, message)

    assert result.returncode == expected, result.stderr
    if expected:
        assert "check_commit_msg" in result.stderr


def test_pre_push_runs_typecheck_and_tests(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    args_file = tmp_path / "make-args"
    fake_make = fake_bin / "make"
    fake_make.write_text(
        '#!/usr/bin/env bash\nprintf \'%s\\n\' "$@" > "$MAKE_ARGS"\n',
        encoding="utf-8",
        newline="\n",
    )
    _make_executable(fake_make)

    env = os.environ.copy()
    env["MAKE_ARGS"] = args_file.as_posix()
    env["PATH"] = f"{fake_bin.as_posix()}{os.pathsep}{env['PATH']}"
    env["PYTHON"] = sys.executable

    result = subprocess.run(
        [_bash(), str(HOOKS / "pre-push")],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
    assert args_file.read_text(encoding="utf-8").splitlines() == [
        "typecheck",
        "test",
        f"PYTHON={sys.executable}",
    ]


def test_pre_commit_runs_a_configured_global_hook_first(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    global_hooks = tmp_path / "global-hooks"
    global_hooks.mkdir()
    marker = tmp_path / "global-ran"
    global_hook = global_hooks / "pre-commit"
    global_hook.write_text('#!/usr/bin/env bash\ntouch "$MARKER"\n', encoding="utf-8", newline="\n")
    _make_executable(global_hook)

    global_config = tmp_path / "global.gitconfig"
    global_config.write_text("", encoding="utf-8")
    run_git(
        repo,
        "config",
        "--file",
        str(global_config),
        "core.hooksPath",
        global_hooks.as_posix(),
        check=True,
    )
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = str(global_config)
    env["MARKER"] = marker.as_posix()

    result = subprocess.run(
        [_bash(), str(HOOKS / "pre-commit")],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr
    assert marker.exists()
