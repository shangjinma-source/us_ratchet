"""Prepared fixed experiment entry. Execute only after root code review."""
import argparse
import gzip
import json
import time
from datetime import datetime
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
from scripts.research.overnight_book_20261105 import run_book

ROOT=Path(__file__).resolve().parents[2]


def read(name):
    return json.loads((ROOT/name).read_bytes())


def merge_pins(destination, source):
    for name, digest in source.items():
        if name in destination and destination[name] != digest:
            raise ValueError('EXPECTED_PIN_CONFLICT:'+name)
        destination[name] = digest


def rebuild_rosters(book, days):
    states={x['decision_date']:x for x in book['selection_account_states']}
    rosters={}
    for audit in book['provider_audit']:
        decision=audit.get('target_decision_date')
        if decision in rosters or not audit.get('selection'):
            continue
        quotes={q['security_id']:q for q in states[decision]['valuation_quotes']}
        quantities=audit['selection']['target_quantities']
        ranked=sorted((s for s,q in quantities.items() if F(q)>0),
                      key=lambda s:(-F(quantities[s])*F(quotes[s]['price']),s))
        rosters[decision]=dict(decision=decision,earliest_buy_session=days[days.index(decision)+1],
                              original_count=len(ranked),selected=ranked[:10],
                              tickers={s:quotes[s]['ticker'] for s in ranked[:10]},discarded=ranked[10:])
    return list(rosters.values())


def validate_mapped_action(raw, sid, events, splits, review):
    if raw['kind']=='dividends':
        mapped=[e for e in events if e['sid']==sid and e['ex_date']==raw['date']]
        rows=[r for r in review['rows'] if r['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND'
              and r['security_id']==sid and r['ex_date']==raw['date']]
        if len(mapped)!=1 or len(rows)!=1:
            raise ValueError('DIVIDEND_MAPPING')
        e,r=mapped[0],rows[0]
        if F(e['amount'])!=F(r['amount_per_share']) or e['payment_date']!=r['payment_date'] or r['currency']!='USD':
            raise ValueError('DIVIDEND_NOMINAL_AMOUNT_OR_PAYDATE')
        observations=r.get('observed_provider_events')
        observation={k:v for k,v in raw.items() if k!='security_id'}
        if observations is not None and raw not in observations and observation not in observations:
            raise ValueError('UNREVIEWED_PROVIDER_OBSERVATION')
        if not r.get('source_references') or any(p not in review['source_hashes'] for p in r['source_references']):
            raise ValueError('DIVIDEND_SOURCE_BINDING')
    elif raw['kind']=='splits':
        mapped=[e for e in splits if e['old_sid']==sid and e['date']==raw['date']]
        rows=[r for r in review['rows'] if r.get('type')=='split_identity' and r['security_id']==sid and r['date']==raw['date']]
        if len(mapped)!=1 or len(rows)!=1:
            raise ValueError('SPLIT_MAPPING')
        e,r=mapped[0],rows[0]
        p=raw.get('provider_payload',raw.get('provider_event',{}))
        if e['new_sid']!=r['new_security_id'] or F(e['ratio'])!=F(r['new_shares'])/F(r['old_shares']) or F(e['ratio'])!=F(p['numerator'])/F(p['denominator']):
            raise ValueError('SPLIT_REVIEW_RATIO_OR_IDENTITY')
        if raw not in r['observed_provider_events']:
            raise ValueError('UNREVIEWED_SPLIT_OBSERVATION')
    else:
        raise ValueError('UNKNOWN_ACTION')


def run(output):
    started=time.monotonic()
    destination=(ROOT/output).resolve()
    if not destination.is_relative_to((ROOT/'tmp').resolve()):
        raise ValueError('ISOLATED_TMP_ONLY')
    destination.mkdir(exist_ok=False)
    inventory=read('tmp/overnight_preflight_20261105/result.json')
    if [r['window'] for r in inventory['results']]!=['2021_2023','2024_2026']:
        raise ValueError('EXACT_TWO_WINDOWS_REQUIRED')
    pins=dict(inventory['verified_expected_hashes'])
    for window in ['2021_2023','2024_2026']:
        merge_pins(pins,read(f'tmp/ema20_economic_20261105/daily/{window}/contract.json')['source_hashes'])

    def check(name, expected=None):
        actual=sha256((ROOT/name).read_bytes()).hexdigest()
        if actual != (expected or pins[name]):
            raise ValueError('SOURCE_CHANGED:'+name)
        return actual

    for name in pins:
        check(name)
    qp, qdiv={},{}
    for name in ['tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin']:
        raw=(ROOT/name).read_bytes()
        body=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
        quote=body['indicators']['quote'][0]
        for i,stamp in enumerate(body['timestamp']):
            day=datetime.fromtimestamp(stamp,ZoneInfo('America/New_York')).date().isoformat()
            row={key:str(quote[key][i]) for key in ['open','close']}
            if day in qp and qp[day]!=row:
                raise ValueError('QQQ_OVERLAP')
            qp[day]=row
        for event in body.get('events',{}).get('dividends',{}).values():
            day=datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()
            value=str(event['amount'])
            if day in qdiv and F(qdiv[day])!=F(value):
                raise ValueError('QQQ_DIVIDEND_OVERLAP')
            qdiv[day]=value
    code_names=['scripts/research/overnight_book_20261105.py','scripts/research/run_overnight_fixed_20261105.py',
                'docs/candidates/overnight_strategy_feasibility_20261105.md',
                'docs/candidates/overnight_execution_ready_20261105.md']
    code_pins={n:sha256((ROOT/n).read_bytes()).hexdigest() for n in code_names}
    inventory_name='tmp/overnight_preflight_20261105/result.json'
    code_pins[inventory_name]=sha256((ROOT/inventory_name).read_bytes()).hexdigest()
    contract=dict(status='STARTED',seconds=600,source_expected_pins=pins,code_pins=code_pins,
                  scenarios=[(0,0),(5,0),(10,0),(5,5)],research_only=True,
                  same_roster_hold_rule='MONTH_CHANGE_SELL_OPEN_REBUY_CLOSE; FINAL_SELL_OPEN')
    (destination/'contract.json').write_text(json.dumps(contract,indent=2),encoding='utf8')
    results=[]
    try:
        for inv in inventory['results']:
            window=inv['window']
            base='recent_continuous_baseline_20261026_v7' if window=='2021_2023' else 'old_continuous_baseline_20261026_v9'
            document=read(f'tmp/{base}/execution_inputs.json')
            priorname=f'tmp/trend_{window}_20261026_v1/execution_inputs.json'
            check(priorname)
            review=read(priorname)['action_review']
            merge_pins(pins,review['source_hashes'])
            for name,value in review['source_hashes'].items():
                check(name,value)
            days=document['assembled']['session_dates']
            if days!=sorted(set(days)):
                raise ValueError('SOURCE_SESSION_DOMAIN')
            rebuilt=rebuild_rosters(read(f'tmp/{base}/book.json'),days)
            if rebuilt!=inv['rosters']:
                raise ValueError('PRECHECK_ROSTERS_DIFFER_FROM_FROZEN_PARENT')
            if len(rebuilt)!=len(document['assembled']['monthly_inputs']):
                raise ValueError('ROSTER_MONTH_COVERAGE')
            events=[dict(sid=e['security_id'],ex_date=e['ex_date'],payment_date=e['payment_date'],amount=e['amount_per_share'])
                    for e in document['dividend_events']]
            splits=[dict(date=e['date'],old_sid=e['security_id'],new_sid=e['new_security_id'],ratio=str(F(e['new_shares'])/F(e['old_shares'])))
                    for e in document['assembled']['actions']]
            tickers={sid:ticker for r in inv['rosters'] for sid,ticker in r['tickers'].items()}
            for event in splits:
                tickers[event['new_sid']]=tickers.get(event['old_sid'],'SMCI')
            missing=document['action_stream_missing']

            def gate(previous,day,holdings):
                if time.monotonic()-started>600:
                    raise ValueError('FIXED_BUDGET_EXHAUSTED')
                for sid,q in holdings.items():
                    if not q:
                        continue
                    ticker=tickers[sid]
                    absent=any(x==sid if isinstance(x,str) else x.get('ticker')==ticker for x in missing)
                    if absent and not any(r['status']=='REVIEWED_NO_ACTION_FOR_PERIOD' and r.get('security_id')==sid
                                          and r['start_exclusive']<=previous and r['end_inclusive']>=day for r in review['rows']):
                        raise ValueError('ABSENCE_SCOPE:'+sid+':'+previous+':'+day)
                    for raw in document['provider_event_inventory']:
                        if raw.get('ticker')!=ticker or not previous<raw['date']<=day:
                            continue
                        validate_mapped_action(raw,sid,events,splits,review)
                for transition in document.get('dated_identity_transitions',[]):
                    if previous<transition['date']<=day and holdings.get(transition['old_sid'],0):
                        if not any(e['old_sid']==transition['old_sid'] and e['new_sid']==transition['new_sid'] and e['date']==transition['date'] for e in splits):
                            raise ValueError('UNKNOWN_IDENTITY_CONVERSION')

            for label,prices,rosters,divs,acts,checker,mode in [
                ('O1',document['ohlc'],inv['rosters'],events,splits,gate,'overnight'),
                ('SAME_ROSTER_HOLD',document['ohlc'],inv['rosters'],events,splits,gate,'monthly_hold'),
                ('O2_QQQ',{'QQQ':qp},[dict(decision=days[0],selected=['QQQ'])],
                 [dict(sid='QQQ',ex_date=d,amount=a,payment_date=None) for d,a in qdiv.items()],[],
                 lambda *args:None,'overnight'),
                ('QQQ_HOLD',{'QQQ':qp},[dict(decision=days[0],selected=['QQQ'])],
                 [dict(sid='QQQ',ex_date=d,amount=a,payment_date=None) for d,a in qdiv.items()],[],
                 lambda *args:None,'monthly_hold')]:
                for slip,fee in contract['scenarios']:
                    if time.monotonic()-started>600:
                        raise ValueError('FIXED_BUDGET_EXHAUSTED')
                    book=run_book(days=days,prices=prices,rosters=rosters,dividends=divs,splits=acts,
                                  mode=mode,slippage_bps=slip,commission_bps=fee,exposure_check=checker,
                                  retry_until_first_fill=label=='QQQ_HOLD')
                    name=f'{window}_{label}_{slip}_{fee}.json'
                    (destination/name).write_text(json.dumps(book,indent=2),encoding='utf8')
                    results.append(dict(file=name,terminal=book['terminal_equity'],drawdown=book['drawdown'],
                                        orders=len(book['orders']),rejects=len(book['rejections']),turnover=book['turnover']))
        for name,value in code_pins.items():
            check(name,value)
        for name,value in pins.items():
            check(name,value)
        (destination/'summary.json').write_text(json.dumps(dict(status='COMPLETE_PENDING_INDEPENDENT_REVIEW',results=results),indent=2),encoding='utf8')
    except Exception as error:
        (destination/'failure.json').write_text(json.dumps(dict(error=repr(error),completed=results,elapsed=time.monotonic()-started),indent=2),encoding='utf8')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-approved',action='store_true')
    parser.add_argument('--output',default='tmp/overnight_fixed_20261105')
    args=parser.parse_args()
    if not args.run_approved:
        parser.error('Root review required; no experiment started')
    run(args.output)
