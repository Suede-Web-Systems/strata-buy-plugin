---
description: Build an optimized broadcast TV spot buy from an avails file and produce a Strata-ready Proposal XML. Use when the user wants to create a buy, place spots, optimize a schedule against a budget, or generate a buy sheet for import into Strata VIEW.
---

# Build buy

Turn an avails file plus the buyer's parameters into a validated, Strata-ready buy file. The pipeline is: **parameters → optimize → inject → validate → simulate**. Every step is a script; never hand-write spot XML.

## 1. Dependencies (first run only)

```bash
python3 -m pip install lxml pulp --break-system-packages
```

(Bare `pip` is often not on PATH.)

If `pulp` fails to install, proceed anyway — the optimizer falls back to a greedy heuristic and labels its output as non-optimal. Tell the user when the fallback was used.

## 2. Parameters — one strategy file per campaign

Clients run many campaigns with different strategies. Each strategy lives in its own TOML in the **working folder** (never the plugin folder — it is read-only when installed from the marketplace, and is replaced on update):

- List existing strategies first: `ls buy-*.toml`. If any exist, show the user each file's `[meta] campaign` line and ask which to use (or whether this buy needs a new one).
- For a new strategy, copy the template under a campaign-specific name and fill it in by **asking the user**, not by guessing:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/config/buy-parameters.template.toml" "./buy-<client>-<campaign>.toml"
```

Ask for at minimum: budget, target demo, and whether the default shape rules (station cap, news floor, overnight cap, daily coverage) match how they want this buy shaped. Fill in `[meta]` so the file is self-describing. Saved this way, rerunning or tweaking any campaign is one command, and the TOML doubles as the audit record of how the buy was shaped — the optimizer also embeds a copy of it in `buy-plan.json`.

## 3. Optimize

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/optimize_buy.py" "<avails.xml>" --config "<buy-strategy.toml>" --out buy-plan.json
```

Solves in seconds on real files (the `[solver]` gap default trades a <=0.1% optimality margin for a ~1000x speedup). If the output says the time cap was hit and optimality is NOT proven, raise `time_limit_s` in the TOML and rerun rather than shipping the unproven plan.

Report the summary: spots, spend, points, CPP, news share, station shares, spots per day. The optimizer only ever buys **valid inventory** (air-day + rated cells). If the CPP looks worse than the buyer expects, explain that phantom inventory is excluded — a CPP computed over unbuyable cells is fiction.

## 4. Generate the file — edit-in-place, always

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/inject_spots.py" "<avails.xml>" buy-plan.json "<output.xml>" --name "<proposal name>"
```

This injects `<SpotsByDay>` blocks into the source file's own bytes. **Never rebuild the XML from scratch and never edit it by hand** — edit-in-place guarantees the seller's terms, comments, and rates round-trip unmodified, which buyers are contractually expected to preserve. The script refuses plans containing invalid spots; if it refuses, the plan is wrong — fix the plan, don't override the script.

## 5. Verify — both gates must pass before the user sees the file

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/validate_proposal.py" "<output.xml>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/simulate_import.py" "<output.xml>"
```

Non-negotiable: a file that fails either gate is not a deliverable. Strata's import drops invalid spots **silently** — the import will look successful while the buy comes up short.

## 6. Deliver

Zip the XML before it is emailed (Strata's own guidance — bare XML corrupts in email transit). Present the user with the file plus a **reconciliation table**: intended spots and dollars. These are the two numbers to check against the Strata scheduler after import.

## Next step — recommend explicitly

End by telling the user: **"Before this goes anywhere, run `/strata-buy:preflight` on the output file"** — and run it for them if they agree. After import, they should compare Strata's scheduler totals to the reconciliation table; any mismatch → `${CLAUDE_PLUGIN_ROOT}/reference/TROUBLESHOOTING.md`.
