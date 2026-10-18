"""Sealed 20-channel, 253-price retrospective input; no fit or execution."""
import argparse
import bisect
import csv
import gzip
import hashlib
import io
import json
import math
import sys
from datetime import date,datetime,timezone
from decimal import Decimal,localcontext
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from backtest import ndx_conditional_historical_price_panel_research as pure
from scripts import ndx_latest_fourteen_panel_independent_readback_20260919 as fourteen
from scripts.ndx_latest_conditional_channels_20260919 import exclusive_publish
BASE=fourteen.BASE
PURE_PATH=ROOT/'backtest/ndx_conditional_historical_price_panel_research.py'
PURE_SHA='e345844ffd33fc5fc6ff34b8f4a25f0cf1d60c02c6d3fe726d468e865b64018f'
REFS={
 'panel':fourteen.PANEL,
 'inventory':dict(path=str(BASE/'current99_conditional_price_inventory_20260919_v1/inventory.json'),sha256='59ebaf50fdf35c6c390a747de026bc353200f64525b9c30f3e14d935aba209f3'),
 'readiness':dict(path=str(BASE/'latest_conditional_input_readiness_20260919_v1/readiness.json'),sha256='b3a215d05cfb085c4637713d65fb86d565def48728cb382efe94ad1e206d3c49'),
 'snapshot':dict(path=str(BASE/'latest_conditional_input_readiness_20260919_v1/observed_inputs/manifest.json'),sha256='7d6faadb89ab130eabfb2f227f19fe5b75efdad98a73c772077430f7a39800c1'),
 'control':dict(path=str(BASE/'ndx_original_8_control_v1/manifest.json'),sha256='2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260'),
 'tsm':dict(path=str(BASE/'current_tsm_raw_capture_20260919_v1/conditional_nominal_quotes_20260919.json'),sha256='b51abeb8b9ef5b1b5cf6f9b8b2a6aaf797091ec02a65f5297d7326c4f7fbc2a3')}
FALSE=('fit_performed','execution_performed','point_in_time_verified','legal_training_input_admitted','promotion_allowed','winner_selected','latest_weights_backfilled','historical_liquidity_admission_verified','historical_risk_labels_verified','nav_publication_time_verified','currency_and_fx_alignment_verified','complete_corporate_actions_verified')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(fourteen.__file__).resolve(),Path(exclusive_publish.__code__.co_filename).resolve(),PURE_PATH)}


def exact(a,b):return fourteen.exact(a,b)
def raw_read(reference,sources):
    p=Path(reference['path']).resolve();raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=reference['sha256']:raise ValueError('Explicit source bytes differ')
    archive.merge(sources,{str(p):reference['sha256']});return raw
def read(reference,sources):return json.loads(raw_read(reference,sources))
def num(value):
    if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Finite nonboolean source number required')
    return Decimal(str(value))
def share(value):
    if type(value) not in (str,int,float):raise ValueError('Explicit nonboolean share ratio required')
    result=Decimal(str(value))
    if not result.is_finite() or result<=0:raise ValueError('Positive finite share ratio required')
    return Fraction(result)
def day(timestamp):
    if type(timestamp) is not int:raise ValueError('Integer provider timestamp required')
    return datetime.fromtimestamp(timestamp,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat()


def verify_receipt(received,calendar):
    value=datetime.fromisoformat(received)
    if value.tzinfo is None or value.utcoffset().total_seconds()!=0:raise ValueError('Explicit UTC receipt required')
    receipt_day=value.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    if any(d>=receipt_day for d in calendar):raise ValueError('Receipt-day prices are incomplete')
    return receipt_day


def inspect_channel(ticker,rows,raw,calendar,event_witnesses):
    """Independent raw nominal audit. Classification remains an explicit assumption."""
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    chart=json.loads(decoded)['chart']['result']
    if len(chart)!=1 or chart[0]['meta']['symbol']!=ticker or chart[0]['meta']['currency']!='USD':raise ValueError('Exact USD provider channel required')
    data=chart[0];timestamps=data['timestamp'];dates=[day(v) for v in timestamps]
    if dates!=sorted(set(dates)):raise ValueError('Unique ordered raw sessions required')
    quote,=data['indicators']['quote'];events=data.get('events',{})
    if any(len(quote[field])!=len(dates) for field in ('open','close')) or [d for d in dates if calendar[0]<=d<=calendar[-1]]!=calendar:raise ValueError('Complete observed raw calendar cannot be compressed')
    if set(events)-{'splits','dividends'}:raise ValueError('Unknown corporate event channel')
    split=[]
    for key,event in events.get('splits',{}).items():
        if key!=str(event['date']) or type(event['splitRatio']) is not str:raise ValueError('Event timestamp/ratio identity differs')
        numerator=num(event['numerator']);denominator=num(event['denominator']);parts=event['splitRatio'].split(':')
        if len(parts)!=2 or numerator<=0 or denominator<=0 or Fraction(parts[0])/Fraction(parts[1])!=Fraction(numerator)/Fraction(denominator):raise ValueError('Exact positive share ratio required')
        split.append(dict(session=day(event['date']),new_shares=str(numerator),old_shares=str(denominator),event_kind='IDENTITY_TRANSITION_SHARE_SPLIT' if ticker=='LRCX' else 'ORDINARY_SHARE_SPLIT',provider_event_key=key,original_provider_fields=event))
    split.sort(key=lambda e:e['session'])
    if len({e['session'] for e in split})!=len(split):raise ValueError('Duplicate split session')
    if ticker!='LRCX':
        expected=[dict(denominator=e['old_shares'],first_adjusted_trading_date=e['session'],numerator=e['new_shares'],provider_event_timestamp=e['original_provider_fields']['date'],specific_event_matched=True,ticker=ticker) for e in split]
        # Provider numeric floats may serialize as 10.0; compare exact rational values.
        if len(event_witnesses)!=len(expected):raise ValueError('Every returned split requires sealed specific-event support')
        for witness,event in zip(event_witnesses,expected):
            for key in ('first_adjusted_trading_date','provider_event_timestamp','specific_event_matched','ticker'):
                if not exact(witness[key],event[key]):raise ValueError('Specific-event witness differs')
            if share(witness['numerator'])!=share(event['numerator']) or share(witness['denominator'])!=share(event['denominator']):raise ValueError('Specific-event ratio differs')
    elif len(split)!=1 or split[0]['session']!='2024-10-03' or Fraction(split[0]['new_shares'])/Fraction(split[0]['old_shares'])!=10:raise ValueError('Exact bounded LRCX transition event required')
    by_date={row['session']:row for row in rows}
    if len(by_date)!=len(rows):raise ValueError('Duplicate saved nominal session')
    position={d:i for i,d in enumerate(dates)};output=[];max_error=Decimal(0)
    with localcontext() as context:
        context.prec=50
        for d in calendar:
            if d not in by_date or d not in position:raise ValueError('Missing nominal/raw predecessor date')
            row=by_date[d];i=position[d]
            if row['ticker']!=ticker or row['currency']!='USD' or type(row['provider_timestamp']) is not int or row['provider_timestamp']!=timestamps[i]:raise ValueError('Daily provider coordinate differs')
            factor=Fraction(1)
            for event in split:
                if event['session']>d:factor*=Fraction(event['new_shares'])/Fraction(event['old_shares'])
            for field in ('open','close'):
                observed=num(quote[field][i]);nominal=num(row['nominal_'+field])
                expected=observed*Decimal(factor.numerator)/Decimal(factor.denominator)
                error=abs(nominal-expected);max_error=max(max_error,error)
                if nominal<=0 or observed<=0 or num(row['quote_'+field])!=observed or error>max(Decimal('1e-10'),abs(expected)*Decimal('1e-12')):raise ValueError('Independent raw nominal comparison failed')
            output.append(dict(session=d,open=row['nominal_open'],close=row['nominal_close']))
    return dict(nominal_rows=output,split_events=split),dict(decoded_sha256=hashlib.sha256(decoded).hexdigest(),all_original_returned_events=events,
        raw_provider_session_count=len(dates),fixed_selected_price_count=253,decimal_open_close_cells=506,maximum_absolute_decimal_error=str(max_error),
        provider_identity_authenticated=False,quote_basis_independently_authenticated=False,complete_actions_verified=False)


def map_nav(raw,calendar):
    if type(calendar) is not list or not calendar or calendar!=sorted(set(calendar)):raise ValueError('Nonempty unique ascending reference sessions required')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))));dates=[r['Date'] for r in rows]
    if dates!=sorted(set(dates)) or not dates or any(date.fromisoformat(d).isoformat()!=d for d in dates+calendar):raise ValueError('Unique canonical NAV/reference observations required')
    values=[]
    for row in rows:
        value=Decimal(row['Close'])
        if not value.is_finite() or value<=0:raise ValueError('Positive finite NAV required')
        values.append(value)
    mapped=[]
    for d in calendar:
        index=bisect.bisect_right(dates,d)-1
        if index<0:raise ValueError('NAV has no previous observation')
        mapped.append(dict(session=d,nav_source_date=dates[index],nav=str(values[index]),same_date=dates[index]==d,
            known_published_by_us_session_cutoff=False))
    returns=[]
    with localcontext() as context:
        context.prec=50
        for before,after in zip(mapped,mapped[1:]):returns.append(dict(session=after['session'],previous_session=before['session'],conditional_original_currency_return=str(Decimal(after['nav'])/Decimal(before['nav'])-1)))
    return dict(rows=mapped,returns=returns,same_date_missing_count=sum(not r['same_date'] for r in mapped),
        alignment='BACKWARD_OBSERVATION_DATE_ONLY_NOT_PUBLICATION_TIME',future_nav_observation_used=False,original_currency_only=True,fx_applied=False,
        publication_time_verified=False,legal_comparison_ready=False)


def encode(value):
    if isinstance(value,pd.DataFrame):return fourteen.prior.frame_payload(value)
    if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
    if isinstance(value,list):return [encode(v) for v in value]
    return value


def build():
    if PURE_SHA is None or LOADED[str(PURE_PATH)]!=PURE_SHA:raise ValueError('Await exact reviewed mathematical kernel')
    sources=dict(LOADED);raw_read(dict(path=str(PURE_PATH),sha256=PURE_SHA),sources)
    docs={key:read(ref,sources) for key,ref in REFS.items()}
    for value in docs.values():
        for key in ('historical_expected_source_hashes','source_hashes'):
            if key in value:archive.merge(sources,value[key])
    archive.verify_expected_sources(sources,archive.load_contract())
    calendar=docs['readiness']['observed_reference_calendar'][-253:]
    if len(calendar)!=253 or calendar[0]!='2025-09-16' or calendar[-1]!='2026-09-17':raise ValueError('Exact bounded historical calendar required')
    universe=docs['panel']['panel']['universe'];candidate_rows=[dict(zip(universe['columns'],row)) for row in universe['data']]
    candidates=sorted(r['ticker'] for r in candidate_rows);control=docs['control']['definition']['securities'];incumbent=sorted(r['ticker'] for r in control)
    inventory={r['ticker']:r for r in docs['inventory']['rows']};channels={};evidence={}
    for ticker in sorted(set(candidates)|set(incumbent)):
        if ticker=='TSM':
            quote=docs['tsm'];reference=REFS['tsm'];reconstruction=quote['reconstruction']
            raw_record=read(quote['raw_readback'],sources);raw_ref=dict(path=raw_record['raw_path'],sha256=raw_record['raw_sha256']);received=quote['received_at_utc'];witness=[]
        else:
            record=inventory[ticker];post=record.get('post_action_reference');reference=(post or record['original_reference'])['artifact_reference'];quote=read(reference,sources)
            if post:
                reconstruction=quote['result'];raw_record=quote['raw_decoding_evidence'];raw_ref=dict(path=raw_record['raw_path'],sha256=raw_record['raw_sha256']);received=reconstruction['received_at_utc'];witness=[]
            else:
                reconstruction=quote['result']['reconstruction'];raw_ref=dict(path=quote['raw_path'],sha256=quote['raw_sha256']);received=quote['received_at_utc'];witness=quote['result']['matched_specific_events']
        for key in ('historical_expected_source_hashes','source_hashes'):
            if key in quote:archive.merge(sources,quote[key])
            if key in quote.get('result',{}):archive.merge(sources,quote['result'][key])
        receipt_day=verify_receipt(received,calendar)
        raw=raw_read(raw_ref,sources);channel,proof=inspect_channel(ticker,reconstruction['rows'],raw,calendar,witness)
        channels[ticker]=channel;evidence[ticker]=dict(quote_reference=reference,raw_reference=raw_ref,received_at_utc=received,receipt_day_excluded=receipt_day,sealed_specific_event_witnesses=witness,**proof)
    nav_entry=docs['snapshot']['files']['nav'];nav_raw=raw_read(dict(path=nav_entry['snapshot_path'],sha256=nav_entry['sha256']),sources)
    meta_entry=docs['snapshot']['files']['nav_manifest'];meta=read(dict(path=meta_entry['snapshot_path'],sha256=meta_entry['sha256']),sources)
    if meta['content_sha256']!=nav_entry['sha256'] or meta['dataset_key']!='012922' or meta['dataset_type']!='fund_nav':raise ValueError('Original NAV sidecar differs')
    minimum={t:('2024-10-03' if t=='LRCX' else None) for t in channels}
    prices=pure.assemble_historical_prices(calendar=calendar,channels=channels,candidate_tickers=candidates,incumbent_tickers=incumbent,minimum_identity_dates=minimum,exclude_on_or_after='2026-09-18')
    nav=map_nav(nav_raw,calendar)
    value=dict(schema='SOURCE_BOUND_TWENTY_CONDITIONAL_HISTORICAL_INPUTS_V1',input_references=REFS,prices=encode(prices),channel_evidence=evidence,
        candidate_coordinate_and_risk_rows=candidate_rows,candidate_full_original_provenance=docs['panel']['panel']['observed_provenance_and_missing'],
        candidate_supplemental_dated_provenance=docs['panel']['supplemental_dated_and_risk_provenance'],
        coordinate_interval_role='EXPLICIT_RETROSPECTIVE_ASSUMPTION_NOT_HISTORICAL_IDENTITY_CERTIFICATION',
        latest_liquidity_role='STATIC_LATEST_63_REFERENCE_NOT_KNOWN_AT_2026_03_18',risk_label_role='STATIC_CONDITIONAL_LABEL_NOT_HISTORICAL_QUALIFICATION',
        incumbent_original_securities=control,incumbent_weights_reoptimized=False,target_012922=nav,target_nav_observed_fetch_time=meta.get('fetched_at'),
        nominal_open_and_close_retained=True,formal_next_open_execution_performed=False,old_close_only_whole_lot_model_called=False,
        historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),**dict.fromkeys(FALSE,False))
    return value


def verify(value):
    if not exact(value,build()):raise ValueError('Complete sealed historical input reconstruction differs')


def publish_verified(path,value):
    verify(value);saved=exclusive_publish(path,value)
    if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Source drift after publication')
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();print(json.dumps(publish_verified(args.output,build())))
