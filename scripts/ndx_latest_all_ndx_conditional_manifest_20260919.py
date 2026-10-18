"""Complete current observation manifest, never a PIT-eligible or fitted universe."""
import argparse,copy,hashlib,json,sys
from collections import defaultdict
from datetime import date
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research';CUTOFF='2026-09-17'
ANCHORS={
 'observation':(BASE/'ndx_current_quote_list_capture_20260919_v1/observation.json','50cbca76647e14d99f4990deff0c6adc7226f31109393df2fa0298b062fc5c77'),
 'issuers':(BASE/'current_92_sec_submissions_capture_20260919_v1/current101_issuer_facts.json','4fdd72c4f8887d59ad802ef37ac1641415888fb9c604b8a91601cb219a023d9d'),
 'prices':(BASE/'current99_conditional_price_inventory_20260919_v1/inventory.json','59ebaf50fdf35c6c390a747de026bc353200f64525b9c30f3e14d935aba209f3'),
 'readiness':(BASE/'latest_conditional_input_readiness_20260919_v1/readiness.json','b3a215d05cfb085c4637713d65fb86d565def48728cb382efe94ad1e206d3c49'),
 'scope':(ROOT/'config/ndx_membership_scope_research_v1.yaml','3136387ea83523bd22068c7f70b282dcd44d9195efed985e630bcacd187f5d2a')}
SCHEMA='LATEST_ALL_NDX_OBSERVED_CONDITIONAL_INPUT_MANIFEST_V1'
FALSE=('industry_filter_applied','legacy_tracks_reused','full_point_in_time_universe_verified','legal_training_input_admitted',
       'security_classes_inferred_from_names','security_id_invented','returns_generated','fit_performed','winner_selected',
       'execution_authorized','point_in_time_verified','promotion_allowed')
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE,Path(publish.__code__.co_filename).resolve())}

def exact(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)
def unique(pairs):
    result={}
    for k,v in pairs:
        if k in result:raise ValueError('Duplicate JSON key')
        result[k]=v
    return result
def dates(values):
    if type(values) is not list or values!=sorted(set(values)) or any(type(d) is not str or date.fromisoformat(d).isoformat()!=d or d>CUTOFF for d in values):raise ValueError('Canonical completed observed dates required')
    return values
def keyed(rows,field,expected):
    if len(rows)!=len(expected) or {r[field] for r in rows}!=set(expected):raise ValueError('Complete unique current security denominator required')
    return {r[field]:r for r in rows}
def coverage(reference,available):
    have=set(available);windows={}
    for key,length in (('latest_fit_adjacent_prices',127),('minimum_snapshot_adjusted_prices',252),('desired_training_prices',505),('liquidity_dates_only',63)):
        required=reference[-length:];missing=[d for d in required if d not in have]
        windows[key]=dict(required_rows=length,first=required[0],last=required[-1],available_count=length-len(missing),missing_dates=missing,date_coverage_complete=not missing)
    pairs=[dict(return_session=b,previous_price_session=a,missing_prices=[d for d in (a,b) if d not in have]) for a,b in zip(reference[-127:],reference[-126:])]
    return dict(windows=windows,fit_return_date_pairs=pairs,fit_return_pairs_with_both_prices=sum(not p['missing_prices'] for p in pairs),
        quote_covers_latest_cutoff=reference[-1] in have,extra_provider_dates_in_training_range=[d for d in available if reference[0]<=d<=reference[-1] and d not in set(reference)])

def assemble(*,observation,issuers,prices,readiness,scope):
    symbols=observation['observed_symbols']
    if len(symbols)!=101 or len(set(symbols))!=101 or observation['observed_security_count']!=101:raise ValueError('Hard 101 current observed securities required')
    if (scope['scope_change']['authorized_scope']!='ALL_POINT_IN_TIME_NASDAQ_100_MEMBERS_MAY_COMPETE'
        or scope['scope_change']['industry_filter_applied'] is not False or scope['scope_change']['scope_changed'] is not True):raise ValueError('All-NDX authorization without industry filtering required')
    if observation['point_in_time_membership_verified'] is not False or issuers['point_in_time_verified'] is not False or prices['point_in_time_verified'] is not False:raise ValueError('Observation is not PIT certification')
    obs=keyed(observation['rows'],'symbol',symbols);ids=keyed(issuers['rows'],'ticker',symbols);quotes=keyed(prices['rows'],'ticker',symbols);ready=keyed(readiness['rows'],'ticker',symbols)
    reference=dates(readiness['observed_reference_calendar'])
    if readiness['cutoff']!=CUTOFF or len(reference)!=505 or reference[-1]!=CUTOFF:raise ValueError('Hard cutoff and full reference calendar required')
    groups=defaultdict(list);rows=[]
    for ticker in symbols:
        issuer=ids[ticker];cik=issuer['current_reported_cik'];iid=issuer['conditional_issuer_id'];q=quotes[ticker];r=ready[ticker]
        if type(cik) is not str or len(cik)!=10 or not cik.isdecimal() or iid!='issuer:'+cik or issuer['reported_exchange']!='Nasdaq' or issuer['current_issuer_ticker_exchange_observed'] is not True:raise ValueError('Explicit SEC current issuer coordinate required')
        candidate=issuer['matched_candidate'];position=issuer['reported_ticker_exchange_position']
        if type(position) is not int or position<0 or candidate['reported_cik']!=cik or candidate['reported_tickers'][position]!=ticker or candidate['reported_exchanges'][position]!='Nasdaq':raise ValueError('Same-position current SEC ticker/exchange required')
        groups[iid].append(ticker)
        blocked=q['status']=='BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE';available=[] if blocked else dates(q['calendar'])
        if q['status'] not in ('BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE','ORIGINAL_CONDITIONAL_REFERENCE','CONDITIONAL_POST_ACTION_REFERENCE'):raise ValueError('Unknown quote use status')
        if not blocked and (type(q['row_count']) is not int or q['row_count']!=len(available)):raise ValueError('Conditional row denominator differs')
        calculated=coverage(reference,available)
        if not exact(calculated,r['coverage']) or r['conditional_price_reference_status']!=q['status'] or r['conditional_available_row_count']!=len(available):raise ValueError('Independently reconstructed coverage differs')
        quote_reference=q.get('post_action_reference') or q['original_reference']
        if not exact(r['source_reference'],quote_reference):raise ValueError('Hard quote reference differs')
        if r['legal_fit_input_ready'] is not False or r['full_ndx_eligible'] is not False or r['point_in_time_membership_verified'] is not False:raise ValueError('Coverage cannot confer qualification')
        failures=[]
        if blocked:failures.append('NO_CONDITIONAL_PRICE_REFERENCE')
        if not calculated['windows']['latest_fit_adjacent_prices']['date_coverage_complete']:failures.append('INSUFFICIENT_127_ADJACENT_PRICES')
        if not calculated['windows']['minimum_snapshot_adjusted_prices']['date_coverage_complete']:failures.append('INSUFFICIENT_LEGACY_252_PRICE_DATES')
        events=copy.deepcopy(q['original_reference']['returned_split_events'])
        for event in events:
            if date.fromisoformat(event['session']).isoformat()!=event['session']:raise ValueError('Event date differs')
        rows.append(dict(ticker=ticker,provider_channel_id='observed_provider_channel:'+ticker,conditional_issuer_id=iid,
            current_reported_cik=cik,current_ticker_exchange_position=position,current_exchange='Nasdaq',
            issuer_observation=copy.deepcopy(issuer),observed_company_display_text=obs[ticker]['companyName'],
            security_id=None,share_class=None,share_class_evidence_status='NOT_ASSEMBLED_NOT_INFERRED_FROM_COMPANY_NAME',
            membership_status='CURRENT_OFFICIAL_OBSERVATION_NOT_VERIFIED_AT_DECISION_CUTOFF',
            price_status=q['status'],conditional_quote_reference=copy.deepcopy(quote_reference),coverage=calculated,
            raw_returned_split_events=events,returned_events_in_fit_price_window=[e for e in events if reference[-127]<=e['session']<=CUTOFF],
            returned_events_on_or_after_liquidity_start=[e for e in events if e['session']>=reference[-63]],
            history_failures=failures,unresolved_qualification=['POINT_IN_TIME_MEMBERSHIP','DATED_SECURITY_INTERVAL_AND_SHARE_CLASS','CONDITIONAL_RETURN_PANEL','VOLUME_UNIT_AND_63_DAY_THRESHOLD','ORIGINAL_RISK_CHAIN'],
            conditional_numeric_fit_date_coverage_only=not calculated['windows']['latest_fit_adjacent_prices']['missing_dates'],
            legal_fit_input_ready=False,point_in_time_verified=False,promotion_allowed=False))
    group_map={k:sorted(v) for k,v in sorted(groups.items())}
    declared_groups=issuers['issuer_to_observed_tickers']
    if len(groups)!=100 or any(len(v)!=len(set(v)) for v in declared_groups.values()) or group_map!={k:sorted(v) for k,v in declared_groups.items()}:raise ValueError('Exact observed issuer denominator differs')
    counts=dict(observed_securities=101,observed_issuers=100,conditional_price_channels=sum(r['price_status']!='BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE' for r in rows),
        fit127_date_coverage=sum(r['coverage']['windows']['latest_fit_adjacent_prices']['date_coverage_complete'] for r in rows),
        minimum252_date_coverage=sum(r['coverage']['windows']['minimum_snapshot_adjusted_prices']['date_coverage_complete'] for r in rows),
        desired505_date_coverage=sum(r['coverage']['windows']['desired_training_prices']['date_coverage_complete'] for r in rows),verified_eligible_issuers=0,legal_fit_ready=0)
    if counts!={'observed_securities':101,'observed_issuers':100,'conditional_price_channels':99,'fit127_date_coverage':96,'minimum252_date_coverage':96,'desired505_date_coverage':91,'verified_eligible_issuers':0,'legal_fit_ready':0}:raise ValueError('Hard observation coverage partition differs')
    return dict(schema=SCHEMA,cutoff=CUTOFF,scope='ALL_NDX_CURRENT_OBSERVED_CONDITIONAL_RESEARCH_NOT_POINT_IN_TIME_ELIGIBILITY',rows=rows,counts=counts,
        issuer_to_observed_tickers=group_map,one_security_per_issuer_per_portfolio_required=True,observed_reference_calendar=reference,
        observation_timing={k:observation.get(k) for k in ('provider_asof','provider_display_date','observation_scope')},
        observation_date_not_membership_effective_date=True,desired505_is_hard_admission_threshold=False,
        all_k_planning_status='NOT_RUN_REQUIRES_EXPLICIT_CONDITIONAL_SUBSET_AND_ORIGINAL_RISK_PARAMETERS',**dict.fromkeys(FALSE,False))

def load_inputs():
    sources=dict(LOADED);docs={}
    for key,(path,h) in ANCHORS.items():
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Hard source differs')
        archive.merge(sources,{str(path):h});docs[key]=yaml.safe_load(raw) if key=='scope' else json.loads(raw,object_pairs_hook=unique)
        for field in ('source_hashes','historical_expected_source_hashes'):
            if field in docs[key]:archive.merge(sources,docs[key][field])
    return docs,sources

def build():
    docs,sources=load_inputs();contract=archive.load_contract();partition=archive.verify_expected_sources(sources,contract)
    result=assemble(**docs);result.update(historical_expected_source_hashes=sources,archive_resolution=partition,
        input_references={k:dict(path=str(p),sha256=h) for k,(p,h) in ANCHORS.items()})
    verify(result);return result

def verify(value):
    docs,required=load_inputs()
    expected=assemble(**docs)
    if any(not exact(value.get(k),v) for k,v in expected.items()):raise ValueError('Observed denominator/fields/research boundary changed')
    if value['input_references']!={k:dict(path=str(p),sha256=h) for k,(p,h) in ANCHORS.items()}:raise ValueError('Hard references differ')
    if value['historical_expected_source_hashes']!=required:raise ValueError('Complete declared source closure required')
    if archive.verify_expected_sources(required,archive.load_contract())!=value['archive_resolution']:raise ValueError('Source partition differs')

def publish_verified(path,value):
    verify(value);saved=publish(path,value);verify(value);return saved

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args();print(json.dumps(publish_verified(args.output,build())))
