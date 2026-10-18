"""Bind reviewed postperiod splits and whole archived historical sources."""
import argparse
import csv
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def prepare():
    pins={}
    def read(name,expected=None):
        raw=(ROOT/name).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected and digest!=expected:raise ValueError('Changed source: '+name)
        pins[name]=digest
        return raw
    result=json.loads(read('tmp/fixed12_training_prepare_20261014_v3/prepared.json','317407059033d0f6ad16943620d2a66b18dc5176a49ccfb0d0ed2986e4bf5217'))
    for name,digest in result['source_hashes'].items():read(name,digest)
    facts=json.loads(read('tmp/fixed12_official_actions_20261014_v1/postperiod_simple_split_web_observations.json'))
    events={e['ticker']:e for e in facts['events']}
    recovery=json.loads(read('tmp/fixed12_archive_recovery_readback_20261014_v1.json','88d401b2e5abcb74155b67cf685a14d1782594a1854b7d5266cb228e860b9c9c'))
    for name,digest in recovery['source_hashes'].items():read(name,digest)
    sources={}
    for evidence in recovery['rows']:
        ticker=evidence['ticker']
        if ticker in ('ANSS','EA'):
            rows=list(csv.DictReader(read(evidence['archive_path']).decode('utf-8-sig').splitlines()))
            closes={r['Date']:r['Close'] for r in rows}
            if len(closes)!=len(rows) or evidence['sina_exact_ohlc_differences']:raise ValueError('Bad archive evidence')
            sources[ticker]=(closes,evidence['archive_path'],evidence['conditional_basis'],evidence)
        elif ticker=='WBD':
            receipt=json.loads(read(evidence['receipt_path']))
            raw=read(evidence['preferred_source'],receipt['raw_sha256'])
            decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            if receipt.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest()!=receipt['decoded_sha256']:raise ValueError('Decoded mismatch')
            p=json.loads(decoded)['chart']['result'][0]
            if p['meta']['symbol']!='WBD' or p['meta']['currency']!='USD':raise ValueError('Wrong WBD quote')
            if p.get('events',{}).get('splits'):raise ValueError('WBD events require separate review')
            zone=ZoneInfo(p['meta']['exchangeTimezoneName'])
            dates=[datetime.fromtimestamp(t,zone).date().isoformat() for t in p['timestamp']]
            if len(dates)!=len(set(dates)):raise ValueError('Duplicate WBD dates')
            closes=dict(zip(dates,p['indicators']['quote'][0]['close']))
            sources[ticker]=(closes,evidence['preferred_source'],'CONDITIONAL_PROVIDER_QUOTE_WITH_NOMINAL_ARCHIVE_OVERLAP',evidence)
    for w in result['windows']:
        d=w['decision_cutoff'];days=w['training_dates']
        for row in w['candidates']:
            ticker=row['ticker']
            if ticker in events:
                evidence=events[ticker]
                date=evidence.get('first_adjusted_session',evidence.get('provider_first_adjusted_session'))
                matches=[e for e in row['postdecision_returned_actions_for_unit_audit_only'] if e['event_date']==date]
                if len(matches)!=1 or Fraction(matches[0]['factor'])!=Fraction(evidence['ratio']):raise ValueError('Event ratio/date mismatch')
                marker='POSTDECISION_ACTION_UNRESOLVED:'+date+':'+matches[0]['factor']
                if marker not in row['blockers']:raise ValueError('Expected unresolved event missing')
                row['blockers'].remove(marker)
                factor=Fraction(row['decision_cost_factor'])*Fraction(evidence['ratio'])
                row['decision_cost_factor']=str(factor)
                row['cost_restoration_evidence'].append(dict(event=matches[0],evidence=evidence))
                if not row['blockers']:
                    row['decision_cost']=str(Fraction(row['decision_quote_observation'])*factor)
                    row['decision_cost_basis']='CONDITIONAL_QUOTE_COORDINATE_RESTORATION_NOT_OFFICIAL_NOMINAL_CERTIFICATION'
            if ticker in sources:
                closes,path,basis,evidence=sources[ticker]
                values=[str(closes[x]) if closes.get(x) is not None else None for x in days]
                if any(v is None or Fraction(v)<=0 for v in values):raise ValueError('Incomplete whole historical source')
                row.update(training_source=path,training_basis=basis,training_close=values,
                    training_gross=[str(Fraction(values[i+21])/Fraction(values[i])) for i in range(0,252,21)],
                    missing_training_dates=[],decision_cost=values[-1],decision_cost_factor='1',
                    decision_cost_basis=basis+'_NOT_OFFICIAL_NOMINAL_CERTIFICATION',
                    source_recovery_evidence=evidence,conditional_no_split_in_training_assumption=True,
                    complete_event_history_certified=False)
                row['blockers']=[b for b in row['blockers'] if b!='NONPANEL_WHOLE_SOURCE_UNIT_AND_SPLIT_REVIEW_REQUIRED']
                row.pop('capture_failure',None)
            row['status']='BLOCKED' if row['blockers'] else ('EXCLUDED_TRAINING_RULE' if row['exclusion_reasons'] else 'READY_CONDITIONAL')
        w['ready_count']=sum(r['status']=='READY_CONDITIONAL' for r in w['candidates'])
        w['status']='BLOCKED' if any(r['blockers'] for r in w['candidates']) else 'READY_CONDITIONAL'
    result['status']='CONDITIONAL_TRAINING_PREPARED_NON_SIMPLE_COORDINATES_PENDING'
    result['source_hashes']=pins
    pins[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for name,digest in pins.items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('Source changed during prepare')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    path=Path(args.output).resolve()
    if path.exists() or (ROOT/'tmp').resolve() not in path.parents:raise ValueError('Create-only tmp required')
    result=prepare();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([dict(date=w['decision_cutoff'],ready=w['ready_count'],blocked=[r['ticker'] for r in w['candidates'] if r['blockers']]) for w in result['windows']]))
