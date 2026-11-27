# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the wheel smoke script."""

from pathlib import Path

import pytest

from scripts import smoke_wheel


def _wheel(directory: Path, name: str = "git_ferret-0.1.0-py3-none-any.whl") -> Path:
    path = directory / name
    path.write_text("", encoding="utf-8")
    return path


def test_find_wheel_returns_the_only_wheel(tmp_path: Path):
    wheel = _wheel(tmp_path)
    assert smoke_wheel.find_wheel(tmp_path) == wheel


def test_find_wheel_rejects_no_wheels(tmp_path: Path):
    with pytest.raises(SystemExit, match="expected one wheel"):
        smoke_wheel.find_wheel(tmp_path)


def test_find_wheel_rejects_multiple_wheels(tmp_path: Path):
    _wheel(tmp_path, "a.whl")
    _wheel(tmp_path, "b.whl")
    with pytest.raises(SystemExit, match="expected one wheel"):
        smoke_wheel.find_wheel(tmp_path)


def test_venv_paths_use_bin_on_posix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(smoke_wheel, "IS_WINDOWS", False)
    python, entry = smoke_wheel.venv_paths(tmp_path)
    assert python == tmp_path / "bin" / "python"
    assert entry == tmp_path / "bin" / "git-ferret"


def test_venv_paths_use_scripts_on_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(smoke_wheel, "IS_WINDOWS", True)
    python, entry = smoke_wheel.venv_paths(tmp_path)
    assert python == tmp_path / "Scripts" / "python.exe"
    assert entry == tmp_path / "Scripts" / "git-ferret.exe"
