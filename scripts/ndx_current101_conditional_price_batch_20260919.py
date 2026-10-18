"""Explicit 92 new / 3 referenced / 6 blocked conditional price observations."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal,localcontext
from fractions import Fraction
from urllib.parse import parse_qs,urlparse
import gzip,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_current_28_split_quote_guard_research as guard
from scripts.ndx_current_22_price_capture_20260919 import save
BASE=guard.previous.BASE
OUTPUT=BASE/'current101_conditional_prices_20260919_v1'
OBS=BASE/'ndx_current_quote_list_capture_20260919_v1/observation.json'
OBS_SHA='50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77'
REGULAR=BASE/'current_regular_segment_quote_probe_20260919_v1/index.json'
REGULAR_SHA='881583623494507fc234821366655a283721c53dec4d7d410b2e78e7feb81b0d'
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
GAP=guard.previous.gap


def read(path,sha,sources):return guard.previous.read(path,sha,sources)


def decode(raw):return json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,object_pairs_hook=guard.previous.nominal._unique_pairs)['chart']['result'][0]


def decimal_audit(raw,rows):
    """Independent event-ratio arithmetic; never read supplied split factors."""
    data=decode(raw);q=data['indicators']['quote'][0]
    day=lambda t:datetime.fromtimestamp(t,timezone.utc).astimezone(guard.previous.nominal.NEW_YORK).date().isoformat()
    daily={day(t):{k:q[k][i] for k in ('open','close')} for i,t in enumerate(data['timestamp'])}
    if len(daily)!=len(data['timestamp']):raise ValueError('Duplicate raw quote dates')
    dates=[r['session'] for r in rows]
    if not dates or dates!=sorted(set(dates)):raise ValueError('Unique ascending output required')
    maximum=Decimal(0)
    with localcontext() as context:
        context.prec=50
        for row in rows:
            factor=Decimal(1)
            for event in data.get('events',{}).get('splits',{}).values():
                if day(event['date'])>row['session']:factor*=Decimal(str(event['numerator']))/Decimal(str(event['denominator']))
            for field in ('open','close'):
                observed=row['nominal_'+field]
                if type(observed) not in (int,float):raise ValueError('Nonboolean finite quote required')
                actual=Decimal(str(observed));expected=Decimal(str(daily[row['session']][field]))*factor
                if not actual.is_finite() or actual<=0 or not expected.is_finite() or expected<=0:raise ValueError('Finite positive quote required')
                error=abs(actual-expected);maximum=max(maximum,error)
                if error>max(Decimal('1e-10'),abs(expected)*Decimal('1e-12')):raise ValueError('Independent Decimal price disagreement')
    return dict(rows=len(rows),maximum_absolute_error=str(maximum),uses_reported_factor=False,independent_raw_event_ratio_recalculation=True)


def build_plan():
    registry=guard.load_registry();sources=dict(registry['historical_expected_source_hashes'])
    GAP.merge(sources,{str(SOURCE):LOADED})
    GAP.merge(sources,guard.previous.LOADED)
    observation=read(OBS,OBS_SHA,sources);regular=read(REGULAR,REGULAR_SHA,sources)
    symbols=observation['observed_symbols']
    if len(symbols)!=101 or len(set(symbols))!=101:raise ValueError('101 original observation required')
    refs={r['ticker']:r for r in regular['entries']}
    if set(refs)!={'HONA','SNDK','FER'}:raise ValueError('Exact three existing regular references required')
    captures={}
    for directory,(indexname,indexsha,plansha,count) in guard.previous.ANCHORS.items():
        folder=BASE/directory;index=read(folder/indexname,indexsha,sources)
        for e in index['entries']:
            receipt=read(e['receipt_path'],e['receipt_sha256'],sources);ticker=e['ticker']
            if ticker in captures:raise ValueError('Duplicate channel')
            _,_,_,_=guard.previous.load_capture(ticker=ticker,raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],sources=sources)
            captures[ticker]=receipt
    if set(captures)!=set(symbols):raise ValueError('Exact 22+79 current101 required')
    blocked=set(symbols)&(guard.previous.gap.original.BLOCKED|guard.previous.gap.original.TRANSITIONS|guard.ADDITIONAL_BLOCKED)
    if blocked!={'CMCSA','LRCX','HON','EXC','TRI','WDC'}:raise ValueError('Exact six blocked intersection required')
    tasks=[]
    for ticker in symbols:
        receipt=captures[ticker]
        row=dict(ticker=ticker,raw_path=receipt['raw_path'],raw_sha256=receipt['raw_sha256'],received_at_utc=receipt['received_at_utc'],exclude_on_or_after=receipt['completed_training_excludes_dates_on_or_after'])
        if ticker in refs:
            ref=refs[ticker];doc=read(ref['path'],ref['sha256'],sources)
            GAP.merge(sources,doc['historical_expected_source_hashes'])
            row.update(mode='REFERENCE_EXISTING_REGULAR',reference=ref)
        elif ticker in blocked:row.update(mode='BLOCKED_COMPLEX_OR_IDENTITY',reason='EXPLICIT_GUARD_BLOCK_NO_PRICE_OUTPUT')
        else:row['mode']='NEW_CONDITIONAL_RECONSTRUCTION'
        tasks.append(row)
    counts={mode:sum(t['mode']==mode for t in tasks) for mode in {t['mode'] for t in tasks}}
    if sorted(counts.values())!=[3,6,92]:raise ValueError('92/3/6 partition required')
    checked=GAP.partition(sources,GAP.drift.load_contract(),require_all=True)
    return dict(schema='CURRENT101_CONDITIONAL_PRICE_PLAN_V1',tasks=tasks,counts=counts,output_directory=str(OUTPUT),historical_expected_source_hashes=sources,verified_source_hashes=checked['verified_source_hashes'],historical_price_cache_gap_observations=checked['historical_gap_observations'],provider_dates_are_exchange_calendar=False,historical_full_source_closure_verified=False,price_identity_verified=False,quote_basis_authenticated=False,point_in_time_verified=False,promotion_allowed=False,returns_generated=False,training_performed=False)


def check_output_prefix(output,entries,tasks):
    done=[e['ticker'] for e in entries]
    if done!=[t['ticker'] for t in tasks[:len(done)]]:raise ValueError('External completed prefix differs')
    existing={p.stem for p in output.glob('*.json') if p.name!='plan.json' and not p.name.startswith('index_') and not p.name.startswith('failure_')}
    if existing!=set(done):raise ValueError('Unindexed saved ticker exists; no automatic recomputation')
    if list(output.glob('failure_*.json')):raise ValueError('Recorded failure requires explicit review; no automatic retry')


FALSE_FIELDS=('price_identity_verified','provider_dates_are_exchange_calendar','historical_alias_join_performed','point_in_time_verified','promotion_allowed','returns_generated','training_performed')


def validate_reconstruction_metadata(reconstruction,raw,ticker,request,receipt):
    data=decode(raw);q=data['indicators']['quote'][0]
    day=lambda t:datetime.fromtimestamp(t,timezone.utc).astimezone(guard.previous.nominal.NEW_YORK).date().isoformat()
    daily={day(t):(t,q['open'][i],q['close'][i]) for i,t in enumerate(data['timestamp'])}
    splits=[]
    for event in data.get('events',{}).get('splits',{}).values():
        ratio=Fraction(str(event['numerator']))/Fraction(str(event['denominator']))
        splits.append(dict(effective_session=day(event['date']),provider_timestamp=event['date'],numerator=str(ratio.numerator),denominator=str(ratio.denominator)))
    splits.sort(key=lambda r:r['effective_session'])
    rows=reconstruction['rows'];end=int(parse_qs(urlparse(request['url']).query)['period2'][0])
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    expected=dict(ticker=ticker,row_count=len(rows),provider_quote_session_count=len(daily),provider_split_events=splits,
        raw_sha256=hashlib.sha256(decoded).hexdigest(),requested_event_horizon_end_utc=datetime.fromtimestamp(end,timezone.utc).isoformat(),received_at_utc=receipt,
        quote_field_basis=guard.previous.nominal.BASIS,basis_was_supplied_not_authenticated=True,dividend_event_count=len(data.get('events',{}).get('dividends',{})),dividends_applied_to_quote=False,
        adjclose_used=False,split_event_coverage_scope='RETURNED_PROVIDER_EVENTS_WITHIN_REQUEST_ONLY',official_split_event_completeness_verified=False,provider_price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False)
    actual={k:v for k,v in reconstruction.items() if k!='rows'}
    if json.dumps(actual,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):raise ValueError('Reconstruction metadata differs from raw conditional contract')
    for row in rows:
        timestamp,opened,closed=daily[row['session']];later=[e for e in splits if e['effective_session']>row['session']];factor=Fraction(1)
        for event in later:factor*=Fraction(int(event['numerator']),int(event['denominator']))
        expected=dict(session=row['session'],ticker=ticker,currency='USD',provider_timestamp=timestamp,quote_open=float(opened),quote_close=float(closed),
            split_factor_numerator=str(factor.numerator),split_factor_denominator=str(factor.denominator),split_factor=float(factor),later_split_effective_sessions=[e['effective_session'] for e in later])
        actual={k:v for k,v in row.items() if k not in ('nominal_open','nominal_close')}
        if json.dumps(actual,sort_keys=True,allow_nan=False)!=json.dumps(expected,sort_keys=True,allow_nan=False):raise ValueError('Quote/factor metadata differs from raw independent ratio')


def validate_saved(document,task,plan,plan_sha):
    if any(document.get(k)!=v for k,v in task.items()) or document.get('plan_sha256')!=plan_sha:raise ValueError('Saved complete task coordinate differs')
    if any(document.get(k) is not False for k in FALSE_FIELDS):raise ValueError('Saved task false disclosure differs')
    if task['mode']=='BLOCKED_COMPLEX_OR_IDENTITY':
        expected=dict(task,status='BLOCKED',reconstruction=None,plan_sha256=plan_sha,**{k:False for k in FALSE_FIELDS})
        if document!=expected:raise ValueError('Blocked task must contain no price result')
        return
    if document.get('status')!='CONDITIONAL_PRICE_NOT_IDENTITY':raise ValueError('Conditional result status differs')
    result=document['result']
    if task['mode']=='REFERENCE_EXISTING_REGULAR':
        if result!=read(task['reference']['path'],task['reference']['sha256'],{}):raise ValueError('Regular reference bytes/result differ')
    else:
        if result.get('schema')!='CURRENT_RECEIPT_28_SPECIFIC_EVENT_QUOTE_GUARD_V1':raise ValueError('New result schema differs')
        for key in ('price_identity_verified','point_in_time_verified','promotion_allowed','returns_generated','training_performed','historical_full_source_closure_verified','quote_basis_independently_authenticated','complete_corporate_action_history_verified','old_strict_registry_passed','absence_of_returned_events_proves_no_corporate_actions','original_capture_names_synthesized'):
            if result.get(key) is not False:raise ValueError('Nested result false disclosure differs')
        if result.get('registry_event_count')!=28 or result.get('registry_guard_eligible_event_count')!=26:raise ValueError('Saved event denominator differs')
        nested=result['historical_expected_source_hashes'];parent=plan['historical_expected_source_hashes']
        if any(parent.get(p)!=h for p,h in nested.items()):raise ValueError('Nested source outside bound plan')
        required={**guard.previous.LOADED,str(guard.SOURCE):guard.LOADED,str(guard.FACT):guard.FACT_SHA,task['raw_path']:task['raw_sha256']}
        if any(nested.get(p)!=h for p,h in required.items()):raise ValueError('Missing nested source closure')
        checked=GAP.partition(nested,GAP.drift.load_contract(),require_all=True)
        if result['verified_source_hashes']!=checked['verified_source_hashes'] or result['historical_price_cache_gap_observations']!=checked['historical_gap_observations'] or 'source_hashes' in result:raise ValueError('Nested source partition differs')
        decoded,receipt,request,evidence=guard.previous.load_capture(ticker=task['ticker'],raw_path=task['raw_path'],raw_sha256=task['raw_sha256'],sources={})
        meta=json.loads(decoded)['chart']['result'][0]['meta']
        if (result.get('original_request')!=request or result.get('original_received_at_utc')!=receipt['received_at_utc'] or
            result.get('raw_decoding_evidence')!=evidence or result.get('provider_metadata')!=meta or
            result.get('receipt_day_excluded')!=task['exclude_on_or_after'] or result.get('conditional_quote_basis')!=guard.previous.nominal.BASIS):raise ValueError('Saved original capture coordinates differ')
        eligible=[e for e in guard.load_registry()['events'] if e['simple_split_guard_eligible']]
        matches=GAP.addressed.previous.first_guard.match_returned_events(decoded=decoded,ticker=task['ticker'],specific_events=eligible,blocked_tickers=GAP.original.BLOCKED|GAP.original.TRANSITIONS|guard.ADDITIONAL_BLOCKED|set(guard.previous.PARTITION_REQUIRED))
        known=GAP.addressed.previous.validate_known_event_denominator(ticker=task['ticker'],matches=matches,events=eligible,request=request)
        partition=dict(path=str(guard.previous.SEGMENTS),sha256=guard.previous.SEGMENTS_SHA,whole_channel_block_is_interface_limitation_not_no_valid_interval=True)
        if (result.get('matched_specific_events')!=matches or result.get('known_in_request_event_dates')!=known or
            result.get('partition_required_channels')!=guard.previous.PARTITION_REQUIRED or result.get('listing_partition_evidence')!=partition or
            result.get('additional_complex_tickers_blocked')!=sorted(guard.ADDITIONAL_BLOCKED)):raise ValueError('Saved event/partition witness differs from hard original facts')
    raw=Path(task['raw_path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=task['raw_sha256']:raise ValueError('Saved task raw changed')
    reconstruction=result['reconstruction'];rows=reconstruction['rows']
    if reconstruction['ticker']!=task['ticker'] or reconstruction['row_count']!=len(rows) or any(r['ticker']!=task['ticker'] for r in rows):raise ValueError('Saved price ticker/count differs')
    if task['mode']=='NEW_CONDITIONAL_RECONSTRUCTION':
        data=decode(raw)
        days=[datetime.fromtimestamp(t,timezone.utc).astimezone(guard.previous.nominal.NEW_YORK).date().isoformat() for t in data['timestamp']]
        expected=[d for d in days if d<task['exclude_on_or_after']]
        if [r['session'] for r in rows]!=expected:raise ValueError('Saved full completed calendar differs')
        validate_reconstruction_metadata(reconstruction,raw,task['ticker'],result['original_request'],result['original_received_at_utc'])
    if document['decimal_audit']!=decimal_audit(raw,rows):raise ValueError('Saved Decimal audit differs')


def validate_index(index,plan,plan_sha):
    entries=index.get('entries',[])
    if (index.get('schema')!='CURRENT101_CONDITIONAL_PRICE_INDEX_V1' or index.get('plan_sha256')!=plan_sha or
        type(index.get('completed')) is not int or index['completed']!=len(entries) or index.get('planned')!=101 or
        index.get('status')!=('COMPLETE' if len(entries)==101 else 'PARTIAL') or
        index.get('point_in_time_verified') is not False or index.get('promotion_allowed') is not False):raise ValueError('External index schema/count/status/disclosure differs')
    if [e['ticker'] for e in entries]!=[t['ticker'] for t in plan['tasks'][:len(entries)]]:raise ValueError('External task prefix differs')
    for entry,task in zip(entries,plan['tasks']):
        if entry['mode']!=task['mode'] or entry['path']!=str(OUTPUT/(task['ticker']+'.json')):raise ValueError('Saved mode/address differs')
        validate_saved(read(entry['path'],entry['sha256'],{}),task,plan,plan_sha)
    return entries


def run(plan,plan_sha,*,index_path=None,index_sha=None,max_new=1):
    if type(max_new) is not int or not 1<=max_new<=101:raise ValueError('Explicit bounded task count required')
    if read(OUTPUT/'plan.json',plan_sha,{})!=plan or plan!=build_plan():raise ValueError('Runtime plan must reproduce hard anchors')
    sources=plan['historical_expected_source_hashes'];contract=GAP.drift.load_contract();GAP.partition(sources,contract,require_all=True)
    entries=[]
    if bool(index_path)!=bool(index_sha):raise ValueError('External index and SHA together required')
    if index_path:
        index=read(index_path,index_sha,{})
        entries=validate_index(index,plan,plan_sha)
    check_output_prefix(OUTPUT,entries,plan['tasks'])
    for task in plan['tasks'][len(entries):len(entries)+max_new]:
        ticker=task['ticker']
        try:
            raw=Path(task['raw_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=task['raw_sha256']:raise ValueError('Raw changed')
            if task['mode']=='BLOCKED_COMPLEX_OR_IDENTITY':result=dict(task,status='BLOCKED',reconstruction=None)
            else:
                if task['mode']=='REFERENCE_EXISTING_REGULAR':
                    result=read(task['reference']['path'],task['reference']['sha256'],{})
                else:
                    data=decode(raw)
                    calendar=[datetime.fromtimestamp(t,timezone.utc).astimezone(guard.previous.nominal.NEW_YORK).date().isoformat() for t in data['timestamp']]
                    calendar=[d for d in calendar if d<task['exclude_on_or_after']]
                    result=guard.reconstruct_current_receipt_quote(ticker=ticker,raw_path=task['raw_path'],raw_sha256=task['raw_sha256'],calendar=calendar,quote_field_basis=guard.previous.nominal.BASIS)
                audit=decimal_audit(raw,result['reconstruction']['rows'])
                result=dict(task,status='CONDITIONAL_PRICE_NOT_IDENTITY',result=result,decimal_audit=audit)
            result.update(plan_sha256=plan_sha,price_identity_verified=False,provider_dates_are_exchange_calendar=False,historical_alias_join_performed=False,point_in_time_verified=False,promotion_allowed=False,returns_generated=False,training_performed=False)
            validate_saved(result,task,plan,plan_sha)
            GAP.partition(sources,contract,require_all=True)
            path=OUTPUT/(ticker+'.json');sha=save(path,result)
            entries.append(dict(ticker=ticker,path=str(path),sha256=sha,mode=task['mode']))
            index=dict(schema='CURRENT101_CONDITIONAL_PRICE_INDEX_V1',plan_sha256=plan_sha,entries=entries,completed=len(entries),planned=101,status='COMPLETE' if len(entries)==101 else 'PARTIAL',point_in_time_verified=False,promotion_allowed=False)
            indexpath=OUTPUT/('index_'+str(len(entries)).zfill(3)+'.json');indexsha=save(indexpath,index)
            GAP.partition(sources,contract,require_all=True)
            print(json.dumps(dict(path=str(indexpath),sha256=indexsha,completed=len(entries))),flush=True)
        except Exception as error:
            save(OUTPUT/('failure_'+ticker+'.json'),dict(ticker=ticker,error_type=type(error).__name__,message=str(error),not_classified_as_missing_price=True,no_retry_performed=True))
            raise
    return entries


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--plan-sha');parser.add_argument('--index');parser.add_argument('--index-sha');parser.add_argument('--max-new',type=int,default=1);args=parser.parse_args()
    plan=build_plan();path=OUTPUT/'plan.json'
    if not args.execute:
        OUTPUT.mkdir(exist_ok=False);print(json.dumps(dict(path=str(path),sha256=save(path,plan),reconstructions_run=0)))
    else:
        if not args.plan_sha:parser.error('Externally reviewed plan SHA required')
        if read(path,args.plan_sha,{})!=plan:raise ValueError('Hard plan reconstruction differs')
        run(plan,args.plan_sha,index_path=args.index,index_sha=args.index_sha,max_new=args.max_new)
