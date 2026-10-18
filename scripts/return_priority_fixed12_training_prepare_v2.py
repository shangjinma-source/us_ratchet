"""Attach whole saved quote sources; block unaudited decision-unit costs."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import return_priority_fixed12_training_prepare as previous

ROOT = previous.ROOT
CAPTURE = 'tmp/fixed12_missing_quote_capture_20261014_v1'


def prepare():
    result = previous.prepare()
    pins = result['source_hashes']
    pins[str(Path(previous.__file__).resolve())] = hashlib.sha256(Path(previous.__file__).read_bytes()).hexdigest()
    cache = {}

    def read(name, expected=None):
        raw = (ROOT/name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if expected and digest != expected:
            raise ValueError('Changed source: '+name)
        pins[name] = digest
        return raw

    def quote(ticker, supplemental):
        if ticker in cache:
            return cache[ticker]
        base = (CAPTURE if supplemental else 'data/cache/research/current_raw_capture_20261013_v1')+'/'+ticker
        receipt = json.loads(read(base+'.receipt.json'))
        raw = read(base+'.response.bin',receipt['raw_sha256'])
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        if receipt.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest() != receipt['decoded_sha256']:
            raise ValueError('Decoded hash mismatch: '+ticker)
        body = json.loads(decoded)
        provider = (body.get('chart',{}).get('result') or [None])[0]
        if receipt.get('http_status',200) != 200 or not provider or not provider.get('timestamp'):
            cache[ticker] = dict(status='CAPTURE_HAS_NO_DAILY_TIMELINE',receipt=base+'.receipt.json')
            return cache[ticker]
        meta = provider['meta']
        if meta['symbol'] != ticker or meta['currency'] != 'USD':
            raise ValueError('Wrong symbol/currency: '+ticker)
        zone = ZoneInfo(meta['exchangeTimezoneName'])
        dates = [datetime.fromtimestamp(t,zone).date().isoformat() for t in provider['timestamp']]
        q = provider['indicators']['quote'][0]
        if len(set(dates)) != len(dates) or any(len(q[k]) != len(dates) for k in ('open','high','low','close')):
            raise ValueError('Malformed timeline: '+ticker)
        closes = dict(zip(dates,q['close']))
        events = [dict(event_date=datetime.fromtimestamp(e['date'],zone).date().isoformat(),provider_event=e)
                  for e in provider.get('events',{}).get('splits',{}).values()]
        cache[ticker] = dict(status='WHOLE_QUOTE_SOURCE_CONDITIONAL',closes=closes,events=events,
            path=base+'.response.bin',receipt=base+'.receipt.json',meta={k:meta.get(k) for k in ('symbol','currency','exchangeName','exchangeTimezoneName')},
            first_date=dates[0],last_date=dates[-1],returned_dividend_count=len(provider.get('events',{}).get('dividends',{})))
        return cache[ticker]

    for window in result['windows']:
        days, decision = window['training_dates'], window['decision_cutoff']
        for row in window['candidates']:
            ticker = row['ticker']
            if ticker == 'SMCI':
                continue
            supplemental = (ROOT/CAPTURE/(ticker+'.receipt.json')).exists()
            if row['training_source'] != previous.PANEL and not supplemental:
                continue
            data = quote(ticker,supplemental)
            if data['status'] != 'WHOLE_QUOTE_SOURCE_CONDITIONAL':
                row['capture_failure'] = data
                continue
            values = [str(data['closes'][d]) if data['closes'].get(d) is not None else None for d in days]
            missing = [d for d,v in zip(days,values) if v is None or Fraction(v)<=0]
            row['training_source'] = data['path']
            row['training_close'] = values
            row['training_basis'] = 'CONDITIONAL_PROVIDER_QUOTE_SPLIT_ADJUSTED'
            row['training_gross'] = None if missing else [str(Fraction(values[i+21])/Fraction(values[i])) for i in range(0,252,21)]
            row['missing_training_dates'] = missing
            row['blockers'] = [b for b in row['blockers'] if b != 'NONPANEL_WHOLE_SOURCE_UNIT_AND_SPLIT_REVIEW_REQUIRED']
            if missing and ticker != 'ARM' and 'INCOMPLETE_PREDECISION_TRAINING' not in row['blockers']:
                row['blockers'].append('INCOMPLETE_PREDECISION_TRAINING')
            row['quote_source_metadata'] = {k:v for k,v in data.items() if k not in ('closes','events')}
            row['returned_splits'] = [e for e in data['events'] if days[0]<=e['event_date']<=decision]
            row['postdecision_returned_actions_for_unit_audit_only'] = [e for e in data['events'] if e['event_date']>decision]
            row['quote_decision_close_observation'] = values[-1]
            row['decision_cost'] = None
            row['decision_cost_basis'] = 'BLOCKED_PENDING_DECISION_UNIT_ACTION_AUDIT'
            row['blockers'].append('DECISION_UNIT_COST_UNVERIFIED')
            row['unit_audit_required'] = ['Distinguish true splits from spinoff/other ratio events before restoring decision units.',
                'Period2-limited provider events may omit later actions affecting historical quote coordinates; event completeness is not proven.',
                'Future action metadata is only a coordinate conversion input, never training predictive information.']
            row['status'] = 'BLOCKED'
        window['ready_count'] = sum(r['status']=='READY_CONDITIONAL' for r in window['candidates'])
        window['status'] = 'BLOCKED' if any(r['blockers'] for r in window['candidates']) else 'READY_CONDITIONAL'
    result['status'] = 'SOURCE_WIRED_COST_UNITS_BLOCKED'
    result['training_price_only_limitations'] = ['Quote ratios are conditional price-only training diagnostics, not dividend-inclusive returns.',
        'Spinoff adjustments may change economic interpretation; no arbitrary ratio is treated as a true split.',
        'No runnable search_arguments are produced; all twelve windows remain represented.']
    result['source_hashes'][str(Path(__file__).resolve())] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,digest in pins.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Source changed during preparation: '+name)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    path=Path(args.output).resolve()
    if (ROOT/'tmp').resolve() not in path.parents or path.exists():
        raise ValueError('Create-only tmp output required')
    result=prepare()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([dict(date=w['decision_cutoff'],complete_training=sum(r['training_gross'] is not None for r in w['candidates']),status=w['status']) for w in result['windows']]))
