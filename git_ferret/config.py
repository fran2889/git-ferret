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
from typing import Any, cast

from git_ferret.gitcmd import run_git

DEFAULT_CONFIG_PATH = Path.home() / ".git-ferret.toml"

# Always excluded from branch reports, whatever the configuration says.
ALWAYS_EXCLUDED = ("main", "master")


class ConfigError(Exception):
    """The config file exists but is not usable as git-ferret configuration.

    A malformed file is the user's mistake, not a crash: the CLI turns this into
    the same one-line usage error as a mistyped flag.
    """


def _one_line(exc: BaseException) -> str:
    """*exc* as a single line, for a message that has to stay one line."""
    return " ".join(str(exc).split())


def _strings(value: object, *, allow_string: bool) -> list[str] | None:
    """*value* as a list of strings, or ``None`` when it is not one.

    ``tomllib`` hands back ``Any``, which strict type checking treats as
    unknown; doing the narrowing here keeps the validation in one place and the
    rest of :meth:`Config.load` fully typed. ``author`` accepts a bare string
    (one identity is the common case); ``whitelist.patterns`` does not, because
    a list is what the documented shape says.
    """
    if isinstance(value, str):
        return [value] if allow_string else None
    if not isinstance(value, list):
        return None
    items: list[str] = []
    for item in cast("list[object]", value):
        if not isinstance(item, str):
            return None
        items.append(item)
    return items


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
        """Read the TOML config. A missing file is not an error.

        A file that exists but cannot be understood raises :class:`ConfigError`
        rather than surfacing as a traceback: in a weekly cron job a crash and a
        clean run are both non-zero for reasons nobody can read.
        """
        config_path = path if path is not None else DEFAULT_CONFIG_PATH
        if not config_path.exists():
            return cls()
        try:
            data: dict[str, Any] = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"{config_path}: {_one_line(exc)}") from None

        author = _strings(data.get("author", []), allow_string=True)
        if author is None:
            raise ConfigError(f"{config_path}: 'author' must be a string or a list of strings")

        whitelist_table = data.get("whitelist", {})
        if not isinstance(whitelist_table, dict):
            raise ConfigError(f"{config_path}: 'whitelist' must be a table")
        table = cast("dict[str, object]", whitelist_table)
        whitelist = _strings(table.get("patterns", []), allow_string=False)
        if whitelist is None:
            raise ConfigError(f"{config_path}: 'whitelist.patterns' must be a list of strings")

        return cls(author=split_identities(author), whitelist=whitelist)

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
