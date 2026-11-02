# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""End-to-end coverage: all three subcommands over a realistic repository tree."""

from pathlib import Path
from typing import TextIO

import pytest
from typer.testing import CliRunner

from git_ferret import cli as cli_module
from git_ferret.cli import build_parser
from tests.helpers import clone_local, commit, make_repo, run

runner = CliRunner()


def _tree(tmp_path: Path):
    """A pushed+stale branch, a merged branch, a clean branch, and a remote-less repo."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")

    run(src, "checkout", "-b", "stale-work")
    (src / "f.txt").write_text("a\nSTALE\nc\n")
    commit(src, "work")
    run(src, "checkout", "main")

    run(src, "checkout", "-b", "already-done")
    (src / "d.txt").write_text("done\n")
    commit(src, "finished work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "already-done")
    commit(src, "merge already-done")

    clone = clone_local(src, tmp_path / "project")
    run(clone, "fetch", "--all", "--prune")

    # Unpushed work that exists only in the clone.
    run(clone, "checkout", "-b", "local-only", "origin/main")
    (clone / "mine.txt").write_text("mine\n")
    commit(clone, "local only")
    run(clone, "checkout", "main")

    make_repo(tmp_path / "solo")  # a repository with no remote at all
    return tmp_path


def test_local_end_to_end_emits_valid_markdown(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    assert res.exit_code == 0, res.output
    assert res.stdout.startswith("# git-ferret")
    assert "\x1b[" not in res.stdout


def test_all_three_subcommands_succeed(tmp_path: Path):
    root = _tree(tmp_path)
    for cmd in ("local", "remote", "merged"):
        res = runner.invoke(build_parser(), [cmd, str(root), "--no-fetch"])
        assert res.exit_code == 0, f"{cmd} failed: {res.output}"


def test_reports_every_discovered_repo(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    assert "project" in res.stdout
    assert "solo" in res.stdout


def test_output_has_no_tables(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    assert "|" not in res.stdout


def test_every_finding_carries_a_marker(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    for line in res.stdout.splitlines():
        if line.startswith("- ") and "`" in line:
            assert "[" in line and "]" in line, f"unmarked finding: {line}"


def test_findings_are_not_dashed_off_from_their_marker(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    for line in res.stdout.splitlines():
        if line.startswith("- ") and "`" in line:
            # `branch` [MARKER] detail: the marker delimits itself, so a
            # separator in front of it is a third thing to read past.
            assert "— " not in line, f"dashes still in the output: {line}"


def test_merged_reports_the_merged_branch(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["merged", str(root), "--no-fetch"])
    assert "origin/already-done" in res.stdout
    assert "safe to delete" in res.stdout


def test_merged_marks_the_deletion_candidate_in_the_marker(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["merged", str(root), "--no-fetch"])
    # The point of the command: which branch can go, readable from the marker
    # alone, without reading a line of detail.
    assert "- 🗑️ `origin/already-done` [SAFE TO DELETE]" in res.stdout
    assert "[OK]" not in res.stdout


def test_merged_does_not_recommend_the_stale_branch(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["merged", str(root), "--no-fetch"])
    assert "origin/stale-work" not in res.stdout.split("safe to delete")[0]


def test_stale_warning_present_when_no_fetch(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    assert "stale" in res.stdout.lower()


def test_nested_repo_is_not_reported_twice(tmp_path: Path):
    outer = make_repo(tmp_path / "outer")
    make_repo(outer / "vendor" / "inner")
    res = runner.invoke(build_parser(), ["local", str(tmp_path), "--no-fetch"])
    assert res.stdout.count("## ") == 1


def test_repo_without_base_branch_states_the_reason(tmp_path: Path):
    repo = make_repo(tmp_path / "trunky")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "-m", "main", "trunk")
    res = runner.invoke(build_parser(), ["local", str(tmp_path), "--no-fetch"])
    assert "no base branch" in res.stdout
    # `local` still lists branches, so its heading must not say it skipped the
    # branch analysis; only `remote` and `merged` skip it.
    assert "skipped" not in res.stdout


def test_local_does_not_write_without_update(tmp_path: Path):
    root = _tree(tmp_path)
    before = run(root / "project", "status", "--porcelain").stdout
    runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    after = run(root / "project", "status", "--porcelain").stdout
    assert before == after


def test_headings_are_relative_to_the_given_root(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    headings = [ln for ln in res.stdout.splitlines() if ln.startswith("## ")]
    assert sorted(headings) == ["## project", "## solo", "## src"]
    assert str(root) not in res.stdout


def test_scanning_a_single_repo_names_it_as_dot(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root / "solo"), "--no-fetch"])
    assert "## .\n" in res.stdout


def test_every_heading_is_preceded_by_a_blank_line(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    # The terminal pads headings on the way out; the file must not depend on it.
    for before, heading in zip(res.stdout.split("\n"), res.stdout.split("\n")[1:], strict=False):
        if heading.startswith("## "):
            assert before == "", f"no blank line above: {heading!r}"


def test_every_heading_is_followed_by_its_fetch_line(tmp_path: Path):
    root = _tree(tmp_path)
    res = runner.invoke(build_parser(), ["local", str(root), "--no-fetch"])
    lines = res.stdout.split("\n")
    headings = [i for i, line in enumerate(lines) if line.startswith("## ")]
    for index in headings:
        assert lines[index + 1] != "", f"title and its line split apart: {lines[index]!r}"


def test_each_repository_is_fetched_just_before_its_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Streaming is the point of fetching per repository: the fetch for a repo is
    # followed immediately by that repo's section, not deferred behind every
    # other fetch. Record the two calls at the CLI boundary and leave git real.
    for name in ("a", "b"):
        repo = make_repo(tmp_path / name)
        (repo / "f.txt").write_text("a\n")
        commit(repo, "base")

    events: list[tuple[str, str]] = []
    real_fetch = cli_module._fetch_report  # pyright: ignore[reportPrivateUsage]
    real_emit = cli_module.emit

    def recording_fetch(repo: Path, no_fetch: bool) -> tuple[bool, bool]:
        events.append(("fetch", repo.name))
        return real_fetch(repo, no_fetch)

    def recording_emit(text: str, stream: TextIO | None = None) -> None:
        for name in ("a", "b"):
            if text.startswith(f"## {name}\n"):
                events.append(("section", name))
        real_emit(text, stream)

    monkeypatch.setattr(cli_module, "_fetch_report", recording_fetch)
    monkeypatch.setattr(cli_module, "emit", recording_emit)

    res = runner.invoke(build_parser(), ["local", str(tmp_path), "--no-fetch"])

    assert res.exit_code == 0, res.output
    assert events == [
        ("fetch", "a"),
        ("section", "a"),
        ("fetch", "b"),
        ("section", "b"),
    ]
