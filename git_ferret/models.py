# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Shared data shapes for analysis and reporting.

Every analysis task produces these, and the report task renders them, so the
names and fields here are the contract between the two halves of the program.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path

# `git merge-tree --write-tree` exit codes, verified empirically. They separate
# the three failure modes without heuristics: 0 is a clean merge, 1 lists
# conflicting hunks, 128 is a refusal with no merge base.
MERGED_EXIT = 0
CONFLICT_EXIT = 1


class Status(StrEnum):
    """A single finding's state, rendered as a capitalised bracketed marker."""

    OK = "OK"
    NOT_PUSHED = "NOT_PUSHED"
    NOT_MERGED = "NOT_MERGED"
    DIVERGED = "DIVERGED"
    UPSTREAM_DELETED = "UPSTREAM_DELETED"
    CONFLICTS = "CONFLICTS"
    UNKNOWN = "UNKNOWN"
    DIRTY = "DIRTY"
    DETACHED = "DETACHED"
    STASH = "STASH"
    UNREACHABLE = "UNREACHABLE"
    NO_BASE = "NO_BASE"
    # The two verdicts `merged` produces for a branch that is genuinely merged.
    # They are statuses rather than a boolean on the finding because the marker
    # is what a reader scans: a candidate and a branch that must be kept are
    # not the same thing, and `[OK]` said they were.
    SAFE_TO_DELETE = "SAFE_TO_DELETE"
    UNSAFE_TO_DELETE = "UNSAFE_TO_DELETE"

    @property
    def MARKER(self) -> str:
        """The bracketed text that carries the meaning.

        Emoji are decorative; this is the part that must survive a font-less
        terminal, a pipe, and a copy-paste into a ticket.
        """
        return f"[{self.value.replace('_', ' ')}]"

    @property
    def EMOJI(self) -> str:
        """The glyph for this status, so a list can be scanned by shape.

        One per status, rather than three shared across all of them: with ⚠️ on
        seven different findings it distinguished nothing at a glance, which is
        the only job an emoji has once the marker is there.
        """
        return EMOJI_FOR[self]


# Keyed by the enum rather than by its string, so a status added above without
# a glyph here fails at import rather than quietly rendering nothing.
EMOJI_FOR: dict[Status, str] = {
    Status.OK: "✓",
    Status.NOT_PUSHED: "⬆️",
    Status.NOT_MERGED: "🔀",
    Status.DIVERGED: "↔️",
    Status.UPSTREAM_DELETED: "🧹",
    Status.CONFLICTS: "💥",
    Status.UNREACHABLE: "🔌",
    Status.UNKNOWN: "❓",
    Status.DIRTY: "✏️",
    Status.STASH: "📦",
    Status.DETACHED: "📍",
    Status.NO_BASE: "🧭",
    Status.SAFE_TO_DELETE: "🗑️",
    Status.UNSAFE_TO_DELETE: "🚫",
}


@dataclass(frozen=True)
class Finding:
    """One line of the report about one branch or worktree.

    ``branch`` holds the display ref: a bare name for local analysis, an
    ``origin/x``-style ref for remote analysis.

    ``emoji`` is an override, not a requirement: left blank it falls back to the
    status's own glyph when the line is rendered, so a caller cannot forget it
    and produce a line with no shape to scan. It exists for the one case where a
    status is not quite the verdict being reported.
    """

    branch: str
    status: Status
    detail: str = ""
    emoji: str = ""


@dataclass
class BranchInfo:
    """A local branch and its relationship to its upstream."""

    name: str
    remote: str | None = None
    upstream: str | None = None
    upstream_gone: bool = False
    ahead: int = 0
    behind: int = 0
    has_upstream: bool = False
    last_commit_rel: str = ""


@dataclass
class WorktreeInfo:
    """One worktree of a repository, primary or linked."""

    path: Path
    branch: str | None
    dirty: bool = False
    dirty_detail: str = ""


@dataclass
class RepoReport:
    """Everything the report needs to say about one repository."""

    path: Path
    base_ref: str | None = None
    fetched_at: datetime | None = None
    fetch_failed: bool = False
    fetch_attempted: bool = True
    # Whether the repository has a remote at all. A local-only repository has
    # nothing to refresh, so it is never "stale"; it already says so with its
    # own [UNREACHABLE] finding.
    has_remote: bool = True
    skipped_reason: str | None = None
    worktrees: list[WorktreeInfo] = field(default_factory=list[WorktreeInfo])
    findings: list[Finding] = field(default_factory=list[Finding])

    @property
    def is_stale(self) -> bool:
        """Whether this report rests on state this run did not refresh.

        True whenever no fetch was attempted (``--no-fetch``) or the attempt
        failed. A repository that was never fetched is a different case from one
        fetched seconds ago, and both differ from one holding month-old refs.

        False for a repository with no remote: there is nothing that could have
        been refreshed, and counting it would inflate a warning that exists to
        flag state which could be out of date.
        """
        if not self.has_remote:
            return False
        return not self.fetch_attempted or self.fetch_failed or self.fetched_at is None
