"""Build unadmitted membership intervals and quote extraction requirements."""
import argparse
import csv
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path


def prepare(source):
    rows = list(csv.DictReader(source.read_text(encoding='utf-8-sig').splitlines()))
    dates = [r['date'] for r in rows]
    if dates != sorted(set(dates)):
        raise ValueError('UNSORTED_OR_DUPLICATE_EFFECTIVE_DATES')
    start, end = '2007-12-01', '2010-12-31'
    intervals = []
    for index, row in enumerate(rows):
        until = (date.fromisoformat(rows[index+1]['date'])-timedelta(days=1)).isoformat() if index+1 < len(rows) else end
        if row['date'] > end or until < start:
            continue
        labels = row['tickers'].split(',')
        if len(labels) != len(set(labels)):
            raise ValueError('DUPLICATE_MEMBER_LABEL')
        for ticker in labels:
            intervals.append(dict(ticker=ticker, start=max(start,row['date']), end=min(end,until),
                                  source_effective_date=row['date']))
    labels = sorted({r['ticker'] for r in intervals})
    query_only = ['SYMC','QQQQ','QQQ','SPY','MNST','BB','LINTA','LINTB','NWSA','NWS','NUAN']
    return dict(status='NOT_ADMITTED', source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                diagnostic_range=dict(start=start,end=end), memberships=intervals,
                member_labels=labels, query_only_labels=query_only,
                extract_tickers=sorted(set(labels+query_only)),
                extract_start='2006-12-01', extract_end='2011-01-10',
                decisions=[], sessions=[], identities=[],
                decision_schema='Actual last exchange session of each month from December 2007 through November 2010; derive only after calendar evidence review',
                blockers=['Community reconstruction may apply modern labels to historical members',
                          'No security identity is inferred from matching symbols',
                          'Calendar and monthly decisions not yet authenticated',
                          'Range is diagnostic only, not final evaluation interval'],
                economic_searches=0)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(prepare(args.source),stream,ensure_ascii=False,indent=2)
