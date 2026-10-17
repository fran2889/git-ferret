"""Tests that a linked worktree is not reported as a second repository.

A worktree whose directory sits beside its main repository (a common hotfix
layout) has a `.git` file, so naive discovery reports the same repository twice
and fetches it twice.
"""

from pathlib import Path

from git_ferret.discovery import discover_repos
from tests.helpers import commit, make_repo, run


def _repo_with_sibling_worktree(tmp_path: Path):
    repo = make_repo(tmp_path / "api-server")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "worktree", "add", str(tmp_path / "api-server-hotfix"), "-b", "hotfix")
    return repo, tmp_path / "api-server-hotfix"


def test_linked_worktree_is_not_reported_as_a_second_repo(tmp_path: Path):
    _repo_with_sibling_worktree(tmp_path)
    found = discover_repos(tmp_path)
    assert [p.name for p in found] == ["api-server"]


def test_linked_worktree_is_still_reachable_as_a_worktree(tmp_path: Path):
    from git_ferret.discovery import list_worktrees

    repo, hotfix = _repo_with_sibling_worktree(tmp_path)
    paths = [p.name for p, _ in list_worktrees(repo)]
    assert "api-server-hotfix" in paths
    assert hotfix.exists()


def test_the_main_worktree_wins_as_representative(tmp_path: Path):
    repo, _hotfix = _repo_with_sibling_worktree(tmp_path)
    found = discover_repos(tmp_path)
    assert found == [repo]


def test_unrelated_repo_is_still_discovered_alongside(tmp_path: Path):
    _repo_with_sibling_worktree(tmp_path)
    make_repo(tmp_path / "other-project")
    found = discover_repos(tmp_path)
    assert {p.name for p in found} == {"api-server", "other-project"}
