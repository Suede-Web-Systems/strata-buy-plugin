#!/usr/bin/env python3
"""Validate a SpotTVCableProposal XML file against Suede's inferred schema,
plus Strata-convention checks that XSD cannot express.

Usage: python3 validate_proposal.py <file.xml> [more.xml ...]
Exit code 0 = all files pass XSD validation (warnings don't fail the run).
"""
import sys, os
from lxml import etree

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'schema')
NSP = 'http://www.AAAA.org/schemas/spotTVCableProposal'
NS = {'p': NSP}

def convention_warnings(path, tree):
    w = []
    raw = open(path, 'rb').read()
    if b'\r\n' not in raw:
        w.append("no CRLF line endings (Strata VIEW emits CRLF; unconfirmed whether required)")
    if b"<?xml version='1.0'" in raw[:60]:
        w.append("single-quoted XML declaration (Strata emits double quotes; unconfirmed whether required)")
    root = tree.getroot()
    for e in root.iter('{%s}DayDetailedPeriod' % NSP):
        kids = [c.tag.split('}')[-1] for c in e]
        if 'NumberOfSpots' in kids:
            w.append("uses <NumberOfSpots> — Strata emits <SpotsByDay>; a file using NumberOfSpots was REJECTED by Strata on 2026-08-11")
            break
        if 'SpotsByDay' in kids and kids.index('SpotsByDay') > kids.index('DemoValues'):
            w.append("<SpotsByDay> appears after <DemoValues> — Strata emits it before")
            break
    for e in root.iter('{%s}SpotsByDay' % NSP):
        if all(c.text == '0' for c in e):
            w.append("all-zero <SpotsByDay> block found — Strata omits the block entirely for unbought days")
            break
    # referential integrity
    outlets = {o.get('outletId') for o in root.iter('{%s}TelevisionStation' % NSP)}
    demos = {d.get('DemoId') for d in root.iter('{%s}DemoCategory' % NSP)}
    listids = set()
    for o in root.iter('{%s}OutletReference' % NSP):
        if o.get('outletFromProposalRef') is not None:
            if o.get('outletFromProposalRef') not in outlets:
                w.append(f"OutletReference points to missing outletId {o.get('outletFromProposalRef')}")
            listids.add(o.get('outletForListId'))
        elif o.get('outletFromListRef') is not None and o.get('outletFromListRef') not in listids:
            w.append(f"avail line references missing outletForListId {o.get('outletFromListRef')}")
    for dv in root.iter('{%s}DemoValue' % NSP):
        if dv.get('demoRef') not in demos:
            w.append(f"DemoValue references missing DemoId {dv.get('demoRef')}")
            break
    # AIR-DAY CHECK (added 2026-08-18 after TEST-B): Strata silently DROPS any spot
    # placed on a weekday whose <Days> flag is 'N' on that avail line. Confirmed
    # empirically: 330/330 non-air-day spots dropped, 344/344 air-day spots kept.
    import datetime
    TP = 'http://www.AAAA.org/schemas/TVBGeneralTypes'
    bad = 0
    ex = None
    for line in root.iter('{%s}AvailLineWithDetailedPeriods' % NSP):
        daysel = line.find('{%s}DayTimes/{%s}DayTime/{%s}Days' % (NSP, NSP, NSP))
        if daysel is None:
            continue
        flags = [c.text == 'Y' for c in daysel]  # Mon..Sun
        for pd in line.iter('{%s}DayDetailedPeriod' % NSP):
            sb = pd.find('{%s}SpotsByDay' % NSP)
            if sb is None:
                continue
            counts = [int(c.text) for c in sb]
            for i, n in enumerate(counts):
                if n > 0 and not flags[i]:
                    bad += n
                    if ex is None:
                        name = line.findtext('{%s}AvailName' % NSP)
                        ex = f"{name} {pd.get('startDate')}"
            wd = datetime.date.fromisoformat(pd.get('startDate')).weekday()
            for i, n in enumerate(counts):
                if n > 0 and i != wd and pd.get('startDate') == pd.get('endDate'):
                    w.append(f"spot weekday does not match period date ({pd.get('startDate')})")
                    break
    if bad:
        w.append(f"{bad} spot(s) placed on non-air days (Days flag = N) — Strata WILL silently drop these (e.g. {ex})")
    return w

def main():
    schema = etree.XMLSchema(etree.parse(os.path.join(HERE, 'spotTVCableProposal.xsd')))
    failed = False
    for path in sys.argv[1:]:
        tree = etree.parse(path)
        ok = schema.validate(tree)
        print(f"{'PASS' if ok else 'FAIL'}  {os.path.basename(path)}")
        if not ok:
            failed = True
            for err in schema.error_log[:10]:
                print(f"      line {err.line}: {err.message}")
        for warn in convention_warnings(path, tree):
            print(f"      WARN: {warn}")
    sys.exit(1 if failed else 0)

if __name__ == '__main__':
    main()
