"""Prepare full-domain historical execution evidence; no search or book calls."""
import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
TRAINING='tmp/fixed12_training_prepare_20261014_v6/prepared.json'
HOLDING='tmp/fixed12_holding_prepare_20261014_v3/prepared.json'
CALENDAR='tmp/fixed12_monthly_limit_inputs_20261014_v2/prepared.json'
COVERAGE='tmp/current_monthly_reoptimization_coverage_20261014_v1.json'
FIELDS=('open','high','low','close')


def prepare():
    pins={}
    def read(path,expected=None):
        raw=(ROOT/path).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if expected is not None and digest!=expected:raise ValueError('SOURCE_CHANGED:'+path)
        if path in pins and pins[path]!=digest:raise ValueError('PIN_CONFLICT')
        pins[path]=digest
        return raw
    def document(path):
        result=json.loads(read(path))
        for name,digest in result.get('source_hashes',{}).items():read(name,digest)
        return result
    training=document(TRAINING);holding=document(HOLDING);old=document(CALENDAR);coverage=json.loads(read(COVERAGE))
    # Coverage also pins a mutable planning note; source files below are independently verified.
    read('tmp/current_monthly_backtest_gap_20261014_v1.json')
    read('scripts/return_priority_current_monthly_actual_equity_inputs.py')
    calendar=old['session_dates'];groups={};windows=[]
    for w in training['windows']:
        args=w['search_arguments']
        windows.append(dict(decision_date=w['decision_cutoff'],member_denominator=w['member_denominator'],search_arguments=args,
            exclusions=w['exclusions'],information_cutoff=w['decision_cutoff'],entered_cash_policy='OVERRIDE_ONLY_WITH_ACTUAL_CASH_PLUS_TRADABLE_HELD_MARKS_AT_DECISION'))
        for c in w['candidates']:
            if c['security_id'] in args['prices']:groups.setdefault(c['security_id'],[]).append((w['decision_cutoff'],c))
    dates=[w['decision_date'] for w in windows]
    if dates!=old['contract']['decision_dates'] or len(dates)!=12:raise ValueError('REGISTERED_DECISION_DATES_MISMATCH')
    if len(calendar)!=250 or calendar!=sorted(set(calendar)) or calendar[0]!='2024-07-31' or calendar[-1]!='2025-07-30':raise ValueError('CONTINUOUS_CALENDAR_MISMATCH')
    active_dates=[calendar[calendar.index(day)+1] for day in dates]
    if len({day[:7] for day in active_dates})!=12:raise ValueError('DUPLICATE_ACTIVE_TARGET_MONTH')
    for w,active in zip(windows,active_dates):w['active_date']=active
    cache={};prices={};provenance={};metadata={};gaps=[];actions={};mergers={};settlements={}
    for w in holding['windows']:
        a=w['outcome_arguments_without_target_weights']
        for e in a['split_events']:
            key=(e['security_id'],e['date'])
            if key in actions and actions[key]!=e:raise ValueError('SPLIT_CONFLICT')
            actions[key]=e
        for e in a['cash_stock_merger_events']:mergers[e['event_id']]=e
        for key,value in a['fractional_settlements'].items():
            if key in settlements and settlements[key]!=value:raise ValueError('FRACTION_TERMS_CONFLICT')
            settlements[key]=value
        if a['cash_merger_events'] or a['unmodelled_action_events']:raise ValueError('NEW_ACTION_REVIEW_REQUIRED')
    for sid,records in sorted(groups.items()):
        start,c=records[0];path=c['training_source'];ticker=c['ticker']
        if len({r['training_source'] for _,r in records})!=1:raise ValueError('WHOLE_SOURCE_CHANGED')
        if path not in cache:
            raw=read(path)
            if path.endswith('.csv'):
                raw_rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
                data={r['Date']:{k:r[k.title()] for k in FIELDS} for r in raw_rows};events=[];dividends=[]
                if len(data)!=len(raw_rows):raise ValueError('DUPLICATE_DATES')
            else:
                p=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
                if p['meta']['symbol']!=ticker or p['meta']['currency']!='USD':raise ValueError('IDENTITY_MISMATCH')
                zone=ZoneInfo(p['meta']['exchangeTimezoneName']);day=lambda v:datetime.fromtimestamp(v,zone).date().isoformat()
                dates=[day(v) for v in p['timestamp']];q=p['indicators']['quote'][0]
                if len(set(dates))!=len(dates) or any(len(q[k])!=len(dates) for k in FIELDS):raise ValueError('TIMELINE_ALIGNMENT')
                data={d:{k:str(q[k][i]) for k in FIELDS if q[k][i] is not None} for i,d in enumerate(dates)}
                events=[dict(event_date=day(e['date']),factor=str(Fraction(str(e['numerator']))/Fraction(str(e['denominator'])))) for e in p.get('events',{}).get('splits',{}).values()]
                dividends=[dict(event_date=day(e['date']),provider_event=e) for e in p.get('events',{}).get('dividends',{}).values()]
            cache[path]=(data,events,dividends)
        data,events,dividends=cache[path];factor=Fraction(c['decision_cost_factor']);reviewed=[e['event'] for e in c.get('cost_restoration_evidence',[]) if e['event']['event_date']>start]
        if not path.endswith('.csv') and {(e['event_date'],Fraction(e['factor'])) for e in events if e['event_date']>start}!={(e['event_date'],Fraction(e['factor'])) for e in reviewed}:raise ValueError('UNREVIEWED_COORDINATE_EVENT:'+ticker)
        prices[sid]={}
        for day in calendar:
            if day<start:continue
            multiplier=factor
            for event in reviewed:
                if event['event_date']<=day:multiplier/=Fraction(event['factor'])
            source=data.get(day,{})
            values={k:str(Fraction(source[k])*multiplier) if k in source else None for k in FIELDS}
            if all(v is not None for v in values.values()):
                op,hi,lo,cl=(Fraction(values[k]) for k in FIELDS)
                if not 0<lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError('INVALID_OHLC:'+ticker+day)
            else:gaps.append(dict(security_id=sid,ticker=ticker,date=day,reason='SOURCE_UNAVAILABLE_NO_FILL_OR_REPLACEMENT'))
            prices[sid][day]=values
        for decision,row in records:
            if Fraction(prices[sid][decision]['close'])!=Fraction(row['decision_cost']):raise ValueError('DECISION_COST_DISAGREEMENT:'+ticker+decision)
        metadata[sid]=dict(ticker=ticker,issuer_id=c['issuer_id'])
        provenance[sid]=dict(whole_source=path,required_from=start,required_to=calendar[-1],price_basis='CONDITIONAL_RESTORED_HISTORICAL_NOMINAL_NOT_CERTIFIED',
            initial_coordinate_factor=str(factor),subsequent_coordinate_events=reviewed,identity_evidence=c['identity_evidence'],identity_bridge=c.get('identity_bridge'),
            returned_dividends=[e for e in dividends if start<e['event_date']<=calendar[-1]],dividend_payment_dates_known=False,
            future_coordinate_events_used_only_for_unit_restoration=True,source_http_authenticated=not path.endswith('.csv'))
    migrations=[]
    for ticker,sids in coverage['same_ticker_multiple_sids'].items():
        ordered=sorted(sids,key=lambda sid:groups[sid][0][0]);old_sid,new_sid=ordered
        matching=[e for (sid,_),e in actions.items() if sid==old_sid]
        if len(matching)!=1:raise ValueError('AMBIGUOUS_IDENTITY_ACTION')
        e=matching[0]
        migrations.append(dict(date=e['date'],old_sid=old_sid,new_sid=new_sid,ticker=ticker,new_shares=e['new_shares'],old_shares=e['old_shares'],
            source_references=e['source_references']+[TRAINING,HOLDING],execution_support_required=True,
            same_economic_action_as_split=True,apply_share_factor_exactly_once=True,
            identity_scope='CONDITIONAL_EXISTING_OLD_NEW_CUSIP_MAPPING_NOT_GENERAL_IDENTITY_CERTIFICATION'))
    executable_actions=[]
    migrated_keys={(m['old_sid'],m['date']) for m in migrations}
    for e in actions.values():
        if (e['security_id'],e['date']) not in migrated_keys:
            executable_actions.append(dict(type='split',**e))
    for migration in migrations:
        executable_actions.append(dict(type='split_identity',**migration))
        old_sid,new_sid=migration['old_sid'],migration['new_sid']
        if provenance[old_sid]['whole_source']!=provenance[new_sid]['whole_source']:raise ValueError('MIGRATION_SOURCE_MISMATCH')
        # Earlier migrated residual can precede the new SID's first monthly eligibility.
        for day,bar in prices[old_sid].items():
            if day>=migration['date']:
                if day in prices[new_sid] and prices[new_sid][day]!=bar:raise ValueError('MIGRATION_COORDINATE_MISMATCH')
                prices[new_sid][day]=bar.copy()
        prices[new_sid]=dict(sorted(prices[new_sid].items()))
        provenance[new_sid]['residual_coverage_from']=migration['date']
        provenance[new_sid]['residual_coordinate_evidence_from_old_sid']=old_sid
        provenance[old_sid]['not_tradable_as_old_identity_from']=migration['date']
    return dict(schema='MONTHLY_ACTUAL_EQUITY_FULL_DOMAIN_INPUTS_V1',status='PREPARED_CONDITIONAL_KERNEL_ACTION_ADAPTATION_REQUIRED',
        session_dates=calendar,windows=windows,metadata=metadata,ohlc=prices,source_provenance=provenance,actions=executable_actions,split_events_reference_only=list(actions.values()),identity_migrations=migrations,
        cash_stock_merger_events=list(mergers.values()),fractional_settlements=settlements,price_gaps=gaps,source_hashes=pins,
        initial_cash='20000',initial_shares={},fee_bps='0',minimum_cash_buffer='0',search_protocol=training['protocol'],
        search_calls=0,book_calls=0,network_calls=0,selection_changed_for_future_price_coverage=False,point_in_time_certified=False,independent_oos=False,
        required_execution_rules=['Old SID prices after migration are economic coordinate observations only; migrate holdings and targets to new SID once, never trade both identities independently.',
            'ANSS stops available tradable OHLC after 2025-07-16. Use explicit conditional mixed-entitlement evidence or BLOCK exposure; never fill missing prices or treat payment/delivery as known.',
            'Unpaid cash and stock rights remain nontradable, excluded from investable capital; total economic valuation must be reported separately.',
            'Do not use returned coordinate factors as share changes without the explicit split/migration event list.'],
        limitations=['Conditional quote coordinate restoration and archived nominal-overlap evidence; not official nominal or complete corporate-action certification.',
            'PRICE_ONLY_EXCLUDES_CASH_DIVIDENDS: returned dividend events retained per security; ex-date does not prove payment. Calendar is the saved QQQ timeline, not certified exchange completeness.',
            'This is a full-domain input preparation, not a new strategy result or selection.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    output=args.output.resolve()
    if output.exists() or not output.is_relative_to(ROOT/'tmp'):raise ValueError('CREATE_ONLY_TMP_OUTPUT_REQUIRED')
    result=prepare();output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),windows=len(result['windows']),securities=len(result['metadata']),price_gaps=len(result['price_gaps']),split_events=len(result['actions']),identity_migrations=len(result['identity_migrations']))))
