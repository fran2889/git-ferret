# `--quiet` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--quiet` / `-q` to `local`, `remote`, and `merged` so only repositories with findings are printed.

**Architecture:** Filter at the CLI's emission point. A shared `_emit_repo` helper skips `render_repo` when quiet is set and the report's `findings` list is empty. Fetching, analysis, remote-health probing, and the stale/analysed counters keep running for hidden repositories, so the footer and the fast-forward block are unaffected. Rendering and analysis modules do not change.

**Tech Stack:** Python 3.14, typer, pytest, ruff, pyright strict, uv.

**Spec:** `docs/superpowers/specs/2026-11-03-quiet-flag-design.md`

## Global Constraints

- Python 3.14 or newer; no new dependencies.
- The report stays markdown with no ANSI escapes and no tables.
- Read-only behaviour is unchanged: `local --update` remains the only write.
- Findings never change the exit code. `0` means the run completed.
- Quiet hides only repositories whose `findings` list is empty. `[OK]` findings count, so a repository with one is printed in full.
- The header, the stale warning, and a non-empty `## fast-forwarded` block always print.
- The stale warning counts every analysed repository, including hidden ones.
- Non-quiet output is byte-for-byte unchanged.
- Prose is ASCII and uses hyphens, not em-dashes.
- Run tests with `uv run --no-sync python -m pytest`; run the gate with `uv run --no-sync make check`.

## Review Focus

- Every repository clean plus `--no-fetch`: header and stale warning only, with no repository sections, and the warning still counting the hidden repositories.
- A repository whose only finding is `[OK]`: still printed in full, because any finding counts.
- `local --quiet --update` where the fast-forwarded branch produces no finding: the section is hidden but `## fast-forwarded` still prints.
- `remote --quiet` with a filter that matches nothing versus one that matches: header-only versus a full section, since every `remote` finding is `[OK]`.
- An analysis failure during a quiet run: the `error analysing ...` line still reaches stderr, the run continues, and the exit code stays 0.

---

### Task 1: Quiet filtering for `local`

**Files:**
- Modify: `git_ferret/cli.py` (add helper, flag, and call site in `local`)
- Test: `tests/test_end_to_end.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: existing `RepoReport.findings`, `render_repo`, `emit`.
- Produces:
  - `_emit_repo(report: RepoReport, root: Path, quiet: bool) -> None`
  - `local(..., quiet: bool = typer.Option(False, "--quiet", "-q", ...))`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_end_to_end.py` (with imports `subprocess` and a `pytest` import already present):

```python
def _clean_clone(tmp_path: Path, dest: Path) -> Path:
    """A freshly fetched clone with only `main`: nothing for a scan to report."""
    src = make_repo(tmp_path / "fixtures" / f"{dest.name}-src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    return clone_local(src, dest)


def _with_unpushed_branch(tmp_path: Path, dest: Path) -> Path:
    """A clone carrying one local branch that exists nowhere on the remote."""
    clone = _clean_clone(tmp_path, dest)
    run(clone, "checkout", "-b", "local-only", "origin/main")
    (clone / "mine.txt").write_text("mine\n")
    commit(clone, "local only")
    run(clone, "checkout", "main")
    return clone


def test_quiet_prints_only_the_header_when_every_repository_is_clean(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert res.stdout == "# git-ferret\n\n"


def test_short_quiet_flag_is_accepted(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["local", str(clone), "-q"])
    assert res.exit_code == 0, res.output
    assert res.stdout == "# git-ferret\n\n"


def test_quiet_still_prints_a_repository_with_findings(tmp_path: Path):
    clone = _with_unpushed_branch(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert "## .\n" in res.stdout
    assert "`local-only` [NOT PUSHED]" in res.stdout
    assert "fetched " in res.stdout


def test_quiet_keeps_a_repository_whose_only_finding_is_ok(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    run(clone, "checkout", "-b", "clean-branch", "origin/main")
    run(clone, "checkout", "main")
    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert "## .\n" in res.stdout
    assert "`clean-branch` [OK]" in res.stdout


def test_quiet_keeps_the_stale_warning_while_hiding_the_section(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet", "--no-fetch"])
    assert res.exit_code == 0, res.output
    assert res.stdout.startswith("# git-ferret")
    assert "## " not in res.stdout
    assert "1 of 1 repositories" in res.stdout


def test_quiet_still_counts_hidden_repositories_as_stale(tmp_path: Path):
    scan = tmp_path / "scan"
    _clean_clone(tmp_path, scan / "one")
    _with_unpushed_branch(tmp_path, scan / "two")
    res = runner.invoke(build_parser(), ["local", str(scan), "--quiet", "--no-fetch"])
    assert res.exit_code == 0, res.output
    assert res.stdout.count("## ") == 1
    assert "2 of 2 repositories" in res.stdout


def test_quiet_keeps_the_fast_forwarded_block(tmp_path: Path):
    src = make_repo(tmp_path / "fixtures" / "ff-src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    (src / "f.txt").write_text("a\nb\n")
    commit(src, "second")

    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet", "--update"])
    assert res.exit_code == 0, res.output
    assert "## fast-forwarded" in res.stdout
    assert "`main` fast-forwarded" in res.stdout
    assert "## ." not in res.stdout


def test_quiet_does_not_hide_an_analysis_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clone = _clean_clone(tmp_path, tmp_path / "clean")

    def refuse(*args: object, **kwargs: object) -> None:
        raise subprocess.SubprocessError("git said no")

    monkeypatch.setattr(cli_module, "analyse_local", refuse)
    res = runner.invoke(build_parser(), ["local", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert "error analysing" in res.stderr
```

Add to `tests/test_cli.py`:

```python
def test_local_help_lists_quiet_flag():
    help_text = _help("local")
    assert "--quiet" in help_text
    assert "-q" in help_text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_end_to_end.py -k quiet tests/test_cli.py::test_local_help_lists_quiet_flag -v`

Expected: the behavior tests fail because `--quiet` is not a known option, and the help test fails because `--quiet` is absent.

- [ ] **Step 3: Implement the helper and the `local` flag**

In `git_ferret/cli.py`, add above `local`:

```python
def _emit_repo(report: RepoReport, root: Path, quiet: bool) -> None:
    """Print one repository's section, unless quiet hides it.

    The filter lives here, after analysis and after the stale and analysed
    counters have been updated, so a hidden repository still counts in the
    footer and still contributes its findings to nothing else. Rendering is
    unchanged; quiet removes whole sections, never lines.
    """
    if quiet and not report.findings:
        return
    emit(render_repo(report, root))
```

Add the option to `local` after `update`:

```python
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Print only repositories with findings."
    ),
```

Replace `emit(render_repo(report, root))` inside `local` with:

```python
        _emit_repo(report, root, quiet)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_end_to_end.py -k quiet tests/test_cli.py::test_local_help_lists_quiet_flag -v`

Expected: PASS.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run --no-sync make check`

Expected: format check, lint, SPDX check, pyright, and the full suite all pass.

```bash
git add git_ferret/cli.py tests/test_end_to_end.py tests/test_cli.py
git commit -m "feat(cli): add quiet filtering to local"
```

---

### Task 2: Quiet filtering for `remote` and `merged`

**Files:**
- Modify: `git_ferret/cli.py` (flags on `remote` and `merged`, `_run`, `run_command`)
- Test: `tests/test_end_to_end.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `_emit_repo(report, root, quiet)` and the `_clean_clone(tmp_path, dest)` test helper from Task 1.
- Produces:
  - `remote(..., quiet: bool = typer.Option(False, "--quiet", "-q", ...))`
  - `merged(..., quiet: bool = typer.Option(False, "--quiet", "-q", ...))`
  - `_run(analysis, path, no_fetch, author, branch_filter, quiet) -> None`
  - `run_command(command, path, no_fetch, author=None, branch_filter=None, quiet=False) -> None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_end_to_end.py`:

```python
def _clone_with_branch(tmp_path: Path, dest: Path, name: str) -> Path:
    """A clone whose remote already carries branch *name*."""
    src = make_repo(tmp_path / "fixtures" / f"{dest.name}-src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", name)
    return clone_local(src, dest)


def _clone_with_merged_branch(tmp_path: Path, dest: Path) -> Path:
    """A clone whose remote branch `done` is already squashed into main."""
    src = make_repo(tmp_path / "fixtures" / f"{dest.name}-src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "checkout", "-b", "done")
    (src / "f.txt").write_text("a\ndone\n")
    commit(src, "work")
    run(src, "checkout", "main")
    run(src, "merge", "--squash", "done")
    commit(src, "merge done")
    return clone_local(src, dest)


def test_remote_quiet_hides_a_repository_with_no_matching_branches(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["remote", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert res.stdout == "# git-ferret\n\n"


def test_remote_quiet_keeps_a_repository_with_matching_branches(tmp_path: Path):
    clone = _clone_with_branch(tmp_path, tmp_path / "clean", "feature")
    res = runner.invoke(build_parser(), ["remote", str(clone), "--quiet", "--branch", "feature"])
    assert res.exit_code == 0, res.output
    assert "## .\n" in res.stdout
    assert "`origin/feature` [OK]" in res.stdout


def test_merged_quiet_hides_a_repository_with_nothing_merged(tmp_path: Path):
    clone = _clean_clone(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["merged", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert res.stdout == "# git-ferret\n\n"


def test_merged_quiet_keeps_a_repository_with_a_verdict(tmp_path: Path):
    clone = _clone_with_merged_branch(tmp_path, tmp_path / "clean")
    res = runner.invoke(build_parser(), ["merged", str(clone), "--quiet"])
    assert res.exit_code == 0, res.output
    assert "## .\n" in res.stdout
    assert "`origin/done` [SAFE TO DELETE]" in res.stdout
```

Add to `tests/test_cli.py`:

```python
@pytest.mark.parametrize("command", ["remote", "merged"])
def test_remote_and_merged_help_list_quiet(command: str):
    help_text = _help(command)
    assert "--quiet" in help_text
    assert "-q" in help_text
```

Add `import pytest` to `tests/test_cli.py` if it is not already present.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-sync python -m pytest tests/test_end_to_end.py -k "remote_quiet or merged_quiet" tests/test_cli.py::test_remote_and_merged_help_list_quiet -v`

Expected: the behavior tests fail because `--quiet` is unknown to those commands, and the help test fails because the flag is absent.

- [ ] **Step 3: Implement the flags and thread them through**

In `git_ferret/cli.py`, add the same option to `remote` and `merged` after `branch`:

```python
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Print only repositories with findings."
    ),
```

Pass it to `_run` in both commands:

```python
    _run(ANALYSES["remote"], path, no_fetch, author, branch, quiet)
```

```python
    _run(ANALYSES["merged"], path, no_fetch, author, branch, quiet)
```

Add the parameter to `_run`:

```python
def _run(
    analysis: Analysis,
    path: Path,
    no_fetch: bool,
    author: list[str] | None,
    branch_filter: str | list[str] | None,
    quiet: bool,
) -> None:
```

Replace `emit(render_repo(report, root))` inside `_run` with:

```python
        _emit_repo(report, root, quiet)
```

Add a trailing parameter to `run_command` and forward it:

```python
def run_command(
    command: str,
    path: Path,
    no_fetch: bool,
    author: list[str] | None = None,
    branch_filter: str | list[str] | None = None,
    quiet: bool = False,
) -> None:
    """Run one named subcommand's analysis over *path*."""
    _run(ANALYSES[command], path, no_fetch, author or [], branch_filter, quiet)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-sync python -m pytest tests/test_end_to_end.py -k "remote_quiet or merged_quiet" tests/test_cli.py::test_remote_and_merged_help_list_quiet -v`

Expected: PASS.

- [ ] **Step 5: Run the gate and commit**

Run: `uv run --no-sync make check`

Expected: everything passes, including the existing `run_command` callers in `tests/test_remote.py`.

```bash
git add git_ferret/cli.py tests/test_end_to_end.py tests/test_cli.py
git commit -m "feat(cli): add quiet filtering to remote and merged"
```

---

### Task 3: Document the flag

**Files:**
- Modify: `README.md` (command reference and output section)

**Interfaces:**
- Consumes: the behaviour implemented in Tasks 1 and 2.
- Produces: user-facing documentation only.

- [ ] **Step 1: Add the command reference row**

In the table under `## Command reference`, add after the `--no-fetch` row:

```markdown
| `--quiet`, `-q` | `local`, `remote`, `merged` | Print only repositories with findings. |
```

- [ ] **Step 2: Describe what quiet keeps**

Under `## Using it regularly`, after the sentence about findings not changing the exit code, add:

```markdown
`--quiet` suppresses the section for any repository with no findings. The header, the stale
warning, and a non-empty `## fast-forwarded` block still print, so a quiet run is still a complete
report of what happened.
```

- [ ] **Step 3: Verify the docs and commit**

Run: `rg -n -- "--quiet" README.md`

Expected: the command table row and the new paragraph both appear.

```bash
git add README.md
git commit -m "docs: describe the quiet flag"
```
