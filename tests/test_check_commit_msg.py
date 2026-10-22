# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the Conventional Commits subject checker the hook runs."""

from pathlib import Path

import pytest

from scripts.check_commit_msg import main, subject_of, validate


def _message(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(body)
    return path


@pytest.mark.parametrize(
    "subject",
    [
        "feat: add --version",
        "fix(cli): handle a missing path",
        "feat(api)!: drop the legacy flag",
        "docs: update the readme",
        "ci: run the suite on windows",
        "revert: restore the old parser",
        "chore: bump the lockfile",
        "test: cover the commit checker",
        "build: pin the build backend",
        "perf: avoid a second fetch",
        "refactor: split the report renderer",
        "style: wrap the long line",
        "chore: process the report",  # a word ending in "s" is not automatically rejected
    ],
)
def test_valid_subjects_pass(subject: str) -> None:
    assert validate(subject) is None


@pytest.mark.parametrize(
    "subject",
    [
        "feat add --version",
        "feature: add a thing",
        "Feat: add a thing",
        "feat: Add a thing",
        "feat: add a thing.",
        "feat: added a thing",
        "feat: adds a thing",
        "feat: adding a thing",
        "fix: fixed the bug",
        "fix: fixes the bug",
        "fix: fixing the bug",
        "docs(scope): updated the docs",
        "chore: bumping the version",
        "ci: ran the suite",
        "feat: ",
        "feat:  ",
    ],
)
def test_invalid_subjects_are_rejected(subject: str) -> None:
    assert validate(subject) is not None


@pytest.mark.parametrize(
    "subject",
    [
        "Merge branch 'main'",
        "Merge pull request #12 from fran2889/feat/x",
        'Revert "feat: add a thing"',
        "fixup! feat: add a thing",
        "squash! fix: repair the parser",
        "amend! docs: rewrite the guide",
        "Squashed commit of the following:",
    ],
)
def test_git_generated_subjects_pass_through(subject: str) -> None:
    assert validate(subject) is None


def test_subject_skips_blank_and_comment_lines() -> None:
    text = "\n# a comment\n\nfeat: add --version\n\n# Please enter the commit message\n"
    assert subject_of(text) == "feat: add --version"


def test_subject_skips_a_configured_comment_char() -> None:
    text = "; a comment\n\nfeat: add --version\n"
    assert subject_of(text, comment_char=";") == "feat: add --version"


def test_subject_with_an_empty_comment_char_reads_the_first_line() -> None:
    assert subject_of("feat: add --version\n", comment_char="") == "feat: add --version"


def test_subject_of_an_empty_message_is_none() -> None:
    assert subject_of("\n# only comments\n") is None


def test_main_accepts_a_valid_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_commit_msg", str(_message(tmp_path, "feat: add --version\n"))]) == 0
    assert capsys.readouterr().err == ""


def test_main_rejects_a_bad_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_commit_msg", str(_message(tmp_path, "feat: Add a thing.\n"))]) == 1
    assert "description" in capsys.readouterr().err.lower()


def test_main_rejects_an_empty_message(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_commit_msg", str(_message(tmp_path, "\n# nothing here\n"))]) == 1
    assert "empty" in capsys.readouterr().err.lower()


def test_main_uses_a_configured_comment_char(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _message(tmp_path, "; nothing here\n")
    assert main(["check_commit_msg", str(path), ";"]) == 1
    assert "empty" in capsys.readouterr().err.lower()


def test_main_reports_a_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check_commit_msg", str(tmp_path / "absent")]) == 1
    assert "does not exist" in capsys.readouterr().err
