#!/usr/bin/env python3
"""Parse and summarize a Proposal XML avails/schedule file.

Usage:
  python3 parse_avails.py <file.xml> [--json OUT.json]

Prints a market summary (stations, flight, demos, daypart vocabulary,
per-station inventory, and buyable vs phantom counts). With --json, also
writes the full structured inventory for downstream tools.

JSON shape (all downstream tools consume this, not the XML):
  { proposal: {id, name, start, end, week_start_day, advertiser, survey},
    stations: [callLetters...],
    demos: {demoRef: label}, target_demo: demoRef, warnings: [str...],
    lines: [ {index, station, daypart, avail_name, program, start_time,
              end_time, overnight, days: [7 bools Mon..Sun],
              periods: [ {date, end_date, weekday (0=Mon), rate,
                          ratings: {demoRef: float}, air_day: bool,
                          spots: [7 ints Mon..Sun] | null} ]} ] }
"""
import sys, json, argparse
from collections import Counter
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from proposal_lib import parse, buyable_cells, spot_totals, FormatError


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml')
    ap.add_argument('--json')
    a = ap.parse_args()
    try:
        inv = parse(a.xml)
    except FormatError as e:
        sys.exit('UNSUPPORTED FILE STRUCTURE: %s.\n'
                 'Consult reference/FORMAT.md before improvising.' % e)
    for w in inv['warnings']:
        print('WARNING: %s' % w)
    pr = inv['proposal']
    n_periods = sum(len(L['periods']) for L in inv['lines'])
    if n_periods == 0:
        sys.exit('No rate periods found: file parsed but carries no '
                 'day-detailed periods. Consult reference/FORMAT.md.')
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
    n_zero = n_air - len(cells)
    zero_d = sum(2 * p['rate'] for L in inv['lines'] for p in L['periods']
                 if p['air_day'] and p['ratings'].get(inv['target_demo'], 0.0) <= 0)
    print(f"  on-air but 0.0 target rating: {n_zero}  (${zero_d:,.0f} at 2 spots/cell; "
          f"excluded from buyable -- deliberate, e.g. cheap overnights the survey doesn't measure)")

    st = {}
    for L in inv['lines']:
        st.setdefault(L['station'], {'lines': 0, 'buyable': 0, 'phantom': 0,
                                     'zero': 0, 'rates': []})
        st[L['station']]['lines'] += 1
    for L in inv['lines']:
        for p in L['periods']:
            e = st[L['station']]
            if not p['air_day']:
                e['phantom'] += 1
            elif p['ratings'].get(inv['target_demo'], 0.0) <= 0:
                e['zero'] += 1
            else:
                e['buyable'] += 1
                e['rates'].append(p['rate'])
    print(f"\n{'station':<9}{'lines':>6}{'buyable':>9}{'phantom':>9}{'0-rated':>9}"
          f"{'min rate':>10}{'avg rate':>10}{'max rate':>10}")
    for k in sorted(st):
        e = st[k]
        r = e['rates'] or [0]
        print(f"{k:<9}{e['lines']:>6}{e['buyable']:>9}{e['phantom']:>9}{e['zero']:>9}"
              f"{min(r):>10,.0f}{sum(r)/len(r):>10,.0f}{max(r):>10,.0f}")

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
