"""New immutable-archive authority wrapper; no live-cache equivalence assertion."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_post_action_quote_probe_20260919 as previous
from backtest import ndx_root_price_archive_contract_research as archive
core,capture,interval_plan=previous.core,previous.capture,previous.interval_plan
LOADED=dict(previous.LOADED)
LOADED.update({str(Path(__file__).resolve()):hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),str(archive.SOURCE):archive.LOADED})
SCHEMA='POST_ACTION_FOUR_ARCHIVE_AUTHORITY_QUOTE_PROBE_V2'


def strict_decimal_audit(raw,result):
    if type(result.get('row_count')) is not int or result['row_count']!=len(result['rows']):
        raise ValueError('Actual integer complete row count required')
    for row in result['rows']:
        if type(row.get('factor')) is not int or row['factor']!=1:
            raise ValueError('Actual integer unit factor required; bool forbidden')
    return core.decimal_quote_audit(raw,result)


def partition(sources):
    contract=archive.load_contract()
    value=archive.verify_expected_sources(sources,contract)
    # All 111 authority bytes are checked, but this quote has no root-CSV input.
    # Do not add unrelated original CSV pointers to pretend they were dependencies.
    if set(sources)&set(contract['rows']) or value['archive_resolutions'] or value['historical_gap_observations']:
        raise ValueError('Unexpected historical root price dependency in four-quote input')
    return value


def prepare(ticker):
    """Read-only source and receipt preflight; does not reconstruct prices."""
    if ticker not in core.interval.SUPPORTED:raise ValueError('Only four reviewed post-action boundaries')
    plan=interval_plan.build();row,=[r for r in plan['rows'] if r['ticker']==ticker]
    sources=dict(LOADED);archive.merge(sources,plan['source_hashes'])
    decoded,receipt,request,evidence=capture.load_capture(ticker=ticker,raw_path=row['raw_path'],raw_sha256=row['raw_sha256'],sources=sources)
    if (row['decoded_sha256']!=evidence['decoded_sha256']
            or receipt['completed_training_excludes_dates_on_or_after']!=row['proposed_interval']['completed_before']):
        raise ValueError('Hard plan/receipt coordinates differ')
    checked=partition(sources)
    return row,decoded,receipt,request,evidence,sources,checked


def verify(value):
    if value.get('schema')!=SCHEMA:raise ValueError('New archive wrapper schema required')
    expected=value['historical_expected_source_hashes']
    if any(expected.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded wrapper source omitted')
    if partition(expected)!=value['archive_resolution']:raise ValueError('Exact archive/strict source partition differs')
    if (value['archive_authority_counts']!=dict(total=111,exact_expected_historical_bytes=85,sealed_unrecovered_observations=26)
            or type(value['actual_root_price_csv_dependency_count']) is not int or value['actual_root_price_csv_dependency_count']!=0):
        raise ValueError('Authority and actual input dependencies must remain distinct')
    for key in ('original_live_root_paths_verified','original_26_observations_asserted_live_unchanged',
        'historical_full_source_closure_recovered','price_identity_verified','point_in_time_verified','promotion_allowed',
        'old_whole_channel_guard_called','old_nominal_reconstruction_called','returns_generated','training_performed'):
        if value.get(key) is not False:raise ValueError('Unverified research scope upgraded')
    if type(value['result']['row_count']) is not int or value['result']['row_count']!=len(value['result']['rows']):raise ValueError('Integer row count required')
    if any(type(r['factor']) is not int or r['factor']!=1 for r in value['result']['rows']):raise ValueError('Integer unit factors required')


def build(ticker):
    row,decoded,receipt,request,evidence,sources,_=prepare(ticker)
    floor,cusip,role=core.interval.SUPPORTED[ticker]
    result=core.reconstruct_post_action_quote(raw=decoded,ticker=ticker,calendar=row['proposed_interval']['calendar'],
        official_boundary=dict(ticker=ticker,first_post_action_session=floor,post_action_cusip=cusip,role=role),
        request=request,received_at_utc=receipt['received_at_utc'],quote_field_basis=core.BASIS)
    if result['returned_split_like_events']!=row['all_returned_events']:raise ValueError('Every original split-like event must remain')
    decimal=strict_decimal_audit(decoded,result)
    value=dict(schema=SCHEMA,ticker=ticker,result=result,decimal_audit=decimal,original_interval_plan_row=row,raw_decoding_evidence=evidence,
        historical_expected_source_hashes=sources,archive_resolution=partition(sources),
        archive_authority_counts=dict(total=111,exact_expected_historical_bytes=85,sealed_unrecovered_observations=26),
        actual_root_price_csv_dependency_count=0,original_live_root_paths_verified=False,original_26_observations_asserted_live_unchanged=False,
        historical_full_source_closure_recovered=False,price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False,
        old_whole_channel_guard_called=False,old_nominal_reconstruction_called=False,old_sources_modified=False,
        returns_generated=False,training_performed=False,live_state_modified=False)
    verify(value);return value


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only archive quote probe')
    verify(value);saved=previous.publish(path,value);verify(value);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ticker',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.ticker))))
