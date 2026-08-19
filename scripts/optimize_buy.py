#!/usr/bin/env python3
"""Optimize a spot buy over the BUYABLE inventory of an avails file.

Usage:
  python3 optimize_buy.py <avails.xml> --config <params.toml> --out <buy.json>

Maximizes rating points for the configured demo subject to the buy-shape
rules in the config. Uses the CBC integer-program solver (pulp) when
available; otherwise falls back to a labeled greedy heuristic.
Never places a spot on a non-air day or an unrated cell.
"""
import sys, json, argparse
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from proposal_lib import parse, buyable_cells


def load_config(path):
    txt = open(path, 'rb').read()
    try:
        import tomllib
        return tomllib.loads(txt.decode())
    except ImportError:
        pass
    # minimal fallback parser for the flat template (py < 3.11, no deps)
    cfg = {}
    section = cfg
    for raw in txt.decode().splitlines():
        s = raw.split('#', 1)[0].strip()
        if not s:
            continue
        if s.startswith('['):
            section = cfg.setdefault(s.strip('[]'), {})
            continue
        k, v = [x.strip() for x in s.split('=', 1)]
        if v.startswith('['):
            section[k] = [x.strip().strip('"\'') for x in v.strip('[]').split(',') if x.strip()]
        elif v in ('true', 'false'):
            section[k] = v == 'true'
        elif v.startswith(('"', "'")):
            section[k] = v.strip('"\'')
        else:
            section[k] = float(v) if '.' in v else int(v)
    return cfg


def pick_demo(inv, want):
    if want in (None, '', 'target'):
        return inv['target_demo']
    for ref, label in inv['demos'].items():
        if want.lower().replace(' ', '') in label.lower().replace(' ', ''):
            return ref
    sys.exit(f"ERROR: demo {want!r} not found. File carries: {list(inv['demos'].values())}")


def summarize(cells, x, label):
    spots = sum(x)
    cost = sum(n * c['rate'] for n, c in zip(x, cells))
    pts = sum(n * c['rating'] for n, c in zip(x, cells))
    news = sum(n * c['rating'] for n, c in zip(x, cells) if c['news'])
    on = sum(n * c['rate'] for n, c in zip(x, cells) if c['overnight'])
    st, day = {}, {}
    for n, c in zip(x, cells):
        if n:
            st[c['station']] = st.get(c['station'], 0) + n * c['rate']
            day[c['date']] = day.get(c['date'], 0) + n
    print(f"\n=== BUY ({label}) ===")
    print(f"spots={spots}  spend=${cost:,.2f}  points={pts:,.1f}  CPP=${cost/pts:,.2f}" if pts else "no buy")
    print(f"news share of points: {news/pts:.1%}" if pts else "")
    print(f"overnight spend: ${on:,.0f} ({on/cost:.1%})" if cost else "")
    print("spend by station:", {k: f"${v:,.0f} ({v/cost:.0%})" for k, v in sorted(st.items())})
    print("spots by day:", dict(sorted(day.items())))
    return spots, cost, pts


def solve_ilp(cells, cfg, dates):
    import time
    import pulp
    B = float(cfg['buy']['budget'])
    cap = int(cfg['buy']['max_spots_per_cell'])
    solver_cfg = cfg.get('solver', {})
    gap = float(solver_cfg.get('gap', 0.001))
    limit = int(solver_cfg.get('time_limit_s', 60))
    prob = pulp.LpProblem('buy', pulp.LpMaximize)
    x = [pulp.LpVariable(f'x{i}', 0, cap, cat='Integer') for i in range(len(cells))]
    prob += pulp.lpSum(x[i] * cells[i]['rating'] for i in range(len(cells)))
    prob += pulp.lpSum(x[i] * cells[i]['rate'] for i in range(len(cells))) <= B
    for s in set(c['station'] for c in cells):
        prob += pulp.lpSum(x[i] * cells[i]['rate'] for i in range(len(cells))
                           if cells[i]['station'] == s) <= cfg['shape']['station_spend_cap'] * B
    fl = cfg['shape']['news_points_floor']
    prob += pulp.lpSum(x[i] * cells[i]['rating'] * ((1 if cells[i]['news'] else 0) - fl)
                       for i in range(len(cells))) >= 0
    prob += pulp.lpSum(x[i] * cells[i]['rate'] for i in range(len(cells))
                       if cells[i]['overnight']) <= cfg['shape']['overnight_spend_cap'] * B
    if cfg['buy'].get('cover_every_day', True):
        for d in dates:
            prob += pulp.lpSum(x[i] for i in range(len(cells)) if cells[i]['date'] == d) >= 1
    # A tiny gap tolerance turns minutes of optimality-proving into
    # sub-second solves (measured: 180s -> 0.2s on a real 930-cell file,
    # points within 0.08%). Without it CBC burns the whole time limit
    # proving the last fraction of a percent.
    print(f"solving ILP: {len(cells)} cells, gap <={gap:.1%}, time cap {limit}s ...")
    t0 = time.time()
    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=limit, gapRel=gap))
    wall = time.time() - t0
    if pulp.LpStatus[prob.status] not in ('Optimal',):
        raise RuntimeError(f'solver status {pulp.LpStatus[prob.status]}')
    # CBC reports 'Optimal' even when stopped by the time limit with an
    # unproven incumbent, so label by what actually happened.
    if wall >= limit * 0.98:
        label = (f'ILP, time-capped at {limit}s -- best solution found, '
                 f'optimality NOT proven (raise [solver] time_limit_s to verify)')
    else:
        label = f'ILP, within {gap:.1%} of optimal ({wall:.1f}s)'
    return [int(round(v.value() or 0)) for v in x], label


def solve_greedy(cells, cfg, dates):
    """Fallback: efficiency-sorted fill with cap/floor repairs. NOT optimal."""
    B = float(cfg['buy']['budget'])
    cap = int(cfg['buy']['max_spots_per_cell'])
    stcap = cfg['shape']['station_spend_cap'] * B
    oncap = cfg['shape']['overnight_spend_cap'] * B
    x = [0] * len(cells)
    spend = 0.0
    st = {}
    on = 0.0
    order = sorted(range(len(cells)), key=lambda i: -cells[i]['rating'] / cells[i]['rate'])

    def can(i):
        c = cells[i]
        return (x[i] < cap and spend + c['rate'] <= B
                and st.get(c['station'], 0) + c['rate'] <= stcap
                and (not c['overnight'] or on + c['rate'] <= oncap))

    def add(i):
        nonlocal spend, on
        c = cells[i]
        x[i] += 1
        spend += c['rate']
        st[c['station']] = st.get(c['station'], 0) + c['rate']
        if c['overnight']:
            on += c['rate']

    # day coverage first
    if cfg['buy'].get('cover_every_day', True):
        for d in dates:
            for i in order:
                if cells[i]['date'] == d and can(i):
                    add(i)
                    break
    # news floor: prioritize news until floor holds throughout the fill
    fl = cfg['shape']['news_points_floor']
    for i in order:
        while can(i):
            pts = sum(x[j] * cells[j]['rating'] for j in range(len(cells)))
            news = sum(x[j] * cells[j]['rating'] for j in range(len(cells)) if cells[j]['news'])
            if not cells[i]['news'] and pts and (news + 0.0) / (pts + cells[i]['rating']) < fl:
                # adding non-news would break the floor; try news instead
                cand = next((k for k in order if cells[k]['news'] and can(k)), None)
                if cand is None:
                    break
                add(cand)
                continue
            add(i)
    return x, 'greedy fallback — NOT guaranteed optimal (pulp/CBC unavailable)'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xml')
    ap.add_argument('--config', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    cfg = load_config(a.config)
    inv = parse(a.xml)
    demo = pick_demo(inv, cfg.get('demo', {}).get('optimize_demo', 'target'))
    news_set = set(cfg['shape']['news_dayparts'])
    cells = []
    for c in buyable_cells(inv, demo):
        c['news'] = c['daypart'] in news_set
        cells.append(c)
    if not cells:
        sys.exit('ERROR: no buyable inventory (air-day + rated) in this file.')
    dates = sorted(set(c['date'] for c in cells))
    print(f"buyable cells: {len(cells)} across {len(dates)} days; optimizing demo {inv['demos'][demo]!r}")
    try:
        x, label = solve_ilp(cells, cfg, dates)
    except Exception as e:
        print(f"[ILP unavailable: {e}] using greedy fallback", file=sys.stderr)
        x, label = solve_greedy(cells, cfg, dates)
    spots, cost, pts = summarize(cells, x, label)
    buy = {f"{c['line']}|{c['date']}": n for n, c in zip(x, cells) if n > 0}
    json.dump({'method': label, 'demo': demo, 'config': cfg,
               'summary': {'spots': spots, 'spend': round(cost, 2),
                           'points': round(pts, 2)},
               'buy': buy}, open(a.out, 'w'))
    print(f"\nwrote {a.out} ({len(buy)} cells)")


if __name__ == '__main__':
    main()
