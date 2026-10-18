"""One actual AMZN reconstruction across original required sessions; no returns."""
from datetime import datetime
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_simple_split_exact_gap_research as guard
SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
BASE=ROOT/'data/cache/research'


def build():
    sources={str(SOURCE):LOADED}
    def bound(path,expected):
        path=Path(path);raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('External source differs')
        guard.original.merge_source(sources,path,expected)
        return raw
    def read(path,expected):return json.loads(bound(path,expected))
    index=read(BASE/'provider_gap_batch12_capture_20260912_v1/completed_queue_sha_event_index.json',
               '5d9d2b55d88441045c3b3c98cfb0c33687a707da030266ff028e151b35357117')
    prior=read(BASE/'provider_gap_batch12_capture_20260912_v1/coverage_addendum.json',
               '6fc0d5ee29cecb12ae70433fece84cd43e64ae90030aa92fe00f95880a3b1b22')
    variant,=index['provider_channels']['AMZN']
    reference,=variant['references']
    batch,=[row for row in index['batches'] if row['manifest_path']==reference['manifest_path']]
    manifest=read(batch['manifest_path'],batch['manifest_sha256'])
    capture,=[row for row in manifest['probes'] if row['ticker']=='AMZN']
    if capture['response_path']!=variant['path'] or capture['response_sha256']!=variant['sha256']:
        raise ValueError('Manifest raw coordinate differs')
    calendar=sorted({day for required in prior['calendar_requirements'].values()
                     for day in set(required['return_dates'])|set(required['previous_close_by_return_date'].values())})
    if not {'2022-06-03','2022-06-06'}<=set(calendar):raise ValueError('Split boundary absent')
    result=guard.reconstruct_raw_addressed_nominal_quote(provider_manifest_path=batch['manifest_path'],
        provider_manifest_sha256=batch['manifest_sha256'],raw_path=variant['path'],raw_sha256=variant['sha256'],
        ticker='AMZN',calendar=calendar,quote_field_basis=guard.nominal.BASIS)
    guard.merge(sources,result['historical_expected_source_hashes'])
    raw=bound(variant['path'],variant['sha256']);decoded=gzip.decompress(raw)
    if hashlib.sha256(decoded).hexdigest()!=capture['decoded_sha256']:raise ValueError('Decoded source differs')
    chart,=json.loads(decoded)['chart']['result'];quote,=chart['indicators']['quote']
    original={datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat():
              (quote['open'][i],quote['close'][i]) for i,t in enumerate(chart['timestamp'])}
    events=chart['events']['splits']
    if len(events)!=1:raise ValueError('Unexpected AMZN event denominator')
    event,=events.values()
    if (event['numerator']!=20 or event['denominator']!=1 or event['splitRatio']!='20:1' or
        datetime.fromtimestamp(event['date'],ZoneInfo('America/New_York')).date().isoformat()!='2022-06-06'):
        raise ValueError('Actual AMZN split event differs')
    rows=result['reconstruction']['rows']
    if len(rows)!=len(calendar):raise ValueError('Requested session denominator differs')
    maximum=Decimal(0);before=after=0
    for row,day in zip(rows,calendar):
        if row['session']!=day:raise ValueError('Independent session coordinate differs')
        factor=20 if day<'2022-06-06' else 1
        if factor==20:before+=1
        else:after+=1
        if row['split_factor']!=factor:raise ValueError('Independent split factor differs')
        for field,i in [('open',0),('close',1)]:
            independent=Decimal(str(original[day][i]))*factor
            delta=abs(Decimal(str(row['nominal_'+field]))-independent)
            maximum=max(maximum,delta)
            if delta>Decimal('0.00000001'):raise ValueError('Independent raw component differs')
    checked=guard.partition(sources,guard.drift.load_contract(),require_all=True)
    result.update(schema='AMZN_ACTUAL_NOMINAL_RECONSTRUCTION_EXACT_GAP_PROBE_20260919_V1',
        calendar=calendar,calendar_scope='UNION_OF_15_ORIGINAL_RETURN_DATES_AND_EACH_REQUIRED_PREVIOUS_CLOSE',
        observed_session_calendar_not_independently_certified=True,
        independent_component_check=dict(method='DECIMAL_RAW_QUOTE_TIMES_OFFICIAL_20_BEFORE_20220606_ELSE_1',
            all_requested_rows_checked=len(rows),factor20_rows=before,factor1_rows=after,
            maximum_absolute_open_close_error=str(maximum),raw_returned_split_count=1,
            split_boundary_rows=[row for row in rows if row['session'] in ('2022-06-03','2022-06-06')]),
        quote_field_basis_is_explicit_conditional_input=True,source_price_identity_authenticated=False,
        economic_returns_generated=False,training_performed=False,orders_executed=False,network_requests=0)
    return guard.attach_partition(result,sources,checked)


if __name__=='__main__':
    report=build();folder=BASE/'amzn_exact_gap_nominal_probe_20260919_v1';folder.mkdir(parents=True,exist_ok=True)
    path=folder/'nominal_quote_reconstruction.json'
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as handle:handle.write(raw)
    checked=guard.partition(report['historical_expected_source_hashes'],guard.drift.load_contract(),require_all=True)
    if checked['verified_source_hashes']!=report['verified_source_hashes']:raise ValueError('Source partition changed after publication')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),independent=report['independent_component_check'])))
