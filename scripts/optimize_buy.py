#!/usr/bin/env python3
"""Optimize a spot buy over the BUYABLE inventory of an avails file.

Usage:
  python3 optimize_buy.py <avails.xml> --config <params.toml> --out <buy.json>

Maximizes rating points for the configured demo subject to the buy rules in
the config. Uses the CBC integer-program solver (pulp) when available; a
greedy fallback exists only for legacy [shape]-style configs — generic
[[constraint]] rules require the ILP.
Never places a spot on a non-air day or an unrated cell.

Constraint system (see config/buy-parameters.template.toml for examples):
  [[constraint]] blocks scope a floor and/or cap onto a slice of inventory.
  Scope keys (all optional, AND-ed together; lists are any-of, matched
  case-insensitively; programs use * glob against program AND avail name):
      dayparts / stations / programs / dates / overnight / name (label)
  per = "station" | "daypart" | "date" applies the rule to EACH distinct
  value separately (e.g. a spend cap per station).
  metric = "spots" | "spend" | "points" | "spend_share" | "points_share"
  (shares are of the total budget / total points), with min= and/or max=.
  Idioms: must-buy = metric "spots" with min; exclusion = max = 0.
  [filters] min_rating / max_cpp_per_spot drop cells before optimizing.
Legacy [shape] keys (station_spend_cap, news_points_floor+news_dayparts,
overnight_spend_cap) are converted to equivalent constraints automatically.
"""
import sys, json, argparse, fnmatch
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from proposal_lib import parse, buyable_cells

METRICS = ('spots', 'spend', 'points', 'spend_share', 'points_share')
SCOPE_KEYS = ('dayparts', 'stations', 'programs', 'dates', 'overnight')
CON_KEYS = SCOPE_KEYS + ('name', 'per', 'metric', 'min', 'max')


def load_config(path):
    txt = open(path, 'rb').read()
    try:
        import tomllib
        return tomllib.loads(txt.decode())
    except ImportError:
        pass
    # minimal fallback parser for the template shapes (py < 3.11, no deps)
    cfg = {}
    section = cfg
    for raw in txt.decode().splitlines():
        s = raw.split('#', 1)[0].strip()
        if not s:
            continue
        if s.startswith('[['):
            section = {}
            cfg.setdefault(s.strip('[]'), []).append(section)
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


def in_scope(con, cell):
    if 'dayparts' in con and cell['daypart'].upper() not in {d.upper() for d in con['dayparts']}:
        return False
    if 'stations' in con and cell['station'].upper() not in {s.upper() for s in con['stations']}:
        return False
    if 'programs' in con and not any(
            fnmatch.fnmatch(cell['program'].upper(), p.upper())
            or fnmatch.fnmatch(cell['avail_name'].upper(), p.upper())
            for p in con['programs']):
        return False
    if 'dates' in con and cell['date'] not in con['dates']:
        return False
    if 'overnight' in con and bool(cell['overnight']) != bool(con['overnight']):
        return False
    return True


def normalize_constraints(cfg):
    """Legacy [shape] keys + explicit [[constraint]] blocks -> one list."""
    cons = []
    shape = cfg.get('shape', {})
    if 'station_spend_cap' in shape:
        cons.append({'name': 'station spend cap', 'per': 'station',
                     'metric': 'spend_share', 'max': shape['station_spend_cap']})
    if shape.get('news_points_floor'):
        cons.append({'name': 'news points floor',
                     'dayparts': shape.get('news_dayparts', []),
                     'metric': 'points_share', 'min': shape['news_points_floor']})
    if 'overnight_spend_cap' in shape:
        cons.append({'name': 'overnight spend cap', 'overnight': True,
                     'metric': 'spend_share', 'max': shape['overnight_spend_cap']})
    for i, c in enumerate(cfg.get('constraint', [])):
        c = dict(c)
        c.setdefault('name', f'constraint #{i + 1}')
        bad = [k for k in c if k not in CON_KEYS]
        if bad:
            sys.exit(f"ERROR: constraint {c['name']!r} has unknown key(s) {bad}. "
                     f"Allowed: {list(CON_KEYS)} (note plurals: dayparts, stations, programs, dates)")
        if c.get('metric') not in METRICS:
            sys.exit(f"ERROR: constraint {c['name']!r} needs metric = one of {METRICS}")
        if 'min' not in c and 'max' not in c:
            sys.exit(f"ERROR: constraint {c['name']!r} needs min = and/or max =")
        if 'min' in c and 'max' in c and c['min'] > c['max']:
            sys.exit(f"ERROR: constraint {c['name']!r} has min > max")
        if c.get('per') not in (None, 'station', 'daypart', 'date'):
            sys.exit(f"ERROR: constraint {c['name']!r}: per must be station, daypart, or date")
        cons.append(c)
    return cons


def expand_constraints(cons, cells):
    """Expand per= rules; attach member-cell index sets; police zero-match
    floors loudly (a floor over nothing is a vocabulary mistake, not a buy)."""
    out = []
    for con in cons:
        variants = [con]
        if con.get('per'):
            key = con['per']
            vals = sorted({c[key] for c in cells if in_scope(con, c)})
            variants = [{**{k: v for k, v in con.items() if k != 'per'},
                         'name': f"{con['name']} [{val}]",
                         {'station': 'stations', 'daypart': 'dayparts', 'date': 'dates'}[key]: [val]}
                        for val in vals]
        for v in variants:
            S = [i for i, c in enumerate(cells) if in_scope(v, c)]
            if not S and v.get('min', 0) > 0:
                vocab = {'dayparts in this file': sorted({c['daypart'] for c in cells}),
                         'stations': sorted({c['station'] for c in cells})}
                sys.exit(f"ERROR: constraint {v['name']!r} sets a floor but matches ZERO "
                         f"buyable cells — check the scope labels against the file.\n"
                         f"  {vocab}")
            if not S:
                print(f"note: constraint {v['name']!r} matches no buyable cells; cap is trivially satisfied")
            out.append({**v, 'members': S})
    return out


def apply_filters(cells, cfg):
    f = cfg.get('filters', {})
    kept, drop_r, drop_c = [], 0, 0
    for c in cells:
        if f.get('min_rating') and c['rating'] < float(f['min_rating']):
            drop_r += 1
            continue
        if f.get('max_cpp_per_spot') and c['rate'] / c['rating'] > float(f['max_cpp_per_spot']):
            drop_c += 1
            continue
        kept.append(c)
    if drop_r:
        print(f"filter min_rating={f['min_rating']}: dropped {drop_r} cells")
    if drop_c:
        print(f"filter max_cpp_per_spot=${f['max_cpp_per_spot']}: dropped {drop_c} cells")
    return kept


def summarize(cells, x, label):
    spots = sum(x)
    cost = sum(n * c['rate'] for n, c in zip(x, cells))
    pts = sum(n * c['rating'] for n, c in zip(x, cells))
    st, day = {}, {}
    for n, c in zip(x, cells):
        if n:
            st[c['station']] = st.get(c['station'], 0) + n * c['rate']
            day[c['date']] = day.get(c['date'], 0) + n
    print(f"\n=== BUY ({label}) ===")
    print(f"spots={spots}  spend=${cost:,.2f}  points={pts:,.1f}  CPP=${cost/pts:,.2f}" if pts else "no buy")
    print("spend by station:", {k: f"${v:,.0f} ({v/cost:.0%})" for k, v in sorted(st.items())})
    print("spots by day:", dict(sorted(day.items())))
    return spots, cost, pts


def achieved(con, cells, x, B, total_pts):
    S = con['members']
    if con['metric'] == 'spots':
        return sum(x[i] for i in S)
    if con['metric'] == 'spend':
        return sum(x[i] * cells[i]['rate'] for i in S)
    if con['metric'] == 'points':
        return sum(x[i] * cells[i]['rating'] for i in S)
    if con['metric'] == 'spend_share':
        return sum(x[i] * cells[i]['rate'] for i in S) / B
    if con['metric'] == 'points_share':
        return sum(x[i] * cells[i]['rating'] for i in S) / total_pts if total_pts else 0.0


def fmt(metric, v):
    return (f"{v:.1%}" if metric.endswith('_share')
            else f"${v:,.0f}" if metric == 'spend'
            else f"{v:,.1f}" if metric == 'points' else f"{int(v)}")


def report_constraints(cons, cells, x, B):
    if not cons:
        return
    total_pts = sum(n * c['rating'] for n, c in zip(x, cells))
    print("\nconstraints:")
    for con in cons:
        got = achieved(con, cells, x, B, total_pts)
        bounds = ' '.join(f"{b}={fmt(con['metric'], con[b])}" for b in ('min', 'max') if b in con)
        print(f"  {con['name']:<32} {con['metric']:<13} {bounds:<22} achieved={fmt(con['metric'], got)}")


def solve_ilp(cells, cfg, cons, dates):
    import time
    import pulp
    B = float(cfg['buy']['budget'])
    cap = int(cfg['buy']['max_spots_per_cell'])
    solver_cfg = cfg.get('solver', {})
    gap = float(solver_cfg.get('gap', 0.001))
    limit = int(solver_cfg.get('time_limit_s', 60))
    n = len(cells)
    prob = pulp.LpProblem('buy', pulp.LpMaximize)
    x = [pulp.LpVariable(f'x{i}', 0, cap, cat='Integer') for i in range(n)]
    prob += pulp.lpSum(x[i] * cells[i]['rating'] for i in range(n))
    prob += pulp.lpSum(x[i] * cells[i]['rate'] for i in range(n)) <= B
    for con in cons:
        S, m = con['members'], con['metric']
        if m == 'points_share':
            # share of TOTAL points is nonlinear as written; linearized:
            # sum(r_i x_i, i in S) >= fl * sum(r_i x_i, all)  <=>
            # sum(r_i x_i * (in_S - fl)) >= 0   (same trick for max)
            ins = set(S)
            if 'min' in con:
                prob += pulp.lpSum(x[i] * cells[i]['rating'] * ((1 if i in ins else 0) - con['min'])
                                   for i in range(n)) >= 0
            if 'max' in con:
                prob += pulp.lpSum(x[i] * cells[i]['rating'] * ((1 if i in ins else 0) - con['max'])
                                   for i in range(n)) <= 0
            continue
        if m == 'spots':
            expr, lo, hi = pulp.lpSum(x[i] for i in S), con.get('min'), con.get('max')
        elif m == 'spend':
            expr, lo, hi = pulp.lpSum(x[i] * cells[i]['rate'] for i in S), con.get('min'), con.get('max')
        elif m == 'points':
            expr, lo, hi = pulp.lpSum(x[i] * cells[i]['rating'] for i in S), con.get('min'), con.get('max')
        elif m == 'spend_share':
            expr = pulp.lpSum(x[i] * cells[i]['rate'] for i in S)
            lo = con['min'] * B if 'min' in con else None
            hi = con['max'] * B if 'max' in con else None
        if lo is not None:
            prob += expr >= lo
        if hi is not None:
            prob += expr <= hi
    if cfg['buy'].get('cover_every_day', True):
        for d in dates:
            prob += pulp.lpSum(x[i] for i in range(n) if cells[i]['date'] == d) >= 1
    # A tiny gap tolerance turns minutes of optimality-proving into
    # sub-second solves (measured: 180s -> 0.2s on a real 930-cell file,
    # points within 0.08%). Without it CBC burns the whole time limit
    # proving the last fraction of a percent.
    print(f"solving ILP: {n} cells, {len(cons)} constraints, gap <={gap:.1%}, time cap {limit}s ...")
    t0 = time.time()
    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=limit, gapRel=gap))
    wall = time.time() - t0
    status = pulp.LpStatus[prob.status]
    if status == 'Infeasible':
        sys.exit("ERROR: constraints are jointly INFEASIBLE — no buy satisfies all of:\n  "
                 + '\n  '.join(c['name'] for c in cons)
                 + "\nplus budget/coverage. Relax a floor, raise the budget, or loosen [filters], then rerun.")
    if status not in ('Optimal',):
        raise RuntimeError(f'solver status {status}')
    # CBC reports 'Optimal' even when stopped by the time limit with an
    # unproven incumbent, so label by what actually happened.
    if wall >= limit * 0.98:
        label = (f'ILP, time-capped at {limit}s -- best solution found, '
                 f'optimality NOT proven (raise [solver] time_limit_s to verify)')
    else:
        label = f'ILP, within {gap:.1%} of optimal ({wall:.1f}s)'
    return [int(round(v.value() or 0)) for v in x], label


def solve_greedy(cells, cfg, dates):
    """Legacy fallback: efficiency-sorted fill honoring [shape] rules only.
    NOT optimal, and it does NOT understand [[constraint]] blocks."""
    B = float(cfg['buy']['budget'])
    cap = int(cfg['buy']['max_spots_per_cell'])
    shape = cfg.get('shape', {})
    stcap = shape.get('station_spend_cap', 1.0) * B
    oncap = shape.get('overnight_spend_cap', 1.0) * B
    news_set = {d.upper() for d in shape.get('news_dayparts', [])}
    for c in cells:
        c['news'] = c['daypart'].upper() in news_set
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
    fl = shape.get('news_points_floor', 0)
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
    for w in inv['warnings']:
        print(f"WARNING: {w}")
    demo = pick_demo(inv, cfg.get('demo', {}).get('optimize_demo', 'target'))
    cells = list(buyable_cells(inv, demo))
    if not cells:
        sys.exit('ERROR: no buyable inventory (air-day + rated) in this file.')
    cells = apply_filters(cells, cfg)
    if not cells:
        sys.exit('ERROR: [filters] removed every buyable cell — loosen min_rating / max_cpp_per_spot.')
    dates = sorted(set(c['date'] for c in cells))
    print(f"buyable cells: {len(cells)} across {len(dates)} days; optimizing demo {inv['demos'][demo]!r}")
    cons = expand_constraints(normalize_constraints(cfg), cells)
    try:
        import pulp  # noqa: F401
        have_pulp = True
    except ImportError:
        have_pulp = False
    if have_pulp:
        x, label = solve_ilp(cells, cfg, cons, dates)
    elif cfg.get('constraint'):
        sys.exit('ERROR: [[constraint]] rules require the ILP solver.\n'
                 'Install it: python3 -m pip install pulp --break-system-packages')
    else:
        x, label = solve_greedy(cells, cfg, dates)
    spots, cost, pts = summarize(cells, x, label)
    report_constraints(cons, cells, x, float(cfg['buy']['budget']))
    buy = {f"{c['line']}|{c['date']}": n for n, c in zip(x, cells) if n > 0}
    json.dump({'method': label, 'demo': demo, 'config': cfg,
               'summary': {'spots': spots, 'spend': round(cost, 2),
                           'points': round(pts, 2)},
               'buy': buy}, open(a.out, 'w'))
    print(f"\nwrote {a.out} ({len(buy)} cells)")


if __name__ == '__main__':
    main()
