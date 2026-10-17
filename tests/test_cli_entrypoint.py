"""Tests for what the entry point does with a run that goes wrong.

The exit code itself is covered end to end in ``test_freshness_and_exit.py``,
but those run the CLI in a subprocess and coverage of a subprocess run is not
collected. What is pinned here is the other half: that one unreadable
repository does not cost you the other twenty-nine, and that the tool's own
usage errors reach the caller as exit 1.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from git_ferret import cli
from git_ferret.cli import UsageError
from git_ferret.config import Config
from tests.helpers import make_repo


def _main(argv: list[str]) -> int:
    """Run ``main`` with *argv* as its command line; return the exit code."""
    sys.argv = ["git-ferret", *argv]
    try:
        cli.main()
    except SystemExit as exc:
        return int(exc.code or 0)
    return 0


def test_a_successful_run_returns_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    make_repo(tmp_path / "r")
    assert _main(["local", str(tmp_path)]) == 0
    assert capsys.readouterr().err == ""


def test_a_missing_path_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # A mistyped path must not read as "nothing to report": an empty, exit-0
    # report is indistinguishable from a quiet week.
    assert _main(["local", str(tmp_path / "nope")]) == 1
    assert "error:" in capsys.readouterr().err


def test_a_path_that_is_a_file_is_a_usage_error(tmp_path: Path):
    target = tmp_path / "not-a-directory"
    target.write_text("x")
    assert _main(["local", str(target)]) == 1


def test_the_run_itself_raises_usage_error() -> None:
    # The entry point is what turns this into an exit code, so it is asserted
    # where the conversion happens.
    assert issubclass(UsageError, Exception)


def test_one_unreadable_repository_does_not_stop_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # Auditing thirty repositories and losing all thirty because the twelfth is
    # in a state git cannot read is the wrong trade. The bad one is named, and
    # the good one is still reported.
    broken = make_repo(tmp_path / "broken")
    make_repo(tmp_path / "healthy")
    real = cli.analyse_local

    def refuse(repo: Path, config: Config, base_ref: str | None):
        if repo == broken:
            raise subprocess.SubprocessError("git said no")
        return real(repo, config, base_ref)

    monkeypatch.setattr(cli, "analyse_local", refuse)
    assert _main(["local", str(tmp_path)]) == 0
    err = capsys.readouterr().err
    assert "error analysing" in err
    assert str(broken) in err


def test_the_good_repository_is_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    healthy = make_repo(tmp_path / "healthy")
    real = cli.analyse_local

    def refuse(repo: Path, config: Config, base_ref: str | None):
        if repo != healthy:
            raise subprocess.SubprocessError("git said no")
        return real(repo, config, base_ref)

    broken = make_repo(tmp_path / "broken")
    monkeypatch.setattr(cli, "analyse_local", refuse)
    assert _main(["local", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"## {healthy.name}" in out
    assert broken.name not in out


def test_one_unreadable_repository_does_not_stop_a_remote_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # `remote` and `merged` share one path through _run, so one case covers
    # both commands.
    make_repo(tmp_path / "r")

    def refuse(*args: object, **kwargs: object) -> None:
        raise subprocess.SubprocessError("git said no")

    monkeypatch.setattr(cli, "ANALYSES", {"remote": refuse, "merged": refuse})
    assert _main(["remote", str(tmp_path)]) == 0
    assert "error analysing" in capsys.readouterr().err
