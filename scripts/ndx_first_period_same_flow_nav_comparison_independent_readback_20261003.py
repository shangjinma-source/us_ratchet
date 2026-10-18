"""Independent saved-only first-eight metrics and evidence readback. No producer imports."""
import argparse, hashlib, json, os, math
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, Context, localcontext
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/first_period_same_flow_nav_comparison_20261003_v1'
OUTPUT=ROOT/'data/cache/research/first_period_same_flow_nav_comparison_independent_readback_20261003_v1'
RESULT_SHA='6877875e31fae9668350832fca7ba23ec75f7477bf7d12a54f0d1ae1c7c05749'
PUBLICATION_SHA='22cd0b538d5f5d46033ccfbcaa93004a4a898c6e8c9499ee84d873ac77d0b35a'
PRODUCER_REFERENCE={'path': 'E:\\Git\\us_ratchet\\scripts\\ndx_first_period_same_flow_nav_comparison_20261003.py', 'sha256': '2e0b239fe5c9054e81db3401c0df864424a051e50679f8444ce906736552e10a'}
PINS={'candidate_accounts': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/accounts.json', '4112089be89d196405da8df2e1a6266eb7ad95baad992b0759e28c7c8800c792'), 'candidate_publication': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/publication.json', 'd841df9120aead6a9cc8c0e6d003c5e4d48beed380d31fbe0d69daa032145ec9'), 'candidate_review_report': ('DYNAMIC_FIRST_PERIOD_CASH_BUY_HOLD_INDEPENDENT_READBACK_20261002.md', '95cb53e82b7f7c120659ffcebced7bd9a74e2899b2c03fd8a94c554e53005f3f'), 'candidate_reader': ('scripts/ndx_first_period_cash_buy_hold_independent_review_20261002.py', '023cb1ebfd5d3c0e15606c13f2eb279e5e27fc67734e93ad65fd71648412e70b'), 'incumbent_accounts': ('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v2/accounts.json', '7a9514dbe38b30196302453d833d31552ab3da62bd3fabc142e7c75e6a606d8a'), 'incumbent_publication': ('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v2/publication.json', '9ce38205f97506b300a6fada34652308a87cd3f882a350d8336ad646b3412204'), 'incumbent_audit': ('data/cache/research/first_period_incumbent_cash_flow_independent_readback_20261003_v2/independent_readback.json', '10b4e93693163fb7d49fd115d71754588ad592edce4b927496c38214b8ff2872'), 'incumbent_reader': ('scripts/ndx_first_period_incumbent_cash_flow_independent_readback_20261003.py', '2a3b07741eef36b822c2c357935fe992fc708e01bda94fe2bfcd39387215d745'), 'benchmark': ('data/cache/research/return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'), 'currency_manifest': ('data/cache/research/fund_012922_currency_source_20261002_v1/manifest.json', 'ff4f51f7463f0c805f6ae0542aea46883ba2476b416364d293d93d7026a5b284'), 'currency_html': ('data/cache/research/fund_012922_currency_source_20261002_v1/issuer_listing.html', '89f8a7a02aa843193bbfab8acd3a273ff7053d69fcc4256f242eb453dc43d292'), 'core': ('backtest/ndx_first_period_same_flow_comparison_research.py', 'b4c95cf965f449747ef6a9845aa59cde0386ac678c8a3d23d3d0b88f4a0423c6'), 'metrics': ('backtest/ndx_cash_fork_reference_window_research.py', '0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163')}
FLAGS=('formal_dual_benchmark_admission','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','cross_window_ranking_performed','win_rate_calculated','account_simulation_called','saved_candidates_reselected','source_bytes_authenticated_by_this_pure_module','full_transitive_source_closure_reverified','historical_price_identity_certified','fx_equivalence_verified','total_return_claimed','candidate_decision_time_executability_verified','decision_information_sets_equivalent','execution_policies_equivalent','executable_strategy_advantage_claimed','nav_publication_time_verified','nav_dataset_currency_binding_certified','subscription_execution_equivalence_verified')
ASYMMETRY={'candidate_quantity_information':'HISTORICAL_CONDITIONAL_SEARCH_USING_EXECUTION_OPEN_PRICES','incumbent_quantity_information':'PRIOR_DECISION_CLOSE_FROZEN_NO_OPEN_REPLAN','candidate_later_policy':'ONE_OFF_TOPUP_THEN_FIXED_HOLDINGS','incumbent_later_policy':'ORIGINAL_SCHEDULE_REBALANCES_USING_COUNTERFACTUAL_OWN_STATE','scope':'MATCHED_INITIAL_STATE_AND_FLOW_DO_NOT_CERTIFY_MATCHED_INFORMATION_OR_EXECUTABLE_ADVANTAGE'}
def require(ok,message):
    if not ok:raise ValueError(message)
def exact(a,b,message='Exact saved projection'):
    require(json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False),message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def ptr(ref,p):return dict(ref,json_pointer=p)
def rat(v):
    require(type(v) is dict and set(v)=={'numerator','denominator'} and all(type(x) is str for x in v.values()),'Ratio fields')
    require(int(v['denominator'])>0,'Positive denominator');return F(int(v['numerator']),int(v['denominator']))
def enc(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def false(d,keys=FLAGS):
    for k in keys:require(d[k] is False,'False authority '+k)
def close_decimal(saved,expected):
    require(type(saved) is str,'Decimal string')
    with localcontext(Context(prec=110)):
        value=Decimal(saved);require(value.is_finite() and abs(value-expected)/max(Decimal(1),abs(expected))<Decimal('1e-70'),'Independent annual arithmetic')
def check_metrics(m,days,wealth):
    require(len(days)==len(wealth)==107 and wealth[0]==1 and all(x>0 for x in wealth),'107 positive wealth points')
    # All earlier/later pairs, independent of production running-peak implementation.
    dd=max(F(0),max(1-wealth[j]/wealth[i] for j in range(107) for i in range(j+1)))
    require(rat(m['cumulative_return'])==wealth[-1]-1 and rat(m['maximum_drawdown'])==dd,'Exact return/drawdown')
    for k,n in [('observation_count',107),('interval_count',106)]:require(type(m[k]) is int and m[k]==n,'Exact metrics count')
    require(m['initial_one_in_drawdown'] is True and m['annualized_return_calculated'] is True,'Initial point/annualization')
    exact(m['wealth'],[dict(session=d,normalized_wealth=enc(v)) for d,v in zip(days,wealth)])
    exact(m['annualization'],dict(formula='terminal_normalized_wealth ** (252 / interval_count) - 1',sessions_per_year=252,interval_count=106,decimal_precision=80,rounding='ROUND_HALF_EVEN',arithmetic='DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',annualization_is_historical_diagnostic=True,short_window_below_252_intervals=True,short_window_limitation='SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',formal_admission_allowed=False))
    with localcontext(Context(prec=110)):
        annual=((Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator)).ln()*Decimal(252)/Decimal(106)).exp()-1
    close_decimal(m['annualized_return_diagnostic_decimal'],annual)
    return wealth[-1]-1,dd,annual

def inspect(out,candidates,incumbent,benchmark,refs):
    require(out['schema']=='FIRST_PERIOD_EIGHT_SAME_FLOW_NAV_REFERENCE_COMPARISON_V1','Comparison schema')
    for k,n in [('scenario_count',8),('incumbent_path_count',2)]:require(type(out[k]) is int and out[k]==n,'Output scope')
    false(out);exact(out['policy_asymmetry'],ASYMMETRY)
    require(out['comparison_scope']=='SAME_INITIAL_STATE_SAME_FLOW_CONDITIONAL_USD_PATHS_DISTINCT_RESEARCH_POLICIES','Comparison scope')
    for key in ('annualized_return_calculated','annualization_is_historical_diagnostic','short_and_unequal_windows_not_aggregated'):require(out[key] is True,'Diagnostic semantics')
    for k in ('cohort_statistics_computed','future_return_selection_feedback'):require(out[k] is False,'No feedback/cohort')
    require(out['wealth_arithmetic']=='SAVED_CUMULATIVE_TWR_PLUS_ONE_NOT_ACCOUNT_EQUITY_RATIO','TWR not equity')
    require(out['reference_metrics_dependency_sha256']==PINS['metrics'][1],'Declared frozen metrics')
    days=benchmark['calendar'];require(len(days)==107 and days==sorted(set(days)) and days[:2]==['2023-03-31','2023-04-03'] and days[-1]=='2023-09-01','Full fixed calendar')
    for d in days:require(date.fromisoformat(d).isoformat()==d,'Canonical date')
    exact(candidates['observed_calendar'],days)
    require(benchmark['schema']=='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1','Benchmark schema');false(benchmark,('point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','execution_rerun'))
    nav=benchmark['nav'];false(nav,('publication_time_verified','currency_fx_equivalence_verified','subscription_redemption_fee_equivalence_verified'))
    require(nav['role']=='012922_NATIVE_CURRENCY_RETROSPECTIVE_NAV' and [r['session'] for r in nav['rows']]==days,'Native NAV role/full rows')
    navout=out['nav_reference'];exact(navout['calendar'],days);exact(navout['metadata'],{k:v for k,v in nav.items() if k!='rows'})
    require(navout['currency_label']=='CNY_CONDITIONAL_CURRENT_ISSUER_LABEL_NOT_HISTORICAL_CLASS_CERTIFICATION','Currency scope');false(navout,('fx_conversion_performed','nav_source_reexecuted','formal_admission_allowed'))
    values=[];observations=[];dated={};previous=None
    for i,row in enumerate(nav['rows']):
        require(type(row['nav']) is float and math.isfinite(row['nav']) and row['nav']>0,'Saved float NAV')
        n=F(str(row['nav']));nd=row['nav_date'];require(date.fromisoformat(nd).isoformat()==nd and nd<=days[i] and (previous is None or nd>=previous),'Backward NAV date')
        require(nd not in dated or dated[nd]==n,'Conflicting dated NAV');dated[nd]=n;previous=nd;values.append(n)
        observations.append(dict(reference=ptr(refs['benchmark'],f'/nav/rows/{i}'),source_row=row,decimal_literal=str(row['nav']),encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE',calendar_day_lag=(date.fromisoformat(days[i])-date.fromisoformat(nd)).days,publication_time=None))
    exact(navout['observations'],observations);navmetrics=check_metrics(navout['metrics'],days,[v/values[0] for v in values])
    require(len(candidates['rows'])==len(out['rows'])==len(incumbent['scenario_mappings'])==8 and len(incumbent['paths'])==2,'Exact cardinalities')
    mappings={r['scenario_id']:(i,r) for i,r in enumerate(incumbent['scenario_mappings'])};paths={r['path_id']:(i,r) for i,r in enumerate(incumbent['paths'])}
    require(len(mappings)==8 and len(paths)==2,'Unique mappings');coordinates=set();pathuses={k:0 for k in paths}
    for i,(r,c) in enumerate(zip(out['rows'],candidates['rows'])):
        mi,mp=mappings[c['scenario_id']];pi,p=paths[mp['path_id']];a=p['account'];initial=c['accounting_inputs']['initial'];ev=c['input_row']['cash_event']
        exact(mp['original_input_row'],c['input_row']);exact(mp['input_reference'],c['input_reference']);exact(mp['candidate_account_reference'],ptr(refs['candidate_accounts'],f'/rows/{i}'))
        coordinate=(c['input_row']['lane'],ev['amount_usd']);require(coordinate not in coordinates and coordinate[0] in ('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE') and coordinate[1] in ('1000','10000'),'Unique four lanes/two amounts');coordinates.add(coordinate);pathuses[mp['path_id']]+=1
        require(ev['decision_date']=='2023-03-31' and ev['execution_date']=='2023-04-03' and mp['path_id']=='2023-03-31|'+ev['amount_usd'],'Scenario dates/path')
        preserved={'scenario_id':c['scenario_id'],'input_row':c['input_row'],'original_input_reference':c['input_reference'],'incumbent_mapping_preserved':mp,'candidate_selected_plan_reference':c['selected_plan_reference'],'candidate_saved_selection':c['saved_selection'],'candidate_selection_reference':c['selection_reference'],'candidate_initial_state':initial,'incumbent_initial_state':a['initial'],'calendar':days,'policy_asymmetry':ASYMMETRY}
        for k,v in preserved.items():exact(r[k],v,k)
        for k,v in {'candidate_paired_row_reference':ptr(refs['candidate_accounts'],f'/rows/{i}'),'incumbent_path_reference':ptr(refs['incumbent_accounts'],f'/paths/{pi}'),'incumbent_mapping_reference':ptr(refs['incumbent_accounts'],f'/scenario_mappings/{mi}'),'fund_nav_reference':ptr(refs['benchmark'],'/nav')}.items():exact(r[k],v,k)
        require(initial['session']==a['initial']['session']=='2023-03-31' and initial['holdings']==a['initial']['holdings']=={} and initial['close_prices']=={} and len(a['initial']['close_prices'])==8,'Initial empty holdings/plan marks')
        require(F(initial['cash_usd'])==F(a['initial']['cash_usd'])==25000 and all(F(v)>0 for v in a['initial']['close_prices'].values()),'Initial cash/marks')
        require(F(c['accounting_inputs']['transaction_cost_bps'])==F(a['transaction_cost_bps'])==F(c['input_row']['transaction_cost_bps']),'Fee contract')
        require(a['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN' and a['risk_is_order_gate'] is False,'Close plan policy')
        require(c['account']['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES' and a['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES','Flow timing')
        stats={}
        for role,daily,account,ref,base in [('candidate',c['account']['rows'],c['account'],refs['candidate_accounts'],f'/rows/{i}/account/rows'),('same_flow_incumbent',a['daily'],a,refs['incumbent_accounts'],f'/paths/{pi}/account/daily')]:
            require([x['session'] for x in daily]==days[1:] and len(daily)==106,'106 exact intervals')
            false(account,('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled'))
            for j,x in enumerate(daily):require(F(x['cash_injection_usd'])==(F(ev['amount_usd']) if j==0 else 0),'One exact flow')
            require(F(account['total_cash_injection_usd'])==F(ev['amount_usd']) and rat(account['chained_twr'])==rat(daily[-1]['cumulative_twr']),'Aggregate flow/TWR')
            exact(r['observations'][role],[dict(reference=ptr(ref,f'{base}/{j}'),source_row=x) for j,x in enumerate(daily)])
            stats[role]=check_metrics(r['metrics'][role],days,[F(1)]+[1+rat(x['cumulative_twr']) for x in daily])
        diff=r['candidate_minus_incumbent']
        for j,k in enumerate(('cumulative_return','maximum_drawdown')):require(rat(diff[k])==stats['candidate'][j]-stats['same_flow_incumbent'][j],'Signed difference')
        with localcontext(Context(prec=110)):
            close_decimal(diff['annualized_return_diagnostic_decimal'],stats['candidate'][2]-stats['same_flow_incumbent'][2])
            nd=r['nav_distances'];dist={role:tuple(abs(v-n) for v,n in zip(s,navmetrics)) for role,s in stats.items()}
            for role,ds in dist.items():
                for j,k in enumerate(('cumulative_return','maximum_drawdown')):require(rat(nd['absolute_distances'][role][k])==ds[j],'Absolute NAV distance')
                close_decimal(nd['absolute_distances'][role]['annualized_return_diagnostic_decimal'],ds[2])
            for j,k in enumerate(('cumulative_return','maximum_drawdown')):require(rat(nd['candidate_minus_incumbent_absolute_distance'][k])==dist['candidate'][j]-dist['same_flow_incumbent'][j],'Distance difference')
            close_decimal(nd['candidate_minus_incumbent_absolute_distance']['annualized_return_diagnostic_decimal'],dist['candidate'][2]-dist['same_flow_incumbent'][2])
        require(nd['negative_difference_means_smaller_distance'] is True and nd['currency_equivalence_verified'] is False and nd['scope']=='EX_POST_NATIVE_NAV_VS_USD_PATH_DIAGNOSTIC_NOT_FX_NEUTRAL_OR_EXECUTABLE_BENCHMARK_GATE','No FX certification')
        require(diff['annual_difference_precision']==80 and type(diff['annual_difference_precision']) is int and diff['annual_difference_rounding']=='ROUND_HALF_EVEN' and diff['annual_difference_is_historical_diagnostic'] is True,'Annual diagnostic')
        false(r)
        for key in ('same_initial_state_verified_within_supplied_documents','same_flow_timing_and_amount_verified_within_supplied_documents'):require(r[key] is True,'Matched scenario semantics')
        require(r['initial_state_scope']=='EQUAL_EMPTY_HOLDINGS_AND_25000_CASH_INCUMBENT_EIGHT_CLOSE_MARKS_PLAN_ONLY','Initial state scope')
        require(r['currency_scope']=='USD_CONDITIONAL_SAVED_PATHS_NOT_NEW_PRICE_IDENTITY_OR_FX_CERTIFICATION','Currency scope')
    require(set(pathuses.values())=={4},'Four exact mappings per path')
    return dict(scenarios=8,incumbent_paths=2,independent_metrics=17,account_observation_rows=1696,nav_observations=107,interval_count=106,annual_method='INDEPENDENT_DECIMAL110_LN_EXP_TOLERANCE_1E_MINUS70',drawdown_method='EXACT_FRACTION_ALL_EARLIER_LATER_PAIRS_INCLUDING_INITIAL_ONE',accounts_recomputed=False,formal_admission=False)
def expected_sources():
    refs={k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in PINS.items()}
    base={PRODUCER_REFERENCE['path']:PRODUCER_REFERENCE['sha256']}
    for r in refs.values():
        require(r['path'] not in base or base[r['path']]==r['sha256'],'Source conflict');base[r['path']]=r['sha256']
    require(len(base)==14 and len(refs)==13,'Fixed producer plus thirteen dependencies')
    return refs,base

def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader changed')
    for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source changed '+p)

def load_json(path,h,sources):
    b=Path(path).read_bytes();require(sha(b)==h,'Consumed bytes hash');sources[str(path)]=h;return json.loads(b)

def check_parent_evidence(d,refs):
    for role,pschema in [('candidate','FIRST_PERIOD_CASH_BUY_HOLD_PUBLICATION_V1'),('incumbent','FIRST_PERIOD_INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V2')]:
        doc=d[role+'_accounts'];pub=d[role+'_publication'];require(pub['schema']==pschema and pub['status']==('PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS' if role=='candidate' else 'PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS'),'Parent receipt schema/status')
        exact(pub['account_reference'],refs[role+'_accounts']);exact(pub['source_hashes'],doc['source_hashes']);false(pub,('orders_executed','point_in_time_verified','promotion_allowed'));false(doc,('orders_executed','point_in_time_verified','promotion_allowed'))
    a=d['incumbent_audit'];require(a['schema']=='FIRST_PERIOD_INCUMBENT_CASH_FLOW_INDEPENDENT_READBACK_V1' and a['status']=='PASS','Incumbent audit')
    exact(a['accounts_reference'],refs['incumbent_accounts']);exact(a['publication_reference'],refs['incumbent_publication']);require(a['reader_sha256']==refs['incumbent_reader']['sha256'],'Incumbent reader')
    for key,value in dict(paths=2,daily=212,decisions=12,mappings=8).items():require(type(a['counts'][key]) is int and a['counts'][key]==value,'Exact saved audit scope')
    false(a,('formal_admission','point_in_time_verified','promotion_allowed','production_functions_called','old_experiments_reexecuted'))
    for role in ('incumbent_accounts','incumbent_publication','incumbent_reader'):require(a['source_hashes'].get(refs[role]['path'])==refs[role]['sha256'],'Audit direct source')
    for role in ('candidate_accounts','candidate_publication'):
        require(refs[role]['sha256'] in d['candidate_review_report'].decode('utf-8') and refs[role]['sha256'] in d['candidate_reader'].decode('utf-8'),'Saved candidate readback')
    require(refs['candidate_reader']['sha256'] in d['candidate_review_report'].decode('utf-8'),'Saved candidate reader evidence')
    c=d['currency_manifest'];require(c['schema']=='FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1' and c['fund_code']=='012922' and c['currency']=='CNY','Conditional issuer currency')
    exact(c['source_reference'],refs['currency_html'])
    false(c,('nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','fx_rates_supplied','point_in_time_verified','promotion_allowed','subscription_terms_verified'))

def readback(*,execute=False):
    require(execute is True,'Explicit execute');require(not OUTPUT.exists(),'Independent namespace exists')
    require(all(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef') for h in (RESULT_SHA,PUBLICATION_SHA)),'Pending actual pins')
    refs,base=expected_sources();sources={str(SOURCE):LOADED_SHA,**base};guard(sources)
    require({p.name for p in PARENT.iterdir()}=={'started.json','comparison.json','publication.json'},'Exact parent success directory')
    outref=dict(path=str(PARENT/'comparison.json'),sha256=RESULT_SHA);pubref=dict(path=str(PARENT/'publication.json'),sha256=PUBLICATION_SHA)
    out=load_json(outref['path'],RESULT_SHA,sources);pub=load_json(pubref['path'],PUBLICATION_SHA,sources)
    started_bytes=(PARENT/'started.json').read_bytes();sources[str(PARENT/'started.json')]=sha(started_bytes);started=json.loads(started_bytes)
    require(started['schema']=='FIRST_PERIOD_SAME_FLOW_NAV_COMPARISON_STARTED_V1' and started['retry_allowed'] is False,'Started contract')
    exact(started['input_references'],refs);exact(started['source_hashes'],base);exact(out['source_hashes'],base);exact(pub['source_hashes'],base);exact(out['input_references'],refs)
    require(pub['schema']=='FIRST_PERIOD_SAME_FLOW_NAV_COMPARISON_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON','Publication success');exact(pub['comparison_reference'],outref)
    pubflags=('orders_executed','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','economic_winner_selected','account_simulation_called','full_transitive_source_closure_reverified','candidate_decision_time_executability_verified')
    false(pub,pubflags);false(started,pubflags)
    docs={}
    for role,r in refs.items():
        b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed dependency')
        docs[role]=json.loads(b) if role in ('candidate_accounts','candidate_publication','incumbent_accounts','incumbent_publication','incumbent_audit','benchmark','currency_manifest') else b
    check_parent_evidence(docs,refs)
    exact(out['currency_manifest_preserved'],docs['currency_manifest']);exact(out['parent_source_hashes_preserved_not_reaudited'],{k:docs[k].get('source_hashes',{}) for k in ('candidate_accounts','incumbent_accounts','benchmark')})
    require(out['candidate_audit_evidence_type']=='SAVED_REVIEW_REPORT_AND_READER_NOT_NEW_MACHINE_ATTESTATION' and out['benchmark_numeric_audit_reperformed'] is False,'Evidence scope')
    detail=inspect(out,docs['candidate_accounts'],docs['incumbent_accounts'],docs['benchmark'],refs)
    guard(sources)
    report=dict(schema='FIRST_PERIOD_SAME_FLOW_NAV_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',comparison_reference=outref,publication_reference=pubref,reader_sha256=LOADED_SHA,source_hashes=sources,detail=detail,started_reference_externally_anchored=False,started_scope='CURRENT_SAVED_BYTES_CHECKED_AGAINST_FIXED_INPUTS_NOT_EXTERNAL_STARTED_ATTESTATION',formal_admission=False,point_in_time_verified=False,promotion_allowed=False,account_simulation_called=False,production_metrics_called=False,full_transitive_source_closure_reverified=False)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        payload=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode();path=OUTPUT/'independent_readback.json'
        with path.open('xb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
        guard(sources);require(path.read_bytes()==payload and {p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Final independent output bytes/directory')
        return dict(path=str(path),sha256=sha(payload))
    except Exception as error:
        failure=(json.dumps(dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False),sort_keys=True)+'\n').encode()
        with (OUTPUT/'failure.json').open('xb') as f:f.write(failure);f.flush();os.fsync(f.fileno())
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');args=p.parse_args();print(json.dumps(readback(execute=args.execute)))
