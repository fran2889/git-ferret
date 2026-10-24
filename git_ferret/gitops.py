# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Git operations that back the analyses: fetch, base refs, branch state.

Nothing here decides anything about what to report; it only asks git questions
and returns answers. The verdict logic lives in ``analysis/``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from git_ferret.gitcmd import GitError, run_git, run_git_text
from git_ferret.models import BranchInfo

# Tried in order. The remote-tracking ref wins because `merged` recommends
# deleting *remote* branches, and the only question that matters is whether the
# branch is absorbed into the branch the remote actually has. A stale local
# `main` would report a live branch as safe to delete.
BASE_CANDIDATES = ("origin/main", "origin/master", "main", "master")


def fetch_all(repo: Path) -> tuple[bool, datetime | None]:
    """``git fetch --all --prune``, returning a failed fetch rather than raising.

    ``--all`` rather than a bare fetch because analyses read remote branches
    across every configured remote; fetching only ``origin`` would leave the
    others permanently stale while the tool reported confident verdicts about
    them. Returns ``(success, time_of_last_successful_fetch)``.

    A fetch that runs past the timeout is a failed fetch like any other: the run
    carries on and the repository is reported as stale. A git that cannot be
    executed at all is an environment failure, not a fetch failure, and is left
    to the run boundary (:func:`git_ferret.gitcmd.require_git`).
    """
    try:
        proc = run_git(repo, "fetch", "--all", "--prune")
    except GitError:
        # check=False only raises for a timeout; a non-zero exit is handled
        # below, and a git that cannot run at all is GitUnavailable and must
        # reach the boundary.
        return False, None
    if proc.returncode != 0:
        return False, None
    return True, fetch_head_mtime(repo)


def _git_dir(repo: Path) -> Path:
    git_dir = Path(run_git_text(repo, "rev-parse", "--git-dir"))
    return git_dir if git_dir.is_absolute() else repo / git_dir


def fetch_head_mtime(repo: Path) -> datetime | None:
    """Modification time of ``.git/FETCH_HEAD``, or ``None`` if it is absent.

    Only a cross-run timestamp can support a meaningful staleness warning;
    "time since this run" would render as zero on every heading.
    """
    fetch_head = _git_dir(repo) / "FETCH_HEAD"
    if not fetch_head.exists():
        return None
    return datetime.fromtimestamp(fetch_head.stat().st_mtime)


def refs_updated_at(repo: Path) -> datetime | None:
    """When the remote-tracking refs were last written, or ``None``.

    ``git clone`` writes remote-tracking refs but no ``FETCH_HEAD``, so relying on
    that file alone labels every freshly cloned repository "never fetched" --
    a false staleness signal on the freshest state possible. The refs are the
    thing actually being read, so their write time is the honest answer.

    ``packed-refs`` counts too, since ``git gc`` moves loose refs into it.
    """
    git_dir = _git_dir(repo)
    newest: float | None = None

    candidates = [git_dir / "FETCH_HEAD", git_dir / "packed-refs"]
    remotes = git_dir / "refs" / "remotes"
    if remotes.is_dir():
        candidates.extend(p for p in remotes.rglob("*") if p.is_file())

    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest:
            newest = mtime
    return datetime.fromtimestamp(newest) if newest is not None else None


def resolve_base_ref(repo: Path) -> str | None:
    """The ref to treat as the base branch, or ``None`` when there is none.

    Never guesses ``develop`` or ``trunk``: absence means the repository is
    skipped with a warning, not that a plausible guess is made.
    """
    for candidate in BASE_CANDIDATES:
        proc = run_git(repo, "rev-parse", "--verify", "--quiet", candidate)
        if proc.returncode == 0:
            return candidate
    return None


def base_ref_is_remote(base_ref: str | None) -> bool:
    """Whether *base_ref* is a remote-tracking ref rather than a local one."""
    return base_ref is not None and "/" in base_ref


def tree_hash(repo: Path, ref: str) -> str | None:
    """Tree object of *ref*, the value the merge test compares against."""
    proc = run_git(repo, "rev-parse", f"{ref}^{{tree}}")
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def stash_entries(repo: Path) -> list[str]:
    """One description line per stash entry, newest first."""
    output = run_git_text(repo, "stash", "list")
    return [line for line in output.splitlines() if line.strip()]


def _ref_exists(repo: Path, ref: str) -> bool:
    return run_git(repo, "rev-parse", "--verify", "--quiet", ref).returncode == 0


def _merge_ref(repo: Path, branch: str) -> str | None:
    """A comparison ref for a branch whose upstream ref has been deleted.

    The remote-tracking ref is gone, so there is nothing left to compare
    against directly. The base branch is the best remaining yardstick: commits
    on this branch that the base does not have are the ones at risk.
    """
    for candidate in ("origin/main", "origin/master", "main", "master"):
        if candidate != branch and _ref_exists(repo, candidate):
            return candidate
    return None


def configured_upstream(repo: Path, branch: str) -> tuple[str | None, str | None]:
    """``(remote, upstream_ref)`` configured for *branch*, ignoring existence.

    ``%(upstream:short)`` is empty for a deleted upstream, so the configured
    pair has to come from git config directly. A branch whose upstream was
    deleted still *has* an upstream, which is a different finding from having
    none, and conflating them hides the very thing this tool reports.
    """
    remote = run_git(repo, "config", "--get", f"branch.{branch}.remote")
    merge = run_git(repo, "config", "--get", f"branch.{branch}.merge")
    remote_name = remote.stdout.strip() or None
    merge_ref = merge.stdout.strip() or None
    if not remote_name or not merge_ref:
        return None, None
    short = merge_ref.removeprefix("refs/heads/")
    return remote_name, f"{remote_name}/{short}"


def list_branches(repo: Path) -> list[BranchInfo]:
    """Every local branch, with its upstream relationship.

    A branch whose upstream ref is gone still has a configured upstream, so it
    is not "no upstream": it is a deleted upstream, which is a different
    finding and the reason pruning matters.
    """
    names = run_git_text(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    branches: list[BranchInfo] = []
    for name in (n.strip() for n in names.splitlines()):
        if not name:
            continue
        remote, upstream = configured_upstream(repo, name)
        upstream_gone = upstream is not None and not _ref_exists(repo, upstream)

        ahead = behind = 0
        if upstream:
            # Compare against the configured merge ref even when the remote
            # tracking ref is gone: the commits ahead are exactly the work that
            # exists only locally, which is the number a deleted-upstream
            # finding needs to report.
            comparison = upstream if not upstream_gone else _merge_ref(repo, name)
            if comparison and _ref_exists(repo, comparison):
                counts = run_git(
                    repo, "rev-list", "--left-right", "--count", f"{name}...{comparison}"
                )
                if counts.returncode == 0:
                    # Output is tab-separated: <ahead>\t<behind>.
                    fields = counts.stdout.split()
                    if len(fields) == 2:
                        ahead, behind = int(fields[0]), int(fields[1])

        branches.append(
            BranchInfo(
                name=name,
                remote=remote,
                upstream=upstream,
                upstream_gone=upstream_gone,
                ahead=ahead,
                behind=behind,
                has_upstream=bool(upstream),
                last_commit_rel=_last_commit_relative(repo, name),
            )
        )
    return branches


def _last_commit_relative(repo: Path, ref: str) -> str:
    proc = run_git(repo, "log", "-1", "--format=%cr", ref)
    return proc.stdout.strip() if proc.returncode == 0 else ""
