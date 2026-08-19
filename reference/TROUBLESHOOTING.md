# Troubleshooting — keyed by symptom

## "Invalid Proposal XML file. Import stopped."

Strata rejected the file structurally. It's all-or-nothing: no partial
import, no field-level detail. Checklist, in order of likelihood:

1. Run `scripts/validate_proposal.py` — it catches the known causes:
   `<NumberOfSpots>` instead of `<SpotsByDay>`, spots block in the wrong
   position, broken `outletId`/`DemoId` references, malformed
   `UniqueMessageID`.
2. Was the file emailed as bare XML? Transit corruption is FreeWheel's #1
   documented cause. Re-send zipped.
3. Was the file hand-edited in a text editor? Editors quietly convert CRLF
   to LF and re-indent. Regenerate with `scripts/inject_spots.py` instead.

## Import succeeded but totals are short

This is the **air-day rule** (see FORMAT.md): spots on weekdays flagged
`N` in a line's `<Days>` are dropped silently.

1. Run `scripts/simulate_import.py` on the file that was imported. It will
   list exactly which spots Strata dropped and why, and its predicted
   totals should match what the Strata scheduler shows.
2. If the simulator predicts the shortfall exactly → the buy plan included
   phantom inventory. Rebuild with `/strata-buy:build-buy` (the optimizer
   masks phantom cells automatically).
3. If the simulator does NOT explain the discrepancy → this is a new,
   unknown drop rule. Diff the imported-then-re-exported file against the
   sent file period by period, find the pattern, and report it to Suede so
   the toolkit can be updated. Do not guess.

## VIEW prompts to select a survey

Expected, not an error. The survey named in the file isn't installed
locally. Pick the matching survey (or the closest substitute) — but note
that substituting re-derives ratings from the substitute book rather than
honoring the file's numbers. Declining the prompt cancels the import.

## File imported as a new scheduler instead of merging

Merge requires the active scheduler's flight dates, demo, and survey to
match the file. A mismatch silently falls back to "import as new
scheduler." Not data loss — but check which scheduler you're looking at
before concluding spots are missing.

## Optimizer says "no buyable inventory"

Every period in the file is either on a non-air day or missing a rating
for the chosen demo. Check the demo setting in the parameters TOML against
the demo panel reported by `/strata-buy:ingest-avails` — a demo name that
doesn't match the file's panel is the usual cause.

## Optimizer output says "greedy fallback — NOT guaranteed optimal"

`pulp`/CBC wasn't available, so a heuristic ran instead. The buy is valid
(all constraints respected) but may leave points on the table. Fix:
`pip install pulp --break-system-packages`, then rerun.

## CPP is much higher than a previous estimate

Ask whether the previous estimate was computed over unmasked inventory.
A CPP that includes phantom (non-air-day) cells understates true cost —
in one real market the honest CPP was ~40% higher than the phantom-
inflated figure. The masked number is the real one.
