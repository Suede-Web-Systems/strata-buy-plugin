# strata-buy-plugin

Claude Code plugin that builds, validates, and preflights broadcast TV buy
sheets (AAAA `SpotTVCableProposal` XML) for import into Strata VIEW. Real
money rides on these files: a wrong number becomes a wrong media buy.

## Map

- `scripts/proposal_lib.py` — **the single source of format truth.** All
  format knowledge lives here + `reference/FORMAT.md`. Never parse the XML
  ad hoc elsewhere.
- `scripts/` — parse_avails, optimize_buy, inject_spots, validate_proposal,
  simulate_import. Pipeline: parameters → optimize → inject → validate →
  simulate.
- `skills/` — the three shipped skills (ingest-avails, build-buy, preflight).
- `reference/FORMAT.md` — empirical Strata behavior (what's confirmed vs
  inferred, and how we know). `reference/TROUBLESHOOTING.md` — by symptom.
- `config/buy-parameters.template.toml` — the buyer-facing constraint
  vocabulary.
- `.claude/skills/pr/` — internal: run `/pr` before committing or opening
  a PR here.

## Iron rules

1. **Never read a raw avails/Proposal XML into context** (20k–120k lines).
   Go through `parse_avails.py`. The `--json` schema is in its docstring —
   use those field names, don't guess.
2. **Never hand-write or re-serialize spot XML.** `inject_spots.py`
   edit-in-place only. Seller files must round-trip byte-identical outside
   the injected blocks.
3. **Fail loudly, never plausibly-wrong.** Unknown file shapes raise
   `FormatError`; a crash costs minutes, a silently wrong phantom count
   costs a client's buy. Don't "handle" unfamiliar structures by guessing.
4. **Label empirical claims.** Statements about Strata import behavior are
   either *confirmed* (cite the test, e.g. the 674/674 air-day run) or
   *inferred* — FORMAT.md shows the convention. Never upgrade inferred to
   confirmed without a real import test.
5. **Both gates before any deliverable**: `validate_proposal.py` AND
   `simulate_import.py` must pass. Never soften a FAIL.
6. **No client data — or references to it — anywhere public.** This repo
   is public. Internal/client documents must not be identifiable from
   code, docs, CHANGELOG, commit messages, or PR text: no document names,
   advertisers, markets, station call letters, survey names, or dollar
   figures from real files. Anonymize to scale metrics (rounded cell
   counts, percentages, timings). Fictional examples use WXXX-style call
   letters. The only fixture is `reference/examples/sample-avails.xml`.
7. **Every user-facing change**: bump `.claude-plugin/plugin.json`, add an
   evidence-based CHANGELOG entry (measured numbers, not adjectives), and
   follow `/pr` for the commit/PR.

## Verifying changes

- Regression: run changed scripts against a real avails file — top-line
  numbers (periods, phantom %, buyable $, spot totals) must be identical
  unless the change intends otherwise.
- Attack: build small synthetic variants of the failure mode you're fixing
  (see CHANGELOG 0.1.1–0.1.3 for the pattern) and check both gates' exit
  codes.
- Check exit codes directly (`cmd >/dev/null; echo $?`), never after a
  pipe — `$?` after `cmd | head` is head's exit code. This trap has bitten
  twice in this repo.
- Dev loop: installed plugins run from the marketplace cache, not this
  repo. To test via the skills, sync changed files into the cache or
  reinstall; otherwise invoke `scripts/` directly by path.

## Environment

- `python3 -m pip install lxml pulp --break-system-packages` (bare `pip`
  is often absent; `pulp` optional but the ILP needs it).
- Skills reference `${CLAUDE_PLUGIN_ROOT}`; scripts must run from any cwd.
