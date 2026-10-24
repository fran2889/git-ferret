# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Rendering findings as markdown.

The output must be readable on a terminal *and* valid markdown in a file, so
this module produces plain text and never emits ANSI escapes or box-drawing
characters. Terminal prettification happens later, in :func:`emit`, and only
when stdout is a TTY.

There are no tables: wide tables do not wrap in a terminal, and this report is
read on screen far more often than in a rendered file.

Spacing is part of the text. A repository's title and the fetch stamp beneath
it are one unit with no blank line between; a blank line separates one
repository from the next.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from git_ferret.models import Finding, RepoReport

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"
WARNING_EMOJI = "⚠️"


def _line_for(finding: Finding) -> str:
    """One markdown list item: optional emoji, marker, branch, detail.

    The marker always stands on its own, so a missing glyph costs readability
    but never information. No separator before the marker: ``[NOT PUSHED]``
    delimits itself, and a dash between two self-delimiting parts is a third
    thing to read past.

    An emoji left blank falls back to the status's own glyph, so a list reads
    by shape rather than by which call sites remembered to pass one. An override
    is reserved for the one case where a status is not quite the verdict.
    """
    emoji = finding.emoji or finding.status.EMOJI
    parts = [f"{emoji} `{finding.branch}` {finding.status.MARKER}"]
    if finding.detail:
        parts.append(finding.detail)
    return "- " + " ".join(parts)


def _block(lines: list[str]) -> str:
    """Join *lines* into a markdown block terminated by one blank line.

    Every block ends the same way, so appending one to another always leaves a
    blank line between them without any caller having to add one.
    """
    return "\n".join(lines).rstrip("\n") + "\n\n"


def display_path(path: Path, root: Path | None) -> str:
    """*path* as a heading should show it: relative to the scan root.

    The root the user typed is the one part of the path they already know, so
    repeating it above every heading is pure noise, and with thirty
    repositories it is the noise that wraps. A repository that *is* the root
    prints as ``.``, matching how worktree findings name it.

    A path outside *root* keeps its full form rather than raising: discovery
    only ever yields repositories under the root, so this is a guard against a
    report losing its own subject, not a case with a nicer rendering.
    """
    if root is not None:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _header_line(report: RepoReport) -> str:
    """Everything this repository's own line has to say, on one line.

    One line, because the line under a title is joined to it by the renderer
    when the pair is read as a paragraph: a ``skipped:`` note on a second line
    reaches the screen glued to the first with a space where the newline was,
    and the two spellings of the same report stop matching.
    """
    parts: list[str] = []
    if report.fetched_at is not None:
        stamp = report.fetched_at.strftime(TIMESTAMP_FORMAT)
        if report.fetch_failed:
            parts.append(f"fetch failed; analysed from state as of {stamp}")
        else:
            parts.append(f"fetched {stamp}")
    elif report.fetch_failed:
        parts.append("fetch failed; no local refs to analyse")
    else:
        parts.append("never fetched")

    if report.base_ref:
        parts.append(f"base: {report.base_ref}")

    if report.skipped_reason:
        parts.append(f"skipped: {report.skipped_reason}")

    return " · ".join(parts)


def render_repo(report: RepoReport, root: Path | None = None) -> str:
    """One repository's section, terminated by the blank line after it.

    The title and the line under it belong together: the fetch stamp describes
    that repository, so it sits directly beneath the name with nothing between
    them. Sections are separated by one blank line, which is written into the
    text rather than left to the renderer. A markdown document has no way to
    say "space after the last block", so the terminal is what supplies it when
    blocks are streamed one at a time, and a report then runs together exactly
    where the file does not.
    """
    lines = [f"## {display_path(report.path, root)}", _header_line(report), ""]
    for finding in report.findings:
        lines.append(_line_for(finding))
    return _block(lines)


def render_header() -> str:
    """The document title, as a block separated from the first repository."""
    return _block(["# git-ferret"])


def render_footer(stale_count: int, total: int) -> str:
    """The stale-state warning, printed once after the report.

    It sits at the end rather than the top because repositories are fetched one
    at a time as their analysis starts: the count is not knowable until the last
    one has been read, and printing it early would mean delaying every result
    behind every fetch. Each repository's heading still carries its own
    timestamp, so the detail is available without reaching the footer.
    """
    if not stale_count:
        return ""
    return _block(
        [
            f"> {WARNING_EMOJI}  {stale_count} of {total} repositories "
            f"analysed from stale local state (no successful fetch this run)",
        ]
    )


def render_report(reports: list[RepoReport], stale_count: int, root: Path | None = None) -> str:
    """The whole report as markdown text, for callers holding every result.

    Same lines as streaming them one at a time, so the two cannot drift; only
    the trailing blank line is dropped, because a document ends with one
    newline rather than with a separator.
    """
    body = "".join(render_repo(report, root) for report in reports)
    return (render_header() + body + render_footer(stale_count, len(reports))).rstrip() + "\n"


def _split_heading(text: str) -> tuple[str, str]:
    """A leading ``##`` title line and the rest of the block, or just the text.

    A section title is rendered on its own so that the line beneath it stays
    beneath it. Rendered inside one markdown document, ``rich`` puts a blank
    line between a heading and whatever follows; here that "whatever" is the
    fetch stamp, which belongs to the title, and the gap pushes the two halves
    of one header apart.
    """
    title, newline, body = text.partition("\n")
    if newline and title.startswith("## "):
        return title, body
    return "", text


def emit(text: str, stream: TextIO | None = None) -> None:
    """Write *text*, richly only when the destination is a terminal.

    Piping must yield clean markdown, so styling is confined to the TTY path.
    The entry point reconfigures its streams to UTF-8, so this writes the text
    as-is rather than degrading characters the stream cannot encode.
    """
    out = stream if stream is not None else sys.stdout
    if not getattr(out, "isatty", lambda: False)():
        out.write(text)
        return

    from rich.console import Console
    from rich.markdown import Markdown

    console = Console(file=out, force_terminal=True)
    title, body = _split_heading(text)
    if title:
        console.print(Markdown(title))
    console.print(Markdown(body))
    # Markdown drops blank lines at the end of a document, so the gap between
    # two streamed blocks has to be written out here. Without it the terminal
    # runs one repository into the next while the file separates them.
    console.print()
