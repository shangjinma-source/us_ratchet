"""Bound CDNS retrospective price-return/liquidity sample, never portfolio admission."""
import argparse,gzip,hashlib,json,math,sys
from decimal import Decimal,localcontext
from datetime import datetime
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_split_neutral_price_return_research as kernel
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_current101_price_independent_audit_20260919 as raw_reader
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research'
ANCHORS={
 'readiness':('latest_conditional_input_readiness_20260919_v1/readiness.json','b3a215d05cfb085c4637713d65fb86d565def48728cb382efe94ad1e206d3c49'),
 'quote':('current101_conditional_prices_20260919_v1/CDNS.json','266128aa22c917dc8588e18282695101608383c71d1245ec150e7461bca905e3'),
 'dated_identity':('four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json','a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4'),
 'current_issuer':('current_92_sec_submissions_capture_20260919_v1/current101_issuer_facts.json','4fdd72c4f8887d59ad802ef37ac1641415888fb9c604b8a91601cb219a023d9d'),
 'official_action_gap':('cdns_history_source_probe_20260919_v1/manifest.json','da44ff4b8d3228dbbc8579a94fa2512891606c38d8b5ee04898c2d7153483491'),
 'member_before':('ndx_current_quote_list_capture_20260912_v1/observation.json','950a76544cc63d11ed492b8feb37f2d7eebe4212f42b1761e9ac9a65938a5e38'),
 'member_after':('ndx_current_quote_list_capture_20260919_v1/observation.json','50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77')}
SID='security:0000813672:127387108';ISSUER='issuer:0000813672';CUTOFF='2026-09-17'
LOADED=dict(raw_reader.LOADED)
for p in (Path(__file__).resolve(),kernel.SOURCE,archive.SOURCE,Path(publish.__code__.co_filename).resolve()):archive.merge(LOADED,{str(p):archive.drift.file_sha(p)})


def decimal_positive(v):
    if type(v) not in (int,float,Decimal):raise ValueError('Nonboolean positive numeric observation required')
    d=Decimal(str(v))
    if not d.is_finite() or d<=0:raise ValueError('Finite positive observation required')
    return d


def calculate(*,decoded,quote_rows,reference,liquidity_threshold):
    if len(reference)!=505 or reference!=sorted(set(reference)) or reference[-1]!=CUTOFF:raise ValueError('Fixed full 505-date reference required')
    data=json.loads(decoded,object_pairs_hook=raw_reader.unique,parse_float=Decimal)['chart']['result'][0]
    events=data.get('events',{})
    if type(events) is not dict or set(events)-{'splits','dividends'} or type(events.get('splits',{})) is not dict:raise ValueError('Explicit returned-event channels required; unknown events cannot be discarded')
    if data['meta']['symbol']!='CDNS' or data['meta']['currency']!='USD' or data.get('events',{}).get('splits',{}):raise ValueError('Bound CDNS zero-returned-split sample only')
    dates=[raw_reader.day(t) for t in data['timestamp']];quotes=data['indicators']['quote'][0]
    if dates!=sorted(set(dates)) or any(len(quotes[k])!=len(dates) for k in ('open','close','volume')):raise ValueError('Complete unique raw O/C/volume dimensions required')
    if reference!=[d for d in dates if d<=CUTOFF][-505:]:raise ValueError('Reference must preserve the latest consecutive observed sessions')
    rows={r['session']:r for r in quote_rows}
    if len(rows)!=len(quote_rows) or [r['session'] for r in quote_rows]!=sorted(rows):raise ValueError('Unique saved daily quote coordinate required')
    positions={d:i for i,d in enumerate(dates)};fit=reference[-127:];liquid=reference[-63:]
    if any(d not in rows or d not in positions for d in reference):raise ValueError('No missing or compressed required observations allowed')
    for day in reference:
        row=rows[day];i=positions[day]
        if (row['ticker']!='CDNS' or row['currency']!='USD' or type(row['provider_timestamp']) is not int or row['provider_timestamp']!=data['timestamp'][i]
            or type(row['split_factor']) not in (int,float) or row['split_factor']!=1
            or row['split_factor_numerator']!='1' or row['split_factor_denominator']!='1' or row['later_split_effective_sessions']!=[]):raise ValueError('Conditional nominal unit/coordinate differs')
        for field in ('open','close'):
            expected=decimal_positive(quotes[field][i]);actual=decimal_positive(row['nominal_'+field])
            if actual!=decimal_positive(row['quote_'+field]) or abs(expected-actual)>Decimal('1e-12'):raise ValueError('Nominal quote must match original zero-split raw')
    payload=dict(schema='ndx_split_neutral_return_input_v1',basis='NOMINAL_CLOSE',event_denominator_scope='EXPLICIT_ALL_SUBMITTED_SECURITY_SESSIONS',
        dividend_adjustment_in_close=False,calendar=fit,securities={SID:{'issuer_id':ISSUER}},
        rows=[dict(security_id=SID,issuer_id=ISSUER,ticker='CDNS',session=d,close=rows[d]['nominal_close']) for d in fit],
        daily_share_ratios=[dict(security_id=SID,session=d,new_shares=1,old_shares=1) for d in fit])
    returns=kernel.calculate_split_neutral_price_returns(payload);maximum=Decimal(0);liquidity=[]
    with localcontext() as ctx:
        ctx.prec=50
        if len(returns['rows'])!=126:raise ValueError('Exactly 127 prices must produce 126 price returns')
        for before,after,row in zip(fit,fit[1:],returns['rows']):
            expected=decimal_positive(quotes['close'][positions[after]])/decimal_positive(quotes['close'][positions[before]])-1
            if row['session']!=after or row['previous_session']!=before or type(row['price_return']) not in (int,float) or not math.isfinite(row['price_return']):raise ValueError('Return predecessor coordinate differs')
            error=abs(Decimal(str(row['price_return']))-expected);maximum=max(maximum,error)
            if error>Decimal('1e-14'):raise ValueError('Independent Decimal price return differs')
        for day in liquid:
            volume=quotes['volume'][positions[day]]
            if type(volume) is not int or volume<=0:raise ValueError('Positive integer actual daily volume required')
            close=decimal_positive(quotes['close'][positions[day]])
            liquidity.append(dict(session=day,volume_shares=volume,nominal_close=str(close),dollar_volume=str(close*volume)))
        median=sorted(Decimal(r['dollar_volume']) for r in liquidity)[31];threshold=decimal_positive(liquidity_threshold)
    return dict(input_payload=payload,price_returns=returns,independent_decimal_return_max_error=str(maximum),
        liquidity_rows=liquidity,median_dollar_volume_usd=str(median),minimum_median_dollar_volume_usd=str(threshold),
        liquidity_numerical_threshold_passed=median>=threshold,liquidity_basis='RAW_VOLUME_SHARES_TIMES_CONDITIONAL_NOMINAL_CLOSE',
        liquidity_legality_or_corporate_action_unit_independently_certified=False)


def build():
    sources=dict(LOADED)
    def read(p,h,json_value=True):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Hard evidence bytes differ')
        archive.merge(sources,{p:h});return raw_reader.loads(raw) if json_value else raw
    docs={k:read(BASE/p,h) for k,(p,h) in ANCHORS.items()}
    for doc in docs.values():
        for key in ('source_hashes','historical_expected_source_hashes'):
            if key in doc:archive.merge(sources,doc[key])
    readiness=docs['readiness'];quote=docs['quote'];identity,=[r for r in docs['dated_identity']['rows'] if r['ticker']=='CDNS']
    current,=[r for r in docs['current_issuer']['rows'] if r['ticker']=='CDNS']
    if identity['security_id']!=SID or identity['issuer_cik']!='0000813672' or identity['cusip']!='127387108' or current['current_reported_cik']!='0000813672' or current['reported_ticker_exchange_position']!=0 or current['reported_exchange']!='Nasdaq':raise ValueError('Exact dated/current issuer facts required')
    if any('CDNS' not in docs[k]['observed_symbols'] for k in ('member_before','member_after')):raise ValueError('Bound official quote-list observations must contain CDNS')
    gap=docs['official_action_gap']
    if len(gap['probes'])!=2 or any(r['http_status']!=403 for r in gap['probes']):raise ValueError('Preserved two refused official-action responses required')
    for probe in gap['probes']:
        failed=read(probe['response_path'],probe['response_sha256'],False)
        if type(probe['response_bytes']) is not int or len(failed)!=probe['response_bytes'] or probe['credentials_sent'] is not False or probe['attempt_count']!=1:raise ValueError('Original failed receipt differs')
        start=datetime.fromisoformat(probe['started_at_utc']);end=datetime.fromisoformat(probe['received_at_utc'])
        if start.utcoffset() is None or end.utcoffset() is None or end<start:raise ValueError('Original response observation time differs')
    read(ROOT/'DYNAMIC_CDNS_ACTION_EVIDENCE_GAP_20260919.md','ace531967be76a6a64c521e53a6b33ef52a75afc966235a75a069e1eb88109f6',False)
    if readiness['cutoff']!=CUTOFF or quote['ticker']!='CDNS' or quote['result']['reconstruction']['quote_field_basis']!=raw_reader.BASIS:raise ValueError('Fixed cutoff/basis required')
    snap=read(**dict(p=readiness['source_snapshot']['path'],h=readiness['source_snapshot']['sha256']))
    config=snap['files']['generator'];generator=yaml.safe_load(read(config['snapshot_path'],config['sha256'],False))
    threshold=generator['input_contract']['minimum_median_dollar_volume_usd']
    if type(threshold) not in (int,float) or threshold!=50000000:raise ValueError('Original explicit liquidity threshold differs')
    raw=read(quote['raw_path'],quote['raw_sha256'],False);info=raw_reader.inspect_raw(raw,'CDNS')
    folder=Path(quote['raw_path']).parent;receipt_path=folder/'CDNS.receipt.json';receipt=read(receipt_path,sources[str(receipt_path)])
    started=read(folder/'CDNS.started.json',receipt['started_sha256']);raw_reader.verify_request(quote,receipt,started,info)
    if CUTOFF>=receipt['completed_training_excludes_dates_on_or_after']:raise ValueError('Receipt-day observations cannot enter the sample')
    decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    numerical=calculate(decoded=decoded,quote_rows=quote['result']['reconstruction']['rows'],reference=readiness['observed_reference_calendar'],liquidity_threshold=threshold)
    partition=archive.verify_expected_sources(sources,contract)
    result=dict(schema='LATEST_CDNS_RETROSPECTIVE_PRICE_RETURN_LIQUIDITY_SAMPLE_V1',cutoff=CUTOFF,security_id=SID,issuer_id=ISSUER,
        mapping_scope='EXPLICIT_RESEARCH_COORDINATE_FROM_DATED_FACTS_NOT_PROVIDER_INSTRUMENT_ID',
        dated_identity_fact=identity,current_issuer_observation=current,
        action_evidence_scope='ONLY_RETURNED_RAW_EVENTS_CONDITIONAL_RATIO_ONE',
        official_action_evidence_gap=gap,
        official_action_table_verified=False,record_date_used_as_ex_date=False,execution_authorized=False,
        gap_explanation='NO_COMPLETE_LOCAL_OFFICIAL_ACTION_HISTORY; NO_RETURNED_SPLITS_DOES_NOT_PROVE_NO_ACTIONS',
        membership_observation_refs={k:dict(path=str(BASE/ANCHORS[k][0]),sha256=ANCHORS[k][1]) for k in ('member_before','member_after')},
        received_at_utc=receipt['received_at_utc'],receipt_day_excluded=receipt['completed_training_excludes_dates_on_or_after'],
        returned_raw_events=info['data'].get('events',{}),numerical=numerical,historical_expected_source_hashes=sources,archive_resolution=partition,
        price_return_excludes_cash_dividends=True,ratio_one_is_explicit_research_condition=True,
        provider_instrument_id_invented=False,evidence_available_date_backdated=False,old_295_day_identity_adjudication_extended=False,
        current_cusip_interval_verified=False,provider_legal_security_binding_verified=False,complete_actions_verified=False,
        complete_ndx_membership_asof_verified=False,risk_chain_qualification_performed=False,calendar_is_official_exchange_calendar=False,
        legal_training_input_admitted=False,fit_performed=False,point_in_time_verified=False,promotion_allowed=False)
    verify(result);return result


def validate_numerical(numerical):
    error_text=numerical['independent_decimal_return_max_error']
    if type(error_text) is not str:raise ValueError('Decimal error text required')
    error=Decimal(error_text)
    if not error.is_finite() or error<0 or error>Decimal('1e-14'):raise ValueError('Bounded finite reported Decimal error required')
    if numerical['liquidity_legality_or_corporate_action_unit_independently_certified'] is not False or numerical['liquidity_basis']!='RAW_VOLUME_SHARES_TIMES_CONDITIONAL_NOMINAL_CLOSE':raise ValueError('Conditional volume units cannot be certified')
    payload=numerical['input_payload'];prices=payload['rows'];ratios=payload['daily_share_ratios'];calendar=payload['calendar']
    if (len(calendar)!=127 or calendar!=sorted(set(calendar)) or calendar[-1]!=CUTOFF or payload['securities']!={SID:{'issuer_id':ISSUER}}
        or len(prices)!=127 or len(ratios)!=127 or payload['basis']!='NOMINAL_CLOSE' or payload['dividend_adjustment_in_close'] is not False):raise ValueError('Exact conditional 127-price coordinate required')
    if any(r!={'security_id':SID,'session':d,'new_shares':1,'old_shares':1} or type(r['new_shares']) is not int or type(r['old_shares']) is not int for d,r in zip(calendar,ratios)):raise ValueError('Explicit conditional integer 1:1 cells required')
    if any(r['security_id']!=SID or r['issuer_id']!=ISSUER or r['ticker']!='CDNS' or r['session']!=d for d,r in zip(calendar,prices)):raise ValueError('Exact CDNS price coordinate required')
    actual=kernel.calculate_split_neutral_price_returns(payload)
    if json.dumps(actual,sort_keys=True,allow_nan=False)!=json.dumps(numerical['price_returns'],sort_keys=True,allow_nan=False):raise ValueError('Full kernel result and research flags must reproduce')
    rows=numerical['liquidity_rows']
    if len(rows)!=63 or [r['session'] for r in rows]!=calendar[-63:]:raise ValueError('Exact 63 liquidity observations required')
    with localcontext() as ctx:
        ctx.prec=50
        for row,price in zip(rows,prices[-63:]):
            if type(row['volume_shares']) is not int or row['volume_shares']<=0:raise ValueError('Actual positive integer volume required')
            close=Decimal(row['nominal_close']);dollar=Decimal(row['dollar_volume'])
            if not close.is_finite() or close<=0 or close!=decimal_positive(price['close']) or dollar!=close*row['volume_shares']:raise ValueError('Conditional dollar-volume units differ')
        median=sorted(Decimal(r['dollar_volume']) for r in rows)[31]
        if Decimal(numerical['median_dollar_volume_usd'])!=median or Decimal(numerical['minimum_median_dollar_volume_usd'])!=Decimal(50000000) or numerical['liquidity_numerical_threshold_passed'] is not (median>=50000000):raise ValueError('Conditional liquidity threshold differs')

def verify(value):
    if value.get('action_evidence_scope')!='ONLY_RETURNED_RAW_EVENTS_CONDITIONAL_RATIO_ONE' or any(value[k] is not False for k in ('official_action_table_verified','record_date_used_as_ex_date','execution_authorized')):raise ValueError('Returned-event-only scope must not become official no-action certification')
    if value.get('schema')!='LATEST_CDNS_RETROSPECTIVE_PRICE_RETURN_LIQUIDITY_SAMPLE_V1' or value.get('cutoff')!=CUTOFF or value.get('security_id')!=SID:raise ValueError('Fixed sample schema/coordinate required')
    if value.get('issuer_id')!=ISSUER or value['price_return_excludes_cash_dividends'] is not True or value['ratio_one_is_explicit_research_condition'] is not True:raise ValueError('Explicit price-return/conditional basis required')
    validate_numerical(value['numerical'])
    sources=value['historical_expected_source_hashes'];required=dict(LOADED,**{str(BASE/p):h for p,h in ANCHORS.values()})
    required[str(ROOT/'DYNAMIC_CDNS_ACTION_EVIDENCE_GAP_20260919.md')]='ace531967be76a6a64c521e53a6b33ef52a75afc966235a75a069e1eb88109f6'
    if any(sources.get(p)!=h for p,h in required.items()):raise ValueError('Required evidence/source omitted')
    if archive.verify_expected_sources(sources,archive.load_contract())!=value['archive_resolution']:raise ValueError('Archive source partition differs')
    if any(value[k] is not False for k in ('provider_instrument_id_invented','evidence_available_date_backdated','old_295_day_identity_adjudication_extended',
        'current_cusip_interval_verified','provider_legal_security_binding_verified','complete_actions_verified','complete_ndx_membership_asof_verified',
        'risk_chain_qualification_performed','calendar_is_official_exchange_calendar','legal_training_input_admitted','fit_performed','point_in_time_verified','promotion_allowed')):raise ValueError('Conditional sample claim upgraded')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    value=build();verify(value);saved=publish(args.output,value);verify(value);print(json.dumps(saved))
