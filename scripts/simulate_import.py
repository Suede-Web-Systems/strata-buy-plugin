#!/usr/bin/env python3
"""Predict what Strata VIEW will keep from a buy file (the air-day drop rule).

Usage:
  python3 simulate_import.py <buy.xml>

Prints intended vs predicted post-import totals — the two numbers to compare
against the Strata scheduler after import. Exits 1 if any spots would be
silently dropped.

The rule (confirmed empirically, 674/674 periods, exact to the penny):
Strata silently drops any spot whose weekday is flagged 'N' in the avail
line's <Days>, with no error message.
"""
import sys, argparse
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from lxml import etree
from proposal_lib import parse, spot_totals, WEEKDAYS, FormatError


def simulate(path):
    """Returns True if the file passes (no predicted spot loss)."""
    inv = parse(path)
    for w in inv['warnings']:
        print(f"WARNING: {w}")
    ts, td, ss, sd = spot_totals(inv)
    print(f"intended:            {ts:>6} spots   ${td:>12,.2f}")
    print(f"predicted survival:  {ss:>6} spots   ${sd:>12,.2f}")
    if ts == 0:
        print("(file carries no spots — nothing to import)")
        return True
    if ss == ts:
        print("=> PASS: 100% predicted survival. After import, Strata should show the totals above.")
        print("   (This gate checks the air-day drop rule only — structure must "
              "also pass validate_proposal.py.)")
        return True
    print(f"=> FAIL: {ts-ss} spot(s) / ${td-sd:,.2f} would be SILENTLY DROPPED. Offending spots:")
    shown = 0
    for L in inv['lines']:
        for pd in L['periods']:
            if not pd['spots']:
                continue
            for i, n in enumerate(pd['spots']):
                if n > 0 and not (L['days'][i] and i == pd['weekday']):
                    if shown < 25:
                        print(f"   {L['station']} {L['avail_name']!r} {pd['date']} ({WEEKDAYS[i]}) x{n} — air days: {''.join('MTWTFSS'[j] if f else '-' for j, f in enumerate(L['days']))}")
                    shown += 1
    if shown > 25:
        print(f"   ... and {shown-25} more")
    return False


def main():
    ap = argparse.ArgumentParser(description='Predict what Strata VIEW will keep from a buy file.')
    ap.add_argument('xml', nargs='+')
    a = ap.parse_args()
    failed = False
    for path in a.xml:
        if len(a.xml) > 1:
            print(f"--- {path}")
        try:
            if not simulate(path):
                failed = True
        except FormatError as e:
            print(f"UNSUPPORTED FILE STRUCTURE: {e}.\nConsult reference/FORMAT.md before improvising.")
            failed = True
        except (etree.XMLSyntaxError, OSError) as e:
            print(f"NOT PARSEABLE AS XML: {e}")
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
