# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""The command line interface.

Three subcommands, each independently runnable. All default to fetching and all
accept ``--no-fetch``, so the intended rhythm is one fetching run followed by
cheap repeat runs against local state.

Report-only: the sole write this tool performs is ``git merge --ff-only``
behind ``local --update``, which is off unless asked for.
"""

from __future__ import annotations

import functools
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import click
import typer

from git_ferret import __version__
from git_ferret.analysis.health import report_remote_health
from git_ferret.analysis.local import analyse_local
from git_ferret.analysis.remote import (
    analyse_merged_candidates,
    analyse_remote,
)
from git_ferret.config import Config, ConfigError, resolve_identities
from git_ferret.discovery import discover_repos, list_worktrees
from git_ferret.gitcmd import GitError, GitUnavailable, require_git, run_git
from git_ferret.gitops import fetch_all, refs_updated_at, resolve_base_ref
from git_ferret.models import RepoReport
from git_ferret.report import display_path, emit, render_header, render_repo

app = typer.Typer(help="Audit many local git repositories at once. Reports only.")

Analysis = Callable[[Path, Config, str | None, list[str], str | list[str] | None], RepoReport]

ANALYSES: dict[str, Analysis] = {
    "local": lambda repo, cfg, base, ids, bfilter: analyse_local(repo, cfg, base),
    "remote": analyse_remote,
    "merged": analyse_merged_candidates,
}


def _show_version(value: bool) -> None:
    """Print the version and stop, before typer asks for a subcommand.

    A bug report that cannot name the version it was filed against is worth
    much less, so this answers without a scan and without a repository.
    """
    if value:
        print(f"git-ferret {__version__}")
        raise typer.Exit()


@app.callback()
def _toplevel(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    """Audit many local git repositories at once. Reports only."""


def _aborts_on_interrupt(func: Callable[..., None]) -> Callable[..., None]:
    """Turn Ctrl-C into the framework's own abort: one line, exit 1.

    ``standalone_mode=False`` makes typer swallow ``KeyboardInterrupt`` instead
    of letting it reach :func:`main`, so an interrupted scan exits 0 having
    printed nothing. A report you script against has to tell an interrupted run
    from a clean one, and silence is not a way to tell them apart.
    """

    @functools.wraps(func)
    def wrapper(*args: object, **kwargs: object) -> None:
        try:
            func(*args, **kwargs)
        except KeyboardInterrupt:
            raise typer.Abort from None

    return wrapper


@app.command()
@_aborts_on_interrupt
def local(
    path: Path = typer.Argument(Path("."), help="Directory to scan recursively."),
    no_fetch: bool = typer.Option(
        False, "--no-fetch", help="Skip fetching; use existing local state."
    ),
    update: bool = typer.Option(
        False,
        "--update",
        help="Fast-forward clean worktrees. This is the only write this tool performs.",
    ),
) -> None:
    """Branches checked out locally, worktrees, dirty state."""
    config = Config.load()
    root = _resolve_root(path)
    require_git()
    updated: list[tuple[Path, str]] = []

    repos = discover_repos(root)
    # Fetch every repository before writing anything. The stale warning names
    # how many of how many this run could not refresh, and that count is only
    # knowable once every fetch has been attempted; deciding it from the first
    # repository reported "1 of 1" for any run and missed a stale repo that was
    # not first.
    fetch_state = _fetch_every(repos, no_fetch)
    emit(render_header(*_stale_counts(repos, fetch_state)))

    for repo in repos:
        base_ref = resolve_base_ref(repo)
        try:
            report = analyse_local(repo, config, base_ref)
        except (GitError, OSError, subprocess.SubprocessError) as exc:
            _warn(f"error analysing {repo}: {exc}")
            continue
        _stamp_fetch(report, fetch_state[repo])
        report_remote_health(repo, report)
        if update:
            updated.extend((repo, branch) for branch in fast_forward_worktrees(repo))
        emit(render_repo(report, root))

    _emit_summary(updated, root)


@app.command()
@_aborts_on_interrupt
def remote(
    path: Path = typer.Argument(Path(".")),
    no_fetch: bool = typer.Option(False, "--no-fetch"),
    author: list[str] = typer.Option(
        [], "--author", help="Substring of 'Name <email>'. Repeatable, or comma-separated."
    ),
    branch: list[str] = typer.Option(
        [], "--branch", help="Substring of the branch name. Repeatable, or comma-separated."
    ),
) -> None:
    """Remote branches matching the filters."""
    _run(ANALYSES["remote"], path, no_fetch, author, branch)


@app.command()
@_aborts_on_interrupt
def merged(
    path: Path = typer.Argument(Path(".")),
    no_fetch: bool = typer.Option(False, "--no-fetch"),
    author: list[str] = typer.Option(
        [], "--author", help="Substring of 'Name <email>'. Repeatable, or comma-separated."
    ),
    branch: list[str] = typer.Option(
        [], "--branch", help="Substring of the branch name. Repeatable, or comma-separated."
    ),
) -> None:
    """Remote branches whose changes are already in the base branch."""
    _run(ANALYSES["merged"], path, no_fetch, author, branch)


def build_parser() -> typer.Typer:
    """The configured app, exposed so tests can drive it."""
    return app


class UsageError(Exception):
    """A problem with how the tool was invoked, as opposed to what it found."""


# Everything the entry point treats as "you typed it wrong": the tool's own
# errors (bad usage, unusable config), plus the framework's. typer has exposed
# its own exception hierarchy since 0.27.2 -- the floor in pyproject.toml -- so
# an unknown flag or command arrives as typer's, not click's. An `except` clause
# written against click's classes would miss it entirely: the error escapes
# unhandled and the user gets a traceback for a typo. Both stringify to the
# message the user needs, which is why one handler covers them.
_USAGE_ERRORS: tuple[type[Exception], ...] = (
    UsageError,
    ConfigError,
    typer.TyperException,
    click.ClickException,
)


def _resolve_root(path: Path) -> Path:
    """The scan root, or a usage error if it is not a directory.

    A mistyped path must not produce an empty, exit-0 report: in a weekly cron
    job that is indistinguishable from "everything is fine".

    This raises ``UsageError`` rather than ``typer.Exit`` because typer's own
    ``__call__`` swallows non-ClickException exceptions, so a deliberate exit
    code raised inside a command never reaches the entry point.
    """
    root = path.expanduser().resolve()
    if not root.is_dir():
        raise UsageError(f"not a directory: {root}")
    return root


def _warn(message: str) -> None:
    print(message, file=sys.stderr)


def _fetch_report(repo: Path, no_fetch: bool) -> tuple[bool, bool]:
    """Fetch *repo* unless asked not to; return ``(attempted, failed)``.

    The one place a fetch happens. Its outcome is recorded on the report the
    caller is about to build, so the analyses stay free of the network and the
    stale warning and the ``[UNREACHABLE]`` finding read from the same source.
    """
    if no_fetch:
        return False, False
    ok, _when = fetch_all(repo)
    return True, not ok


def _fetch_every(repos: list[Path], no_fetch: bool) -> dict[Path, tuple[bool, bool]]:
    """Fetch every repository, so the header can describe the whole run."""
    return {repo: _fetch_report(repo, no_fetch) for repo in repos}


def _stamp_fetch(report: RepoReport, fetch: tuple[bool, bool]) -> None:
    """Record the run's fetch outcome on *report*, for the heading and warning."""
    report.fetch_attempted, report.fetch_failed = fetch


def _stale_counts(repos: list[Path], fetch_state: dict[Path, tuple[bool, bool]]) -> tuple[int, int]:
    """``(stale, total)`` for the top warning, over the whole run.

    Staleness is the report's own rule (nothing refreshed this run), evaluated
    from the fetch outcome and the on-disk refs rather than from any one
    repository's heading.
    """
    stale = sum(
        1
        for repo in repos
        if RepoReport(
            path=repo,
            fetch_attempted=fetch_state[repo][0],
            fetch_failed=fetch_state[repo][1],
            fetched_at=refs_updated_at(repo),
        ).is_stale
    )
    return stale, len(repos)


def _run(
    analysis: Analysis,
    path: Path,
    no_fetch: bool,
    author: list[str] | None,
    branch_filter: str | list[str] | None,
) -> None:
    config = Config.load()
    root = _resolve_root(path)
    require_git()

    repos = discover_repos(root)
    # Fetch every repository first (see `local`): the stale warning's count is a
    # property of the run, not of whichever repository happens to be first.
    fetch_state = _fetch_every(repos, no_fetch)
    emit(render_header(*_stale_counts(repos, fetch_state)))

    for repo in repos:
        # Base ref resolved AFTER the fetch above. Resolving first would judge a
        # branch against a local `main` that this run's own fetch is about to
        # supersede, reporting live branches as unmerged.
        base_ref = resolve_base_ref(repo)
        identities = resolve_identities(author or [], config, repo)
        try:
            report = analysis(repo, config, base_ref, identities, branch_filter)
        except (GitError, OSError, subprocess.SubprocessError) as exc:
            _warn(f"error analysing {repo}: {exc}")
            continue
        _stamp_fetch(report, fetch_state[repo])
        report_remote_health(repo, report)
        emit(render_repo(report, root))


def run_command(
    command: str,
    path: Path,
    no_fetch: bool,
    author: list[str] | None = None,
    branch_filter: str | list[str] | None = None,
) -> None:
    """Run one named subcommand's analysis over *path*."""
    _run(ANALYSES[command], path, no_fetch, author or [], branch_filter)


def _emit_summary(updated: list[tuple[Path, str]], root: Path) -> None:
    """The record of what this run wrote, one line per fast-forward.

    No marker on these lines: the section says what they are, and a status
    marker here would be a judgement about work that was simply done as asked.
    """
    if not updated:
        return
    lines = ["## fast-forwarded", ""]
    lines += [
        f"- {display_path(repo, root)}: `{branch}` fast-forwarded" for repo, branch in updated
    ]
    emit("\n".join(lines) + "\n")


def fast_forward_worktrees(repo: Path) -> list[str]:
    """The branches fast-forwarded in *repo*, and nothing else.

    ``git merge --ff-only`` in each clean, attached worktree that is behind its
    upstream. Git itself refuses a fast-forward that would overwrite a locally
    modified file, so the checks here are about *reporting* rather than about
    safety, and the one check that cannot be read fails closed.

    Only the branches that moved are returned, because every other outcome is
    already in the repository's own section: a detached HEAD, a dirty worktree,
    a worktree whose status could not be read (``worktree_status`` reports that
    as dirty, which is what it is for), a branch with no upstream, and a
    diverged one each produce a finding there. Listing them again under a
    heading that says "fast-forwarded" would put work that was deliberately
    not done beside work that was.

    The one case no finding covers is a base branch (``main``, ``master``, the
    resolved base ref) with no upstream: base branches are excluded from branch
    findings by design, on the grounds that they are not findings. It is left
    unreported for that reason, not by oversight.
    """
    updated: list[str] = []
    for worktree, branch in list_worktrees(repo):
        if branch is None:
            continue
        status = run_git(worktree, "status", "--porcelain", check=False)
        if status.returncode != 0 or status.stdout.strip():
            continue
        has_upstream = (
            run_git(worktree, "rev-parse", "--verify", "--quiet", "@{upstream}").returncode == 0
        )
        if not has_upstream:
            continue
        behind = run_git(worktree, "rev-list", "--count", "HEAD..@{upstream}")
        if behind.returncode == 0 and behind.stdout.strip() == "0":
            continue
        proc = run_git(worktree, "merge", "--ff-only")
        if proc.returncode == 0:
            updated.append(branch)
    return updated


def _configure_output() -> None:
    """Write the report as UTF-8 even where the console defaults otherwise.

    The report uses emoji markers and quotes branch names and repository paths.
    A redirected stream on Windows encodes cp1252, so the first marker would
    raise ``UnicodeEncodeError``; a POSIX stream under ``LANG=C`` has the same
    problem with ASCII. Contributors and issues are UTF-8, so state that for
    both streams rather than degrading the text to the console's code page.

    ``errors="replace"`` is the backstop for a POSIX path whose bytes are not
    UTF-8: git output is already decoded leniently, but a directory name is
    not, and losing one glyph beats losing the run.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except OSError, ValueError:
            # Detached or already-closed stream: nothing to configure.
            continue


def main() -> None:
    """Entry point.

    Everything this tool considers a usage problem -- a bad flag, an unknown
    command, a path that is not a directory, an unusable config file -- is one
    line on stderr and exit 1. A failure that stops the run before it finishes
    is one line and exit 2. A git that cannot be executed is one of those
    failures rather than a finding, because the scan never produced a report
    anyone could trust. Findings themselves never change the exit code.

    ``standalone_mode=False`` is what makes that possible: it hands the
    framework's errors over instead of letting it print and exit itself. Without
    it a mistyped flag escapes as an unhandled exception, which means a
    traceback for what is a typo, and an exit code that is 1 only because
    unhandled exceptions happen to be.

    The same mode decides how an exit *code* comes back. Rather than raising,
    typer returns it -- the command's own return value, or the code of any
    ``typer.Exit`` it raised -- so the return value is what has to be read here.
    """
    _configure_output()
    try:
        code = app(standalone_mode=False)
    except _USAGE_ERRORS as exc:
        _warn(f"error: {exc}")
        raise SystemExit(1) from None
    except GitUnavailable as exc:
        # The documented meaning of 2: the run stopped before it could
        # complete. Git disappearing mid-scan reaches this too, because the
        # per-repository handlers deliberately do not catch it.
        _warn(f"error: {exc}")
        raise SystemExit(2) from None
    except typer.Abort:
        _warn("aborted")
        raise SystemExit(1) from None
    # Anything else is an environment failure or a bug: the run could not
    # complete. That is the documented meaning of exit 2, and it is what tells
    # a crash apart from a usage error for anything scripting this tool.
    except Exception as exc:
        _warn(f"error: {exc}")
        raise SystemExit(2) from None
    # Every command is annotated `-> None`, so a return value here is the exit
    # code of a `typer.Exit` a command raised deliberately. Anything else is a
    # successful run.
    raise SystemExit(code if isinstance(code, int) else 0)


if __name__ == "__main__":
    main()
