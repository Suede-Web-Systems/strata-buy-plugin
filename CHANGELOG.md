# Changelog

## 0.1.2 — 2026-08-19

Optimizer speed and multi-campaign config, from the second test-drive pass:

- **~60x faster solves.** CBC was spending its entire hardcoded 180s time
  limit proving optimality it had already found (measured: identical
  655.8-point solution at 15s and 180s on a real 930-cell file). New
  `[solver]` config: `gap` (default 0.001) and `time_limit_s` (default 60).
  Measured results: 930 cells 180s -> 2.9s at -0.05% points; 6,655-cell
  larger file solves in 0.4s.
- **Honest solver labels.** PuLP/CBC reports "Optimal" even when stopped
  by the time limit with an unproven incumbent. Output now says
  "within X% of optimal (Ns)" or, when time-capped, that optimality is
  NOT proven and how to fix it.
- **One strategy file per campaign.** Template gains `[meta]`
  (campaign/notes) and `[solver]` sections; build-buy skill now lists
  `buy-*.toml` strategies, asks which to use, and names new ones
  `buy-<client>-<campaign>.toml` in the working folder — the plugin
  install dir is read-only on marketplace installs (e.g. Cowork).
- **Audit trail:** `buy-plan.json` now embeds the full config and a
  spots/spend/points summary alongside the buy.
- `.gitignore` hardened: secrets (.env, keys), client data (root XML/PRX/
  ZIP, buy-*.toml, plan/inventory JSON), Python/OS junk, `.claude/`.
- build-buy SKILL.md: `python3 -m pip` install line.

## 0.1.1 — 2026-08-19

Hardening pass from the first live test drive (two real avails files:
different markets and campaign types):

- **Fail loudly on unsupported structure** instead of silently ignoring it:
  multiple `AvailList`s, weekly-grain `AvailLineWithPeriods`, non-station
  outlets, and multi-`DayTime` lines now raise `FormatError` with a message
  naming the shape. Previously these could yield a plausible-but-wrong
  summary (a corrupted air-day mask corrupts the phantom count).
- Friendly diagnostics for two confirmed crash paths: zero rate periods
  (was `ZeroDivisionError`) and missing `TargetDemo` (was `AttributeError`;
  now falls back to the first demo with a printed WARNING). Missing
  `Advertiser` no longer crashes.
- `parse_avails.py` now prints a per-station table (lines / buyable /
  phantom / 0-rated / min-avg-max rate) and an explicit accounting line for
  on-air periods with a 0.0 target rating, which were previously folded
  into the buyable gap without explanation.
- Documented the `--json` schema in the script docstring; `parse()` output
  gains a `warnings` list.
- SKILL.md: `python3 -m pip` (bare `pip` is often absent), plus guidance to
  surface parser WARNINGs and the 0-rated exclusion to the buyer.

## 0.1.0 — 2026-08-19

Initial release. Encodes the format and import-behavior research from the
August 2026 pilot:

- Parser, optimizer, injector, validator, and import simulator for
  AAAA `SpotTVCableProposal` v0.3.0.5A ("Proposal XML") files.
- **Air-day rule** (discovered 2026-08-18): Strata VIEW silently drops any
  spot placed on a weekday whose `<Days>` flag is `N` on that avail line.
  The validator blocks such files and the simulator predicts exact
  post-import totals. In one real avails file, 59% of rate periods fell on
  non-air days — "phantom inventory" that must be masked before optimizing.
- Edit-in-place generation: spot blocks are injected into the source file's
  own bytes, never re-serialized, so seller terms round-trip unmodified.
