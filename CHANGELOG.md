# Changelog

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
