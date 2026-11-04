# Add `--quiet` to print only repositories with findings

## Intent

A scan over thirty repositories prints a section for every one of them, including
the repositories with nothing to say. The three that matter are buried, and a
week-to-week diff moves whenever an unrelated clean repository is added or
removed. `--quiet` hides the repositories that produced no findings.

## Goals

- `local`, `remote`, and `merged` accept `--quiet`, with `-q` as the short flag.
- A repository with any finding is printed in full, exactly as it is today.
- The header always prints, so an empty quiet run is still a valid report.
- The stale-state warning still prints, and still counts every analysed
  repository, including the ones quiet hid.
- The `## fast-forwarded` block still prints when non-empty: it records writes,
  not findings.
- Exit codes are unchanged. Findings never change them, and quiet changes
  nothing about what the run did.
- Non-quiet output is byte-for-byte unchanged.

## Non-goals

- No change to what counts as a finding, and no change to any analysis.
- No new flag for hiding the `fetched ...` line on printed repositories. The
  issue leaves it in as the default, and it qualifies the findings below it.
- No filtering of stderr warnings. A repository whose analysis failed did not
  produce a report; quiet is about report sections, not about errors.

## Anti-goals

- Quiet that hides the stale warning. That warning describes the whole run and
  is the main way this report can mislead, so hiding it would make the flag
  dangerous.
- Quiet that hides repositories whose only finding is `[OK]`. The user chose
  "any finding counts": `remote` produces `[OK] remote branch` lines by design,
  and a quiet `remote` that printed nothing after matching branches would be
  useless. A "clean" repository is one whose findings list is empty.

## Approaches

1. **Filter at the CLI emission point (chosen).** Both loops already decide when
   to print a section. Add a small `_emit_repo(report, root, quiet)` helper that
   returns without emitting when `quiet` is set and `report.findings` is empty,
   and call it from `local` and `_run`. Fetching, analysis, remote-health
   probing, and the stale/analysed counters keep running for hidden
   repositories, so the footer is unaffected. Rendering is untouched.
2. **Teach the renderer about quiet.** Adding `quiet` to `render_repo` would put
   a display-policy decision in the presentation layer and still require the CLI
   to thread the flag through. `render_report` is only used by tests, so there
   is no second caller to serve.
3. **Drop findings for clean repositories during analysis.** Rejected: it would
   change the `findings` contract, remove `[OK]` lines other callers rely on,
   and conflate analysis with presentation.

## Decisions

- `--quiet` and `-q` are declared on all three subcommands. There is no clash.
- A repository is printed when `not quiet or report.findings` is truthy.
- Counters and the stale warning are computed over every analysed repository,
  before the quiet filter.
- `run_command` gains a trailing `quiet: bool = False` so its existing
  positional callers keep working.
- The README command table gains a `--quiet` row, and the output section gains
  one sentence about what it hides.

## Left to the builder

- Exact helper name and whether the quiet condition lives inline or in a small
  predicate, as long as both commands share one decision.
- Test fixture shape for "a repository with no findings". A freshly fetched
  clone with only `main` and no extra branches qualifies; `--no-fetch` would
  add the stale warning and make a header-only assertion harder to read.
