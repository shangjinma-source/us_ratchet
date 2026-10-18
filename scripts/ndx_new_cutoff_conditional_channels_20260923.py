"""New-window conditional channel arithmetic from original raw bytes, never admission."""
import argparse
from copy import deepcopy
from datetime import datetime
from decimal import Context, Decimal, localcontext
from fractions import Fraction
import gzip
import hashlib
from importlib.resources import files
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];BASE=ROOT/'data/cache/research'
sys.path.insert(0,str(ROOT))
from backtest import ndx_conditional_channel_input_research as kernel
KERNEL=Path(kernel.__file__).resolve()
KERNEL_SHA='68595f10bde6d917682d8543ebd081462f0df90b0e330f606ca1ac9a2c596804'
OUTPUT=BASE/'new_cutoff_conditional_channels_20260923_v1/channels.json'
NY_SOURCE=Path(str(files('tzdata.zoneinfo.America').joinpath('New_York'))).resolve()
NY_BYTES=NY_SOURCE.read_bytes();NY=ZoneInfo.from_file(BytesIO(NY_BYTES),key='America/New_York')
LOADED={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (SOURCE,KERNEL,NY_SOURCE)}
BOUND={
 'bridge':('new_cutoff_event_policy_20260923_v1/bridge.json','d2f7824197cb30c119eb8297d6dda784e33ff2589010e36f63d4e9850267d7bd'),
 'completeness':('new_cutoff_completeness_20260923_v1/manifest.json','d4b16c34ea81e6925dc8cb1d0f56cfdb80731aa7078c64bfd734b4fb375cfbd1'),
}
FALSE=('http_performed','fit_performed','identity_interval_verified','point_in_time_verified',
 'complete_corporate_actions_verified','legal_training_input_admitted','promotion_allowed',
 'volume_units_independently_certified','exchange_calendar_verified','dividend_cash_flows_included',
 'old_outputs_spliced','missing_values_filled','full_transitive_source_closure_reverified')
PRICE_REASONS={'NEW_127_OBSERVED_OHLC_COVERAGE_SHORT','NEW_POST_ACTION_PARTITION_SHORT_OF_127',
 'COMPLEX_RETURNED_EVENT_NOT_ORDINARY_CERTIFICATE','NEW_OLD_SPLIT_PAYLOAD_DIFF_REQUIRES_REVIEW','UNRESOLVED_RETURNED_EVENTS'}


def require(ok,message):
    if not ok:raise ValueError(message)


def unique(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def loads(raw,decimal=False):
    def reject(value):raise ValueError('Nonfinite JSON literal')
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject,parse_float=Decimal if decimal else float)


def decimal_json(value):
    if isinstance(value,Decimal):return str(value)
    raise TypeError('Unsupported JSON value: '+type(value).__name__)


def encode(value):
    return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False,default=decimal_json)+'\n').encode()


def reference(role):
    relative,digest=BOUND[role];return dict(path=str(BASE/relative),sha256=digest)


def guard(sources):
    require(LOADED[str(KERNEL)]==KERNEL_SHA,'Loaded kernel differs')
    for path,digest in {**sources,**LOADED}.items():
        require(hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,'Source changed: '+path)


def read(ref,sources):
    path=str(Path(ref['path']).resolve());digest=ref['sha256']
    require(path not in sources or sources[path]==digest,'Conflicting source')
    raw=Path(path).read_bytes();require(hashlib.sha256(raw).hexdigest()==digest,'Source bytes differ')
    sources[path]=digest;return raw


def parse_raw(raw,ticker):
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    body=loads(decoded,True);chart=body['chart']
    require(chart.get('error') is None and len(chart['result'])==1,'Single successful channel required')
    result=chart['result'][0]
    expected=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1d')
    require(all(result['meta'].get(key)==value for key,value in expected.items()),'Raw metadata differs')
    times=result['timestamp']
    require(times and all(type(stamp) is int and stamp>0 for stamp in times),'Integer timestamps required')
    days=[datetime.fromtimestamp(stamp,NY).date().isoformat() for stamp in times]
    require(days==sorted(set(days)) and times==sorted(set(times)),'Unique ordered raw sessions required')
    require(all(kernel._session(stamp)==day for stamp,day in zip(times,days)),'Frozen kernel timezone differs from pinned NY bytes')
    quotes=result['indicators']['quote'];require(len(quotes)==1,'Single quote array required')
    quotes=quotes[0]
    require(all(len(quotes[key])==len(days) for key in ('open','high','low','close','volume')),'Raw dimensions differ')
    events=result.get('events',{});require(type(events) is dict and set(events)<={'splits','dividends'},'Unknown event family')
    require(all(type(events.get(key,{})) is dict for key in ('splits','dividends')),'Event maps required')
    return result,days,hashlib.sha256(decoded).hexdigest()


def policies_for_raw(result,bridge_row):
    mapping=bridge_row['event_policy_bridge'];splits=result.get('events',{}).get('splits',{})
    require(splits==loads(encode(bridge_row['new_returned_splits']),True),'Bridge splits differ from raw')
    mapped=mapping['events']
    require(len(mapped)==len(splits) and {item['provider_event_key'] for item in mapped}==set(splits),'Full split policy denominator required')
    policies=[]
    for item in sorted(mapped,key=lambda row:row['session']):
        event=splits[item['provider_event_key']]
        require(type(event['date']) is int and str(event['date'])==item['provider_event_key'],'Event key/date differs')
        day=datetime.fromtimestamp(event['date'],NY).date().isoformat()
        require(day==item['session'],'Event NY day differs')
        numerator,denominator=event['numerator'],event['denominator']
        require(type(numerator) in (int,Decimal) and type(denominator) in (int,Decimal) and numerator>0 and denominator>0,'Positive event ratio required')
        ratio=Fraction(numerator)/Fraction(denominator)
        parts=event['splitRatio'].split(':')
        require(len(parts)==2 and Fraction(parts[0])>0 and Fraction(parts[1])>0 and Fraction(parts[0])/Fraction(parts[1])==ratio,'Event ratio text differs')
        if item['status']!='SPECIFIC_POLICY_MATCH':continue
        policy=item['policy'];require(policy['session']==day and Fraction(policy['numerator'],policy['denominator'])==ratio,'Policy ratio/day differs')
        require(policy['kind'] in ('ORDINARY_SPLIT','BEFORE_PARTITION_UNMODELLED'),'Unknown policy')
        if policy['kind']=='ORDINARY_SPLIT':require(item.get('specific_event_reference') is not None,'Specific ordinary evidence required')
        else:require(mapping['regular_floor'] and day<=mapping['regular_floor'],'Unmodelled event after floor')
        policies.append(dict(session=day,numerator=ratio.numerator,denominator=ratio.denominator,kind=policy['kind']))
    return policies


def reconstruct(raw,bridge_row,calendar):
    ticker=bridge_row['ticker'];result,days,decoded_sha=parse_raw(raw,ticker)
    require(decoded_sha==bridge_row['new_decoded_sha256'],'Decoded raw differs from bridge')
    policies=policies_for_raw(result,bridge_row)
    reasons=list(bridge_row['new_window_derivation']['reasons'])
    require(set(reasons)<=PRICE_REASONS|{'NEW_63_RAW_VOLUME_COVERAGE_SHORT','SAVED_VOLUME_UNIT_RESTRICTION_RETAINED'},'Unknown coverage reason')
    floor=bridge_row['new_window_derivation']['policy_floor']
    blocked=[reason for reason in reasons if reason in PRICE_REASONS]
    events=loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0].get('events',{})
    base=dict(ticker=ticker,status='BLOCKED_PRICE_INPUT' if blocked else 'CONDITIONAL_NUMERIC_RESULT',reasons=reasons,
        bridge_row=deepcopy(bridge_row),raw_reference=bridge_row['new_raw_reference'],receipt_reference=bridge_row['new_receipt_reference'],
        raw_decoded_sha256=decoded_sha,returned_events=events,event_policy=policies,regular_floor=floor,
        quote_rows=None,channel_input=None,conditional_reconstruction_performed=False,**dict.fromkeys(FALSE,False))
    if blocked:return base
    require(len(policies)==len(events.get('splits',{})),'Unmapped split cannot enter arithmetic')
    require([day for day in days if day<='2026-09-21'][-127:]==calendar,'Latest original 127 dates differ')
    require(floor is None or floor<=calendar[0],'Whole calendar must follow partition floor')
    positions={day:index for index,day in enumerate(days)};quotes=result['indicators']['quote'][0]
    rows=[]
    with localcontext(Context(prec=80)):
        for day in calendar:
            index=positions[day];factor=Fraction(1);later=[]
            for policy in policies:
                if policy['kind']=='ORDINARY_SPLIT' and policy['session']>day:
                    factor*=Fraction(policy['numerator'],policy['denominator']);later.append(policy['session'])
            row=dict(session=day,ticker=ticker,currency='USD',provider_timestamp=result['timestamp'][index],
                split_factor_numerator=str(factor.numerator),split_factor_denominator=str(factor.denominator),
                split_factor=float(factor),later_split_effective_sessions=later)
            for field in ('open','close'):
                value=quotes[field][index]
                require(type(value) in (int,Decimal) and value>0 and Decimal(value).is_finite(),'Positive Decimal quote required')
                row['quote_'+field]=Decimal(value)
                row['nominal_'+field]=Decimal(value)*Decimal(factor.numerator)/Decimal(factor.denominator)
            rows.append(row)
        calculated=kernel.build_channel_input(ticker=ticker,raw_bytes=raw,quote_rows=rows,calendar=calendar,cutoff='2026-09-21',
            exclude_on_or_after='2026-09-23',event_policy=policies,regular_floor=floor)
    if ticker in ('MNST','CRWD'):
        require(calculated['liquidity']['status']=='BLOCKED_VOLUME_UNIT_UNKNOWN','Saved volume unit restriction must remain blocked')
    base.update(quote_rows=loads(encode(rows)),channel_input=calculated,conditional_reconstruction_performed=True)
    return base


def validate_receipt(ticker,receipt,started,raw,rawref):
    require(receipt['ticker']==started['ticker']==ticker and all(receipt.get(key)==value for key,value in started.items()),'Started/receipt binding differs')
    require(type(receipt['attempt_count']) is int and receipt['attempt_count']==1 and receipt['http_status']==200 and
        receipt['promotion_allowed'] is False and receipt['point_in_time_verified'] is False,'Receipt scope differs')
    require(dict(path=receipt['raw_path'],sha256=receipt['raw_sha256'])==rawref and receipt['raw_bytes']==len(raw),'Receipt raw binding differs')
    require(receipt['plan_sha256']=='96696abaaa7a8d9dc2765ce436ec2b312af74f4490243a963732bcf26bfedf71' and
        receipt['runner_sha256']=='f26d8c29533d21c1ae35779f7eb8b3ff5ba9143632f9fe0091b3955bee4713bd','Capture generation differs')
    start=datetime.fromisoformat(receipt['started_at_utc']);end=datetime.fromisoformat(receipt['received_at_utc'])
    require(start.tzinfo is not None and end.tzinfo is not None and start.utcoffset().total_seconds()==end.utcoffset().total_seconds()==0 and end>=start,'UTC capture time differs')
    require(start.astimezone(NY).date().isoformat()==end.astimezone(NY).date().isoformat()==receipt['completed_training_excludes_dates_on_or_after']=='2026-09-23','Receipt day differs')
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+ticker+'?period1=1640995200&period2='+str(int(start.timestamp()))+'&interval=1d&events=div,splits'
    require(receipt['request_url']==receipt['final_url']==url and receipt['request_method']=='GET' and receipt['credentials_sent'] is False,'Receipt URL differs')


def build():
    sources=dict(LOADED);guard(sources)
    bridge=loads(read(reference('bridge'),sources));complete=loads(read(reference('completeness'),sources))
    require(bridge['schema']=='NEW_CUTOFF_101_EVENT_POLICY_BRIDGE_V1' and bridge['input_references']['completeness']==reference('completeness'),'Hard bridge scope differs')
    require(bridge['price_generation_allowed'] is False and bridge['promotion_allowed'] is False and complete['promotion_allowed'] is False,'Source authority cannot be upgraded')
    calendar=complete['observed_reference_calendar_127']
    require(len(calendar)==127 and calendar==sorted(set(calendar)) and calendar[-1]=='2026-09-21' and bridge['observed_reference_calendar_127']==calendar,'Observed calendar differs')
    members=[row['ticker'] for row in complete['rows'] if row['role']=='OBSERVED_MEMBER_PROVIDER_CHANNEL']
    require(len(members)==len(set(members))==101 and [row['ticker'] for row in bridge['rows']]==members,'Exact 101 channel order required')
    require(all(row['volume_63']['numerical_coverage_complete'] is True for row in complete['rows']
                if row['ticker'] in members), 'This version requires the sealed complete 63-day raw volume observations')
    require(all('NEW_63_RAW_VOLUME_COVERAGE_SHORT' not in row['new_window_derivation']['reasons'] for row in bridge['rows']),
            'Raw volume numerical gaps require a separately reviewed version; no fabricated volume')
    rows=[]
    for item in bridge['rows']:
        require(item['price_generation_allowed'] is False and item['promotion_allowed'] is False,'Row scope upgraded')
        raw=read(item['new_raw_reference'],sources);receipt=loads(read(item['new_receipt_reference'],sources))
        startedref=dict(path=str(Path(item['new_receipt_reference']['path']).with_name(item['ticker']+'.started.json')),sha256=receipt['started_sha256'])
        started=loads(read(startedref,sources));validate_receipt(item['ticker'],receipt,started,raw,item['new_raw_reference'])
        row=reconstruct(raw,item,calendar);row['started_reference']=startedref;rows.append(row)
    guard(sources)
    return dict(schema='NEW_CUTOFF_CONDITIONAL_CHANNELS_V1',scope='CONDITIONAL_RESEARCH_CALCULATION',candidate_cutoff='2026-09-21',
        member_queue_count=101,full_capture_queue_count=104,additional_roles=bridge['additional_roles'],
        calendar=calendar,rows=rows,conditional_reconstruction_performed=True,bridge_price_generation_allowed=False,
        raw_volume_scope='SEALED_COMPLETE_63_DAY_NUMERICAL_OBSERVATIONS_ONLY_UNIT_UNCERTAINTY_REMAINS_SEPARATE',
        summary=dict(conditional_price_channels=sum(row['status']=='CONDITIONAL_NUMERIC_RESULT' for row in rows),
                     blocked_price_channels=sum(row['status']=='BLOCKED_PRICE_INPUT' for row in rows)),
        kernel_reference=dict(path=str(KERNEL),sha256=KERNEL_SHA),input_references={role:reference(role) for role in BOUND},
        source_hashes=sources,**dict.fromkeys(FALSE,False))


def publish():
    require(not OUTPUT.parent.exists(),'Fresh fixed namespace required')
    value=build();guard(value['source_hashes']);raw=encode(value)
    OUTPUT.parent.mkdir(parents=True,exist_ok=False)
    with OUTPUT.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    guard(value['source_hashes']);require(OUTPUT.read_bytes()==raw,'Published bytes differ')
    require({path.name for path in OUTPUT.parent.iterdir()}=={'channels.json'},'Unexpected namespace entry')
    return dict(path=str(OUTPUT),sha256=hashlib.sha256(raw).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
    require(args.publish,'Explicit --publish required');print(json.dumps(publish()))
