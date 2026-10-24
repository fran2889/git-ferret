# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the two load-bearing freshness invariants.

1. A run that reads local state never silently claims a fetch happened, and
   warns about staleness.
2. The base ref is resolved AFTER fetching, so `merged` judges branches against
   the branch the remote actually has.
"""

from pathlib import Path

import pytest

from git_ferret import cli as cli_module
from git_ferret.analysis.merged import merge_verdict
from git_ferret.cli import run_command
from git_ferret.config import Config
from git_ferret.gitcmd import GitError
from git_ferret.gitops import resolve_base_ref
from git_ferret.models import RepoReport
from tests.helpers import commit, make_repo, run


def _upstream_with_squash_merged(tmp_path: Path):
    """A remote whose `feat` is squash-merged into main."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feat")
    (src / "f.txt").write_text("a\nFEAT\n")
    commit(src, "work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "feat")
    commit(src, "merged")
    return src


def test_never_fetched_repo_falls_back_to_local_base(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert resolve_base_ref(repo) == "main"


def test_merged_uses_origin_base_after_fetching(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    # A repo with a remote configured but never fetched: before the run there is
    # no origin/main, so resolving the base first would judge against a local
    # main that is 40 commits behind.
    src = _upstream_with_squash_merged(tmp_path)
    repo = make_repo(tmp_path / "local")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", src.resolve().as_uri())
    assert resolve_base_ref(repo) == "main"  # pre-fetch

    run_command("merged", Path(tmp_path / "local"), False, [], None)

    out = capsys.readouterr().out
    assert "base: origin/main" in out
    assert "safe to delete" in out
    assert "origin/feat" in out


def test_ground_truth_is_merged_after_the_run(tmp_path: Path):
    src = _upstream_with_squash_merged(tmp_path)
    repo = make_repo(tmp_path / "local")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", src.resolve().as_uri())
    run_command("merged", Path(tmp_path / "local"), False, [], None)
    assert resolve_base_ref(repo) == "origin/main"
    assert merge_verdict(repo, "origin/main", "origin/feat").value == "MERGED"


def test_stale_state_under_no_fetch_is_flagged_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    # --no-fetch must never be silently treated as fresh.
    src = _upstream_with_squash_merged(tmp_path)
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", src.resolve().as_uri())
    run_command("local", Path(tmp_path / "r"), True, [], None)
    capsys.readouterr()

    run_command("local", Path(tmp_path / "r"), True, [], None)
    out = capsys.readouterr().out
    assert "stale" in out.lower()


def test_heading_does_not_claim_a_fetch_that_did_not_happen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    src = _upstream_with_squash_merged(tmp_path)
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", src.resolve().as_uri())
    run_command("local", Path(tmp_path / "r"), True, [], None)
    out = capsys.readouterr().out
    # Under --no-fetch the heading must not read as a fresh fetch.
    assert "fetched 202" not in out or "stale" in out.lower()


def test_successful_fetch_is_not_reported_stale(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    src = _upstream_with_squash_merged(tmp_path)
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\nb\n")
    commit(repo, "base")
    run(repo, "remote", "add", "origin", src.resolve().as_uri())
    run_command("local", Path(tmp_path / "r"), False, [], None)
    out = capsys.readouterr().out
    assert "stale" not in out.lower()


def test_missing_path_is_a_usage_error(tmp_path: Path):
    # The exit code is asserted end to end in test_freshness_and_exit.py
    # against the real entry point; this only pins that the command refuses
    # rather than degrading to an empty, exit-0 report.
    # _resolve_root is private, and reaching for it is the point: the exit code
    # is covered end to end elsewhere, this pins the refusal itself.
    from git_ferret.cli import UsageError, _resolve_root  # pyright: ignore[reportPrivateUsage]

    with pytest.raises(UsageError):
        _resolve_root(tmp_path / "nope")


def test_report_records_whether_fetch_was_attempted():
    r = RepoReport(path=Path("/tmp/r"), base_ref="origin/main", fetch_attempted=False)
    assert r.fetch_attempted is False


def test_stale_warning_counts_only_repositories_that_were_analysed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    # A repository whose analysis failed produced no section, so it cannot be
    # counted stale or fresh. The footer divides analysed repositories, not
    # discovered ones, and the failed one is already on stderr.
    for name in ("a", "b"):
        repo = make_repo(tmp_path / name)
        (repo / "f.txt").write_text("a\n")
        commit(repo, "base")

    real_analyse = cli_module.analyse_local

    def fail_on_b(repo: Path, config: Config, base_ref: str | None) -> RepoReport:
        if repo.name == "b":
            raise GitError(["status"], 128, "boom")
        return real_analyse(repo, config, base_ref)

    monkeypatch.setattr(cli_module, "analyse_local", fail_on_b)

    run_command("local", tmp_path, True, [], None)
    captured = capsys.readouterr()

    assert "1 of 1 repositories" in captured.out
    assert "## b" not in captured.out
    assert "error analysing" in captured.err
