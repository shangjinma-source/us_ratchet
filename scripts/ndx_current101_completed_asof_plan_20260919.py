"""Current 101 observed channels: completed raw-date inventory and new-asof plan."""
from datetime import datetime,timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlparse
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research';NY=ZoneInfo('America/New_York')
ANCHORS={
 'ndx_current_quote_list_capture_20260919_v1/observation.json':'50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77',
 'current_22_price_capture_20260919_v1/coverage_readback.json':'85b7c60865be7a7bfb6f86ee6d6c93b9faa5a5c662a43016911835cebe99556e',
 'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json':'5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117'}


def main():
    observed_at=datetime.now(timezone.utc);sources={}
    def read(path,expected):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==expected,path
        assert path not in sources or sources[path]==expected;sources[path]=expected
        return raw
    observation,new,old=[json.loads(read(BASE/path,sha)) for path,sha in ANCHORS.items()]
    symbols=observation['observed_symbols'];assert len(symbols)==len(set(symbols))==101
    newrows={row['ticker']:row for row in new['rows']};assert len(newrows)==22
    assert set(newrows)==set(symbols)-set(old['provider_channels'])
    sys.path.insert(0,str(ROOT))
    sys.path.append(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages')
    from backtest import ndx_specific_split_registry_v2_research as registry
    registry_status='NOT_VERIFIED';registry_error=None
    try:
        result=registry.load_registry();registry_status='HISTORICAL_REGISTRY_SOURCE_CLOSURE_VERIFIED'
        for path,sha in result['source_hashes'].items():read(path,sha)
    except ValueError as error:registry_error=str(error)
    registry_file=Path(registry.__file__).resolve();sources[str(registry_file)]=hashlib.sha256(registry_file.read_bytes()).hexdigest()
    rows=[];latest_new_dates=[];regular_periods=[]
    for ticker in symbols:
        variants=[]
        if ticker in newrows:
            raw=newrows[ticker]
            descriptors=[dict(path=raw['raw_path'],sha256=raw['raw_sha256'],references=[dict(received_at_utc=raw['received_at_utc'],request_url=raw['request_url'])])]
        else:descriptors=old['provider_channels'][ticker]
        for descriptor in descriptors:
            raw=read(descriptor['path'],descriptor['sha256'])
            decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
            chart=json.loads(decoded)['chart'];assert chart['error'] is None and len(chart['result'])==1
            data=chart['result'][0];meta=data['meta'];assert meta['symbol']==ticker
            times=data.get('timestamp',[]);quote,=data['indicators']['quote'];assert len(quote['open'])==len(quote['close'])==len(times)
            receipts=[datetime.fromisoformat(ref['received_at_utc']) for ref in descriptor['references'] if ref.get('received_at_utc')]
            cutoff=min(receipts).astimezone(NY).date().isoformat() if receipts else None
            calendar=[datetime.fromtimestamp(ts,timezone.utc).astimezone(NY).date().isoformat() for ts in times]
            assert calendar==sorted(set(calendar))
            completed=[];zero_volume=[]
            for i,day in enumerate(calendar):
                finite=all(type(quote[key][i]) in (int,float) and math.isfinite(quote[key][i]) and quote[key][i]>0 for key in ('open','close'))
                if finite and cutoff and day<cutoff:completed.append(day)
                if finite and quote.get('volume',[None]*len(times))[i]==0:zero_volume.append(day)
            events=[]
            for key,event in data.get('events',{}).get('splits',{}).items():
                events.append(dict(provider_key=key,**event,session=datetime.fromtimestamp(event['date'],timezone.utc).astimezone(NY).date().isoformat()))
            regular=meta.get('currentTradingPeriod',{}).get('regular')
            if ticker in newrows and regular:
                regular_periods.append(dict(ticker=ticker,start_utc=datetime.fromtimestamp(regular['start'],timezone.utc).isoformat(),
                    end_utc=datetime.fromtimestamp(regular['end'],timezone.utc).isoformat(),asof_before_reported_regular_end=observed_at.timestamp()<regular['end']))
            urls=[ref['request_url'] for ref in descriptor['references'] if ref.get('request_url')]
            period2=[int(parse_qs(urlparse(url).query)['period2'][0]) for url in urls if 'period2' in parse_qs(urlparse(url).query)]
            variants.append(dict(path=descriptor['path'],sha256=descriptor['sha256'],request_urls=urls,request_period2_epochs=period2,
                actual_receipts_utc=[x.isoformat() for x in receipts],receipt_day_excluded=cutoff,
                latest_observed_date=calendar[-1] if calendar else None,latest_completed_finite_open_close_date=max(completed) if completed else None,
                completed_dates=completed,completed_finite_open_close_count=len(completed),zero_volume_finite_bar_dates=zero_volume,
                provider_currency=meta.get('currency'),provider_exchange=meta.get('exchangeName'),provider_symbol=meta['symbol'],returned_splits=events))
        eligible=[v['latest_completed_finite_open_close_date'] for v in variants if v['latest_completed_finite_open_close_date']]
        latest=max(eligible) if eligible else None
        if ticker in newrows and latest:latest_new_dates.append(latest)
        splits=[event for v in variants for event in v['returned_splits']]
        if ticker in registry.TRANSITIONS:guard='BLOCKED_EXPLICIT_SECURITY_IDENTITY_TRANSITION'
        elif ticker in registry.BLOCKED:guard='BLOCKED_COMPLEX_CORPORATE_ACTION'
        elif splits:guard='RETURNED_SPLIT_EVENTS_REQUIRE_CURRENT_GUARD_REVALIDATION'
        else:guard='NO_RETURNED_SPLITS_OBSERVED_NOT_ACTION_COMPLETENESS'
        rows.append(dict(ticker=ticker,channel_cohort='NEW_22_RECEIPTS' if ticker in newrows else 'PRIOR_107_CHANNEL_OVERLAP',
            latest_completed_finite_open_close_date=latest,raw_variants=variants,split_guard_status=guard,
            registry_source_status=registry_status,quote_basis_authenticated=False,provider_symbol_is_not_security_identity=True,
            historical_identity_verified=False,current_security_identity_adjudicated=False,tradable_admission=False))
    # This is an observed completed candidate cutoff, not an exchange-calendar certification.
    target=max(latest_new_dates);assert target<observed_at.astimezone(NY).date().isoformat()
    queue=[]
    for row in rows:
        have=set(day for v in row['raw_variants'] for day in v['completed_dates'])
        row['covers_observed_latest_completed_cutoff']=target in have
        if target not in have:
            periods=[n for v in row['raw_variants'] for n in v['request_period2_epochs']]
            queue.append(dict(ticker=row['ticker'],reason='NEW_ASOF_CAPTURE_NEEDED_FOR_LATER_COMPLETED_CUTOFF',target_completed_cutoff=target,
                prior_latest_completed_date=row['latest_completed_finite_open_close_date'],prior_max_request_period2=max(periods) if periods else None,
                requested_period1_utc_epoch=1640995200,requested_period2_policy='ACTUAL_NEW_REQUEST_START_UTC_STRICTLY_GREATER_THAN_PRIOR_MAX',
                existing_raw_preserved=True,write_directory=str(BASE/'current79_new_asof_capture_20260919_v1'),
                exact_duplicate_request_forbidden=True,max_attempts_per_new_asof_request=1,
                request_purpose='ISOLATED_NEW_ASOF_OBSERVATION_NOT_RETRY_OF_PRIOR_CAPTURE',identity_and_action_admission=False))
    dates=[row['latest_completed_finite_open_close_date'] for row in rows]
    common=set(rows[0]['raw_variants'][0]['completed_dates'])
    for row in rows:
        common&={day for v in row['raw_variants'] for day in v['completed_dates']}
    for row in rows:
        for variant in row['raw_variants']:variant.pop('completed_dates')
    sources[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for path,sha in sources.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha,path
    report=dict(schema='ndx_current101_completed_asof_raw_update_plan_20260919_v1',source_hashes=sources,
        observed_at_utc=observed_at.isoformat(),observed_at_new_york=observed_at.astimezone(NY).isoformat(),
        provider_regular_period_observations=regular_periods,observed_pool_count=101,prior_overlap_count=79,new_capture_count=22,
        latest_observed_completed_cutoff=target,official_exchange_calendar_verified=False,
        latest_shared_completed_date_all101=max(common) if common else None,
        completed_cutoff_covered_count=101-len(queue),update_queue_count=len(queue),rows=rows,new_asof_update_queue=queue,
        split_registry_source_status=registry_status,split_registry_source_error=registry_error,
        complete_original_registry_provenance_verified=registry_status=='HISTORICAL_REGISTRY_SOURCE_CLOSURE_VERIFIED',
        old_raw_overwritten=False,http_requests_performed=0,training_performed=False,returns_generated=False,
        latest_current_membership_certified=False,point_in_time_verified=False,promotion_allowed=False)
    folder=BASE/'current101_completed_asof_plan_20260919_v1';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'completed_asof_plan.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),cutoff=target,update_count=len(queue),
                         common_completed=report['latest_shared_completed_date_all101'],sources=len(sources),registry_status=registry_status)))


if __name__=='__main__':main()
