"""Route name-level SEC candidates to saved price evidence, without admission."""
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path


def build(root):
    paths=['tmp/bull_bear_membership_diagnostic_20261025_v1/sec_company_identity_leads.json',
           'tmp/github_history_routes_20261025/wiki_coverage.json',
           'tmp/github_history_routes_20261025/yahoo_foreign_probe/manifest.json']
    leads,wiki,yahoo=[json.loads((root/p).read_bytes()) for p in paths]
    coverage=wiki['coverage'];quotes={r['ticker']:r for r in yahoo}
    # Only query routes: no change to source members, issuer IDs or price units.
    routes={'GOOG':('GOOGL','OFFICIAL_CLASS_A_RENAME_LEAD'),
            'MNST':('MWW','OFFICIAL_MONSTER_WORLDWIDE_LEAD'),
            'ERTS':('EA','UNREVIEWED_SYMBOL_ROUTE'),
            'WFMI':('WFM','UNREVIEWED_SYMBOL_ROUTE'),
            'UAUA':('UAL','UNREVIEWED_MERGER_ROUTE'),
            'RIMM':('BB','UNREVIEWED_MARKET_AND_RENAME_ROUTE'),
            'JOYG':('JOY','UNREVIEWED_SYMBOL_ROUTE')}
    records=[]
    for lead in leads['rows']:
        ticker=lead['candidate_historical_ticker'];found=[]
        if ticker:
            query,kind=routes.get(ticker,(ticker,'SAME_LABEL_NOT_IDENTITY_CERTIFICATION'))
            record=coverage.get(query)
            if record and record['first']<='2007-09-30' and record['last']>='2006-12-01':
                found.append(dict(provider='WIKI',query=query,identity_route=kind,coverage=record))
            if query in quotes and quotes[query].get('rows',0):
                found.append(dict(provider='YAHOO',query=query,identity_route=kind,coverage=quotes[query]))
            for q in sorted({ticker,query}):
                path=root/'tmp/legacy_three_probe_20261025'/f'{q}.csv'
                if not path.exists():continue
                name=path.relative_to(root).as_posix();paths.append(name)
                finite=[]
                with path.open(encoding='utf-8-sig') as stream:
                    for row in csv.DictReader(stream):
                        try:valid=all(Decimal(row[k]).is_finite() and Decimal(row[k])>0 for k in ('Open','High','Low','Close'))
                        except (InvalidOperation,KeyError):valid=False
                        if valid:finite.append(row['Date'])
                finite.sort()
                if finite and finite[0]<='2007-09-30' and finite[-1]>='2006-12-01':
                    found.append(dict(provider='QSTK',query=q,identity_route=kind,source=name,
                        finite_first=finite[0],finite_last=finite[-1],finite_window_rows=sum('2007-01-01'<=d<='2009-12-31' for d in finite)))
        records.append(dict(lead,price_routes=found,price_admitted=False))
    return dict(status='NOT_ADMITTED',scope='SEC 2007-09-30 name candidates, not old 135-label universe',
                sources={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in sorted(set(paths))},
                records=records,no_candidate_route=[r['candidate_historical_ticker'] for r in records if r['candidate_historical_ticker'] and not r['price_routes']],
                limitations=['Availability is not full interval coverage','All identity, price unit, corporate action and index eligibility admission remains pending',
                             'Old MNST must never use beverage MNST history','Novellus/NVIDIA unresolved row is retained with no ticker'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=build(args.root)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(dict(records=len(result['records']),no_candidate_route=result['no_candidate_route'])))
