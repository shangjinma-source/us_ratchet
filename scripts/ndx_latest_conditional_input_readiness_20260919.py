"""Per-channel latest-cutoff coverage, not legal returns or all-NDX admission."""
import argparse
import csv
import gzip
from datetime import date, datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys
from zoneinfo import ZoneInfo
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research'
INVENTORY=BASE/'current99_conditional_price_inventory_20260919_v1/inventory.json'
INVENTORY_SHA='59ebaf50fdf35c6c390a747de026bc353200f64525b9c30f3e14d935aba209f3'
CUTOFF='2026-09-17'
SNAPSHOT_FILES={
 'scope':'config/ndx_membership_scope_research_v1.yaml',
 'search':'config/ndx_dynamic_shadow_fresh_search_v1.yaml',
 'generator':'config/ndx_dynamic_shadow_candidate_generator_v1.yaml',
 'objective':'config/ndx_portfolio_objective_v1.yaml',
 'nav':'data/cache/funds/012922.csv','nav_manifest':'data/cache/funds/012922.csv.manifest.json',
 'QQQ':'data/cache/QQQ.csv','SPY':'data/cache/SPY.csv','TSM_cache':'data/cache/TSM.csv'}
CONTROL=BASE/'ndx_original_8_control_v1/manifest.json'
CONTROL_SHA='2ca955ce951061a2aa89242c53c645775f36a658e2f51db1dc3732582317a260'
CONTROL_QUOTES=BASE/'incumbent_price_source_probe_20260912_v1/manifest.json'
CONTROL_QUOTES_SHA='4e30f0f7e48b157eb4a5f60cd5d6531b097d2a276f977444838778411e30d77e'
DEPENDENCIES=('backtest/ndx_dynamic_cutoff_refit_research.py','backtest/ndx_dynamic_shadow_candidate_snapshot.py',
              'backtest/ndx_dynamic_shadow_fresh_search.py')
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,
    Path(publish.__code__.co_filename).resolve(),*(ROOT/p for p in DEPENDENCIES))}


def sha(raw):return hashlib.sha256(raw).hexdigest()


def sealed_snapshot(folder):
    """Create new research copies; never rewrite root files or older archives."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);rows={};original={}
    for key,relative in SNAPSHOT_FILES.items():
        path=ROOT/relative;raw=path.read_bytes();digest=sha(raw);target=folder/(key+path.suffix)
        with target.open('xb') as stream:stream.write(raw)
        rows[key]=dict(original_path=str(path),snapshot_path=str(target.resolve()),sha256=digest,bytes=len(raw))
        original[str(path)]=digest
    for p,h in original.items():
        if sha(Path(p).read_bytes())!=h:raise ValueError('Original input changed during snapshot')
    value=dict(schema='LATEST_INPUT_COVERAGE_OBSERVED_BYTES_SNAPSHOT_V1',captured_at_utc=datetime.now(timezone.utc).isoformat(),
        cutoff=CUTOFF,files=rows,source_hashes=dict(LOADED),root_files_modified=False,
        provider_calendar_is_exchange_calendar=False,point_in_time_verified=False,promotion_allowed=False)
    path=folder/'manifest.json';publish(path,value)
    return path,sha(path.read_bytes())


def requirements(scope,search,generator):
    if (scope['scope_change']['authorized_scope']!='ALL_POINT_IN_TIME_NASDAQ_100_MEMBERS_MAY_COMPETE'
            or scope['scope_change']['industry_filter_applied'] is not False
            or scope['unchanged_guards']['original_risk_parameter_source']!='EXPLICIT_ORIGINAL_PER_RUN_CONTRACT'):
        raise ValueError('Original authorized all-NDX scope required')
    s=search['search_contract'];g=generator['input_contract']
    values=dict(fit_return_rows=s['fit_days'],forward_evaluation_return_rows=s['window_days'],rolling_step_rows=s['step_days'],
        minimum_snapshot_adjusted_price_rows=g['minimum_common_adjusted_price_rows'],desired_training_price_rows=g['training_lookback_rows'],
        liquidity_observation_rows=g['nominal_price_liquidity_lookback_rows'])
    if any(type(v) is not int for v in values.values()) or values!=dict(fit_return_rows=126,forward_evaluation_return_rows=126,
        rolling_step_rows=21,minimum_snapshot_adjusted_price_rows=252,desired_training_price_rows=505,liquidity_observation_rows=63):
        raise ValueError('Recognized original per-stage numeric lengths changed')
    return dict(values,fit_adjacent_price_rows=values['fit_return_rows']+1,
        desired_505_is_hard_admission_threshold=False,
        minimum_252_scope='LEGACY_SNAPSHOT_MINIMUM_ADJUSTED_PRICE_ROWS_NOT_ALL_NDX_QUALIFICATION',
        desired_505_scope='LEGACY_SNAPSHOT_TAIL_CAP_TARGET_NOT_MINIMUM_ADMISSION',
        original_track_filter_reused=False,all_ndx_runtime_generator_implemented_by_this_report=False,
        first_prospective_decision_not_before=str(generator['schedule_contract']['first_decision_not_before']),
        cutoff_is_research_observation_not_prospective_decision_seal=True)


def observed_calendar(raw,cutoff):
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    dates=[r['Date'] for r in rows]
    if not dates or dates!=sorted(set(dates)) or any(date.fromisoformat(d).isoformat()!=d for d in dates):
        raise ValueError('Unique ascending observed calendar dates required')
    result=[d for d in dates if d<=cutoff]
    if not result or result[-1]!=cutoff:raise ValueError('Observed QQQ/SPY calendar lacks cutoff')
    return result


def assess_calendar(*,reference,available,requirements):
    if reference!=sorted(set(reference)) or len(reference)<requirements['desired_training_price_rows']:
        raise ValueError('Full ordered reference observations required')
    if type(available) is not list or available!=sorted(set(available)):raise ValueError('Unique available date list required')
    have=set(available);fit=reference[-requirements['fit_adjacent_price_rows']:]
    pairs=[dict(return_session=b,previous_price_session=a,missing_prices=[d for d in (a,b) if d not in have])
           for a,b in zip(fit,fit[1:])]
    windows={}
    for name,length in (('latest_fit_adjacent_prices',requirements['fit_adjacent_price_rows']),
            ('minimum_snapshot_adjusted_prices',requirements['minimum_snapshot_adjusted_price_rows']),
            ('desired_training_prices',requirements['desired_training_price_rows']),
            ('liquidity_dates_only',requirements['liquidity_observation_rows'])):
        expected=reference[-length:];missing=[d for d in expected if d not in have]
        windows[name]=dict(required_rows=length,first=expected[0],last=expected[-1],available_count=length-len(missing),
            missing_dates=missing,date_coverage_complete=not missing)
    return dict(windows=windows,fit_return_date_pairs=pairs,fit_return_pairs_with_both_prices=sum(not p['missing_prices'] for p in pairs),
        quote_covers_latest_cutoff=reference[-1] in have,extra_provider_dates_in_training_range=[d for d in available if reference[-505]<=d<=reference[-1] and d not in set(reference)])


def benchmark_readiness(captured,reference,needed,records,read):
    objective=yaml.safe_load(captured['objective'])
    source=objective['data_sources']['target_012922']
    if (source['csv_path']!=SNAPSHOT_FILES['nav'] or source['manifest_path']!=SNAPSHOT_FILES['nav_manifest']
            or source['expected_dataset_key']!='012922' or source['expected_dataset_type']!='fund_nav'):
        raise ValueError('Original objective benchmark source differs')
    nav_manifest=json.loads(captured['nav_manifest']);nav=list(csv.DictReader(io.StringIO(captured['nav'].decode('utf-8-sig'))))
    nav_dates=[r['Date'] for r in nav]
    if (nav_manifest['content_sha256']!=sha(captured['nav']) or nav_manifest['row_count']!=len(nav)
            or nav_manifest['dataset_key']!='012922' or nav_manifest['dataset_type']!='fund_nav'
            or nav_dates!=sorted(set(nav_dates)) or any(not math.isfinite(float(r['Close'])) or float(r['Close'])<=0 for r in nav)):
        raise ValueError('Current NAV byte/manifest/row binding differs')
    observed=[d for d in nav_dates if d<=CUTOFF]
    align=[]
    for day in reference:
        candidates=[d for d in observed if d<=day]
        align.append(dict(reference_session=day,latest_nav_source_date_at_or_before=candidates[-1] if candidates else None,
            source_value_published_by_session_cutoff_verified=False))
    control=json.loads(read(CONTROL,CONTROL_SHA));definition=control['definition'];securities=definition['securities']
    if (len(securities)!=8 or [r['ticker'] for r in securities]!=objective['benchmark_registry']['original_8_incumbent']['tickers']
            or abs(sum(r['target_weight'] for r in securities)-1)>1e-12):raise ValueError('Hard original eight weights differ')
    mapping={r['ticker']:r for r in records};control_rows=[]
    old_quotes=json.loads(read(CONTROL_QUOTES,CONTROL_QUOTES_SHA))
    probe,=[p for p in old_quotes['probes'] if p['name']=='yahoo_tsm_through_received_daily_events']
    raw=read(probe['response_path'],probe['response_sha256']);decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    tsm=json.loads(decoded)['chart']['result'][0]
    if tsm['meta']['symbol']!='TSM' or tsm['meta']['currency']!='USD':raise ValueError('Original TSM channel differs')
    received=datetime.fromisoformat(probe['received_at_utc']);receipt_day=received.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    tsm_dates=[datetime.fromtimestamp(t,timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat() for t in tsm['timestamp']]
    tsm_completed=[d for d in tsm_dates if d<receipt_day]
    tsm_coverage=assess_calendar(reference=reference,available=tsm_completed,requirements=needed)
    for security in securities:
        ticker=security['ticker']
        control_rows.append(dict(security,coverage=mapping[ticker]['coverage'] if ticker in mapping else tsm_coverage,
            price_source_status='CURRENT_99_CONDITIONAL_CHANNEL' if ticker in mapping else 'OLDER_RAW_TSM_CHANNEL_NOT_CURRENT_99_CONDITIONAL_OUTPUT',
            adjusted_returns_verified=False,current_security_interval_binding_verified=False))
    tsm_cache=observed_calendar(captured['TSM_cache'],CUTOFF)
    return dict(pure_latest_cutoff_fit_requires_dual_benchmark_returns=False,
        pure_fit_needs='Selected legal adjusted returns, dated SID/issuer/risk mapping, original fit parameters and prior target if anchored',
        historical_candidate_evaluation_requires_both_benchmark_return_panels=True,
        target_012922=dict(source_definition=source,latest_nav_date_at_or_before_cutoff=observed[-1] if observed else None,
            observed_fetch_time=nav_manifest.get('fetched_at'),publication_time_known=nav_manifest.get('publication_time_known'),
            nav_manifest_hash_matched=True,fit_reference_dates_without_same_date_nav=[d for d in reference[-127:] if d not in observed],
            last505_reference_source_date_diagnostics=align,alignment_or_forward_fill_performed=False,
            publication_time_at_US_cutoff_verified=False,currency_and_fx_alignment_verified=False,legal_comparison_ready=False),
        original8=dict(manifest_path=str(CONTROL),manifest_sha256=CONTROL_SHA,definition_sha256=control['definition_sha256'],
            securities=control_rows,weights_reoptimized=False,current_broker_holdings_used=False,
            tsm_old_raw_reference=dict(path=probe['response_path'],sha256=probe['response_sha256'],received_at_utc=probe['received_at_utc'],
                receipt_day_excluded=receipt_day,latest_raw_date=tsm_dates[-1],latest_completed_raw_date=tsm_completed[-1]),
            tsm_latest_cache_calendar_coverage=assess_calendar(reference=reference,available=tsm_cache,requirements=needed),
            tsm_cache_not_substituted_for_verified_nominal_or_adjusted_input=True,legal_comparison_ready=False))


def build(snapshot_path,snapshot_sha256):
    sources=dict(LOADED)
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if sha(raw)!=h:raise ValueError('Explicit sealed input SHA differs')
        archive.merge(sources,{p:h});return raw
    snapshot=json.loads(read(snapshot_path,snapshot_sha256))
    if snapshot['schema']!='LATEST_INPUT_COVERAGE_OBSERVED_BYTES_SNAPSHOT_V1' or snapshot['cutoff']!=CUTOFF or set(snapshot['files'])!=set(SNAPSHOT_FILES):
        raise ValueError('Exact new observation snapshot required')
    archive.merge(sources,snapshot['source_hashes']);captured={}
    for key,row in snapshot['files'].items():
        if Path(row['original_path'])!=ROOT/SNAPSHOT_FILES[key]:raise ValueError('Original input role differs')
        captured[key]=read(row['snapshot_path'],row['sha256'])
        if len(captured[key])!=row['bytes']:raise ValueError('Snapshot byte count differs')
    needed=requirements(*(yaml.safe_load(captured[key]) for key in ('scope','search','generator')))
    qqq=observed_calendar(captured['QQQ'],CUTOFF);spy=observed_calendar(captured['SPY'],CUTOFF)
    length=needed['desired_training_price_rows']
    if qqq[-length:]!=spy[-length:]:raise ValueError('QQQ/SPY observed trailing calendar disagreement')
    reference=qqq[-length:]
    inventory=json.loads(read(INVENTORY,INVENTORY_SHA))
    if inventory['schema']!='CURRENT101_WITH_99_CONDITIONAL_PRICE_REFERENCES_V1' or inventory['conditional_channels']!=99:raise ValueError('Hard 99 conditional inventory required')
    archive.merge(sources,inventory['historical_expected_source_hashes'])
    if archive.verify_expected_sources(inventory['historical_expected_source_hashes'],archive.load_contract())!=inventory['archive_resolution']:
        raise ValueError('Inventory archive closure differs')
    records=[]
    notices={'CEG':'Historical when-issued CEGVV must not be joined by ticker alone; latest interval identity still unverified',
        'GEHC':'Historical when-issued phase must remain separate; latest interval identity still unverified',
        'WBD':'Predecessor share-class conversion is not a ticker rename; historical joining remains unverified',
        'SPCX':'Former same-ticker ETF history is not current issuer history; independent current channel only',
        'TRI':'Known 2026 corporate action absent from current raw event list; no conditional interval supplied',
        'CMCSA':'No independently completed conditional post-action quote interval in this bound inventory'}
    for row in inventory['rows']:
        ticker=row['ticker'];calendar=row.get('calendar',[])
        if row['status']=='BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE':
            quote_calendar=[];raw_available_count=row['original_reference'].get('valid_completed_raw_count')
        else:
            quote_calendar=calendar;raw_available_count=row['original_reference'].get('valid_completed_raw_count')
        coverage=assess_calendar(reference=reference,available=quote_calendar,requirements=needed)
        insufficient=not coverage['windows']['latest_fit_adjacent_prices']['date_coverage_complete']
        records.append(dict(ticker=ticker,conditional_price_reference_status=row['status'],conditional_available_row_count=len(quote_calendar),
            raw_completed_rows_observed_not_admitted=raw_available_count,coverage=coverage,
            latest_fit_price_coverage_status='INSUFFICIENT_OR_BLOCKED' if insufficient else 'COVERAGE_ONLY_LEGAL_RETURN_INPUT_NOT_YET_ESTABLISHED',
            identity_history_notice=notices.get(ticker),source_reference=row.get('post_action_reference') or row['original_reference'],
            historical_security_interval_identity_verified=False,point_in_time_membership_verified=False,
            adjusted_training_returns_verified=False,volume63_verified=False,median_dollar_volume_threshold_passed=None,
            legal_fit_input_ready=False,full_ndx_eligible=False,promotion_allowed=False))
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    benchmarks=benchmark_readiness(captured,reference,needed,records,read)
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    report=dict(schema='LATEST_PER_SECURITY_CONDITIONAL_INPUT_READINESS_V1',cutoff=CUTOFF,requirements=needed,
        observed_reference_calendar=reference,reference_scope='QQQ_SPY_AGREEING_OBSERVED_SESSIONS_NOT_OFFICIAL_EXCHANGE_CALENDAR',
        source_snapshot=dict(path=str(Path(snapshot_path).resolve()),sha256=snapshot_sha256),rows=records,
        observed_channels=101,conditional_price_channels=99,
        fit_price_coverage_complete_count=sum(r['coverage']['windows']['latest_fit_adjacent_prices']['date_coverage_complete'] for r in records),
        latest_fit_coverage_insufficient_tickers=[r['ticker'] for r in records if r['latest_fit_price_coverage_status']=='INSUFFICIENT_OR_BLOCKED'],
        minimum252_date_coverage_count=sum(r['coverage']['windows']['minimum_snapshot_adjusted_prices']['date_coverage_complete'] for r in records),
        desired505_date_coverage_count=sum(r['coverage']['windows']['desired_training_prices']['date_coverage_complete'] for r in records),
        legal_fit_ready_count=0,dual_benchmark_readiness=benchmarks,historical_expected_source_hashes=sources,archive_resolution=checked,
        necessary_next_inputs=['Explicit adjusted-return basis and all intervening corporate-action policy',
            'Dated security_id/issuer/ticker interval and membership evidence for decision cutoff',
            'Independent session calendar validation and original-risk-chain labels',
            '63-session volume and nominal-price dollar-liquidity evidence, not OHLC presence',
            '012922 cutoff publication/source-date/FX alignment and frozen incumbent contemporaneous inputs'],
        missing_prices_filled=False,returns_generated=False,fit_performed=False,legacy_track_eligibility_reused=False,
        provider_calendar_is_exchange_calendar=False,full_ndx_coverage_verified=False,point_in_time_verified=False,promotion_allowed=False)
    verify(report);return report


def verify(report):
    expected=report['historical_expected_source_hashes']
    if any(expected.get(p)!=h for p,h in LOADED.items()) or expected.get(str(INVENTORY))!=INVENTORY_SHA:raise ValueError('Required source omitted')
    if archive.verify_expected_sources(expected,archive.load_contract())!=report['archive_resolution']:raise ValueError('Archive source partition changed')
    if any(report[k] is not False for k in ('missing_prices_filled','returns_generated','fit_performed','legacy_track_eligibility_reused',
        'provider_calendar_is_exchange_calendar','full_ndx_coverage_verified','point_in_time_verified','promotion_allowed')):raise ValueError('Coverage cannot upgrade eligibility')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-directory',required=True);args=parser.parse_args()
    folder=Path(args.output_directory).resolve();manifest,h=sealed_snapshot(folder/'observed_inputs')
    report=build(manifest,h);path=folder/'readiness.json';verify(report);publish(path,report);verify(report)
    print(json.dumps(dict(path=str(path),sha256=sha(path.read_bytes()),fit_coverage=report['fit_price_coverage_complete_count'],insufficient=report['latest_fit_coverage_insufficient_tickers'])))
