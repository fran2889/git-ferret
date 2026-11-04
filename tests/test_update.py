# SPDX-FileCopyrightText: 2026 Fran
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for the --update write path.

This is the only code in the project permitted to change a repository, so its
refusals are asserted as carefully as its effect: each test below checks that
HEAD did not move, not merely that nothing was printed.
"""

import shutil
from pathlib import Path

from typer.testing import CliRunner

from git_ferret.cli import (
    _fast_forward_ref,  # pyright: ignore[reportPrivateUsage]
    _move_ref,  # pyright: ignore[reportPrivateUsage]
    build_parser,
    fast_forward_branches,
)
from git_ferret.gitcmd import run_git
from tests.helpers import clone_local, commit, make_repo, run


def _head(repo: Path) -> str:
    return run(repo, "rev-parse", "HEAD").stdout.strip()


def _behind_clone(tmp_path: Path) -> Path:
    """A clone whose checked-out branch is one commit behind its upstream."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "feat", "origin/main")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")
    # Keep the clone's own `main` current: these tests are about the
    # checked-out worktree path, and an unchecked-out `main` behind its
    # upstream would now legitimately move through the ref-only path too.
    run(clone, "branch", "--force", "main", "origin/main")
    return clone


def _ref_only_behind_clone(tmp_path: Path) -> Path:
    """A clone whose local `feat` branch is behind origin/feat and not checked out."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    return clone


def _symbolic_alias_to_main_clone(tmp_path: Path) -> Path:
    """A clone whose `alias` is a symbolic ref to a dirty, behind `main`."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "symbolic-ref", "refs/heads/alias", "refs/heads/main")
    run(clone, "config", "branch.alias.remote", "origin")
    run(clone, "config", "branch.alias.merge", "refs/heads/main")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")
    (clone / "wip.txt").write_text("dirty\n")
    return clone


def _symbolic_alias_to_remote_clone(tmp_path: Path) -> Path:
    """A clone whose `alias` is a symbolic ref to `refs/remotes/origin/other`."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "other")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "symbolic-ref", "refs/heads/alias", "refs/remotes/origin/other")
    run(clone, "config", "branch.alias.remote", "origin")
    run(clone, "config", "branch.alias.merge", "refs/heads/main")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")
    # Keep the checked-out `main` from legitimately moving through either pass,
    # so the test observes `alias` alone.
    (clone / "wip.txt").write_text("dirty\n")
    return clone


def test_fast_forwards_a_clean_worktree_behind_upstream(tmp_path: Path):
    clone = _behind_clone(tmp_path)
    assert run(clone, "rev-list", "--count", "HEAD..@{upstream}").stdout.strip() == "1"

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-list", "--count", "HEAD..@{upstream}").stdout.strip() == "0"


def test_fast_forwards_an_unchecked_out_branch_behind_upstream(tmp_path: Path):
    clone = _ref_only_behind_clone(tmp_path)
    assert run(clone, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert run(clone, "rev-list", "--count", "feat..origin/feat").stdout.strip() == "1"

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-parse", "feat").stdout == run(clone, "rev-parse", "origin/feat").stdout


def test_fast_forwards_an_unchecked_out_base_branch(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "work")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")

    assert fast_forward_branches(clone) == ["main"]
    assert run(clone, "rev-parse", "main").stdout == run(clone, "rev-parse", "origin/main").stdout


def test_a_local_branch_named_like_the_upstream_does_not_shadow_it(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    base = run(clone, "rev-parse", "HEAD").stdout.strip()
    run(clone, "branch", "origin/feat", base)
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    upstream = run(clone, "rev-parse", "refs/remotes/origin/feat").stdout.strip()
    assert upstream != base

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-parse", "feat").stdout.strip() == upstream


def test_a_nonstandard_fetch_refspec_uses_the_real_upstream(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    # Move the remote-tracking refs out of refs/remotes/origin/*, so the
    # hardcoded origin/feat ref is stale while the real upstream moves.
    run(clone, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/upstream/*")
    run(clone, "fetch", "--all", "--prune")
    run(clone, "branch", "--track", "feat", "upstream/feat")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    upstream = run(clone, "rev-parse", "refs/remotes/upstream/feat").stdout.strip()
    assert run(clone, "rev-parse", "refs/remotes/origin/feat").stdout.strip() != upstream

    assert fast_forward_branches(clone) == ["feat"]
    assert run(clone, "rev-parse", "feat").stdout.strip() == upstream


def test_a_ref_that_moved_after_it_was_read_is_not_clobbered(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    stale = _head(repo)
    run(repo, "checkout", "-b", "feat")
    (repo / "feat.txt").write_text("feat\n")
    commit(repo, "feat work")
    moved = _head(repo)
    run(repo, "checkout", "main")
    run(repo, "merge", "--ff-only", "feat")
    (repo / "upstream.txt").write_text("upstream\n")
    commit(repo, "upstream work")
    new = _head(repo)

    assert _move_ref(repo, "feat", new, stale) is False
    assert run(repo, "rev-parse", "feat").stdout.strip() == moved


def test_a_missing_branch_is_not_recreated(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    old = _head(repo)
    new = _head(repo)
    run(repo, "branch", "gone")
    run(repo, "branch", "-D", "gone")

    assert _move_ref(repo, "gone", new, old) is False
    assert run(repo, "branch", "--list", "gone").stdout.strip() == ""


def test_a_symbolic_branch_is_not_dereferenced_to_move_main(tmp_path: Path):
    clone = _symbolic_alias_to_main_clone(tmp_path)
    main_before = run(clone, "rev-parse", "main").stdout.strip()
    assert main_before != run(clone, "rev-parse", "origin/main").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "main").stdout.strip() == main_before
    assert run(clone, "symbolic-ref", "refs/heads/alias").stdout.strip() == "refs/heads/main"


def test_a_symbolic_branch_is_not_dereferenced_to_move_a_remote_tracking_ref(tmp_path: Path):
    clone = _symbolic_alias_to_remote_clone(tmp_path)
    other_before = run(clone, "rev-parse", "refs/remotes/origin/other").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "refs/remotes/origin/other").stdout.strip() == other_before
    assert (
        run(clone, "symbolic-ref", "refs/heads/alias").stdout.strip() == "refs/remotes/origin/other"
    )


def test_a_branch_checked_out_after_the_snapshot_is_not_moved(tmp_path: Path):
    clone = _ref_only_behind_clone(tmp_path)
    linked = tmp_path / "linked"
    run(clone, "worktree", "add", str(linked), "feat")
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert _fast_forward_ref(clone, "feat", "refs/remotes/origin/feat") is False
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def test_a_local_upstream_is_not_moved(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "branch", "feat")
    run(repo, "branch", "--set-upstream-to=main", "feat")
    before = run(repo, "rev-parse", "feat").stdout.strip()
    (repo / "f.txt").write_text("a\nmore\n")
    commit(repo, "main work")

    assert fast_forward_branches(repo) == []
    assert run(repo, "rev-parse", "feat").stdout.strip() == before


def test_an_unreadable_worktree_is_not_ref_updated(tmp_path: Path):
    clone = _ref_only_behind_clone(tmp_path)
    linked = tmp_path / "linked"
    run(clone, "worktree", "add", str(linked), "feat")
    shutil.rmtree(linked)
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def _paused_rebase_clone(tmp_path: Path, *rebase_args: str) -> Path:
    """A clone whose linked worktree is stopped in a rebase of ``feat``."""
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "checkout", "-b", "feat")
    (src / "local.txt").write_text("local\n")
    commit(src, "local work")
    run(src, "checkout", "main")
    (src / "local.txt").write_text("main side\n")
    commit(src, "main work")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    linked = tmp_path / "linked"
    run(clone, "worktree", "add", str(linked), "feat")
    run(src, "checkout", "feat")
    (src / "up.txt").write_text("up\n")
    commit(src, "upstream work")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    # A conflicting rebase leaves HEAD detached and rebase state on disk.
    rebase = run_git(linked, "rebase", *rebase_args, "origin/main")
    assert rebase.returncode != 0
    # Keep the checked-out main worktree from moving through the worktree pass,
    # so the assertion observes the ref-only pass alone.
    (clone / "wip.txt").write_text("wip\n")
    return clone


def test_a_rebase_in_progress_skips_the_ref_only_pass(tmp_path: Path):
    """A rebase detaches HEAD, so its branch would otherwise look unchecked-out."""
    clone = _paused_rebase_clone(tmp_path)
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def test_an_apply_rebase_in_progress_skips_the_ref_only_pass(tmp_path: Path):
    clone = _paused_rebase_clone(tmp_path, "--apply")
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def test_a_bisect_in_progress_skips_the_ref_only_pass(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "feat")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "branch", "--track", "feat", "origin/feat")
    run(src, "checkout", "feat")
    (src / "f.txt").write_text("a\none\n")
    commit(src, "one")
    (src / "f.txt").write_text("a\ntwo\n")
    commit(src, "two")
    run(src, "checkout", "main")
    run(clone, "fetch", "--all", "--prune")
    run(clone, "bisect", "start")
    run(clone, "bisect", "bad", "origin/feat")
    run(clone, "bisect", "good", "main")
    before = run(clone, "rev-parse", "feat").stdout.strip()

    assert fast_forward_branches(clone) == []
    assert run(clone, "rev-parse", "feat").stdout.strip() == before


def test_rollup_reports_an_unchecked_out_branch(tmp_path: Path):
    _ref_only_behind_clone(tmp_path)

    res = CliRunner().invoke(build_parser(), ["local", str(tmp_path), "--no-fetch", "--update"])

    assert res.exit_code == 0, res.output
    assert "- clone: `feat` fast-forwarded\n" in res.output


def test_skips_dirty_worktree(tmp_path: Path):
    clone = _behind_clone(tmp_path)
    (clone / "uncommitted.txt").write_text("wip\n")
    before = _head(clone)

    assert fast_forward_branches(clone) == []
    # The dirty file must survive untouched and the branch must not have moved.
    assert (clone / "uncommitted.txt").read_text() == "wip\n"
    assert _head(clone) == before


def test_skips_branch_with_no_upstream(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    run(repo, "checkout", "-b", "solo")
    before = _head(repo)

    assert fast_forward_branches(repo) == []
    assert _head(repo) == before


def test_skips_detached_head(tmp_path: Path):
    repo = make_repo(tmp_path / "r")
    (repo / "f.txt").write_text("a\n")
    commit(repo, "base")
    sha = run(repo, "rev-parse", "HEAD").stdout.strip()
    run(repo, "checkout", sha)

    assert fast_forward_branches(repo) == []
    assert _head(repo) == sha


def test_up_to_date_worktree_is_not_reported(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, tmp_path / "clone")

    assert fast_forward_branches(clone) == []


def test_does_not_delete_anything(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    run(src, "branch", "keepme")
    clone = clone_local(src, tmp_path / "clone")
    run(clone, "checkout", "-b", "keepme", "origin/keepme")
    before = run(clone, "branch", "--format=%(refname)").stdout
    fast_forward_branches(clone)
    after = run(clone, "branch", "--format=%(refname)").stdout
    assert before == after


def _updatable_tree(tmp_path: Path):
    """A root holding one clean worktree that --update will move.

    Returns the root to scan. `origin-src` has no remote, so it is reported but
    never updated: the roll-up should name `app` alone.
    """
    root = tmp_path / "src"
    src = make_repo(root / "origin-src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")
    clone = clone_local(src, root / "app")
    run(clone, "checkout", "-b", "feat", "origin/main")
    (src / "f.txt").write_text("a\nremote\n")
    commit(src, "remote work")
    run(clone, "fetch", "--all", "--prune")
    # Only `feat` is meant to move here; keep the clone's unchecked-out
    # `main` current so it is not a second ref-only update.
    run(clone, "branch", "--force", "main", "origin/main")
    return root


def test_rollup_names_repositories_relative_to_the_root(tmp_path: Path):
    root = _updatable_tree(tmp_path)

    res = CliRunner().invoke(build_parser(), ["local", str(root), "--update"])

    assert res.exit_code == 0, res.output
    # Same rule as a section heading: the root the user typed is not repeated.
    assert "## app\n" in res.output
    assert "- app: `feat` fast-forwarded\n" in res.output
    assert str(root) not in res.output


def test_rollup_is_a_block_of_its_own(tmp_path: Path):
    res = CliRunner().invoke(build_parser(), ["local", str(_updatable_tree(tmp_path)), "--update"])

    lines = res.output.split("\n")
    heading = lines.index("## fast-forwarded")
    # One blank line either side: the block does not open a gap of its own.
    assert lines[heading - 1] == ""
    assert lines[heading + 1] == ""


def test_stale_footer_is_separated_from_the_rollup(tmp_path: Path):
    # --no-fetch leaves the clone, which has a remote, stale; origin-src has no
    # remote and is not counted. The rollup is followed by the footer: two
    # blocks, not a fast-forward line with a quote glued underneath it.
    root = _updatable_tree(tmp_path)

    res = CliRunner().invoke(build_parser(), ["local", str(root), "--no-fetch", "--update"])

    assert res.exit_code == 0, res.output
    assert "- app: `feat` fast-forwarded\n\n> " in res.stdout
    assert "1 of 2 repositories" in res.stdout


def test_rollup_is_absent_when_nothing_was_updated(tmp_path: Path):
    src = make_repo(tmp_path / "src")
    (src / "f.txt").write_text("a\n")
    commit(src, "base")

    res = CliRunner().invoke(build_parser(), ["local", str(tmp_path), "--update"])

    assert res.exit_code == 0, res.output
    assert "fast-forwarded" not in res.output


def test_rollup_lines_carry_no_status_marker(tmp_path: Path):
    res = CliRunner().invoke(build_parser(), ["local", str(_updatable_tree(tmp_path)), "--update"])

    rollup = res.output.split("## fast-forwarded")[1]
    assert "[OK]" not in rollup


def test_skips_are_not_repeated_in_the_rollup(tmp_path: Path):
    root = _updatable_tree(tmp_path)
    (root / "app" / "wip.txt").write_text("x\n")

    res = CliRunner().invoke(build_parser(), ["local", str(root), "--update"])

    # The dirty worktree is a finding in its own section, not an update.
    assert "[DIRTY]" in res.stdout
    assert "## fast-forwarded" not in res.stdout
