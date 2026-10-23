# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""User configuration: identity resolution and the branch whitelist.

Identity precedence is ``--author`` > ``~/.git-ferret.toml`` > git config, and
it resolves *per repository* because a collection of repos may legitimately
carry different local identities.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path

from git_ferret.gitcmd import run_git

DEFAULT_CONFIG_PATH = Path.home() / ".git-ferret.toml"

# Always excluded from branch reports, whatever the configuration says.
ALWAYS_EXCLUDED = ("main", "master")


def is_always_excluded(branch: str, base_ref: str | None) -> bool:
    """Whether *branch* is ``main``, ``master``, or the resolved base ref.

    The part of exclusion that does not depend on configuration. Callers that
    treat whitelisted branches differently (``local`` keeps a whitelisted branch
    when it has a real problem) add that on top rather than folding it in here.
    """
    if branch in ALWAYS_EXCLUDED:
        return True
    return base_ref is not None and branch in (base_ref, base_ref.split("/")[-1])


def split_identities(values: Iterable[str]) -> list[str]:
    """Split comma-separated identity values and drop blank entries.

    Both the flag and the config file accept a bare string or a list, and a
    user writing ``--author "a@x.com,b@y.com"`` means two identities, not one
    string that will never match an author line.

    Blanks are dropped rather than kept: an empty identity is a substring of
    every author string, so keeping one would report every branch as the user's.
    """
    identities: list[str] = []
    for value in values:
        for part in str(value).split(","):
            cleaned = part.strip()
            if cleaned:
                identities.append(cleaned)
    return identities


@dataclass
class Config:
    """Resolved user configuration.

    ``author`` holds one or more identities; they combine with OR, because the
    intent is "all of my addresses" rather than "a team".
    """

    author: list[str] = field(default_factory=list[str])
    whitelist: list[str] = field(default_factory=list[str])

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Read the TOML config. A missing file is not an error."""
        config_path = path if path is not None else DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return cls()
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        raw_author = data.get("author", [])
        author = split_identities([raw_author] if isinstance(raw_author, str) else list(raw_author))
        whitelist = list(data.get("whitelist", {}).get("patterns", []))
        return cls(author=author, whitelist=whitelist)

    def is_whitelisted(self, branch: str) -> bool:
        """Whether *branch* matches a whitelist pattern.

        Case-sensitive: git branch names are, and a case-insensitive match here
        would silently hide branches the user meant to see.
        """
        return any(fnmatchcase(branch, pattern) for pattern in self.whitelist)


def resolve_identities(cli_author: list[str], config: Config, repo: Path) -> list[str]:
    """Resolve author identities, most specific source first.

    Returns ``[]`` when nothing resolves. An empty result must never be passed
    to git's ``--author``: an empty pattern matches *every* commit, which would
    report every branch as the user's own.
    """
    if cli_author:
        return split_identities(cli_author)
    if config.author:
        return split_identities(config.author)

    name = run_git(repo, "config", "--get", "user.name").stdout.strip()
    email = run_git(repo, "config", "--get", "user.email").stdout.strip()
    if name and email:
        return [f"{name} <{email}>"]
    if email:
        return [email]
    return []


def identity_matches(commits_author_strings: Iterable[str], identities: list[str]) -> bool:
    """Whether any commit was authored by any of *identities*.

    Substring, not equality: the user configures a fragment such as an email
    address and it must match the full ``Name <email>`` git records.

    Blank identities are ignored here as well as at resolution, because the
    empty string is a substring of every author and would otherwise report
    every branch in the repository as the user's own.
    """
    usable = [i for i in identities if i and i.strip()]
    if not usable:
        return False
    authors = list(commits_author_strings)
    return any(identity in author for identity in usable for author in authors)
