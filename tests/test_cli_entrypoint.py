# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for what the entry point does with a run that goes wrong.

The exit code itself is covered end to end in ``test_freshness_and_exit.py``,
but those run the CLI in a subprocess and coverage of a subprocess run is not
collected. What is pinned here is the other half: that one unreadable
repository does not cost you the other twenty-nine, and that the tool's own
usage errors reach the caller as exit 1.
"""

import io
import subprocess
import sys
from pathlib import Path

import pytest
import typer

from git_ferret import __version__, cli
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


def test_version_is_printed_without_running_a_scan(capsys: pytest.CaptureFixture[str]):
    # The bug report template asks for this, so it has to work without a path
    # and without touching a repository.
    assert _main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"git-ferret {__version__}"


def test_a_missing_path_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # A mistyped path must not read as "nothing to report": an empty, exit-0
    # report is indistinguishable from a quiet week.
    assert _main(["local", str(tmp_path / "nope")]) == 1
    assert "error:" in capsys.readouterr().err


def test_a_path_that_is_a_file_is_a_usage_error(tmp_path: Path):
    target = tmp_path / "not-a-directory"
    target.write_text("x")
    assert _main(["local", str(target)]) == 1


def test_an_unknown_flag_is_one_line_and_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
):
    # A typo is the user's mistake, not a crash. The exit code was always 1 --
    # an unhandled exception exits 1 too -- so only the output can tell them
    # apart, which is why this asserts the stderr rather than the code.
    assert _main(["local", "--nonsense"]) == 1
    err = capsys.readouterr().err
    assert "No such option" in err
    assert "Traceback" not in err
    assert len(err.strip().splitlines()) == 1


def test_an_unknown_command_is_one_line_and_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
):
    assert _main(["sideways"]) == 1
    err = capsys.readouterr().err
    assert "sideways" in err
    assert "Traceback" not in err
    assert len(err.strip().splitlines()) == 1


def test_an_interrupt_is_reported_and_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # Silently exiting 0 would make an interrupted scan indistinguishable from a
    # clean one, which is the one thing a report you script against must not be.
    def interrupted(root: Path) -> list[Path]:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "discover_repos", interrupted)
    assert _main(["local", str(tmp_path)]) == 1
    assert "aborted" in capsys.readouterr().err


def test_an_interrupt_in_a_remote_run_is_reported_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    def interrupted(root: Path) -> list[Path]:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "discover_repos", interrupted)
    assert _main(["remote", str(tmp_path)]) == 1
    assert "aborted" in capsys.readouterr().err


def test_an_explicit_exit_code_from_a_command_is_honoured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Under standalone_mode=False typer hands the code back as a return value
    # rather than raising it, so nothing in main() ever sees a typer.Exit to
    # catch. A command that asked for a code of its own has to get it; dropping
    # the return would silently give it 0 instead.
    app = typer.Typer()

    @app.command()
    def boom() -> None:
        raise typer.Exit(7)

    # A second command so typer keeps this a group: with one command it
    # collapses into a root command that takes no subcommand name, and `boom`
    # below would be read as an unexpected argument rather than run.
    @app.command()
    def other() -> None:
        pass

    monkeypatch.setattr(cli, "app", app)
    assert _main(["boom"]) == 7


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


class _RecordingStream:
    """A stream that records how the entry point asks it to encode."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_the_report_is_written_as_utf8(monkeypatch: pytest.MonkeyPatch):
    # The markers are emoji and a branch name can be any UTF-8, but a redirected
    # Windows stream encodes cp1252 and would raise on the first line.
    out, err = _RecordingStream(), _RecordingStream()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)

    cli._configure_output()  # pyright: ignore[reportPrivateUsage]

    assert out.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert err.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_a_stream_that_cannot_be_reconfigured_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
):
    # StringIO and streams owned by a wrapper have no reconfigure; that is not
    # a reason to fail the run.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    cli._configure_output()  # pyright: ignore[reportPrivateUsage]
