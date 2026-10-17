"""Importable git fixture builders, shared by every test module.

These are plain functions, not pytest fixtures: a test calls ``make_repo`` at
the exact path it wants the repository at, which a fixture cannot do without
inventing a second path to ask for one (``from tests.helpers import commit,
make_repo, run``). There is no conftest to go with them.

Fixture setup goes through the same ``git_ferret.gitcmd`` seam as the code
under test. Nothing here touches ``subprocess``: ``gitcmd.py`` is the only
module allowed to shell out.
"""

from __future__ import annotations

from pathlib import Path

from git_ferret.gitcmd import CompletedProcess, run_git

DEV_NAME = "Dev"
DEV_EMAIL = "dev@example.com"


def make_repo(path: Path) -> Path:
    """Create a repository at *path*: branch ``main``, with a usable identity.

    The identity is set locally because a container has no global one, and a
    bare ``git commit`` there fails with "Author identity unknown".
    """
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-b", "main", check=True)
    run_git(path, "config", "user.name", DEV_NAME, check=True)
    run_git(path, "config", "user.email", DEV_EMAIL, check=True)
    return path


def commit(repo: Path, message: str, author: str = f"{DEV_NAME} <{DEV_EMAIL}>") -> None:
    """Stage everything and commit.

    The author is always passed explicitly, so a test can commit as somebody
    else without touching the repository's configured identity.
    """
    run_git(repo, "add", "-A", check=True)
    run_git(repo, "commit", "-m", message, "--author", author, check=True)


def run(repo: Path, *args: str) -> CompletedProcess:
    """Run git in *repo*, raising ``GitError`` if it fails."""
    return run_git(repo, *args, check=True)


def add_branch_with_missing_commit(repo: Path, name: str) -> str:
    """Point branch *name* at an object this repository does not have.

    A ref whose target is gone is what a half-finished fetch, a pruned object
    store or a hand-edited ref file leaves behind. Git still lists the branch,
    and every command that needs the commit behind it fails, which is the state
    the read-only paths have to keep reporting through.
    """
    sha = "1" * 40
    ref = repo / ".git" / "refs" / "heads" / name
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(f"{sha}\n")
    return sha


def clone_local(src: Path, dest: Path, depth: int | None = None) -> Path:
    """Clone *src* into *dest* over ``file://``, so the remote is really fetchable.

    ``depth`` produces a genuinely shallow clone, which the merge tests need.

    The clone gets its own local identity: a clone inherits no ``user.email``,
    so any test that commits inside the clone would otherwise fail with
    "Author identity unknown".
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"file://{src.resolve()}"
    args = ["clone"]
    if depth is not None:
        args += ["--depth", str(depth)]
    args += [url, str(dest)]
    run_git(dest.parent, *args, check=True)
    run_git(dest, "config", "user.name", DEV_NAME, check=True)
    run_git(dest, "config", "user.email", DEV_EMAIL, check=True)
    return dest
