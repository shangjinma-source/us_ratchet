"""Bound TSM response observations at fixed 2026-09-17; no return generation."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current101_price_independent_audit_20260919 as raw_reader
BASE=ROOT/'data/cache/research'
FOLDER=BASE/'current_tsm_raw_capture_20260919_v1'
INDEX=FOLDER/'index.json';INDEX_SHA='a8746baefec9de164f288f441b7d7a456a073b0787d0563edce57a29d229a9bc'
PLAN=FOLDER/'plan.json';PLAN_SHA='a51b093c485aa66ef34dcc13be943e91b3b7940cb43d29c196d5d3bdad0daca7'
REFERENCE=BASE/'current101_conditional_prices_20260919_v1/archive_independent_audit_20260919.json'
REFERENCE_SHA='7fb3a17fe7234a77383d1dd0ae2868f3d4002799419233b3df4b5b418d6297e6'
CUTOFF='2026-09-17'
LOADED=dict(raw_reader.LOADED)
LOADED[str(Path(__file__).resolve())]=raw_reader.drift.file_sha(__file__)


def summarize(info,receipt_day,reference):
    if not reference or reference[-1]!=CUTOFF or reference!=sorted(set(reference)):raise ValueError('Fixed reviewed target calendar required')
    valid=[];null=[]
    for i,date in enumerate(info['days']):
        try:
            for k in ('open','close'):raw_reader.number(info['quotes'][k][i])
        except ValueError:null.append(date)
        else:valid.append(date)
    completed=[d for d in valid if d<receipt_day]
    target=[d for d in completed if d<=CUTOFF]
    required=reference[-5:]
    return dict(full_timestamp_slot_count=len(info['days']),raw_first_date=info['days'][0],raw_last_date=info['days'][-1],
                valid_open_close_count=len(valid),invalid_or_null_open_close_dates=null,receipt_completed_calendar=completed,
                target_cutoff=CUTOFF,target_completed_calendar=target,excluded_after_fixed_target=[d for d in completed if d>CUTOFF],
                excluded_receipt_or_later_dates=[d for d in info['days'] if d>=receipt_day],required_last_five_observed_sessions=required,
                missing_last_five=[d for d in required if d not in target],target_cutoff_covered=CUTOFF in target,
                completed_raw_not_independently_exchange_calendar=True)


def verify(sources):
    for p,h in sources.items():
        if raw_reader.drift.file_sha(p)!=h:raise ValueError('Bound TSM readback source changed: '+p)


def build():
    sources=dict(LOADED)
    def read(p,h,json_value=True):
        p=str(Path(p).resolve());data=Path(p).read_bytes()
        if raw_reader.digest(data)!=h:raise ValueError('Externally bound bytes differ')
        if p in sources and sources[p]!=h:raise ValueError('Source collision')
        sources[p]=h
        return raw_reader.loads(data) if json_value else data
    index=read(INDEX,INDEX_SHA);plan=read(PLAN,PLAN_SHA)
    if (index['schema']!='INCUMBENT_TSM_NEW_ASOF_RAW_INDEX_V1' or index['plan']!=dict(path=str(PLAN),sha256=PLAN_SHA)
        or plan['schema']!='INCUMBENT_TSM_NEW_ASOF_RAW_PLAN_V1' or plan['ticker']!='TSM'
        or plan['target_completed_cutoff']!=CUTOFF or index['target_completed_cutoff']!=CUTOFF):raise ValueError('Fixed TSM incumbent target differs')
    for p,h in plan['source_hashes'].items():
        if p in sources and sources[p]!=h:raise ValueError('Source collision')
        sources[p]=h
    if index['source_hashes']!=plan['source_hashes']:raise ValueError('Original capture closure differs')
    verify(sources)
    entry=index['entry']
    if entry['ticker']!='TSM' or Path(entry['receipt_path'])!=FOLDER/'TSM.receipt.json' or Path(entry['decoded_path'])!=FOLDER/'TSM.decoded.json':raise ValueError('Exact response addresses required')
    receipt=read(entry['receipt_path'],entry['receipt_sha256']);started=read(FOLDER/'TSM.started.json',receipt['started_sha256'])
    if receipt['plan_sha256']!=PLAN_SHA or Path(receipt['raw_path'])!=FOLDER/'TSM.response.bin':raise ValueError('Original request coordinates differ')
    raw=read(receipt['raw_path'],receipt['raw_sha256'],False);info=raw_reader.inspect_raw(raw,'TSM')
    raw_reader.verify_request(dict(ticker='TSM',received_at_utc=receipt['received_at_utc'],exclude_on_or_after=receipt['completed_training_excludes_dates_on_or_after']),receipt,started,info)
    if started['period2_utc_epoch']<=plan['prior_max_request_period2'] or receipt['raw_bytes']!=len(raw):raise ValueError('New-asof horizon/bytes differ')
    parsed=read(entry['decoded_path'],entry['decoded_sha256'])
    if parsed['ticker']!='TSM' or parsed['receipt_sha256']!=entry['receipt_sha256'] or parsed['decoded_sha256']!=info['decoded_sha256'] or parsed['provider_error'] is not None:raise ValueError('Decode evidence differs')
    reference=read(REFERENCE,REFERENCE_SHA)['common_95_conditional_provider_calendar']
    coverage=summarize(info,receipt['completed_training_excludes_dates_on_or_after'],reference)
    dividends=[];seen=set()
    for key,event in info['data'].get('events',{}).get('dividends',{}).items():
        d=raw_reader.day(event['date']);raw_reader.number(event['amount'])
        if key!=str(event['date']) or d in seen or d not in info['days'] or not plan['period1']<=event['date']<=started['period2_utc_epoch']:raise ValueError('Dividend date/value denominator differs')
        seen.add(d);dividends.append(dict(session=d,**event))
    result=dict(schema='INCUMBENT_TSM_NEW_ASOF_RAW_INDEPENDENT_READBACK_V1',index_ref=dict(path=str(INDEX),sha256=INDEX_SHA),
                source_hashes=sources,coverage=coverage,provider_metadata=info['data']['meta'],received_at_utc=receipt['received_at_utc'],
                receipt_day_excluded=receipt['completed_training_excludes_dates_on_or_after'],raw_sha256=receipt['raw_sha256'],decoded_sha256=info['decoded_sha256'],
                raw_path=receipt['raw_path'],request_url=receipt['request_url'],returned_split_events=info['events'],returned_dividend_events=dividends,
                returned_event_kinds=sorted(info['data'].get('events',{})),old_raw_reference=dict(path=plan['original_raw_path'],sha256=plan['original_raw_sha256']),
                prior_request_period2=plan['prior_max_request_period2'],new_request_period2=started['period2_utc_epoch'],
                fixed_99_target_cutoff_upgraded=False,raw_identity_or_quote_basis_authenticated=False,nominal_prices_reconstructed=False,
                complete_actions_verified=False,ndx_membership_claimed=False,old_gap_report_modified=False,returns_generated=False,
                training_performed=False,point_in_time_verified=False,promotion_allowed=False)
    verify(sources);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();result=build()
    with Path(args.output).open('x',encoding='utf8') as stream:json.dump(result,stream,sort_keys=True,indent=2,allow_nan=False);stream.write('\n')
    verify(result['source_hashes'])
    print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=raw_reader.drift.file_sha(args.output),raw_rows=result['coverage']['full_timestamp_slot_count'],target_rows=len(result['coverage']['target_completed_calendar']),missing_last_five=result['coverage']['missing_last_five'],split_count=len(result['returned_split_events']),dividend_count=len(result['returned_dividend_events']))))
