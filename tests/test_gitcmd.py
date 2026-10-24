# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the git subprocess seam."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from git_ferret.gitcmd import (
    TIMEOUT_EXIT,
    GitError,
    GitUnavailable,
    require_git,
    run_git,
    run_git_text,
)
from tests.helpers import commit, make_repo


def test_run_git_text_returns_stdout(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert run_git_text(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_run_git_text_raises_on_error(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    with pytest.raises(GitError) as exc:
        run_git_text(repo, "rev-parse", "does-not-exist")
    assert exc.value.returncode != 0


def test_run_git_check_false_does_not_raise(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    proc = run_git(repo, "rev-parse", "does-not-exist")
    assert proc.returncode != 0


def test_a_missing_git_binary_is_git_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A missing binary is an environment failure, not a repository one: it must
    # not arrive as the GitError that per-repository handlers skip.
    def missing(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr("git_ferret.gitcmd.subprocess.run", missing)
    with pytest.raises(GitUnavailable) as exc:
        run_git(tmp_path, "status")
    assert "cannot run git" in str(exc.value)
    assert not isinstance(exc.value, GitError)


def test_a_git_timeout_is_a_git_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # A slow fetch is exactly the long operation, so the 120s timeout is
    # reachable; it has to be a reported failure, not a traceback.
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr("git_ferret.gitcmd.subprocess.run", timed_out)
    with pytest.raises(GitError) as exc:
        run_git(tmp_path, "fetch")
    assert "timed out" in str(exc.value)
    assert exc.value.returncode == TIMEOUT_EXIT


def test_require_git_reports_the_installed_version():
    assert require_git().startswith("git version ")


def test_a_git_that_cannot_report_its_version_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    def broken(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["git", "--version"], returncode=1, stdout="", stderr="boom"
        )

    monkeypatch.setattr("git_ferret.gitcmd.subprocess.run", broken)
    with pytest.raises(GitUnavailable) as exc:
        require_git()
    assert "boom" in str(exc.value)


def test_a_probe_that_hangs_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    # `git --version` is not a slow repository operation. A hang there is a
    # broken installation and must not keep the user waiting for the fetch
    # timeout.
    def timed_out(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr("git_ferret.gitcmd.subprocess.run", timed_out)
    with pytest.raises(GitUnavailable) as exc:
        require_git()
    assert "did not respond" in str(exc.value)


def test_run_git_decodes_utf8_under_an_ascii_locale(tmp_path: Path):
    # Windows uses the console code page for subprocess text unless told
    # otherwise, and a UTF-8 branch name then raises UnicodeDecodeError. Run
    # the seam in a child interpreter whose locale really is ASCII, so a
    # regression to the locale default fails here rather than on a Windows
    # runner.
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run_git(repo, "branch", "café", check=True)

    # The branch name is built from an escape so the child's ASCII argv does
    # not carry the non-ASCII character itself; this test is about decoding
    # git's output, not about passing unicode through a C-locale command line.
    script = (
        "from pathlib import Path\n"
        "from git_ferret.gitcmd import run_git_text\n"
        "name = 'caf\\u00e9'\n"
        f"found = run_git_text(Path({str(repo)!r}), 'branch', '--list')\n"
        "raise SystemExit(0 if name in found else 1)\n"
    )
    env = {**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0", "PYTHONCOERCECLOCALE": "0"}
    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
