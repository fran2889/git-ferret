# Troubleshooting

Most problems are in the install or the fetch, not the scan. The [README](../README.md) has the
short version; this page has the errors and the commands that fix them.

## When the venv breaks

```console
$ .venv/bin/git-ferret local ~/src
zsh: bad interpreter: /home/you/src/git-ferret/.venv/bin/python3.11: no such file or directory
```

The environment is intact; its Python is gone. Every script installed into `.venv/bin`
(`git-ferret`, `pytest`, `pip`) starts with the absolute path of the interpreter that created the
environment. Once that interpreter is uninstalled, upgraded or switched (`pyenv` or `uv` changing
versions, a Homebrew upgrade, the Python macOS ships changing), all of them fail the same way, and
activating the environment does not help.

Rebuild it. Nothing in `.venv` is unique: its contents come from `pyproject.toml`, plus anything you
installed into it by hand, which is worth listing first if you have:

```console
$ .venv/bin/pip list
$ rm -rf .venv
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e .
```

With uv, the equivalent is:

```console
$ rm -rf .venv
$ uv sync --locked
```

If the version named in the error is one you no longer want (`python3.11` when you are on
`python3.14`), then `python3 -m venv .venv` builds the same broken environment again. Check what
`python3` resolves to with `python3 --version`, or pin the version: `uv venv --python 3.14`.

## Fetch failures

A failed fetch is not fatal. The repository is still analysed from the refs already on disk, the
report marks it `[UNREACHABLE]`, and the run carries the stale warning at the top.

Check that the remote exists and is reachable:

```console
$ git -C ~/src/api remote -v
$ git -C ~/src/api fetch --all --prune
```

If you are offline deliberately, `--no-fetch` says so up front and skips the network entirely:

```console
$ git-ferret local ~/src --no-fetch
```

The report is still labelled stale, because no fetch happened this run. That is not an error; it is
the tool telling you what it read.

## Shallow clones

A shallow clone may not contain the merge base the `merged` analysis needs. Rather than inventing a
conflict, git-ferret reports `[UNKNOWN]` for that branch. Deepen the clone and run again:

```console
$ git -C ~/src/api fetch --unshallow
```

If the repository is intentionally shallow and you do not want the history, the `[UNKNOWN]` marker is
the honest answer. Do not read it as "not merged".

## Missing base branches

git-ferret uses `origin/main`, `origin/master`, `main`, or `master`, in that order. It does not guess
at `develop`, `trunk`, or a team-specific name. A repository with none of those reports `[NO BASE]`,
and `remote` and `merged` skip its branch analysis.

Either create the branch the tool looks for, or add the remote ref it should compare against:

```console
$ git -C ~/src/api branch -a
$ git -C ~/src/api remote show origin
```

The heading states which ref was used, so a fallback to a local `main` is visible. That fallback is a
weaker claim than `origin/main`, and the report treats it as one.

## Windows console encoding

Git output is decoded as UTF-8 rather than with the console code page. If the destination cannot
encode a decorative emoji, that glyph is replaced instead of failing the run; the bracketed marker
still carries the meaning, so the replacement is cosmetic.

If the text still looks wrong, use Windows Terminal or switch the console to UTF-8:

```console
> chcp 65001
```

For a redirected report, write it to a file and read it with an editor that understands UTF-8:

```console
> git-ferret local C:\src --no-fetch > report.md
```

## Where to get help

If none of the above explains what you see, open an issue using the bug report template. Include the
output of `git-ferret --version`, `python --version`, and `git --version`, the exact command, and
the full report or error. The template asks for these because a report that cannot name its versions
cannot be reproduced.
