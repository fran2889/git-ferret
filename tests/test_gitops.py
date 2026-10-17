"""Tests for fetch, base ref resolution, and local branch listing."""

from pathlib import Path

from git_ferret.gitops import (
    base_ref_is_remote,
    fetch_all,
    fetch_head_mtime,
    list_branches,
    resolve_base_ref,
    tree_hash,
)
from tests.helpers import clone_local, commit, make_repo, run


def test_resolve_base_ref_falls_back_to_local(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert resolve_base_ref(repo) == "main"


def test_resolve_base_ref_prefers_origin(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    assert resolve_base_ref(clone) == "origin/main"


def test_resolve_base_ref_prefers_origin_over_stale_local(tmp_path: Path):
    # The base must be the branch the remote actually has. A stale local main
    # would report a live remote branch as safe to delete.
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "advance")
    fetch_all(clone)
    assert resolve_base_ref(clone) == "origin/main"
    assert tree_hash(clone, "origin/main") != tree_hash(clone, "main")


def test_resolve_base_ref_prefers_origin_master(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "-m", "main", "master")
    clone = clone_local(src, tmp_path / "clone")
    assert resolve_base_ref(clone) == "origin/master"


def test_resolve_base_ref_none_when_absent(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "-m", "main", "trunk")
    assert resolve_base_ref(repo) is None


def test_base_ref_is_remote():
    assert base_ref_is_remote("origin/main") is True
    assert base_ref_is_remote("main") is False
    assert base_ref_is_remote(None) is False


def test_fetch_failure_is_not_fatal(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    run(repo, "remote", "add", "origin", "/nonexistent/path.git")
    ok, when = fetch_all(repo)
    assert ok is False and when is None


def test_fetch_success_records_fetch_head_mtime(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    ok, when = fetch_all(clone)
    assert ok is True and when is not None
    assert fetch_head_mtime(clone) is not None


def test_fetch_head_mtime_none_before_any_fetch(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert fetch_head_mtime(repo) is None


def test_list_branches_marks_deleted_upstream(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "gone-branch")
    run(repo, "update-ref", "refs/remotes/origin/keep", "main")
    run(repo, "config", "branch.gone-branch.remote", "origin")
    run(repo, "config", "branch.gone-branch.merge", "refs/heads/gone-branch")
    run(repo, "update-ref", "-d", "refs/remotes/origin/keep")
    branches = {b.name: b for b in list_branches(repo)}
    assert branches["gone-branch"].upstream_gone is True


def test_list_branches_reports_ahead_when_unpushed(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    # A clone has only the default branch locally, so create it and commit
    # there: the work then exists nowhere on the remote.
    run(clone, "checkout", "-b", "feat", "origin/feat")
    (clone / "f.txt").write_text("a\nb\n")
    commit(clone, "local work")
    branches = {b.name: b for b in list_branches(clone)}
    assert branches["feat"].ahead == 1
    assert branches["feat"].has_upstream is True


def test_list_branches_reports_behind_when_remote_moved(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/feat")
    # The remote's `feat` must move, or there is nothing to be behind.
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    fetch_all(clone)
    branches = {b.name: b for b in list_branches(clone)}
    assert branches["feat"].behind == 1
    assert branches["feat"].ahead == 0


def test_gone_upstream_branch_still_counts_as_having_an_upstream(tmp_path: Path):
    # A deleted upstream is a different finding from no upstream at all;
    # conflating them would hide the deletion this tool exists to report.
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "gone-branch")
    run(repo, "update-ref", "refs/remotes/origin/keep", "main")
    run(repo, "config", "branch.gone-branch.remote", "origin")
    run(repo, "config", "branch.gone-branch.merge", "refs/heads/gone-branch")
    run(repo, "update-ref", "-d", "refs/remotes/origin/keep")
    branch = {b.name: b for b in list_branches(repo)}["gone-branch"]
    assert branch.has_upstream is True
    assert branch.upstream == "origin/gone-branch"
    assert branch.remote == "origin"


def test_branch_without_upstream_config_is_marked_as_such(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "solo")
    branch = {b.name: b for b in list_branches(repo)}["solo"]
    assert branch.has_upstream is False
    assert branch.upstream_gone is False


def test_list_branches_clean_branch_is_not_ahead(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "clean")
    branches = {b.name: b for b in list_branches(repo)}
    assert branches["clean"].ahead == 0


def test_list_branches_carries_last_commit_age(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    branches = {b.name: b for b in list_branches(repo)}
    assert "ago" in branches["main"].last_commit_rel


def test_stash_entries_empty_for_clean_repo(tmp_path: Path):
    from git_ferret.gitops import stash_entries

    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    assert stash_entries(repo) == []
