# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for markdown report rendering."""

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from git_ferret.models import Finding, RepoReport, Status
from git_ferret.report import emit, render_header, render_repo, render_report


def _repo(**kwargs: Any) -> RepoReport:
    return RepoReport(path=Path("/tmp/api"), base_ref="origin/main", **kwargs)


class _Terminal(io.StringIO):
    """A stream that claims to be a terminal, so ``emit`` takes the rich path."""

    def isatty(self) -> bool:
        return True


def _on_screen(*blocks: str) -> list[str]:
    """*blocks* as a terminal shows them, one list entry per line.

    The styling is stripped and the right-hand padding that ``rich`` adds to
    fill the width is trimmed, so a test can assert on layout.
    """
    buffer = _Terminal()
    for block in blocks:
        emit(block, buffer)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", buffer.getvalue())
    return [line.rstrip() for line in plain.split("\n")]


def test_render_includes_repo_heading_and_findings():
    rep = _repo()
    rep.findings.append(
        Finding(branch="feat/x", status=Status.NOT_PUSHED, detail="3 commits ahead")
    )
    out = render_report([rep], stale_count=0)
    assert "## /tmp/api" in out
    assert "[NOT PUSHED]" in out
    assert "feat/x" in out


def test_render_uses_absolute_fetch_timestamp():
    rep = _repo(fetched_at=datetime(2026, 10, 16, 9, 41, 2))
    out = render_report([rep], stale_count=0)
    assert "2026-10-16 09:41:02" in out


def test_finding_line_puts_the_marker_straight_after_the_branch():
    rep = _repo()
    rep.findings.append(
        Finding(branch="feat/x", status=Status.NOT_PUSHED, emoji="⬆️", detail="3 commits ahead")
    )
    out = render_report([rep], stale_count=0)
    assert "- ⬆️ `feat/x` [NOT PUSHED] 3 commits ahead\n" in out


def test_render_contains_no_ansi_escapes():
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.OK))
    out = render_report([rep], stale_count=0)
    assert "\x1b[" not in out


def test_render_emits_stale_warning_once():
    out = render_report([_repo()], stale_count=2)
    assert "stale" in out.lower()
    assert out.lower().count("stale") == 1


def test_render_omits_stale_warning_when_none():
    out = render_report([_repo()], stale_count=0)
    assert "stale" not in out.lower()


def test_render_has_no_markdown_tables():
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.OK))
    out = render_report([rep], stale_count=0)
    assert "|" not in out


def test_marker_survives_without_emoji():
    # Emoji are decorative; the marker alone must carry the meaning.
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.CONFLICTS, emoji="❌"))
    out = render_report([rep], stale_count=0)
    assert "[CONFLICTS]" in out


def test_a_missing_emoji_falls_back_to_the_status_glyph():
    # Every call site need not remember to pass one: the status supplies it,
    # so a list reads by shape regardless of who built the finding.
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.DIRTY))
    out = render_report([rep], stale_count=0)
    assert f"- {Status.DIRTY.EMOJI} `b` [DIRTY]" in out


def test_render_survives_missing_emoji_entirely():
    # And an explicitly blank emoji is the same as none: still a line, still a
    # marker, and still the status's own glyph rather than a bare dash.
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.DIRTY, emoji=""))
    out = render_report([rep], stale_count=0)
    assert f"- {Status.DIRTY.EMOJI} `b` [DIRTY]" in out


def test_render_shows_base_ref():
    out = render_report([_repo()], stale_count=0)
    assert "origin/main" in out


def test_render_shows_skipped_reason():
    rep = RepoReport(path=Path("/tmp/web"), base_ref=None, skipped_reason="no base branch")
    out = render_report([rep], stale_count=0)
    assert "no base branch" in out


def test_every_repo_gets_a_heading_even_when_clean():
    out = render_report(
        [_repo(), RepoReport(path=Path("/tmp/clean"), base_ref="origin/main")], stale_count=0
    )
    assert "/tmp/api" in out and "/tmp/clean" in out


def test_starts_with_top_level_heading():
    out = render_report([_repo()], stale_count=0)
    assert out.startswith("# git-ferret")


def test_safe_to_delete_reason_is_shown():
    rep = _repo()
    rep.findings.append(
        Finding(
            branch="origin/done",
            status=Status.SAFE_TO_DELETE,
            detail="safe to delete: merged into origin/main",
            emoji=Status.SAFE_TO_DELETE.EMOJI,
        )
    )
    out = render_report([rep], stale_count=0)
    assert "safe to delete" in out
    assert "- 🗑️ `origin/done` [SAFE TO DELETE] safe to delete: merged into origin/main\n" in out


def test_empty_report_list_still_renders_header():
    out = render_report([], stale_count=0)
    assert out.startswith("# git-ferret")


def test_fetch_failure_is_flagged():
    rep = _repo(fetch_failed=True)
    out = render_report([rep], stale_count=1)
    assert "fetch failed" in out
    # A failed fetch means the run is reading state it could not refresh.
    assert "stale" in out.lower()


def test_fetch_failure_without_a_timestamp_says_so():
    rep = _repo(fetch_failed=True)
    out = render_report([rep], stale_count=1)
    assert "no local refs" in out


def test_heading_is_followed_directly_by_the_fetch_line():
    # The title and the line under it are one unit; only repositories are
    # separated from each other.
    rep = _repo(fetched_at=datetime(2026, 10, 16, 9, 41, 2))
    out = render_report([rep], stale_count=0)
    assert "## /tmp/api\nfetched 2026-10-16 09:41:02" in out


def test_findings_are_separated_from_the_fetch_line():
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.OK))
    out = render_report([rep], stale_count=0)
    assert "base: origin/main\n\n- " in out


def test_repos_are_separated_by_a_blank_line():
    out = render_report(
        [_repo(), RepoReport(path=Path("/tmp/web"), base_ref="origin/main")], stale_count=0
    )
    assert "## /tmp/api\n" in out
    assert "\n\n## /tmp/web\n" in out


def test_a_skipped_repo_is_separated_from_the_previous_one():
    out = render_report(
        [
            _repo(),
            RepoReport(path=Path("/tmp/web"), base_ref=None, skipped_reason="no base branch"),
        ],
        stale_count=0,
    )
    assert "## /tmp/api\n" in out and "\n\n## /tmp/web\n" in out


def test_a_skip_reason_shares_the_header_line():
    # On a second source line it would be one paragraph with the header above
    # it, and the renderer would join them into one line on screen.
    rep = RepoReport(path=Path("/tmp/web"), base_ref=None, skipped_reason="no base branch")
    out = render_report([rep], stale_count=0)
    assert "## /tmp/web\nnever fetched · skipped: no base branch\n" in out


def test_a_repo_that_was_never_fetched_is_not_called_empty():
    # fetched_at is None means there are no refs to date the state, which is a
    # local-only repository, not one without commits. "no commits yet" used to
    # contradict the `base: main` printed right beside it.
    rep = RepoReport(
        path=Path("/tmp/local"), base_ref="main", fetched_at=None, fetch_attempted=False
    )
    out = render_report([rep], stale_count=1)
    assert "no commits yet" not in out
    assert "never fetched" in out


def test_stale_warning_is_separated_from_the_first_repo():
    out = render_report([_repo()], stale_count=1)
    assert "this run)\n\n## /tmp/api" in out


def test_repo_heading_is_relative_to_the_scan_root():
    rep = RepoReport(path=Path("/home/dev/src/api"), base_ref="origin/main")
    out = render_report([rep], stale_count=0, root=Path("/home/dev/src"))
    assert "## api\n" in out
    assert "/home/dev/src" not in out


def test_nested_repo_heading_keeps_its_path_below_the_root():
    rep = RepoReport(path=Path("/home/dev/src/work/api"), base_ref="origin/main")
    out = render_report([rep], stale_count=0, root=Path("/home/dev/src"))
    assert "## work/api\n" in out


def test_the_scan_root_itself_is_named_as_dot():
    rep = RepoReport(path=Path("/home/dev/src"), base_ref="origin/main")
    out = render_report([rep], stale_count=0, root=Path("/home/dev/src"))
    assert "## .\n" in out


def test_a_repo_outside_the_root_keeps_its_full_path():
    # Discovery cannot produce one, but a report that lost its own subject
    # because of a relative-path calculation would be worse than a long path.
    rep = RepoReport(path=Path("/elsewhere/api"), base_ref="origin/main")
    out = render_report([rep], stale_count=0, root=Path("/home/dev/src"))
    assert "## /elsewhere/api\n" in out


def test_without_a_root_the_full_path_is_shown():
    out = render_report([_repo()], stale_count=0)
    assert "## /tmp/api\n" in out


def test_streaming_one_repository_at_a_time_equals_the_whole_document():
    # The CLI streams and the document renderer batches. If they ever disagree
    # about spacing, a report looks right on screen and wrong in a file.
    api = _repo()
    api.findings.append(Finding(branch="feat/x", status=Status.NOT_PUSHED))
    web = RepoReport(path=Path("/tmp/web"), base_ref=None, skipped_reason="no base branch")

    streamed = render_header(stale_count=0, total=2)
    streamed += render_repo(api, root=Path("/tmp")) + render_repo(web, root=Path("/tmp"))

    assert streamed.rstrip() + "\n" == render_report([api, web], stale_count=0, root=Path("/tmp"))


def test_screen_keeps_the_fetch_line_directly_under_the_title():
    # rich pads a heading with a blank line, which would split one header in
    # two and leave the reader wondering which repository the stamp belongs to.
    rep = _repo(fetched_at=datetime(2026, 10, 16, 9, 41, 2))
    lines = _on_screen(render_repo(rep))
    assert lines[0] == "/tmp/api"
    assert lines[1] == "fetched 2026-10-16 09:41:02 · base: origin/main"


def test_screen_separates_one_repository_from_the_next():
    lines = _on_screen(render_repo(_repo()), render_repo(_repo()))
    second = lines.index("/tmp/api", 1)
    assert lines[second - 1] == ""


def test_screen_separates_findings_from_the_line_above_them():
    rep = _repo()
    rep.findings.append(Finding(branch="b", status=Status.OK))
    lines = _on_screen(render_repo(rep))
    assert lines[2] == ""
    assert "[OK]" in lines[3]


def test_screen_shows_a_skip_reason_where_the_file_does():
    rep = RepoReport(path=Path("/tmp/web"), base_ref=None, skipped_reason="no base branch")
    lines = _on_screen(render_repo(rep))
    # Screen and file carry the same words, and the newline between them is
    # still a newline rather than a space.
    assert lines[1] == "never fetched · skipped: no base branch"
    assert lines[2] == ""


def test_screen_keeps_the_document_title_apart_from_the_stale_warning():
    # Only a repository title hugs the line beneath it; the document title is
    # not a header for the warning and keeps its blank line.
    lines = _on_screen(render_header(stale_count=1, total=3))
    assert lines[0].strip() == "git-ferret"
    assert lines[1] == ""


def test_a_failed_fetch_with_a_timestamp_names_the_state_it_read():
    # The two facts a reader needs: the refresh failed, and the report below is
    # from this timestamp rather than from now.
    rep = _repo(fetched_at=datetime(2026, 10, 16, 9, 41, 2), fetch_failed=True)
    out = render_report([rep], stale_count=1)
    assert "fetch failed; analysed from state as of 2026-10-16 09:41:02" in out


def _strict_stream(encoding: str) -> tuple[io.TextIOWrapper, io.BytesIO]:
    """A stream that enforces *encoding* on write, as a real stdout does."""
    raw = io.BytesIO()
    return io.TextIOWrapper(raw, encoding=encoding, errors="strict", newline=""), raw


class _StrictTerminal(io.TextIOWrapper):
    """A strict stream that claims to be a terminal, so ``emit`` uses rich."""

    def isatty(self) -> bool:
        return True


def _terminal(encoding: str) -> tuple[_StrictTerminal, io.BytesIO]:
    raw = io.BytesIO()
    return _StrictTerminal(raw, encoding=encoding, errors="strict", newline=""), raw


def test_emit_survives_a_stream_that_cannot_encode_emoji():
    # Windows consoles and redirected output can be cp1252 or ASCII. The
    # report must still be written, because the bracketed marker carries the
    # meaning; the emoji is decoration.
    rep = _repo()
    rep.findings.append(Finding(branch="feat/x", status=Status.NOT_PUSHED))
    stream, raw = _strict_stream("ascii")

    emit(render_repo(rep), stream)
    stream.flush()

    output = raw.getvalue().decode("ascii")
    assert "`feat/x` [NOT PUSHED]" in output
    assert "## /tmp/api" in output
    assert "⬆" not in output


def test_emit_survives_a_terminal_that_cannot_encode_emoji():
    # rich adds bullet glyphs of its own, so the TTY path needs the same guard
    # as a redirected stream rather than only sanitising the report text.
    rep = _repo()
    rep.findings.append(Finding(branch="feat/x", status=Status.NOT_PUSHED))
    stream, raw = _terminal("ascii")

    emit(render_repo(rep), stream)
    stream.flush()

    output = re.sub(r"\x1b\[[0-9;]*m", "", raw.getvalue().decode("ascii"))
    assert "feat/x [NOT PUSHED]" in output
    assert "/tmp/api" in output
    assert "⬆" not in output


def test_emit_leaves_utf8_output_untouched():
    stream, raw = _strict_stream("utf-8")
    text = "⬆️ `b` [NOT PUSHED]\n"
    emit(text, stream)
    stream.flush()
    assert raw.getvalue() == text.encode()
