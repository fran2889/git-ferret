# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Check a commit message subject against the project's conventions.

Used by ``.githooks/commit-msg``. The rules are deliberately small: a
Conventional Commits type and scope, a lowercase imperative description, and
no trailing period. Git-generated subjects (merges, reverts, fixups, squashes)
pass through untouched, because rewriting them would break the history they
describe.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_TYPES = frozenset(
    {
        "build",
        "chore",
        "ci",
        "docs",
        "feat",
        "fix",
        "perf",
        "refactor",
        "revert",
        "style",
        "test",
    }
)

# Subjects git writes itself, plus the autosquash markers. These are not
# Conventional Commits and are never rewritten by a person.
PASSTHROUGH_PREFIXES = (
    "Merge ",
    'Revert "',
    "Squashed commit of the following:",
    "fixup! ",
    "squash! ",
    "amend! ",
)

SUBJECT_RE = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[a-z0-9._/-]+)\))?!?: (?P<description>.+)$"
)

# A small, explicit list rather than a suffix rule: "process" and "address" are
# imperative and end in "s", so rejecting every such word would reject good
# subjects. These are the forms that actually turn up in a commit subject.
NON_IMPERATIVE = frozenset(
    {
        "added",
        "adds",
        "adding",
        "bumped",
        "bumps",
        "bumping",
        "changed",
        "changes",
        "changing",
        "created",
        "creates",
        "creating",
        "documented",
        "documents",
        "documenting",
        "fixed",
        "fixes",
        "fixing",
        "implemented",
        "implements",
        "implementing",
        "improved",
        "improves",
        "improving",
        "made",
        "makes",
        "making",
        "moved",
        "moves",
        "moving",
        "ran",
        "refactored",
        "refactors",
        "refactoring",
        "removed",
        "removes",
        "removing",
        "renamed",
        "renames",
        "renaming",
        "replaced",
        "replaces",
        "replacing",
        "tested",
        "tests",
        "testing",
        "updated",
        "updates",
        "updating",
    }
)


def subject_of(text: str, comment_char: str = "#") -> str | None:
    """The first real line of a commit message, or ``None`` when there is none.

    Git's editor buffer carries comments after the subject; a hook that read
    the first line blindly would check ``# Please enter ...`` on a message
    whose subject had been deleted. *comment_char* is the character Git is
    configured to use for those comments.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or (comment_char and stripped.startswith(comment_char)):
            continue
        return stripped
    return None


def validate(subject: str) -> str | None:
    """Why *subject* is invalid, or ``None`` when it passes."""
    if subject.startswith(PASSTHROUGH_PREFIXES):
        return None

    match = SUBJECT_RE.match(subject)
    if match is None:
        return "expected 'type(scope)?: description' with a Conventional Commits type"

    commit_type = match.group("type")
    if commit_type not in ALLOWED_TYPES:
        allowed = ", ".join(sorted(ALLOWED_TYPES))
        return f"unknown type '{commit_type}'; use one of: {allowed}"

    description = match.group("description").strip()
    if not description:
        return "the description is empty"
    if description[0].isupper():
        return "the description must start lowercase"
    if description.endswith("."):
        return "the description must not end with a period"

    first_word = description.split()[0].strip("`'\"").lower()
    if first_word in NON_IMPERATIVE:
        return f"the description must be imperative; '{first_word}' is not"
    return None


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: check_commit_msg.py COMMIT_MSG_FILE [COMMENT_CHAR]",
            file=sys.stderr,
        )
        return 1

    path = Path(argv[1])
    if not path.is_file():
        print(f"check_commit_msg: {path} does not exist", file=sys.stderr)
        return 1

    comment_char = argv[2] if len(argv) > 2 and argv[2] not in ("", "auto") else "#"
    subject = subject_of(
        path.read_text(encoding="utf-8", errors="replace"),
        comment_char=comment_char,
    )
    if subject is None:
        print("check_commit_msg: the commit message is empty", file=sys.stderr)
        return 1

    problem = validate(subject)
    if problem is not None:
        print(f"check_commit_msg: {problem}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
