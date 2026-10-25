# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the shared finding and report models."""

from datetime import datetime
from pathlib import Path

from git_ferret.models import Finding, RepoReport, Status


def test_finding_defaults():
    f = Finding(branch="feat/x", status=Status.NOT_PUSHED)
    assert f.detail == "" and f.emoji == ""


def test_repo_report_is_empty_by_default():
    r = RepoReport(path=Path("/tmp/r"))
    assert r.findings == [] and r.worktrees == [] and r.skipped_reason is None


def test_status_values_are_exactly_the_documented_set():
    assert {s.name for s in Status} == {
        "OK",
        "NOT_PUSHED",
        "NOT_MERGED",
        "DIVERGED",
        "UPSTREAM_DELETED",
        "CONFLICTS",
        "UNKNOWN",
        "DIRTY",
        "DETACHED",
        "STASH",
        "UNREACHABLE",
        "NO_BASE",
        "SAFE_TO_DELETE",
        "UNSAFE_TO_DELETE",
    }


def test_marker_text_distinguishes_a_deletion_candidate_from_a_kept_branch():
    # Both are merged branches. Reporting either of them as [OK] told the reader
    # nothing about which one they were being invited to delete.
    assert Status.SAFE_TO_DELETE.MARKER == "[SAFE TO DELETE]"
    assert Status.UNSAFE_TO_DELETE.MARKER == "[UNSAFE TO DELETE]"
    assert Status.OK.MARKER == "[OK]"


def test_status_is_a_str_enum():
    # StrEnum so markers and statuses compare as strings without conversion.
    assert Status.OK == "OK"
    assert f"{Status.NOT_PUSHED}" == "NOT_PUSHED"


def test_status_marker_texts():
    assert Status.OK.MARKER == "[OK]"
    assert Status.NOT_PUSHED.MARKER == "[NOT PUSHED]"
    assert Status.UPSTREAM_DELETED.MARKER == "[UPSTREAM DELETED]"
    assert Status.NO_BASE.MARKER == "[NO BASE]"


def test_every_status_has_an_emoji():
    # The table is keyed by the enum, so a status added without a glyph would
    # raise here rather than render a blank space in the report.
    assert all(status.EMOJI for status in Status)


def test_no_two_statuses_share_an_emoji():
    # Sharing is what made the glyphs useless: seven findings wearing a warning
    # sign look alike at a glance, which is the only glance there is.
    glyphs = [status.EMOJI for status in Status]
    assert len(set(glyphs)) == len(glyphs)


def test_marker_and_emoji_are_separate_concerns():
    # The marker carries the meaning; the emoji is decoration and may be lost.
    assert Status.OK.MARKER == "[OK]" and Status.OK.EMOJI == "✓"


def test_repo_report_is_stale_only_when_nothing_was_refreshed():
    # A successful fetch is fresh; an unfetched or failed one is not.
    assert RepoReport(path=Path("/tmp/r")).is_stale is True
    assert RepoReport(path=Path("/tmp/r"), fetch_attempted=False).is_stale is True
    assert RepoReport(path=Path("/tmp/r"), fetch_failed=True).is_stale is True
    fresh = RepoReport(path=Path("/tmp/r"), fetched_at=datetime(2026, 10, 16))
    assert fresh.is_stale is False
    # No remote means nothing could have been refreshed: local-only is not
    # stale, however long it has been since anything touched it.
    local_only = RepoReport(path=Path("/tmp/r"), fetch_attempted=False, has_remote=False)
    assert local_only.is_stale is False
