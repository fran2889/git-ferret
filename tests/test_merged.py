"""Tests for the tree-based merge verdict.

These are the load-bearing tests of the whole tool: they decide whether a
branch is recommended for deletion.
"""

from pathlib import Path

import pytest

from git_ferret.analysis import merged as merged_module
from git_ferret.analysis.merged import (
    MergeVerdict,
    commits_in_range,
    merge_verdict,
    remote_branches,
)
from tests.helpers import clone_local, commit, make_repo, run


def _clone_with_feature(tmp_path: Path):
    """src: main + feature. clone: both visible as remote branches."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feature")
    (src / "f.txt").write_text("a\nFEATURE\nc\n")
    commit(src, "feature work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    return src, clone


def test_squash_merged_branch_is_merged(tmp_path: Path):
    # Ancestry lies here: the branch is fully merged but not an ancestor.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feature")
    (src / "f.txt").write_text("a\nFEATURE\nc\n")
    commit(src, "feature work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "feature")
    commit(src, "squash merge")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    # Ancestry reports the branch as NOT merged:
    ancestry = run(clone, "branch", "-r", "--merged", "origin/main").stdout
    assert "origin/feature" not in ancestry
    # The tree test reports the truth:
    assert merge_verdict(clone, "origin/main", "origin/feature") is MergeVerdict.MERGED


def test_unmerged_branch_is_not_merged(tmp_path: Path):
    _src, clone = _clone_with_feature(tmp_path)
    assert merge_verdict(clone, "origin/main", "origin/feature") is MergeVerdict.NOT_MERGED


def test_conflicting_branch_reports_conflicts(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "conflict")
    (src / "f.txt").write_text("SIDE-A\nb\nc\n")
    commit(src, "side a")
    run(src, "checkout", "main")
    (src / "f.txt").write_text("SIDE-B\nb\nc\n")
    commit(src, "side b")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    assert merge_verdict(clone, "origin/main", "origin/conflict") is MergeVerdict.CONFLICTS


def test_unrelated_histories_report_unknown_not_conflicts(tmp_path: Path):
    # exit 128 means "no merge base", which is unknown, not a conflict.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "checkout", "--orphan", "orphan")
    (src / "f.txt").write_text("zzz\n")
    run(src, "add", "-A")
    commit(src, "orphan")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    assert merge_verdict(clone, "origin/main", "origin/orphan") is MergeVerdict.UNKNOWN


def test_shallow_repo_is_unknown_not_merged(tmp_path: Path):
    # No merge base locally must never read as merged.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feature")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "feature work")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "shallow", depth=1)
    assert merge_verdict(clone, "origin/main", "origin/feature") is not MergeVerdict.MERGED


def test_remote_branches_lists_origin_refs(tmp_path: Path):
    _src, clone = _clone_with_feature(tmp_path)
    refs = remote_branches(clone)
    assert "origin/feature" in refs
    assert "origin/main" in refs


def test_remote_branches_excludes_head_symref(tmp_path: Path):
    _src, clone = _clone_with_feature(tmp_path)
    refs = remote_branches(clone)
    assert "origin/HEAD" not in refs
    # %(refname:short) renders refs/remotes/origin/HEAD as bare "origin",
    # which would otherwise show up as a phantom branch.
    assert "origin" not in refs


def test_remote_branches_returns_no_phantom_remote_entry(tmp_path: Path):
    _src, clone = _clone_with_feature(tmp_path)
    assert all("/" in ref for ref in remote_branches(clone))


def test_commits_in_range_excludes_base_history(tmp_path: Path):
    # Only the commits the branch introduces, or every branch would match the
    # user, because their commits sit in the base branch's history.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base", author="Fran <fran@z.com>")
    run(src, "checkout", "-b", "theirs")
    (src / "f.txt").write_text("a\ntheirs\n")
    commit(src, "their work", author="Other <o@x.com>")
    run(src, "checkout", "main")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    authors = commits_in_range(clone, "origin/main", "origin/theirs")
    assert authors == ["Other <o@x.com>"]


def test_merged_then_reverted_branch_reports_merged(tmp_path: Path):
    # A documented limitation: reverting does not remove ancestry, so the
    # merge is a genuine no-op and the trees match.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feat")
    (src / "f.txt").write_text("a\nFEAT\n")
    commit(src, "feat work")
    run(src, "checkout", "main")
    run(src, "merge", "--no-ff", "feat", "-m", "merge feat")
    run(src, "revert", "--no-edit", "-m", "1", "HEAD")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    assert merge_verdict(clone, "origin/main", "origin/feat") is MergeVerdict.MERGED


def test_an_unreadable_base_tree_is_not_claimed_as_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Claiming MERGED when the base tree could not be read is the one answer
    # that recommends deleting work somebody still has. UNKNOWN withholds it.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\nb\nc\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feature")
    (src / "f.txt").write_text("a\nFEATURE\nc\n")
    commit(src, "feature work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "feature")
    commit(src, "squash merge")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "fetch", "--all", "--prune")
    assert merge_verdict(clone, "origin/main", "origin/feature") is MergeVerdict.MERGED

    def unreadable_tree(repo: Path, ref: str) -> str | None:
        return None

    monkeypatch.setattr(merged_module, "tree_hash", unreadable_tree)
    assert merge_verdict(clone, "origin/main", "origin/feature") is MergeVerdict.UNKNOWN
