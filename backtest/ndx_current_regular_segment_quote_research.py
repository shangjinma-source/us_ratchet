"""Explicit regular-date partition for three channels; never historical alias stitching."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from types import FunctionType
from backtest import ndx_current_receipt_quote_guard_research as original

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
FLOORS={'HONA':'2026-06-29','SNDK':'2025-02-24','FER':'2024-05-09'}


def reconstruct_regular_segment_quote(*,ticker,raw_path,raw_sha256,calendar,quote_field_basis):
    if ticker not in FLOORS:raise ValueError('Only three explicit regular-date partitions supported')
    if type(calendar) is not list or not calendar or calendar!=sorted(set(original.nominal._day(d) for d in calendar)):
        raise ValueError('Explicit unique ascending calendar required')
    if calendar[0]<FLOORS[ticker]:raise ValueError('Requested calendar crosses regular-way floor; no silent filtering')
    expected={str(SOURCE):LOADED};segments=original.read(original.SEGMENTS,original.SEGMENTS_SHA,expected)
    original.gap.merge(expected,segments['source_hashes'])
    rows=[r for r in segments['rows'] if r['ticker']==ticker]
    if len(rows)!=1 or rows[0]['official_regular_way_start']!=FLOORS[ticker]:raise ValueError('Hard official regular boundary differs')
    original.nominal.verify(expected)
    # Private invocation changes only this explicitly scoped date partition.
    # The original whole-channel guard and every original global remain intact.
    loaded=dict(original.LOADED);original.gap.merge(loaded,{str(SOURCE):LOADED})
    function=original.reconstruct_current_receipt_quote
    scoped=FunctionType(function.__code__,dict(function.__globals__,PARTITION_REQUIRED={},LOADED=loaded),function.__name__,function.__defaults__,function.__closure__)
    try:
        result=scoped(ticker=ticker,raw_path=raw_path,raw_sha256=raw_sha256,calendar=calendar,quote_field_basis=quote_field_basis)
        capture_sources={}
        decoded,_,_,_=original.load_capture(ticker=ticker,raw_path=raw_path,raw_sha256=raw_sha256,sources=capture_sources)
        original.gap.merge(result['historical_expected_source_hashes'],capture_sources)
        body=json.loads(decoded,object_pairs_hook=original.nominal._unique_pairs)['chart']['result'][0]
        dates=[datetime.fromtimestamp(t,timezone.utc).astimezone(original.nominal.NEW_YORK).date().isoformat() for t in body['timestamp']]
        pre=[d for d in dates if d<FLOORS[ticker]]
        result.update(schema='CURRENT_EXPLICIT_REGULAR_DATE_PARTITION_QUOTE_V1',regular_way_floor=FLOORS[ticker],
            partition_required_channels=dict(original.PARTITION_REQUIRED),partition_mode='EXPLICIT_CALLER_CALENDAR_ALL_ON_OR_AFTER_OFFICIAL_REGULAR_DATE',
            pre_regular_provider_dates=pre,pre_regular_provider_date_count=len(pre),full_provider_row_count=len(dates),
            raw_rows_deleted_or_rewritten=False,all_raw_events_still_subject_to_original_guard=True,
            historical_alias_labels_generated=False,regular_date_evidence_is_provider_identity_authentication=False,
            first_regular_return_requires_previous_regular_session=True,returns_generated=False,
            price_identity_verified=False,conditional_regular_date_eligibility_only=True)
        for row in result['reconstruction']['rows']:row['coordinate_scope']='REGULAR_US_DATE_ELIGIBLE_CONDITIONAL_PROVIDER_CHANNEL'
        contract=original.gap.drift.load_contract()
        return original.gap.attach_partition(result,result['historical_expected_source_hashes'],original.gap.partition(result['historical_expected_source_hashes'],contract,require_all=True))
    finally:original.nominal.verify(expected)
