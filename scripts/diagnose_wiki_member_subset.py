"""Diagnose real WIKI subset against all declared historical member labels."""
import argparse
import csv
import hashlib
import json
from fractions import Fraction
from pathlib import Path


def diagnose(requirements, subset):
    request=json.loads(requirements.read_bytes())
    prices={}; invalid=[]; duplicates=[]; splits=[]; dividends=[]
    with subset.open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            ticker,day=row['ticker'],row['date']
            series=prices.setdefault(ticker,{})
            if day in series: duplicates.append([ticker,day])
            series[day]=row
            try:
                opening,high,low,close=[Fraction(row[k]) for k in ('open','high','low','close')]
                valid=0<low<=min(opening,close)<=max(opening,close)<=high
            except (ValueError,ZeroDivisionError):valid=False
            if not valid:invalid.append([ticker,day])
            if Fraction(row['split_ratio'])!=1:splits.append(dict(ticker=ticker,date=day,ratio=row['split_ratio']))
            if Fraction(row['ex-dividend'])!=0:dividends.append(dict(ticker=ticker,date=day,amount=row['ex-dividend']))
    reference=('AAPL','MSFT','INTC')
    if any(not prices.get(t) for t in reference):
        raise ValueError('MISSING_REFERENCE_SERIES')
    sets=[set(prices[t]) for t in reference]
    days=sorted(set.union(*sets))
    months={}
    for day in days:
        if '2007-12'<=day[:7]<='2010-11':months[day[:7]]=day
    decisions=sorted(months.values())
    missing_by_security={ticker:sorted(set(days)-set(prices.get(ticker,{}))) for ticker in request['member_labels']}
    windows=[]
    for decision in decisions:
        index=days.index(decision)
        training=days[max(0,index-252):index+1]
        members=sorted({m['ticker'] for m in request['memberships'] if m['start']<=decision<=m['end']})
        gaps={t:[d for d in training if d not in prices.get(t,{})] for t in members}
        windows.append(dict(date=decision,training_sessions=len(training),members=members,
                            incomplete={t:d for t,d in gaps.items() if d},complete_label_count=sum(not d for d in gaps.values())))
    return dict(status='NOT_ADMITTED',sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (requirements,subset)},
                candidate_calendar=dict(reference_labels=list(reference),reference_date_sets_equal=all(s==sets[0] for s in sets),
                    dates=days,certified=False),decisions=decisions,windows=windows,
                absent_member_labels=[t for t in request['member_labels'] if t not in prices],
                missing_dates_by_member=missing_by_security,invalid_ohlc=invalid,duplicate_rows=duplicates,
                split_events=splits,dividend_events=dividends,
                limitations=['Calendar is a three-stock date union, not authenticated exchange calendar',
                    'Same ticker is not admitted security identity; no alias substitution applied',
                    'Nominal OHLC unit and corporate action accuracy remain unreviewed',
                    'All member labels retained; absence is not an eligibility exclusion'],economic_searches=0)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('requirements','subset','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=diagnose(args.requirements,args.subset)
    with args.output.open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    print(json.dumps(dict(decisions=len(result['decisions']),sessions=len(result['candidate_calendar']['dates']),
        absent_members=len(result['absent_member_labels']),invalid_ohlc=len(result['invalid_ohlc']),
        duplicate_rows=len(result['duplicate_rows']),splits=len(result['split_events']),dividends=len(result['dividend_events']),
        reference_date_sets_equal=result['candidate_calendar']['reference_date_sets_equal'],
        first_window={k:v for k,v in result['windows'][0].items() if k not in ('members','incomplete')},
        last_window={k:v for k,v in result['windows'][-1].items() if k not in ('members','incomplete')})))
