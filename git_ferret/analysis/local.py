# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Local branch and worktree state: what is checked out, and what is amiss."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from git_ferret.config import Config, is_always_excluded
from git_ferret.discovery import list_worktrees
from git_ferret.gitcmd import run_git
from git_ferret.gitops import (
    list_branches,
    refs_updated_at,
    stash_entries,
)
from git_ferret.models import BranchInfo, Finding, RepoReport, Status, WorktreeInfo

NO_BASE_REASON = "no base branch (neither origin/main, origin/master, main nor master)"
SHELF_ROOT = Path(".idea") / "shelf"
AUTO_SHELF_PREFIX = "Uncommitted_changes_before_"
SHELF_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M"


def branch_finding(branch: BranchInfo) -> Finding | None:
    """One finding for *branch*, or ``None`` when it should not be listed.

    Overlapping conditions collapse to a single primary status in precedence
    order, because a branch whose upstream was deleted is simultaneously ahead
    of an upstream that no longer exists. The primary label is the one that
    determines the action, and the supporting detail is kept rather than
    discarded: "upstream deleted" alone cannot distinguish a branch abandoned
    this morning from one abandoned a year ago with work still on it.
    """
    age = _age_suffix(branch.last_commit_rel)
    if branch.upstream_gone:
        extra = f"also {branch.ahead} commits unpushed" if branch.ahead else None
        detail = " · ".join(p for p in (extra, age) if p)
        return _finding(
            branch,
            Status.UPSTREAM_DELETED,
            f"upstream deleted on remote{' · ' + detail if detail else ''}",
        )
    if branch.ahead > 0 and branch.behind > 0:
        return _finding(
            branch,
            Status.DIVERGED,
            f"{branch.ahead} ahead / {branch.behind} behind, cannot fast-forward"
            + (f" · {age}" if age else ""),
        )
    if not branch.has_upstream:
        return _finding(
            branch, Status.NOT_PUSHED, f"no upstream configured{' · ' + age if age else ''}"
        )
    if branch.ahead > 0:
        return _finding(
            branch, Status.NOT_PUSHED, f"{branch.ahead} commits ahead{' · ' + age if age else ''}"
        )
    # Nothing to say beyond the marker: this branch is not the problem, and a
    # "fully pushed" line spends a finding's worth of attention restating that.
    return _finding(branch, Status.OK, age)


def _age_suffix(last_commit_rel: str) -> str:
    if not last_commit_rel:
        return ""
    return f"last commit {last_commit_rel}"


def _finding(branch: BranchInfo, status: Status, detail: str) -> Finding:
    return Finding(
        branch=branch.name,
        status=status,
        detail=detail,
    )


def worktree_status(worktree: Path) -> tuple[bool, str]:
    """``(dirty, detail)`` for one worktree.

    Untracked files count as dirty: they are unsaved work, and a report that
    called a worktree clean while untracked files sat in it would be wrong.

    A status that cannot be read is reported as **dirty**, not clean. This value
    gates the tool's only write, and a safety gate must fail closed, so reporting
    an unreadable worktree as clean would let a fast-forward proceed on a
    worktree whose state is unknown.
    """
    proc = run_git(worktree, "status", "--porcelain", check=False)
    if proc.returncode != 0:
        return True, "worktree status unreadable"
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return False, ""
    untracked = sum(1 for line in lines if line.startswith("??"))
    modified = len(lines) - untracked
    parts: list[str] = []
    if modified:
        parts.append(f"{modified} file{'s' if modified != 1 else ''} modified")
    if untracked:
        parts.append(f"{untracked} untracked")
    return True, ", ".join(parts)


def analyse_local(repo: Path, config: Config, base_ref: str | None) -> RepoReport:
    """Report on every worktree and every non-excluded local branch.

    This never writes anything and never contacts a remote: it reports on
    whatever is already in ``.git``, stamping the age of the last successful
    fetch so a stale answer is visibly stale. Whether a fetch was attempted this
    run, and whether it succeeded, is the caller's to record.
    """
    report = RepoReport(path=repo, base_ref=base_ref)

    # Always stamp the age of the last successful fetch. Without this a
    # --no-fetch run reports no time at all, so stale state becomes
    # indistinguishable from fresh state.
    report.fetched_at = refs_updated_at(repo)

    for path, branch_name in list_worktrees(repo):
        dirty, detail = worktree_status(path)
        report.worktrees.append(
            WorktreeInfo(path=path, branch=branch_name, dirty=dirty, dirty_detail=detail)
        )
        if branch_name is None:
            report.findings.append(
                Finding(
                    branch=str(path),
                    status=Status.DETACHED,
                    detail="detached HEAD",
                )
            )
        if dirty:
            report.findings.append(
                Finding(
                    branch=branch_name or str(path),
                    status=Status.DIRTY,
                    detail=detail,
                )
            )
        _report_shelves(path, branch_name, report)

    if base_ref is None:
        # A missing base is reported, but it does not skip anything here: local
        # branch status (pushed, dirty, ...) is not measured against the base, so
        # the branches are still listed. Only `remote` and `merged`, whose
        # verdicts do depend on the base, mark the repository skipped.
        report.findings.append(
            Finding(
                branch=repo.name,
                status=Status.NO_BASE,
                detail=NO_BASE_REASON,
            )
        )

    _report_stashes(repo, report)

    for branch in list_branches(repo):
        if is_always_excluded(branch.name, base_ref):
            # `main`, `master`, and the base ref are never listed as branches.
            continue
        if config.is_whitelisted(branch.name) and branch_status_is_clean(branch):
            # The whitelist suppresses "exists and is fine". A whitelisted
            # branch with a real problem still surfaces.
            continue
        finding = branch_finding(branch)
        if finding is not None:
            report.findings.append(finding)

    return report


def _report_shelves(worktree: Path, branch: str | None, report: RepoReport) -> None:
    """Report IntelliJ shelves: work parked where no git command can see it."""
    try:
        entries = sorted((worktree / SHELF_ROOT).iterdir(), key=lambda entry: entry.name)
    except OSError:
        # No shelf directory, or one that cannot be read. Neither is a shelf.
        return
    for shelf in entries:
        if not shelf.is_dir() or shelf.name.startswith(AUTO_SHELF_PREFIX):
            continue
        try:
            modified = datetime.fromtimestamp(shelf.stat().st_mtime).strftime(
                SHELF_TIMESTAMP_FORMAT
            )
        except OSError:
            modified = "unknown"
        report.findings.append(
            Finding(
                branch=branch or str(worktree),
                status=Status.SHELF,
                detail=f'IntelliJ shelf "{shelf.name}", modified {modified}, '
                "contents not inspected",
            )
        )


def _report_stashes(repo: Path, report: RepoReport) -> None:
    """Report stashes: they are half-finished work this tool exists to surface."""
    for entry in stash_entries(repo):
        report.findings.append(
            Finding(
                branch=repo.name,
                status=Status.STASH,
                detail=entry,
            )
        )


def branch_status_is_clean(branch: BranchInfo) -> bool:
    """Whether *branch* has nothing worth reporting."""
    return not branch.upstream_gone and branch.ahead == 0 and branch.has_upstream
