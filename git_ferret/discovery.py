# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Finding the repositories to audit, and the worktrees inside each one.

Discovery stops descending at the first repository it finds. A personal
collection routinely contains nested checkouts (a dotfiles repo with cloned
plugins, a vendored dependency), and walking into them would fetch and report
the same tree twice.
"""

from __future__ import annotations

import os
from pathlib import Path

from git_ferret.gitcmd import run_git_text


def is_git_dir(path: Path) -> bool:
    """Whether *path* is a repository root: ``.git`` as a dir or as a file."""
    dot_git = path / ".git"
    return dot_git.is_dir() or dot_git.is_file()


def is_submodule(path: Path) -> bool:
    """Whether *path* is a submodule rather than a repository of the user's.

    A submodule's ``.git`` is a file pointing into the superproject's
    ``.git/modules`` tree. Those are vendored content and get skipped.
    """
    dot_git = path / ".git"
    if not dot_git.is_file():
        return False
    try:
        content = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not content.startswith("gitdir:"):
        return False
    target = content.split(":", 1)[1].strip()
    resolved = Path(target)
    if not resolved.is_absolute():
        resolved = (path / resolved).resolve()
    # Path components, not a string containing "/.git/modules/": Windows
    # writes backslashes, and a directory merely named "modules" is not a
    # submodule's git directory.
    parts = resolved.parts
    return any(
        parts[index] == ".git" and parts[index + 1] == "modules" for index in range(len(parts) - 1)
    )


def _gitdir_target(path: Path) -> Path | None:
    """The git directory a ``.git`` *file* points at, if this is a worktree.

    A linked worktree's ``.git`` is a file naming its directory under the main
    repository's ``.git/worktrees/``. That is what identifies a secondary
    worktree as belonging to a repository already discovered, rather than being
    a repository in its own right.
    """
    dot_git = path / ".git"
    if not dot_git.is_file():
        return None
    try:
        content = dot_git.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content.startswith("gitdir:"):
        return None
    target = Path(content.split(":", 1)[1].strip())
    if not target.is_absolute():
        target = (path / target).resolve()
    return target


def repository_identity(path: Path) -> str | None:
    """A stable key identifying the repository *path* belongs to.

    Main worktrees key on their own ``.git`` directory; linked worktrees key on
    the *main* repository's ``.git`` directory, so several worktrees of one
    repository collapse to a single entry. Submodules key on their superproject
    and are excluded separately.
    """
    dot_git = path / ".git"
    if dot_git.is_dir():
        return str(dot_git.resolve())
    target = _gitdir_target(path)
    if target is None:
        return None
    # .../<repo>/.git/worktrees/<name> -> .../<repo>/.git
    if target.parent.name == "worktrees":
        return str(target.parent.parent)
    return str(target)


def discover_repos(root: Path) -> list[Path]:
    """Every repository at or under *root*, sorted, without descending into one.

    A repository is reported once. A linked worktree sitting beside its main
    repository resolves to the same repository and is not reported again, which
    would otherwise double every finding and fetch the same repository twice.

    Sorting keeps report output deterministic across runs, which is what makes
    two reports worth diffing.
    """
    if not root.is_dir():
        return []

    chosen: dict[str, Path] = {}
    has_main: set[str] = set()
    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        if is_git_dir(current) and not is_submodule(current):
            identity = repository_identity(current)
            if identity is not None:
                if (current / ".git").is_dir():
                    # A main worktree always wins over a linked one.
                    chosen[identity] = current
                    has_main.add(identity)
                elif identity not in has_main:
                    chosen.setdefault(identity, current)
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames if d != ".git"]
    return sorted(chosen.values())


def list_worktrees(repo: Path) -> list[tuple[Path, str | None]]:
    """``(path, branch)`` for every worktree; branch is ``None`` when detached.

    Parses ``git worktree list --porcelain``. A block starts with ``worktree``;
    it carries ``branch`` only when HEAD is attached, so an absent line is the
    signal for a detached worktree.
    """
    output = run_git_text(repo, "worktree", "list", "--porcelain")
    worktrees: list[tuple[Path, str | None]] = []
    path: Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
            worktrees.append((path, None))
        elif line.startswith("branch refs/heads/") and worktrees:
            name = line[len("branch refs/heads/") :]
            worktrees[-1] = (worktrees[-1][0], name)
    return worktrees
