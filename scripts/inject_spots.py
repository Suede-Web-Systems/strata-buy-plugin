#!/usr/bin/env python3
"""Inject a buy plan into a Proposal XML file's OWN BYTES (edit-in-place).

Usage:
  python3 inject_spots.py <source.xml> <buy.json> <output.xml> [--name "New proposal name"]

Never re-serializes the document: it inserts <SpotsByDay> blocks (Strata's
element, Strata's position: after <Rate>, before <DemoValues>) into the raw
lines of the source file, regenerates the UniqueMessageID and sendDateTime,
and leaves every other byte untouched — so seller terms round-trip exactly.

Refuses to inject any spot that falls on a non-air day (Strata would
silently drop it).
"""
import sys, re, json, argparse, random, string, datetime
sys.path.insert(0, __file__.rsplit('/', 1)[0])
from proposal_lib import parse, spot_totals, WEEKDAYS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source')
    ap.add_argument('buy_json')
    ap.add_argument('output')
    ap.add_argument('--name')
    a = ap.parse_args()
    plan = json.load(open(a.buy_json))
    buy = {(int(k.split('|')[0]), k.split('|')[1]): v for k, v in plan['buy'].items()}

    # SAFETY GATE: no spot may land on a non-air day.
    inv = parse(a.source)
    lines_by_idx = {L['index']: L for L in inv['lines']}
    bad = []
    for (li, date), n in buy.items():
        L = lines_by_idx[li]
        wd = datetime.date.fromisoformat(date).weekday()
        pdates = {p['date'] for p in L['periods']}
        if date not in pdates:
            bad.append(f"line {li} ({L['avail_name']}): no rate period on {date}")
        elif not L['days'][wd]:
            bad.append(f"line {li} ({L['avail_name']}): {date} is a {WEEKDAYS[wd]}, not an air day ({''.join('MTWTFSS'[i] if f else '-' for i,f in enumerate(L['days']))})")
    if bad:
        print("REFUSING to inject — plan contains invalid spots Strata would drop:", file=sys.stderr)
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        sys.exit(1)

    raw = open(a.source, 'rb').read().decode('utf-8')
    crlf = '\r\n' if '\r\n' in raw else '\n'
    src_lines = raw.split(crlf)
    out, li, cur, ins, tot = [], -1, None, 0, 0
    for ln in src_lines:
        out.append(ln)
        s = ln.strip()
        if s.startswith('<AvailLineWithDetailedPeriods>'):
            li += 1
        m = re.match(r'<DayDetailedPeriod startDate="([0-9-]+)"', s)
        if m:
            cur = m.group(1)
        if s.startswith('<Rate>') and (li, cur) in buy:
            n = buy[(li, cur)]
            wd = datetime.date.fromisoformat(cur).weekday()
            indent = ln[:len(ln) - len(ln.lstrip('\t'))]
            out.append(indent + '<SpotsByDay>')
            for i, d in enumerate(WEEKDAYS):
                out.append(f'{indent}\t<{d}>{n if i == wd else 0}</{d}>')
            out.append(indent + '</SpotsByDay>')
            ins += 1
            tot += n
    if ins != len(buy):
        sys.exit(f"ERROR: inserted {ins} blocks but plan has {len(buy)} — source/plan mismatch, output NOT written.")
    text = crlf.join(out)
    guid = 'ID' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=52))
    text = re.sub(r'<UniqueMessageID>[^<]+</UniqueMessageID>',
                  f'<UniqueMessageID>{guid}</UniqueMessageID>', text, count=1)
    now = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    text = re.sub(r'sendDateTime="[^"]+"', f'sendDateTime="{now}"', text, count=1)
    if a.name:
        text = re.sub(r'(<Proposal uniqueIdentifier=")[^"]*(")', r'\g<1>' + a.name + r'\2', text, count=1)
        text = re.sub(r'<Name>[^<]*</Name>', f'<Name>{a.name}</Name>', text, count=1)
    open(a.output, 'wb').write(text.encode('utf-8'))

    # parse-back verification
    ts, td, ss, sd = spot_totals(parse(a.output))
    print(f"wrote {a.output}: {ins} blocks, {tot} spots")
    print(f"parse-back: {ts} spots ${td:,.2f}; predicted import survival {ss} spots ${sd:,.2f}")
    if ts != ss:
        sys.exit("ERROR: survival mismatch after write — do not send this file.")


if __name__ == '__main__':
    main()
