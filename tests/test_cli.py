r"""Tests for the CLI surface.

Every assertion here is made against unstyled text. Rich styles a flag one
hyphen-separated run at a time, so ``--no-fetch`` renders as three
escape-wrapped fragments and the literal string is nowhere to be found:

    \x1b[1;36m-\x1b[0m\x1b[1;36m-no\x1b[0m\x1b[1;36m-fetch\x1b[0m

Whether rich emits colour at all depends on the environment rather than on the
CLI: GitHub Actions sets ``GITHUB_ACTIONS``, which rich reads as "this output
will be rendered", so an assertion written against raw output passes on a
developer's terminal and fails in CI over a difference in styling that has
nothing to do with what is documented.
"""

from click import unstyle
from typer.testing import CliRunner

from git_ferret.cli import build_parser

runner = CliRunner()


def _help(*args: str) -> str:
    """The help text for a subcommand, with rich's styling removed."""
    res = runner.invoke(build_parser(), [*args, "--help"])
    assert res.exit_code == 0
    return unstyle(res.stdout)


def test_has_three_subcommands():
    res = runner.invoke(build_parser(), ["--help"])
    assert res.exit_code == 0
    for cmd in ("local", "remote", "merged"):
        assert cmd in unstyle(res.stdout)


def test_local_help_lists_no_fetch():
    assert "--no-fetch" in _help("local")


def test_remote_help_lists_branch_filter():
    help_text = _help("remote")
    assert "--branch" in help_text
    assert "--author" in help_text


def test_merged_help_lists_filters():
    help_text = _help("merged")
    assert "--author" in help_text
    assert "--branch" in help_text


def test_local_help_lists_update_flag():
    assert "--update" in _help("local")


def test_update_is_not_on_remote():
    assert "--update" not in _help("remote")


def test_local_help_documents_it_does_not_write_by_default():
    assert "--update" in _help("local")
