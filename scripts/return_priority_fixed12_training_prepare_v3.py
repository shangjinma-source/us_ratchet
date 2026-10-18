"""Conditional decision-unit restoration from audited simple corporate actions."""
import argparse
import gzip
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
INPUT='tmp/fixed12_training_prepare_20261014_v2/prepared.json'
INPUT_SHA='39668399f363250230e38264a51688e05132d71755feac251bda3cbc99c11eae'
EXTENDED='tmp/fixed12_extended_quote_capture_20261014_v1'


def prepare():
    pins={}
    def read(name,expected=None):
        raw=(ROOT/name).read_bytes()
        digest=hashlib.sha256(raw).hexdigest()
        if expected and digest!=expected: raise ValueError('Source hash differs: '+name)
        pins[name]=digest
        return raw
    result=json.loads(read(INPUT,INPUT_SHA))
    for name,digest in result['source_hashes'].items(): read(name,digest)
    simple=json.loads(read('tmp/historical_split_registry_diagnostic_20261014_v2/explicit_conditional_events.json'))
    extra=json.loads(read('tmp/fixed12_official_actions_20261014_v1/additional_simple_split_web_observations.json'))['events']
    known={}
    azn=json.loads(read('tmp/fixed12_official_actions_20261014_v1/azn_ads_unit_web_observation.json'))
    known[('AZN',azn['first_nyse_ordinary_session'])]=(Fraction(azn['conditional_pre_event_quote_to_ads_price_multiplier']),azn)
    for e in simple:
        for ref in e.get('evidence',[]):
            if ref.get('path') and ref.get('sha256'): read(ref['path'],ref['sha256'])
        known[(e['ticker'],e['event_date'])]=(Fraction(e['factor']),e)
    for e in extra: known[(e['ticker'],e['first_adjusted_session'])]=(Fraction(e['ratio']),e)
    cache={}
    def rawquote(ticker,row):
        if ticker in cache:return cache[ticker]
        ext=(ROOT/EXTENDED/(ticker+'.response.bin')).exists()
        base=EXTENDED+'/'+ticker if ext else 'data/cache/research/current_raw_capture_20261013_v1/'+ticker
        receipt=json.loads(read(base+'.receipt.json'))
        raw=read(base+'.response.bin',receipt['raw_sha256'])
        decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
        if receipt.get('decoded_sha256') and hashlib.sha256(decoded).hexdigest()!=receipt['decoded_sha256']:raise ValueError('Decoded hash differs')
        p=json.loads(decoded)['chart']['result'][0]
        if p['meta']['symbol']!=ticker or p['meta']['currency']!='USD':raise ValueError('Wrong symbol/currency')
        zone=ZoneInfo(p['meta']['exchangeTimezoneName'])
        dates=[datetime.fromtimestamp(t,zone).date().isoformat() for t in p['timestamp']]
        if max(dates)<'2026-10-12':raise ValueError('Insufficient extended observation')
        closes=dict(zip(dates,p['indicators']['quote'][0]['close']))
        events=[dict(event_date=datetime.fromtimestamp(e['date'],zone).date().isoformat(),factor=str(Fraction(str(e['numerator']))/Fraction(str(e['denominator']))),provider_event=e) for e in p.get('events',{}).get('splits',{}).values()]
        cache[ticker]=(closes,events,base+'.response.bin',max(dates))
        return cache[ticker]
    for w in result['windows']:
        decision=w['decision_cutoff'];days=w['training_dates']
        for row in w['candidates']:
            t=row['ticker']
            if t in ('EA','WBD','ANSS'):continue
            closes,events,path,last=rawquote(t,row)
            values=[str(closes[d]) if closes.get(d) is not None else None for d in days]
            if row['training_close'] and any(a is not None and b is not None and Fraction(a)!=Fraction(b) for a,b in zip(row['training_close'],values)):
                raise ValueError('Extended history changed: '+t)
            row['training_source']=path
            row['event_coverage_last_session']=last
            row['decision_quote_observation']=values[-1]
            row['blockers']=[b for b in row['blockers'] if b!='DECISION_UNIT_COST_UNVERIFIED']
            reviewed=[];factor=Fraction(1)
            for e in events:
                if e['event_date']<=decision:continue
                match=known.get((t,e['event_date']))
                if t=='SMCI' and e['event_date']=='2024-10-01' and Fraction(e['factor'])==10:
                    match=(Fraction(10),row.get('identity_bridge') or {'source':'tmp/smci_quote_capture_20261014_v1/conditional_window_inputs.json'})
                if not match or match[0]!=Fraction(e['factor']):
                    row['blockers'].append('POSTDECISION_ACTION_UNRESOLVED:'+e['event_date']+':'+e['factor'])
                else:
                    factor*=match[0];reviewed.append(dict(event=e,evidence=match[1]))
            if t in ('HON','CMCSA','ILMN'):
                row['blockers'].append('NON_SIMPLE_ACTION_PRICE_COORDINATE_REQUIRES_NOMINAL_CROSSCHECK')
            row['postdecision_returned_actions_for_unit_audit_only']=[e for e in events if e['event_date']>decision]
            row['cost_restoration_evidence']=reviewed
            row['decision_cost_factor']=str(factor)
            row['decision_cost']=str(Fraction(values[-1])*factor) if values[-1] and not row['blockers'] else None
            row['decision_cost_basis']='CONDITIONAL_QUOTE_COORDINATE_RESTORATION_NOT_OFFICIAL_NOMINAL_CERTIFICATION' if row['decision_cost'] else 'BLOCKED_SPECIFIC_ACTION_OR_SOURCE'
            for e in extra:
                if e['ticker']==t and e.get('new_cusip') and decision>=e['first_adjusted_session'] and row['security_id']:
                    old=row['security_id'];row['security_id']=old.rsplit(':',1)[0]+':'+e['new_cusip']
                    row['identity_bridge']=dict(status='CONDITIONAL_PRIMARY_CUSIP_SPLIT_BRIDGE',old_security_id=old,evidence=e)
            row['status']='BLOCKED' if row['blockers'] else ('EXCLUDED_TRAINING_RULE' if row['exclusion_reasons'] else 'READY_CONDITIONAL')
        w['ready_count']=sum(r['status']=='READY_CONDITIONAL' for r in w['candidates'])
        w['status']='BLOCKED' if any(r['blockers'] for r in w['candidates']) else 'READY_CONDITIONAL'
    result['status']='CONDITIONAL_COST_RESTORATION_WITH_SPECIFIC_BLOCKERS'
    result['coordinate_assumption']='Provider quote incorporates returned subsequent true splits; absence of returned events is conditional, never completeness certification. Future actions used only to restore historical units.'
    result['source_hashes']=pins
    pins[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    path=Path(args.output).resolve()
    if path.exists() or (ROOT/'tmp').resolve() not in path.parents:raise ValueError('Create-only tmp required')
    result=prepare();path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps([dict(date=w['decision_cutoff'],ready=w['ready_count'],blocked={r['ticker']:r['blockers'] for r in w['candidates'] if r['blockers']}) for w in result['windows']]))
