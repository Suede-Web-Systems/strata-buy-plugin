"""Shared parsing library for AAAA SpotTVCableProposal ("Proposal XML") files.

All strata-buy scripts import from here so format knowledge lives in one place.
Broadcast-day clock: times run 05:00-29:59; hour >= 24 means after midnight
(the small hours of the NEXT calendar day). Period dates are calendar dates;
a spot is valid only if its date's weekday is flagged 'Y' in the line's <Days>.
"""
import datetime
from lxml import etree

P  = 'http://www.AAAA.org/schemas/spotTVCableProposal'
TVB = 'http://www.AAAA.org/schemas/spotTV'
TP = 'http://www.AAAA.org/schemas/TVBGeneralTypes'
NS = {'p': P, 'tvb': TVB, 'tp': TP}
WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def parse(path):
    """Parse a Proposal XML file into a plain-dict inventory."""
    root = etree.parse(str(path)).getroot()
    pr = root.find('p:Proposal', NS)
    al = pr.find('p:AvailList', NS)
    outlets = {o.get('outletId'): o.get('callLetters')
               for o in pr.findall('p:Outlets/p:TelevisionStation', NS)}
    listref = {o.get('outletForListId'): outlets[o.get('outletFromProposalRef')]
               for o in al.findall('p:OutletReferences/p:OutletReference', NS)}
    demos = {}
    for d in al.findall('p:DemoCategories/p:DemoCategory', NS):
        demos[d.get('DemoId')] = '%s %s-%s (%s)' % (
            d.findtext('tvb:Group', '', NS), d.findtext('tvb:AgeFrom', '', NS),
            d.findtext('tvb:AgeTo', '', NS), d.findtext('tvb:DemoType', '', NS))
    target_demo = al.find('p:TargetDemo', NS).get('demoRef')

    lines = []
    for li, L in enumerate(al.findall('p:AvailLineWithDetailedPeriods', NS)):
        dt = L.find('p:DayTimes/p:DayTime', NS)
        flags = [c.text == 'Y' for c in L.find('p:DayTimes/p:DayTime/p:Days', NS)]
        start = dt.findtext('p:StartTime', '', NS)
        periods = []
        for pd in L.findall('p:Periods/p:DayDetailedPeriod', NS):
            date = pd.get('startDate')
            wd = datetime.date.fromisoformat(date).weekday()
            sb = pd.find('p:SpotsByDay', NS)
            ratings = {dv.get('demoRef'): float(dv.text or 0)
                       for dv in pd.findall('p:DemoValues/p:DemoValue', NS)}
            periods.append({
                'date': date,
                'end_date': pd.get('endDate'),
                'weekday': wd,
                'rate': float(pd.findtext('p:Rate', '0', NS)),
                'ratings': ratings,
                'air_day': flags[wd],
                'spots': [int(c.text) for c in sb] if sb is not None else None,
            })
        lines.append({
            'index': li,
            'station': listref[L.find('p:OutletReference', NS).get('outletFromListRef')],
            'daypart': L.findtext('p:DaypartName', '', NS),
            'avail_name': L.findtext('p:AvailName', '', NS),
            'program': dt.findtext('p:ProgramName', '', NS),
            'start_time': start,
            'end_time': dt.findtext('p:EndTime', '', NS),
            'overnight': int(start[:2]) >= 24,
            'days': flags,
            'periods': periods,
        })
    return {
        'proposal': {
            'id': pr.get('uniqueIdentifier'), 'name': pr.findtext('p:Name', '', NS),
            'start': pr.get('startDate'), 'end': pr.get('endDate'),
            'week_start_day': pr.get('weekStartDay'),
            'advertiser': pr.find('p:Advertiser', NS).get('name'),
            'survey': al.findtext('p:Name', '', NS),
        },
        'stations': sorted(set(outlets.values())),
        'demos': demos,
        'target_demo': target_demo,
        'lines': lines,
    }


def buyable_cells(inv, demo_ref=None):
    """Yield (line_index, date, station, rate, rating, is_news_fn-agnostic dict)
    for cells that are actually purchasable: the period exists, falls on a
    flagged air day, and carries a positive rating for the chosen demo."""
    demo_ref = demo_ref or inv['target_demo']
    for L in inv['lines']:
        for pd in L['periods']:
            if not pd['air_day']:
                continue
            rating = pd['ratings'].get(demo_ref, 0.0)
            if rating <= 0:
                continue
            yield {
                'line': L['index'], 'date': pd['date'], 'station': L['station'],
                'rate': pd['rate'], 'rating': rating,
                'daypart': L['daypart'], 'overnight': L['overnight'],
            }


def spot_totals(inv):
    """(spots, dollars) currently carried in the file, and the subset that
    would SURVIVE Strata's air-day drop rule."""
    tot_s = tot_d = ok_s = ok_d = 0
    for L in inv['lines']:
        for pd in L['periods']:
            if not pd['spots']:
                continue
            for i, n in enumerate(pd['spots']):
                if n > 0:
                    tot_s += n
                    tot_d += n * pd['rate']
                    if L['days'][i] and i == pd['weekday']:
                        ok_s += n
                        ok_d += n * pd['rate']
    return tot_s, tot_d, ok_s, ok_d
