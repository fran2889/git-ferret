"""Render ``coverage.xml`` as a Markdown table for the GitHub job summary.

CI already fails the build on a low total (see ``fail_under`` in
``pyproject.toml``), so this does not decide anything. It exists because a
coverage number that is only stored in an artifact is one nobody looks at:
the point is to have the number, and the files that dragged it down, in the
run summary where a reviewer already is.

Usage:

    python scripts/coverage_summary.py [coverage.xml]
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# The same rule as `skip_covered` in pyproject.toml: files at 100% are
# already green, so listing them only buries the ones worth reading.
COVERED = 1.0


def _percentage(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _total(root: ET.Element) -> str:
    return _percentage(float(root.attrib["line-rate"]))


def _rows(root: ET.Element) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for klass in root.iter("class"):
        filename = klass.attrib["filename"]
        rate = float(klass.attrib["line-rate"])
        if rate >= COVERED:
            continue
        missing = sum(1 for line in klass.iter("line") if line.attrib.get("hits") == "0")
        rows.append((filename, _percentage(rate), str(missing)))
    return sorted(rows, key=lambda row: float(row[1].rstrip("%")))


def render(coverage_xml: Path) -> str:
    root = ET.parse(coverage_xml).getroot()
    rows = _rows(root)
    lines = [
        "## Coverage",
        "",
        f"Total: **{_total(root)}**",
        "",
    ]
    if not rows:
        lines.append("Every file is fully covered.")
        return "\n".join(lines)
    lines += ["| File | Cover | Missing |", "|---|---|---|"]
    lines += [f"| `{name}` | {rate} | {missing} |" for name, rate, missing in rows]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("coverage.xml")
    if not path.is_file():
        print(f"coverage_summary: {path} does not exist", file=sys.stderr)
        return 1
    print(render(path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
