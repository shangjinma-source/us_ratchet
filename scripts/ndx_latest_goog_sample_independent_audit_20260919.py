"""Independently read GOOG saved returns/liquidity; never invoke its numerical producer."""
import argparse,gzip,hashlib,json,math,sys
from datetime import datetime
from decimal import Decimal,localcontext
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
RAW=ROOT/'data/cache/research/current79_new_asof_capture_20260919_v1/GOOG.response.bin'
RAW_SHA='7f07ef0dd9833d82edf93776756e56158b19a8dece2aa4c1a064ceba09dcde98'
SAMPLE=ROOT/'data/cache/research/latest_goog_input_sample_20260919_v1/sample.json'
SAMPLE_SHA='a2588e64cb93a59911960d9881eb252c31aa0edbdbf57426ee9e39c90536af3e'
SID='security:0001652044:02079K107';ISSUER='issuer:0001652044';CUTOFF='2026-09-17'
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,Path(publish.__code__.co_filename).resolve())}
FALSE=('provider_instrument_id_invented','evidence_available_date_backdated','old_295_day_identity_adjudication_extended','current_cusip_interval_verified','provider_legal_security_binding_verified','complete_actions_verified','complete_ndx_membership_asof_verified','risk_chain_qualification_performed','calendar_is_official_exchange_calendar','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed','historical_split_event_removed')


def unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('Duplicate JSON key')
        out[k]=v
    return out


def number(value):
    if type(value) not in (int,float,Decimal):raise ValueError('Nonboolean numeric value required')
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Finite numeric value required')
    return result


def inspect(sample,raw,receipt):
    if sample['schema']!='LATEST_GOOG_RETROSPECTIVE_PRICE_RETURN_LIQUIDITY_SAMPLE_V1' or sample['cutoff']!=CUTOFF or sample['security_id']!=SID or sample['issuer_id']!=ISSUER:raise ValueError('Fixed sample coordinate required')
    if any(sample[k] is not False for k in FALSE) or sample['price_return_excludes_cash_dividends'] is not True or sample['ratio_one_is_explicit_research_condition'] is not True:raise ValueError('Conditional scope changed')
    received=datetime.fromisoformat(receipt['received_at_utc'])
    if received.tzinfo is None or sample['received_at_utc']!=receipt['received_at_utc'] or sample['receipt_day_excluded']!=received.astimezone(ZoneInfo('America/New_York')).date().isoformat() or sample['receipt_day_excluded']!=receipt['completed_training_excludes_dates_on_or_after']:raise ValueError('Original receipt date differs')
    data=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw,parse_float=Decimal,object_pairs_hook=unique)['chart']['result'][0]
    if data['meta']['symbol']!='GOOG' or data['meta']['currency']!='USD' :raise ValueError('Bound GOOG USD observation required')
    splits=data.get('events',{}).get('splits',{})
    if set(splits)!={'1658151000'}:raise ValueError('Entire one-event historical denominator required')
    event=splits['1658151000']
    if type(event.get('date')) is not int or event['date']!=1658151000 or number(event.get('numerator'))!=20 or number(event.get('denominator'))!=1 or event.get('splitRatio')!='20:1':raise ValueError('Historical July18 2022 positive20/1 event differs')
    fact=sample['official_specific_split_facts']
    if fact['ticker']!='GOOG' or fact['security_class']!='CLASS_C_CAPITAL' or type(fact['new_shares']) is not int or fact['new_shares']!=20 or type(fact['old_shares']) is not int or fact['old_shares']!=1 or fact['first_adjusted_session']!='2022-07-18' or fact['separately_reported_execution_date']!='2022-07-15' or fact['first_adjusted_date_declaration']!='EXPECTED_IN_APPROVED_8K' or fact['corporate_action_completeness_verified'] is not False:raise ValueError('Official specific ClassC event declaration differs')
    if sample['returned_raw_events']!=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0].get('events',{}):raise ValueError('All raw events must remain unmodified')
    dates=[datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat() for t in data['timestamp']]
    if dates!=sorted(set(dates)):raise ValueError('Unique observed sessions required')
    quotes=data['indicators']['quote'][0]
    if any(len(quotes[k])!=len(dates) for k in ('close','volume')):raise ValueError('Raw dimensions differ')
    positions={d:i for i,d in enumerate(dates)};calendar=[d for d in dates if d<=CUTOFF][-127:];liquid=calendar[-63:]
    if len(calendar)!=127 or calendar[0]<='2022-07-18' or calendar[-1]!=CUTOFF or CUTOFF>=sample['receipt_day_excluded']:raise ValueError('Fixed completed 127-session interval required')
    n=sample['numerical'];payload=n['input_payload'];returns=n['price_returns']
    expected_event=dict(first_adjusted_session='2022-07-18',new_shares=20,old_shares=1,raw_event=dict(date=event['date'],numerator=str(event['numerator']),denominator=str(event['denominator']),splitRatio=event['splitRatio']))
    if json.dumps(n['observed_historical_split'],sort_keys=True)!=json.dumps(expected_event,sort_keys=True):raise ValueError('Saved observed event differs')
    if n['liquidity_legality_or_corporate_action_unit_independently_certified'] is not False or n['liquidity_basis']!='RAW_VOLUME_SHARES_TIMES_CONDITIONAL_NOMINAL_CLOSE':raise ValueError('Conditional liquidity unit disclosure differs')
    if payload['calendar']!=calendar or payload['basis']!='NOMINAL_CLOSE' or payload['dividend_adjustment_in_close'] is not False or payload['securities']!={SID:{'issuer_id':ISSUER}}:raise ValueError('Price-return coordinates differ')
    if len(payload['rows'])!=127 or len(payload['daily_share_ratios'])!=127 or len(returns['rows'])!=126 or returns['calendar']!=calendar:raise ValueError('Exact numerical denominators required')
    for d,row,ratio in zip(calendar,payload['rows'],payload['daily_share_ratios']):
        if number(row['close'])<=0 or number(quotes['close'][positions[d]])<=0:raise ValueError('Positive input Close required')
        if {k:row[k] for k in ('security_id','issuer_id','ticker','session')}!=dict(security_id=SID,issuer_id=ISSUER,ticker='GOOG',session=d):raise ValueError('Daily identity differs')
        if ratio!={'security_id':SID,'session':d,'new_shares':1,'old_shares':1} or type(ratio['new_shares']) is not int or type(ratio['old_shares']) is not int:raise ValueError('Explicit ratio one differs')
        if abs(number(row['close'])-number(quotes['close'][positions[d]]))>Decimal('1e-12'):raise ValueError('Input Close differs from raw')
    maximum=Decimal(0)
    with localcontext() as ctx:
        ctx.prec=50
        for before,after,row in zip(calendar,calendar[1:],returns['rows']):
            if row['security_id']!=SID or row['issuer_id']!=ISSUER or row['session']!=after or row['previous_session']!=before:raise ValueError('Return predecessor identity differs')
            if row['ticker']!='GOOG' or row['previous_ticker']!='GOOG' or row['declared_share_ratio']!='1' or row['applied_share_ratio']!='1':raise ValueError('Return ticker/ratio differs')
            if abs(number(row['close'])-number(quotes['close'][positions[after]]))>Decimal('1e-12') or abs(number(row['previous_close'])-number(quotes['close'][positions[before]]))>Decimal('1e-12'):raise ValueError('Return Close fields differ')
            expected=number(quotes['close'][positions[after]])/number(quotes['close'][positions[before]])-1
            error=abs(number(row['price_return'])-expected);maximum=max(maximum,error)
            if error>Decimal('1e-14'):raise ValueError('Independent return arithmetic differs')
        if [r['session'] for r in n['liquidity_rows']]!=liquid:raise ValueError('Exact last63 liquidity sessions required')
        dollars=[]
        for d,row in zip(liquid,n['liquidity_rows']):
            volume=quotes['volume'][positions[d]];close=number(quotes['close'][positions[d]])
            if type(volume) is not int or volume<=0 or type(row['volume_shares']) is not int or row['volume_shares']!=volume:raise ValueError('Actual raw volume differs')
            dollars.append(close*volume)
            if Decimal(row['nominal_close'])!=close or Decimal(row['dollar_volume'])!=dollars[-1]:raise ValueError('Exact independent liquidity arithmetic differs')
        median=sorted(dollars)[31]
        if Decimal(n['median_dollar_volume_usd'])!=median or Decimal(n['minimum_median_dollar_volume_usd'])!=Decimal(50000000) or n['liquidity_numerical_threshold_passed'] is not (median>=50000000):raise ValueError('Median/threshold differs')
    return dict(price_count=127,return_count=126,return_start=calendar[1],return_end=calendar[-1],price_start=calendar[0],liquidity_count=63,liquidity_start=liquid[0],liquidity_end=liquid[-1],maximum_return_error=str(maximum),median_dollar_volume_usd=str(median),liquidity_decimal_error='0')


def build(path,sha):
    path=Path(path).resolve()
    if path!=SAMPLE or sha!=SAMPLE_SHA:raise ValueError('Hard actual GOOG sample required')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External sample SHA differs')
    sample=json.loads(raw,object_pairs_hook=unique);sources=dict(sample['historical_expected_source_hashes']);archive.merge(sources,LOADED);archive.merge(sources,{str(path):sha,str(RAW):RAW_SHA})
    contract=archive.load_contract()
    if archive.verify_expected_sources(sample['historical_expected_source_hashes'],contract)!=sample['archive_resolution']:raise ValueError('Original source partition differs')
    archive.verify_expected_sources(sources,contract)
    receipt_path=RAW.parent/'GOOG.receipt.json';receipt_raw=receipt_path.read_bytes()
    if hashlib.sha256(receipt_raw).hexdigest()!=sources[str(receipt_path)]:raise ValueError('Bound original receipt differs')
    details=inspect(sample,RAW.read_bytes(),json.loads(receipt_raw,object_pairs_hook=unique));partition=archive.verify_expected_sources(sources,contract)
    return dict(schema='LATEST_GOOG_INDEPENDENT_RAW_DECIMAL_AUDIT_V1',sample=dict(path=str(path),sha256=sha),details=details,historical_expected_source_hashes=sources,archive_resolution=partition,kernel_called=False,fit_performed=False,legal_training_input_admitted=False,point_in_time_verified=False,promotion_allowed=False)


def publish_verified(path,value):
    def verify():
        if any(value['historical_expected_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('Auditor sources omitted')
        if archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())!=value['archive_resolution']:raise ValueError('Sources changed')
    verify();saved=publish(path,value);verify();return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('sample-path','sample-sha256','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();print(json.dumps(publish_verified(args.output,build(args.sample_path,args.sample_sha256))))
