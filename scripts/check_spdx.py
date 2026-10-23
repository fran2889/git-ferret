# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Enforce the SPDX licence header on every Python source file.

The header has to sit in the leading comment block, before the module
docstring. Checking the first few lines alone would miss a file whose header
was pasted below the imports, and a licence that is not attached to the file
is not doing its job.

Roots come from ``make check-spdx``, which passes ``SOURCES``, so the Makefile
stays the only list of source directories.
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

COPYRIGHT = "# SPDX-FileCopyrightText: 2026 Fran"
LICENSE = "# SPDX-License-Identifier: GPL-3.0-only"


def _leading_comments(path: Path) -> list[str]:
    """The comment and blank lines before the first line of code."""
    block: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            block.append(stripped)
            continue
        break
    return block


def missing_header_lines(path: Path) -> list[str]:
    """The required header lines absent from the leading comment block."""
    block = _leading_comments(path)
    return [line for line in (COPYRIGHT, LICENSE) if line not in block]


def has_header(path: Path) -> bool:
    return not missing_header_lines(path)


def python_files(roots: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
        elif root.is_dir():
            files.extend(path for path in root.rglob("*.py") if path.is_file())
    return sorted(files)


def missing_headers(roots: Iterable[Path]) -> list[Path]:
    return [path for path in python_files(roots) if not has_header(path)]


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {Path(argv[0]).name} ROOT [ROOT ...]", file=sys.stderr)
        return 2

    roots = [Path(arg) for arg in argv[1:]]
    missing_roots = [root for root in roots if not root.exists()]
    if missing_roots:
        for root in missing_roots:
            print(f"check_spdx: {root} does not exist", file=sys.stderr)
        return 1

    missing = missing_headers(roots)
    if not missing:
        return 0

    for path in missing:
        lines = ", ".join(repr(line) for line in missing_header_lines(path))
        print(f"check_spdx: {path} is missing {lines}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
