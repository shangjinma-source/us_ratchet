"""Explicit one-ticker post-action quote probe; never executes at import."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_post_action_quote_research as core
from backtest import ndx_current_receipt_quote_guard_research as capture
from scripts import ndx_post_action_interval_plan_20260919 as interval_plan
from scripts.ndx_base_three_cell_window_delta_research import publish

DIRECT=(Path(__file__).resolve(),Path(core.__file__).resolve(),Path(core.interval.__file__).resolve(),
    Path(interval_plan.__file__).resolve(),Path(capture.__file__).resolve(),Path(capture.gap.__file__).resolve(),
    Path(capture.gap.drift.__file__).resolve(),Path(capture.nominal.__file__).resolve(),
    Path(capture.gap.addressed.previous.first_guard.decode_bound_raw.__code__.co_filename).resolve(),
    Path(capture.gap.addressed.__file__).resolve(),Path(capture.gap.addressed.previous.__file__).resolve(),
    Path(publish.__code__.co_filename).resolve())
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in DIRECT}


def verify(value):
    sources=value['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded quote probe dependency omitted')
    checked=capture.gap.partition(sources,capture.gap.drift.load_contract())
    if checked['verified_source_hashes']!=value['verified_source_hashes'] or checked['historical_gap_observations']!=value['historical_price_cache_gap_observations']:
        raise ValueError('Source partitions changed')
    for k in ('historical_full_source_closure_verified','price_identity_verified','point_in_time_verified','promotion_allowed','training_performed','returns_generated'):
        if value[k] is not False:raise ValueError('Unsupported research claim')


def build(ticker):
    if ticker not in core.interval.SUPPORTED:raise ValueError('Only independently reviewed four boundaries')
    plan=interval_plan.build();row,=[r for r in plan['rows'] if r['ticker']==ticker]
    proposal=row['proposed_interval'];sources=dict(LOADED);capture.gap.merge(sources,plan['source_hashes'])
    decoded,receipt,request,evidence=capture.load_capture(ticker=ticker,raw_path=row['raw_path'],raw_sha256=row['raw_sha256'],sources=sources)
    if (row['decoded_sha256']!=evidence['decoded_sha256'] or receipt['completed_training_excludes_dates_on_or_after']!=proposal['completed_before']):
        raise ValueError('Plan and hard original receipt differ')
    floor,cusip,role=core.interval.SUPPORTED[ticker]
    capture.gap.partition(sources,capture.gap.drift.load_contract())
    result=core.reconstruct_post_action_quote(raw=decoded,ticker=ticker,calendar=proposal['calendar'],
        official_boundary=dict(ticker=ticker,first_post_action_session=floor,post_action_cusip=cusip,role=role),
        request=request,received_at_utc=receipt['received_at_utc'],quote_field_basis=core.BASIS)
    if result['returned_split_like_events']!=row['all_returned_events']:raise ValueError('No raw split-like event may be removed')
    decimal=core.decimal_quote_audit(decoded,result)
    checked=capture.gap.partition(sources,capture.gap.drift.load_contract())
    output=dict(schema='POST_ACTION_FOUR_CONDITIONAL_QUOTE_PROBE_V1',ticker=ticker,result=result,decimal_audit=decimal,
        original_interval_plan_row=row,raw_decoding_evidence=evidence,historical_expected_source_hashes=sources,
        verified_source_hashes=checked['verified_source_hashes'],historical_price_cache_gap_observations=checked['historical_gap_observations'],
        old_whole_channel_guard_called=False,old_nominal_reconstruction_called=False,old_sources_modified=False,
        historical_full_source_closure_verified=False,price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False,
        training_performed=False,returns_generated=False,live_state_modified=False)
    verify(output);return output


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only quote probe')
    verify(value);saved=publish(path,value);verify(value);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ticker',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.ticker))))
