"""Tests for repository and worktree discovery."""

from pathlib import Path

from git_ferret.discovery import (
    discover_repos,
    is_git_dir,
    is_submodule,
    list_worktrees,
    repository_identity,
)
from tests.helpers import commit, make_repo, run


def test_discovers_recursively(tmp_path: Path):
    make_repo(tmp_path / "a")
    make_repo(tmp_path / "nested" / "b")
    found = discover_repos(tmp_path)
    assert {p.name for p in found} == {"a", "b"}


def test_does_not_descend_into_a_repo(tmp_path: Path):
    # A repo inside a repo must not be fetched and reported a second time.
    outer = make_repo(tmp_path / "outer")
    make_repo(outer / "vendor" / "inner")
    assert discover_repos(tmp_path) == [outer]


def test_ignores_non_repo_dirs(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "file.txt").write_text("x")
    assert discover_repos(tmp_path) == []


def test_result_is_sorted_for_deterministic_output(tmp_path: Path):
    make_repo(tmp_path / "zeta")
    make_repo(tmp_path / "alpha")
    assert discover_repos(tmp_path) == [tmp_path / "alpha", tmp_path / "zeta"]


def test_missing_root_returns_empty(tmp_path: Path):
    assert discover_repos(tmp_path / "nope") == []


def test_is_submodule_false_for_real_repo(tmp_path: Path):
    assert is_submodule(make_repo(tmp_path / "r")) is False


def test_is_git_dir_true_for_repo(tmp_path: Path):
    assert is_git_dir(make_repo(tmp_path / "r")) is True


def test_is_git_dir_false_for_plain_dir(tmp_path: Path):
    (tmp_path / "plain").mkdir()
    assert is_git_dir(tmp_path / "plain") is False


def test_is_submodule_true_when_gitdir_under_modules(tmp_path: Path):
    # A `.git` file pointing into a superproject's .git/modules is a submodule,
    # which is vendored content rather than one of the user's own repositories.
    superproject = make_repo(tmp_path / "super")
    modules = superproject / ".git" / "modules" / "sub" / "modules" / "thing"
    modules.mkdir(parents=True)
    sub = superproject / "sub"
    sub.mkdir()
    (sub / ".git").write_text(f"gitdir: {modules}\n")
    assert is_submodule(sub) is True
    assert is_git_dir(sub) is True


def test_list_worktrees_returns_main_with_branch(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    wts = list_worktrees(repo)
    assert len(wts) == 1
    assert wts[0][1] == "main"


def test_list_worktrees_reports_detached_as_none(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    sha = run(repo, "rev-parse", "HEAD").stdout.strip()
    run(repo, "checkout", sha)
    wts = list_worktrees(repo)
    assert wts[0][1] is None


def test_a_dot_git_file_that_is_not_a_gitdir_is_not_a_submodule(tmp_path: Path):
    # A `.git` file is only meaningful if it names a git directory. Anything
    # else is not a submodule and must not be skipped as vendored content.
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / ".git").write_text("this is not a gitdir pointer\n")
    assert is_submodule(plain) is False
    assert repository_identity(plain) is None


def test_a_relative_gitdir_is_resolved_against_the_repository(tmp_path: Path):
    # git writes the gitdir pointer as a relative path in some layouts; a
    # submodule is still a submodule either way.
    superproject = make_repo(tmp_path / "super")
    sub = superproject / "sub"
    sub.mkdir()
    (sub / ".git").write_text("gitdir: ../.git/modules/sub\n")
    assert is_submodule(sub) is True


def test_identity_is_none_for_a_directory_that_is_not_a_repository(tmp_path: Path):
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "file.txt").write_text("x")
    assert repository_identity(plain) is None


def test_identity_of_a_relative_gitdir_pointer_is_absolute(tmp_path: Path):
    # Two checkouts reached through different relative pointers must collapse
    # onto the same key, which only holds if the pointer is resolved first.
    repo = make_repo(tmp_path / "r")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: ../r/.git/worktrees/linked\n")
    assert repository_identity(linked) == str((repo / ".git").resolve())


def test_identity_of_a_bare_gitdir_pointer_is_the_target(tmp_path: Path):
    # Not under .git/worktrees, so the pointer is the identity as it stands.
    elsewhere = tmp_path / "elsewhere.git"
    elsewhere.mkdir()
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text(f"gitdir: {elsewhere}\n")
    assert repository_identity(linked) == str(elsewhere)


def test_a_main_worktree_keys_on_its_own_git_dir(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    assert repository_identity(repo) == str((repo / ".git").resolve())
