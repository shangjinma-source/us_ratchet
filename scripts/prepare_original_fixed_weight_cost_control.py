"""Offline original-eight input preparation only; never runs a historical book."""
import argparse
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = 'tmp/daily_verified_domain_experiment_20261016_v2/assembled.json'
PREPARED = 'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json'
CONTROL = 'data/cache/research/ndx_original_8_control_v1/manifest.json'
RAW = 'data/cache/research/current_raw_capture_20261014_v1/TSM.response.bin'
RECEIPT = 'data/cache/research/current_raw_capture_20261014_v1/TSM.receipt.json'
COST_RECEIPT = 'tmp/continuous_guided_cost_stress_20261019_v1/preflight.json'
TSM = 'security:incumbent_overlay:TSM'
SCENARIOS = {'slippage5': {'fee_bps': '0', 'slippage_bps': '5'},
             'fee1_slippage10': {'fee_bps': '1', 'slippage_bps': '10'}}


def build_inputs(*, assembled, prepared, control, raw, receipt, event_scope="SEALED_FULL_DOMAIN"):
    """Pure conditional input builder; does not certify provider price basis."""
    if receipt['raw_sha256'] != sha256(raw).hexdigest() or receipt['status'] != 'RAW_CAPTURED' or receipt['http_status'] != 200 or receipt['body_truncated']:
        raise ValueError('TSM_RAW_RECEIPT_MISMATCH')
    payload = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
    chart = payload['chart']['result'][0]
    meta = chart['meta']
    if any(meta[k] != value for k,value in {'symbol':'TSM','currency':'USD','exchangeName':'NYQ','instrumentType':'EQUITY','exchangeTimezoneName':'America/New_York'}.items()):
        raise ValueError('TSM_COORDINATE_MISMATCH')
    dates = assembled['session_dates']
    if dates != prepared['session_dates'] or dates != sorted(set(dates)):
        raise ValueError('CALENDAR_MISMATCH')
    if str(prepared['initial_cash']) != '20000' or prepared['initial_shares']:
        raise ValueError('FRESH_20000_REQUIRED')
    if any(k != 'dividends' and values for k,values in chart.get('events',{}).items()):
        raise ValueError('TSM_NON_DIVIDEND_ACTION_REQUIRES_REVIEW')
    quote = chart['indicators']['quote'][0]; times = chart['timestamp']
    fields = ('open','high','low','close')
    if any(len(quote[k]) != len(times) for k in fields): raise ValueError('TSM_LENGTH_MISMATCH')
    channel = {}
    for i,ts in enumerate(times):
        day = datetime.fromtimestamp(ts,ZoneInfo('America/New_York')).date().isoformat()
        if day not in dates: continue
        if day in channel: raise ValueError('TSM_DUPLICATE_DATE')
        values = {}
        for field in fields:
            value=quote[field][i]
            if isinstance(value,bool): raise ValueError('TSM_BOOLEAN_PRICE')
            try: value=Fraction(str(value))
            except (ValueError,ZeroDivisionError): raise ValueError('TSM_INVALID_PRICE') from None
            if value <= 0: raise ValueError('TSM_NONPOSITIVE_PRICE')
            values[field]=value
        if not values['low'] <= min(values['open'],values['close']) <= max(values['open'],values['close']) <= values['high']:
            raise ValueError('TSM_OHLC_INCONSISTENT')
        channel[day]={k:str(v) for k,v in values.items()}
    if set(channel) != set(dates): raise ValueError('TSM_INCOMPLETE_CALENDAR')
    definitions=control['definition']['securities']
    if len(definitions)!=8 or {r['ticker'] for r in definitions}!={'NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG'}:
        raise ValueError('EXACT_ORIGINAL_EIGHT_REQUIRED')
    weights={r['security_id']:str(r['target_weight']) for r in definitions}
    if len(weights)!=8 or TSM not in weights: raise ValueError('ORIGINAL_IDENTITY_REQUIRED')
    result=deepcopy(assembled); ohlc=deepcopy(prepared['ohlc'])
    for row in definitions:
        sid=row['security_id']
        if sid==TSM:continue
        if result['metadata'][sid]['ticker']!=row['ticker'] or result['metadata'][sid]['issuer_id']!=row['issuer_id']:
            raise ValueError('ORIGINAL_BASE_IDENTITY_MISMATCH')
        for day in dates:
            if Fraction(ohlc[sid][day]['close'])!=Fraction(result['close_prices'][sid][day]):
                raise ValueError('BASE_CLOSE_UNIT_MISMATCH')
    # Unexposed after-close distributions set a global WAIT in the shared book.
    # Freeze a disclosed reachable-identity event domain, including all successor
    # and child rights identities, rather than dropping events by ticker alone.
    if event_scope not in ('SEALED_FULL_DOMAIN','ORIGINAL_IDENTITY_CLOSURE_CANDIDATE'):raise ValueError('UNKNOWN_EVENT_SCOPE')
    original_events={field:deepcopy(result.get(field,[])) for field in ('actions','provider_actions','cash_stock_merger_events','distribution_events')}
    event_fields=('actions','provider_actions','cash_stock_merger_events','distribution_events')
    identity_fields=('security_id','new_security_id','old_sid','new_sid','parent_sid','post_parent_sid','child_sid')
    reachable=set(weights)
    def identities(event):return {event[k] for k in identity_fields if isinstance(event.get(k),str)}
    all_events=[event for field in event_fields for event in result.get(field,[])]
    changed=True
    while changed:
        before=set(reachable)
        for event in all_events:
            ids=identities(event)
            if ids & reachable:reachable.update(ids)
        changed=before!=reachable
    excluded=[]
    for field in event_fields:
        kept=[]
        for event in result.get(field,[]):
            ids=identities(event)
            if not ids:raise ValueError('ACTION_IDENTITY_UNCLASSIFIABLE')
            if ids & reachable:kept.append(event)
            else:excluded.append(dict(field=field,event=deepcopy(event),reason='OUTSIDE_ORIGINAL_EIGHT_AND_ACTION_IDENTITY_CLOSURE'))
        result[field]=kept
    if event_scope=='SEALED_FULL_DOMAIN':
        result.update(original_events)
    result['original_control_action_scope']=dict(active_policy=event_scope,reachable_security_ids=sorted(reachable),excluded_events=excluded if event_scope!='SEALED_FULL_DOMAIN' else [],candidate_exclusions_not_applied=excluded if event_scope=='SEALED_FULL_DOMAIN' else [],
        policy='UNDIRECTED_ALL_RELATED_IDENTITIES_TRANSITIVE_CLOSURE_CONSERVATIVE',
        rationale='Default preserves sealed full-domain events including unrelated global WAIT. Closure is an unexecuted candidate only.')
    ohlc[TSM]=channel
    result['close_prices'][TSM]={d:v['close'] for d,v in channel.items()}
    tsm=next(r for r in definitions if r['security_id']==TSM)
    result['metadata'][TSM]={k:tsm[k] for k in ('ticker','issuer_id')}
    result['price_source_references'][TSM]=[RAW]
    for plan in result['monthly_inputs']:
        day=plan['decision_date']
        plan['valuation_quotes']=[dict(security_id=sid,ticker=result['metadata'][sid]['ticker'],price=result['close_prices'][sid][day],as_of=day,
            price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',source_references=result['price_source_references'][sid]) for sid in weights]
        plan['search_arguments']={'decision_date':day,'fee_bps':'0','minimum_cash_buffer':'0'}
    return dict(assembled=result,ohlc=ohlc,weights=weights,initial_cash='20000',scenarios=SCENARIOS,
        status='PREPARED_CONDITIONAL_CONTROL_NOT_EXECUTION_AUTHORIZATION',search_calls=0,book_calls=0,
        tsm_returned_dividends_excluded=len(chart.get('events',{}).get('dividends',{})),
        limitations=['Original fixed weights, not original full ratchet replay.',
            'TSM NYSE/USD conditional provider OHLC; complete corporate actions and nominal price authenticity remain unverified.',
            'Ordinary dividends excluded for all arms; price-only, not independent OOS.',
            'Same initial cash/calendar/monthly reset dates and next-open kernel; no optimizer or risk overlay for fixed control.',
            'Floor equity times original weight divided by close; no normalization, residual redistribution or implicit leverage.'])


def prepare():
    def read(name):return json.loads((ROOT/name).read_bytes())
    frozen=read(COST_RECEIPT);pins=dict(frozen['source_hashes'])
    for name,expected in pins.items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise ValueError('BASE_SOURCE_DRIFT')
    for name in (BASE,PREPARED):
        if name not in pins:raise ValueError('BASE_NOT_PINNED')
    for name in (CONTROL,RAW,RECEIPT,COST_RECEIPT,'scripts/prepare_original_fixed_weight_cost_control.py','backtest/original_fixed_weight_cost_next_open.py'):
        actual=sha256((ROOT/name).read_bytes()).hexdigest()
        if name in pins and pins[name]!=actual:raise ValueError('SOURCE_PIN_CONFLICT')
        pins[name]=actual
    bundle=build_inputs(assembled=read(BASE),prepared=read(PREPARED),control=read(CONTROL),raw=(ROOT/RAW).read_bytes(),receipt=read(RECEIPT))
    for plan in bundle['assembled']['monthly_inputs']:
        plan['source_hashes'].update({name:pins[name] for name in (CONTROL,RAW,RECEIPT)})
    bundle['source_hashes']=pins
    bundle['assembled']['source_hashes'].update(pins)
    if len(bundle['assembled']['session_dates'])!=699 or bundle['assembled']['session_dates'][0]!='2023-12-29' or bundle['assembled']['session_dates'][-1]!='2026-10-13' or len(bundle['assembled']['monthly_inputs'])!=34:
        raise ValueError('EXPECTED_698_VALUED_SESSIONS_REQUIRED')
    return bundle


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory');args=parser.parse_args()
    bundle=prepare()
    if args.output_directory:
        directory=Path(args.output_directory);directory.mkdir(parents=True,exist_ok=False)
        with (directory/'inputs.json').open('x',encoding='utf-8') as stream:json.dump(bundle,stream,ensure_ascii=False)
    print(json.dumps(dict(status=bundle['status'],search_calls=0,book_calls=0,sessions=699,monthly_resets=34)))


if __name__=='__main__':main()
