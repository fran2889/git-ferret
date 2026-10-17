"""Tests for the reasons --update declines to fast-forward, and where they land.

"Not a fast-forward" must mean the branch genuinely diverged, not "we declined
to try", or a reader cannot tell what state their branch is in.

The update block itself reports only what it wrote. These reasons belong to the
repository's own section, where they are findings among the rest, so that is
where they are asserted.
"""

from pathlib import Path

from git_ferret.analysis.local import analyse_local
from git_ferret.cli import fast_forward_worktrees
from git_ferret.config import Config
from git_ferret.gitops import resolve_base_ref
from git_ferret.models import Finding, Status
from tests.helpers import clone_local, commit, make_repo, run


def _behind_clone(tmp_path: Path) -> Path:
    """A clone whose checked-out branch is behind its upstream by one commit."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/main")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")
    return clone


def _finding(repo: Path, status: Status) -> Finding:
    rep = analyse_local(repo, Config(), resolve_base_ref(repo))
    return next(f for f in rep.findings if f.status is status)


def test_dirty_worktree_is_reported_as_dirty_above(tmp_path: Path):
    clone = _behind_clone(tmp_path)
    (clone / "wip.txt").write_text("x\n")

    assert fast_forward_worktrees(clone) == []
    finding = _finding(clone, Status.DIRTY)
    assert "untracked" in finding.detail
    # The point of the marker is that it stands for the reason on its own.
    assert "DIRTY" in finding.status.MARKER


def test_diverged_branch_is_reported_as_diverged(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    (clone / "local.txt").write_text("local\n")
    commit(clone, "local work")
    # The remote's `feat` must move too, or the branch is merely ahead.
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")

    assert fast_forward_worktrees(clone) == []
    finding = _finding(clone, Status.DIVERGED)
    assert "1 ahead / 1 behind" in finding.detail
    assert "cannot fast-forward" in finding.detail


def test_worktree_with_no_upstream_is_reported_as_not_pushed(tmp_path: Path):
    clone = _behind_clone(tmp_path)
    run(clone, "branch", "--unset-upstream")

    assert fast_forward_worktrees(clone) == []
    finding = _finding(clone, Status.NOT_PUSHED)
    assert "no upstream configured" in finding.detail


def test_up_to_date_branch_is_not_reported_as_updated(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")

    # Nothing to do is not something that happened.
    assert fast_forward_worktrees(clone) == []


def test_a_fast_forward_names_only_the_branch_that_moved(tmp_path: Path):
    clone = _behind_clone(tmp_path)

    assert fast_forward_worktrees(clone) == ["feat"]
