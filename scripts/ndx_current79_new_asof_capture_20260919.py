"""Isolated new-asof requests for exactly 79 stale channels; default prepare only."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlparse
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_current_22_price_capture_20260919 as previous
BASE=ROOT/'data/cache/research'
OUTPUT=BASE/'current79_new_asof_capture_20260919_v1'
AUTHORITY=BASE/'current101_completed_asof_plan_20260919_v1/completed_asof_plan.json'
AUTHORITY_SHA='2f52297d061e7df0362a4fbced56b888287b577609877db8c9ac792d7112065b'
ANCHORS={
 'ndx_current_quote_list_capture_20260919_v1/observation.json':'50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77',
 'current_22_price_capture_20260919_v1/coverage_readback.json':'85b7c60865be7a7bfb6f86ee6d6c93b9faa5a5c662a43016911835cebe99556e',
 'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json':'5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),Path(previous.__file__).resolve())}


def verify(sources):
    for path,expected in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise ValueError('Bound new-asof source changed: '+path)


def build_plan():
    authority=previous.read_bound(AUTHORITY,AUTHORITY_SHA)
    observation,new,old=[previous.read_bound(BASE/path,sha) for path,sha in ANCHORS.items()]
    queue=authority['new_asof_update_queue'];tickers=[row['ticker'] for row in queue]
    old_overlap=set(observation['observed_symbols'])&set(old['provider_channels']);new22={row['ticker'] for row in new['rows']}
    if (len(tickers)!=79 or len(set(tickers))!=79 or set(tickers)!=old_overlap or set(tickers)&new22
            or len(new22)!=22 or authority['update_queue_count']!=79):raise ValueError('Exact observed 79 only; never recapture new22')
    for row in queue:
        if row['requested_period1_utc_epoch']!=1640995200 or row['write_directory']!=str(OUTPUT) or row['max_attempts_per_new_asof_request']!=1:
            raise ValueError('Original new-asof request contract differs')
        if row['prior_max_request_period2'] is not None and type(row['prior_max_request_period2']) is not int:
            raise ValueError('Original period2 must be explicit integer or unavailable')
        if row['exact_duplicate_request_forbidden'] is not True or row['existing_raw_preserved'] is not True:
            raise ValueError('Original bytes preservation contract differs')
    sources=dict(authority['source_hashes'])
    for path,sha in ({str(AUTHORITY):AUTHORITY_SHA}|{str(BASE/path):sha for path,sha in ANCHORS.items()}|LOADED).items():
        if path in sources and sources[path]!=sha:raise ValueError('Conflicting source SHA')
        sources[path]=sha
    verify(sources)
    return dict(schema='CURRENT79_NEW_ASOF_RAW_CAPTURE_PLAN_V1',queue=queue,tickers=tickers,
        authority_path=str(AUTHORITY),authority_sha256=AUTHORITY_SHA,source_hashes=sources,output_directory=str(OUTPUT),
        maximum_requests_per_batch=8,request_attempt_limit_per_ticker=1,period1_utc_epoch=1640995200,
        period2_policy='ACTUAL_REQUEST_START_UTC_EPOCH_STRICTLY_AFTER_TICKER_OLD_PERIOD2',
        target_completed_cutoff=authority['latest_observed_completed_cutoff'],
        partial_bar_policy='RECEIPT_NEW_YORK_DATE_AND_LATER_EXCLUDED_FROM_COMPLETED_TRAINING',
        old_missing_receipts_not_backfilled=['GOOGL','FTNT'],new22_recaptured=False,old_raw_overwritten=False,
        returns_generated=False,training_performed=False,historical_identity_verified=False,point_in_time_verified=False,promotion_allowed=False)


def load_plan(path,sha):
    saved=previous.read_bound(path,sha)
    if saved!=build_plan():raise ValueError('New-asof plan does not reproduce exact hard anchors')
    return saved


def check_request(url,ticker,row,prior_urls):
    parsed=urlparse(url);query=parse_qs(parsed.query)
    if (parsed.scheme!='https' or parsed.netloc!='query1.finance.yahoo.com' or parsed.path!='/v8/finance/chart/'+ticker
        or query.get('period1')!=['1640995200'] or query.get('interval')!=['1d'] or query.get('events')!=['div,splits']
        or len(query.get('period2',[]))!=1 or not query['period2'][0].isdigit()):raise ValueError('Exact public chart request required')
    period2=int(query['period2'][0]);old=row['prior_max_request_period2']
    if (old is not None and period2<=old) or url in prior_urls:raise ValueError('New request must be strictly later than prior request')
    return period2


def capture_one(row,output,plan_sha,prior_urls,opener=urlopen):
    ticker=row['ticker'];old=row['prior_max_request_period2']
    if old is not None and int(datetime.now(timezone.utc).timestamp())<=old:
        raise ValueError('Actual new request time has not advanced; do not create an attempt')
    def checked_opener(request,**kwargs):
        # The reused capture function has already fsynced started.json here.
        check_request(request.full_url,ticker,row,prior_urls)
        return opener(request,**kwargs)
    return previous.capture_one(ticker,output,plan_sha,checked_opener)


def run_batch(plan,plan_sha,output,index_path=None,index_sha=None,opener=urlopen):
    output=Path(output)
    if str(output)!=plan['output_directory']:raise ValueError('Dedicated new-asof output root required')
    if bool(index_path)!=bool(index_sha):raise ValueError('External index and SHA required together')
    verify(plan['source_hashes']);entries=[]
    authority=previous.read_bound(AUTHORITY,AUTHORITY_SHA)
    originals={row['ticker']:row for row in authority['rows']}
    if index_path:
        prior=previous.read_bound(index_path,index_sha)
        if prior['schema']!='CURRENT79_NEW_ASOF_COMPLETION_INDEX_V1':raise ValueError('New-asof completion index required')
        entries=previous.checked_entries(prior,output,plan_sha)
    done=[row['ticker'] for row in entries]
    if done!=plan['tickers'][:len(done)]:raise ValueError('External completed prefix differs')
    coordinates={row['ticker']:row for row in plan['queue']}
    for entry in entries:
        receipt=previous.read_bound(entry['receipt_path'],entry['receipt_sha256']);ticker=entry['ticker']
        urls={url for v in originals[ticker]['raw_variants'] for url in v['request_urls']}
        check_request(receipt['request_url'],ticker,coordinates[ticker],urls)
    output.mkdir(parents=True,exist_ok=True)
    attempted={p.name.split('.')[0] for p in output.glob('*.started.json')}
    # Any partial write after a durable attempt remains blocked until an
    # externally reviewed offline reconciliation; never retry automatically.
    if attempted!=set(done):raise ValueError('Unindexed attempt exists; reconcile offline, never retry HTTP')
    batch=plan['tickers'][len(done):len(done)+8]
    if not batch:raise ValueError('New-asof queue already complete')
    for ticker in batch:
        urls={url for v in originals[ticker]['raw_variants'] for url in v['request_urls']}
        entries.append(capture_one(coordinates[ticker],output,plan_sha,urls,opener))
    index=dict(schema='CURRENT79_NEW_ASOF_COMPLETION_INDEX_V1',plan_sha256=plan_sha,output_directory=str(output),entries=entries,
        previous_index_path=str(index_path) if index_path else None,previous_index_sha256=index_sha,
        old_receipts_remain_unchanged=True,old_raw_overwritten=False,new22_recaptured=False,training_performed=False,promotion_allowed=False)
    path=output/('completion_index_'+str(len(entries)).zfill(2)+'.json');sha=previous.save(path,index)
    verify(plan['source_hashes'])
    return dict(path=str(path),sha256=sha,attempted_count=len(entries))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true');parser.add_argument('--plan-sha')
    parser.add_argument('--index');parser.add_argument('--index-sha');args=parser.parse_args();path=OUTPUT/'plan.json'
    if not args.execute:
        plan=build_plan();OUTPUT.mkdir(parents=True,exist_ok=True)
        print(json.dumps(dict(path=str(path),sha256=previous.save(path,plan),network_requests=0)))
    else:
        if not args.plan_sha:parser.error('Explicit reviewed external --plan-sha required')
        plan=load_plan(path,args.plan_sha);print(json.dumps(run_batch(plan,args.plan_sha,OUTPUT,args.index,args.index_sha)))
