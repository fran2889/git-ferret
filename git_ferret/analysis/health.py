# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Remote reachability, reported the same way by every command.

A repository with no configured remote, or whose fetch failed, is unreachable:
the two cases are different evidence for the same finding, so they live in one
place and every command reports them identically. The finding is appended to a
report the caller has already stamped with the run's fetch outcome, which is why
this takes a finished report rather than fetching itself.
"""

from __future__ import annotations

from pathlib import Path

from git_ferret.gitcmd import run_git
from git_ferret.models import Finding, RepoReport, Status


def report_remote_health(repo: Path, report: RepoReport) -> None:
    """Append an ``[UNREACHABLE]`` finding when the remote is missing or failed.

    Under ``--no-fetch`` no probe is made, so a server-deleted project is
    undetectable and must not be implied either way; only a missing remote is
    reported then. The fetch failure is read from *report*, so the caller owns
    the one place a fetch happened.
    """
    remotes = run_git(repo, "remote").stdout.split()
    # Recorded on the report so staleness can tell a local-only repository
    # (nothing to refresh, so never stale) from one whose fetch failed.
    report.has_remote = bool(remotes)
    if not remotes:
        report.findings.append(
            Finding(
                branch=repo.name,
                status=Status.UNREACHABLE,
                detail="no remote configured",
            )
        )
    elif report.fetch_attempted and report.fetch_failed:
        report.findings.append(
            Finding(
                branch=repo.name,
                status=Status.UNREACHABLE,
                detail=f"fetch failed for {', '.join(remotes)}",
            )
        )
