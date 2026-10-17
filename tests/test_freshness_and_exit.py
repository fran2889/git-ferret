"""Tests for fetch-age reporting and CLI exit codes.

Both come from the final review:

- `git clone` does not create FETCH_HEAD, so a freshly cloned repository read as
  "never fetched" and was counted stale -- a false staleness signal on the
  freshest state possible, which trains you to ignore the warning that exists
  precisely to stop stale answers passing as current.
- An unrecognised command or flag exited 2; the documented contract is 1 for a
  usage error.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from git_ferret.gitops import fetch_head_mtime, refs_updated_at
from tests.helpers import clone_local, commit, make_repo, run

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "git_ferret.cli", *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


# --- fetch age ----------------------------------------------------------------


def test_fresh_clone_has_a_known_refs_timestamp(tmp_path: Path):
    # `git clone` writes no FETCH_HEAD, so the clone must fall back to the
    # remote-tracking refs rather than reporting "never fetched".
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    assert fetch_head_mtime(clone) is None
    assert refs_updated_at(clone) is not None


def test_refs_timestamp_is_recent_for_a_fresh_clone(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    stamp = refs_updated_at(clone)
    assert stamp is not None
    assert (time.time() - stamp.timestamp()) < 300


def test_refs_updated_at_none_for_a_repo_with_no_refs(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    assert refs_updated_at(repo) is None


def test_fetched_repo_uses_fetch_head(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch")
    assert fetch_head_mtime(clone) is not None
    assert refs_updated_at(clone) is not None


def test_fresh_clone_reports_when_its_refs_were_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    from git_ferret.cli import run_command

    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone_local(src, tmp_path / "clone")

    run_command("local", tmp_path / "clone", True, [], None)
    out = capsys.readouterr().out
    # A fresh clone writes refs but no FETCH_HEAD: the timestamp must come
    # from the refs rather than claiming the repository was never fetched.
    assert "never fetched" not in out
    assert "fetched " in out
    # --no-fetch still warns, because no fetch happened this run.
    assert "stale" in out.lower()


def test_genuinely_stale_state_is_still_flagged(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from git_ferret.cli import run_command

    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch")
    # Age every timestamp this tool could read.
    old = time.time() - 90 * 86400
    git_dir = clone / ".git"
    for path in [git_dir / "FETCH_HEAD", *git_dir.glob("refs/remotes/**/*")]:
        if path.is_file():
            os.utime(path, (old, old))

    run_command("local", tmp_path / "clone", True, [], None)
    assert "stale" in capsys.readouterr().out.lower()


def test_fetch_failure_is_reported_unreachable_and_stale(tmp_path: Path):
    # A failing fetch is the one way a run reads state it could not refresh, so
    # it must surface as [UNREACHABLE] and must mark the run stale. The direct
    # analyse_* tests below this file call the analysis without the CLI's fetch
    # step, so this is the path that actually ships.
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", "/nonexistent/path.git")

    result = _cli("local", str(repo))

    assert result.returncode == 0, result.stderr
    assert "[UNREACHABLE]" in result.stdout
    assert "fetch failed" in result.stdout
    assert "stale" in result.stdout.lower()


def test_stale_warning_names_the_true_count(tmp_path: Path):
    # The warning names how many of how many. It read "1 of 1" for any run
    # because it was rendered from the first repository alone.
    for name in ("a", "b"):
        repo = make_repo(tmp_path / name)
        (repo / "f.txt").write_text("a\n")
        commit(repo, "base")

    result = _cli("local", str(tmp_path), "--no-fetch")

    assert "2 of 2 repositories" in result.stdout


def test_stale_warning_fires_when_a_later_repository_is_stale(tmp_path: Path):
    # One stale repo among many is the case worth nagging about, and it is not
    # necessarily the first one. Here the first repository's fetch succeeds and
    # the second's fails.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")

    scan = tmp_path / "scan"
    clone_local(src, scan / "a-fresh")
    broken = make_repo(scan / "b-broken")
    (broken / "f.txt").write_text("a\n")
    commit(broken, "base")
    run(broken, "remote", "add", "origin", "/nonexistent/path.git")

    result = _cli("local", str(scan))

    assert "stale" in result.stdout.lower()
    assert "1 of 2 repositories" in result.stdout


# --- exit codes ---------------------------------------------------------------


def test_unknown_command_exits_one():
    result = _cli("bogus-command")
    assert result.returncode == 1, result.stderr


def test_unknown_flag_exits_one():
    result = _cli("local", "--bogus-flag")
    assert result.returncode == 1, result.stderr


def test_missing_path_exits_one(tmp_path: Path):
    result = _cli("local", str(tmp_path / "nope"), "--no-fetch")
    assert result.returncode == 1, result.stderr


def test_help_exits_zero():
    assert _cli("--help").returncode == 0


def test_findings_alone_exit_zero(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "never-pushed")
    result = _cli("local", str(tmp_path / "src"), "--no-fetch")
    assert result.returncode == 0, result.stderr


def test_valid_run_exits_zero(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    for cmd in ("local", "remote", "merged"):
        assert _cli(cmd, str(tmp_path / "src"), "--no-fetch").returncode == 0
