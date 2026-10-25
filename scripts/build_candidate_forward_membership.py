"""Unadmitted forward member queue; unresolved identities remain explicit."""
import argparse
import calendar
import hashlib
import json
from datetime import date
from pathlib import Path


def build(anchor,events):
    source=json.loads(anchor.read_bytes());queue=json.loads(events.read_bytes())
    anchor_day=source['asof']
    def canonical(value):
        if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:
            raise ValueError('CANONICAL_ISO_DATE_REQUIRED')
        return value
    canonical(anchor_day)
    labels=[r['candidate_historical_ticker'] or 'UNRESOLVED_SEC_NOVELLUS_NVDA' for r in source['rows']]
    if len(labels)!=100 or len(set(labels))!=100:
        raise ValueError('ANCHOR_MUST_HAVE_100_DISTINCT_RECORDS')
    days=[canonical(e['date']) for e in queue['events']]
    if days!=sorted(set(days)) or any(day<=anchor_day for day in days):
        raise ValueError('EVENT_DATES_MUST_STRICTLY_FOLLOW_ANCHOR')
    members=set(labels)
    timeline=[];blockers=['ANCHOR_NOT_INDEX_CERTIFIED','SEC_NOVELLUS_NVDA_IDENTITY_CONFLICT']
    initial=dict(date=anchor_day,members=sorted(members),blockers=list(blockers),admitted=False)
    for event in queue['events']:
        if event['review']!='OFFICIAL_EVENT_MATCH':blockers.append('UNVERIFIED_EVENT:'+event['date'])
        missing=set(event['removed'])-members;duplicates=set(event['added'])&members
        if missing or duplicates:raise ValueError('EVENT_DOMAIN_CONFLICT:'+event['date'])
        members-=set(event['removed']);members|=set(event['added'])
        timeline.append(dict(date=event['date'],members=sorted(members),blockers=list(blockers),admitted=False))
    monthly=[]
    for year,months in [(2007,range(10,13)),(2008,range(1,13))]:
        for month in months:
            day=f'{year}-{month:02}-{calendar.monthrange(year,month)[1]:02}'
            state=([r for r in timeline if r['date']<=day] or [initial])[-1]
            monthly.append(dict(calendar_month_end=day,decision_session=None,members=state['members'],
                                blockers=state['blockers'],admitted=False))
    return dict(status='NOT_ADMITTED',sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (anchor,events)},
                timeline=timeline,monthly=monthly,limitations=['Calendar month end is not a trading decision date',
                'Provisional events preserved with blockers, never silently admitted','No corporate action or price eligibility inferred'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('anchor','events','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x',encoding='utf-8') as stream:json.dump(build(args.anchor,args.events),stream,indent=2)
