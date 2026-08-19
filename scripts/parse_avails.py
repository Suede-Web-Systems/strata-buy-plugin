#!/usr/bin/env python3
"""Parse and summarize a Proposal XML avails/schedule file.

Usage:
  python3 parse_avails.py <file.xml> [--json OUT.json]

Prints a market summary (stations, flight, demos, daypart vocabulary, and
buyable vs phantom inventory). With --json, also writes the full structured
inventory for downstream tools.
"""
import sys, json, argparse
from collections import Counter
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from proposal_lib import parse, buyable_cells, spot_totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml')
    ap.add_argument('--json')
    a = ap.parse_args()
    inv = parse(a.xml)
    pr = inv['proposal']
    n_periods = sum(len(L['periods']) for L in inv['lines'])
    cells = list(buyable_cells(inv))
    n_air = sum(1 for L in inv['lines'] for p in L['periods'] if p['air_day'])
    max_inv = sum(2 * c['rate'] for c in cells)

    print(f"Proposal: {pr['id']!r}  |  {pr['advertiser']}  |  flight {pr['start']} .. {pr['end']} (week starts {pr['week_start_day']})")
    print(f"Survey:   {pr['survey']}")
    print(f"Stations ({len(inv['stations'])}): {', '.join(inv['stations'])}")
    print(f"Demos: target={inv['demos'].get(inv['target_demo'])}  |  panel: {', '.join(inv['demos'].values())}")
    print(f"\nAvail lines: {len(inv['lines'])}   rate periods: {n_periods}")
    print(f"  on air days:        {n_air}  ({n_air/n_periods:.0%})")
    print(f"  PHANTOM (non-air):  {n_periods-n_air}  ({(n_periods-n_air)/n_periods:.0%})  <- Strata silently drops spots placed here")
    print(f"  buyable (air day + rated): {len(cells)}   max inventory at 2 spots/cell: ${max_inv:,.0f}")
    dp = Counter()
    for L in inv['lines']:
        dp[(L['station'], L['daypart'])] += 1
    vocab = Counter(d for (_, d) in dp)
    print(f"\nDaypart vocabulary ({len(vocab)} labels): {dict(vocab.most_common())}")
    ts, td, ss, sd = spot_totals(inv)
    if ts:
        print(f"\nFile already carries spots: {ts} (${td:,.2f}); predicted to survive import: {ss} (${sd:,.2f})")
    if a.json:
        json.dump(inv, open(a.json, 'w'))
        print(f"\nwrote {a.json}")


if __name__ == '__main__':
    main()
