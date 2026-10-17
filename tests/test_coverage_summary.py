from __future__ import annotations

from pathlib import Path

import pytest

from scripts.coverage_summary import main, render

COVERAGE_XML = """<?xml version="1.0" ?>
<coverage line-rate="0.937" version="7.0">
  <packages>
    <package name="git_ferret">
      <classes>
        <class filename="git_ferret/report.py" line-rate="1.0">
          <lines><line hits="1"/><line hits="3"/></lines>
        </class>
        <class filename="git_ferret/cli.py" line-rate="0.8">
          <lines><line hits="1"/><line hits="0"/><line hits="0"/></lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
"""


def _write(tmp_path: Path, body: str = COVERAGE_XML) -> Path:
    path = tmp_path / "coverage.xml"
    path.write_text(body)
    return path


def test_reports_the_total(tmp_path: Path) -> None:
    summary = render(_write(tmp_path))
    assert "Total: **93.7%**" in summary


def test_skips_fully_covered_files(tmp_path: Path) -> None:
    summary = render(_write(tmp_path))
    assert "cli.py" in summary
    assert "report.py" not in summary


def test_counts_missing_lines(tmp_path: Path) -> None:
    assert "| `git_ferret/cli.py` | 80.0% | 2 |" in render(_write(tmp_path))


def test_says_so_when_everything_is_covered(tmp_path: Path) -> None:
    body = COVERAGE_XML.replace('line-rate="0.8"', 'line-rate="1.0"')
    summary = render(_write(tmp_path, body))
    assert "Every file is fully covered." in summary


def test_missing_report_is_an_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["coverage_summary", str(tmp_path / "absent.xml")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_defaults_to_coverage_xml_in_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["coverage_summary"]) == 0
