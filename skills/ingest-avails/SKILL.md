---
description: Parse and summarize a broadcast TV avails/schedule file (AAAA Proposal XML) from a station, Strata VIEW, or a data provider. Use when the user shares a schedule, avails, rate card, or "Scheduler (tv)" XML file, or asks what inventory a station sent. Reports stations, flight, demos, and — critically — how much of the inventory is actually buyable.
---

# Ingest avails

Parse a `SpotTVCableProposal` ("Proposal XML") file and give the buyer an accurate picture of the market before any buy is built.

## Steps

1. **Never read the raw XML into context.** These files run 20k–120k lines. Always work through the parser:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parse_avails.py" "<file.xml>" --json inventory.json
   ```

   If `lxml` is missing, install it first: `pip install lxml --break-system-packages` (add `pulp` too — the next step needs it).

2. **Present the summary conversationally.** Cover: stations and flight dates, the survey name (matters at import time), the demo panel and target demo, daypart vocabulary (seller files often mix 2-letter codes and long-form names — that's normal, Strata retains them on import), and rate/inventory scale.

3. **Always call out the phantom-inventory number.** Seller files routinely carry rate periods on days a program does not air — in one real file, 59% of periods. Spots placed there are **silently dropped by Strata on import**. Tell the buyer how many periods are phantom and that the optimizer automatically excludes them. If the file already carries spots, report the predicted-survival totals the parser prints.

4. If anything in the file structure looks unfamiliar, consult `${CLAUDE_PLUGIN_ROOT}/reference/FORMAT.md` before improvising.

## Next step — recommend explicitly

End by telling the user: **"Ready to build a buy from this file? Say the word and I'll run `/strata-buy:build-buy`** — I'll ask for your budget, target demo, and buy-shape rules (or reuse your saved parameters file)."
