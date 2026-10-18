"""Read-only four-role exact-window diagnostics; no prior account or benchmark replay."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from fractions import Fraction
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/topup_reference_comparison_20261002_v1'
SCHEMA='TOPUP_FOUR_ROLE_REFERENCE_COMPARISON_V1'
PINS={
 'accounts':('data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json','7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'publication':('data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json','fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'benchmark':('data/cache/research/return_six_period_benchmarks_20260923_v1/benchmarks.json','ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'),
 'currency_manifest':('data/cache/research/fund_012922_currency_source_20261002_v1/manifest.json','ff4f51f7463f0c805f6ae0542aea46883ba2476b416364d293d93d7026a5b284'),
 'currency_html':('data/cache/research/fund_012922_currency_source_20261002_v1/issuer_listing.html','89f8a7a02aa843193bbfab8acd3a273ff7053d69fcc4256f242eb453dc43d292'),
 'pure':('backtest/ndx_cash_fork_reference_window_research.py','0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163')}
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')
FLAGS=dict.fromkeys(('old_accounts_reexecuted','old_benchmark_reexecuted','nav_producer_called','formal_dual_benchmark_admission',
 'point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','cross_window_ranking_performed',
 'full_transitive_source_closure_reverified','nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified',
 'currency_fx_equivalence_verified','nav_publication_time_verified','same_flow_incumbent_policy_modelled'),False)
FLAGS['annualized_return_calculated']=True


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(value): return (json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
def pointer(ref,path): return dict(ref,json_pointer=path)


def float_literal(value):
    require(type(value) is float and math.isfinite(value) and value>0,'Positive saved JSON float required')
    return str(value)


def flows(path):
    events=[]
    for row in path['account']['rows']:
        require(type(row['cash_injection_usd']) is str,'Saved flow string required')
        amount=Fraction(row['cash_injection_usd']); require(amount>=0,'Nonnegative saved flow required')
        if amount:
            events.append({'session':row['session'],'amount_usd':row['cash_injection_usd'],
                'timing':path['account']['cash_event_timing']})
    return events


def assemble(docs,refs,compare):
    accounts,benchmark,currency=(docs[role] for role in ('accounts','benchmark','currency_manifest'))
    require(accounts['schema']=='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1' and len(accounts['rows'])==40
            and type(accounts['scenario_count']) is int and accounts['scenario_count']==40,'Paired forty-account contract')
    require(benchmark['schema']=='RETURN_SIX_PERIOD_REUSED_BENCHMARK_PREFIX_V1','Saved benchmark schema')
    for doc in (accounts,benchmark):
        for flag in ('point_in_time_verified','promotion_allowed'): require(doc[flag] is False,'Parent authority')
    require(benchmark['formal_dual_benchmark_admission'] is False and benchmark['execution_rerun'] is False,'Benchmark scope differs')
    require(currency['schema']=='FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1' and currency['fund_code']=='012922'
            and currency['currency']=='CNY' and currency['source_reference']==refs['currency_html'],'Current currency evidence mismatch')
    for flag in ('nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','fx_rates_supplied',
                 'point_in_time_verified','promotion_allowed','subscription_terms_verified'):
        require(currency[flag] is False,'Current currency metadata must not become historical certification')
    calendar=benchmark['calendar']
    require(len(calendar)==107 and calendar==accounts['observed_calendar'] and calendar==sorted(set(calendar))
            and calendar[0]=='2023-03-31' and calendar[-1]=='2023-09-01','Exact saved common107 calendar')
    inc_rows=benchmark['incumbent']['daily']; nav_rows=benchmark['nav']['rows']
    require([row['session'] for row in inc_rows]==calendar and [row['session'] for row in nav_rows]==calendar,'Complete reference calendar; no dropping')
    require(benchmark['nav']['publication_time_verified'] is False
            and benchmark['nav']['currency_fx_equivalence_verified'] is False
            and benchmark['nav']['subscription_redemption_fee_equivalence_verified'] is False,'NAV scope differs')
    expected={(lane,d,e,amount) for lane in LANES for d,e,_ in CLOCKS for amount in ('1000','10000')}
    seen=set(); ids=set(); rows=[]
    for index,paired in enumerate(accounts['rows']):
        row=paired['input_row']; event=row['cash_event']
        coordinate=(row['lane'],event['decision_date'],event['execution_date'],event['amount_usd'])
        require(coordinate in expected and coordinate not in seen and paired['scenario_id']==row['scenario_id']
                and paired['scenario_id'] not in ids,'Unique complete40 scenario coordinate required')
        seen.add(coordinate); ids.add(paired['scenario_id'])
        candidate=paired['paths']['candidate']; control=paired['paths']['same_flow_zero_trade_control']
        initial=candidate['accounting_inputs']['initial']; initial_control=control['accounting_inputs']['initial']
        require(initial==initial_control and initial['session']==event['decision_date'],'Common initial state required')
        start=calendar.index(initial['session']); window=calendar[start:]; observed=window[1:]
        require(observed[0]==event['execution_date'] and len(observed)==next(n for d,e,n in CLOCKS if d==event['decision_date']),'Exact window length')
        evidence={'candidate':[],'same_flow_zero_trade_control':[],'saved_incumbent':[],'fund_nav':[]}
        twr={}
        for role,path in [('candidate',candidate),('same_flow_zero_trade_control',control)]:
            require([entry['session'] for entry in path['account']['rows']]==observed,'Exact saved path calendar required')
            twr[role]=[]
            for j,entry in enumerate(path['account']['rows']):
                twr[role].append({'session':entry['session'],'cumulative_twr':deepcopy(entry['cumulative_twr'])})
                evidence[role].append({'reference':pointer(refs['accounts'],f'/rows/{index}/paths/{role}/account/rows/{j}'),'source_row':deepcopy(entry)})
        prepared_inc=[]; prepared_nav=[]
        for offset,session in enumerate(window):
            j=start+offset; incumbent=inc_rows[j]; nav=nav_rows[j]
            prepared_inc.append({'session':session,'value':float_literal(incumbent['total_value_usd'])})
            prepared_nav.append({'session':session,'nav_date':nav['nav_date'],'value':float_literal(nav['nav'])})
            evidence['saved_incumbent'].append({'reference':pointer(refs['benchmark'],f'/incumbent/daily/{j}'),
                'source_row':deepcopy(incumbent),'value_field':'total_value_usd','encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE'})
            evidence['fund_nav'].append({'reference':pointer(refs['benchmark'],f'/nav/rows/{j}'),
                'source_row':deepcopy(nav),'value_field':'nav','encoding':'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE'})
        candidate_flows,control_flows=flows(candidate),flows(control)
        require(len(candidate_flows)==1 and candidate_flows[0]['session']==event['execution_date']
                and Fraction(candidate_flows[0]['amount_usd'])==Fraction(event['amount_usd']),'Saved one-flow scenario mismatch')
        result=compare(initial_session=initial['session'],observed_sessions=observed,
            candidate_cumulative_twr=twr['candidate'],control_cumulative_twr=twr['same_flow_zero_trade_control'],
            incumbent_rows=prepared_inc,nav_rows=prepared_nav,candidate_flow_events=candidate_flows,control_flow_events=control_flows,
            candidate_currency='USD',control_currency='USD',incumbent_currency='USD',nav_currency='CNY')
        require(result['schema']=='CASH_FORK_FOUR_ROLE_EXACT_REFERENCE_WINDOW_V1'
                and result['calendar']==window and result['formal_dual_benchmark_admission'] is False,'Pure comparison contract')
        rows.append({'scenario_id':paired['scenario_id'],'lane':row['lane'],'cash_event':deepcopy(event),
            'paired_row_reference':pointer(refs['accounts'],f'/rows/{index}'),'input_row':deepcopy(row),
            'saved_topup_context':deepcopy(paired['topup_context']),
            'saved_selected_plan_reference':deepcopy(paired['selected_plan_reference']),
            'initial_reference':pointer(refs['accounts'],f'/rows/{index}/paths/candidate/accounting_inputs/initial'),
            'saved_initial_state':deepcopy(initial),'observations':evidence,'comparison':result,
            'source_role_limitations':{'same_flow_control':'SAME_FLOW_ZERO_TRADE_NOT_FORMAL_INCUMBENT_POLICY',
                'saved_incumbent':'SAVED_ORIGINAL_REBALANCING_WITHOUT_THIS_INJECTION',
                'fund_nav':'CNY_LABEL_FROM_CURRENT_ISSUER_LISTING_NOT_HISTORICAL_NAV_CERTIFICATION_NO_FX_NO_EXECUTION'},**FLAGS})
    require(seen==expected,'Missing main scenarios')
    return {'schema':SCHEMA,'rows':rows,'scenario_count':40,'input_references':deepcopy(refs),
        'currency_manifest_preserved':deepcopy(currency),
        'benchmark_metadata_without_saved_paths':{key:deepcopy(value) for key,value in benchmark.items() if key not in ('incumbent','nav')},
        'incumbent_metadata_without_path':{key:deepcopy(value) for key,value in benchmark['incumbent'].items() if key!='daily'},
        'nav_metadata_without_path':{key:deepcopy(value) for key,value in benchmark['nav'].items() if key!='rows'},
        'parent_source_hashes_preserved_not_reaudited':{role:deepcopy(doc.get('source_hashes',doc.get('historical_expected_source_hashes',{}))) for role,doc in docs.items()},
        'comparison_role_count':4,'comparison_scope':'SAME_WINDOW_DIAGNOSTICS_NOT_FORMAL_SAME_FLOW_SAME_CURRENCY_BENCHMARK_GATE',
        'short_and_unequal_window_limitation':'KEEP_EACH_WINDOW_INTERVAL_COUNT_NO_CROSS_WINDOW_WINNER',**FLAGS}


def write_new(path,value):
    raw=encode(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output bytes differ')
    return sha(raw)


def load_compare(refs):
    name='backtest.ndx_cash_fork_reference_window_research'
    require(name not in sys.modules,'Fresh CLI required; cached pure module present')
    module=importlib.import_module(name)
    require(Path(module.__file__).resolve()==Path(refs['pure']['path']).resolve(),'Pure module path differs')
    return module.compare_reference_window


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry/overwrite')
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded source differs')
    sources={str(SOURCE):LOADED_SHA}; docs={}; refs={}
    for role,(relative,pin) in PINS.items():
        require(type(pin) is str and len(pin)==64,'Pending source pin')
        path=ROOT/relative; raw=path.read_bytes(); require(sha(raw)==pin,'Input source differs: '+role)
        sources[str(path)]=pin; refs[role]={'path':str(path),'sha256':pin}
        if role not in ('pure','currency_html'): docs[role]=json.loads(raw)
    require({p.name for p in Path(refs['accounts']['path']).parent.iterdir()}=={'accounts.json','publication.json','started.json'},'Incomplete account publication')
    receipt=docs['publication']
    require(receipt['schema']=='OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1'
            and receipt['status']=='PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'
            and receipt['account_reference']==refs['accounts'] and receipt['source_hashes']==docs['accounts']['source_hashes'],'Account publication differs')
    for flag in ('point_in_time_verified','promotion_allowed','orders_executed'):
        require(receipt[flag] is False,'Publication authority changed')
    compare=load_compare(refs)
    def guard():
        for path,pin in sources.items(): require(sha(Path(path).read_bytes())==pin,'Source drift')
    guard(); OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'schema':'TOPUP_REFERENCE_COMPARISON_STARTED_V1','started_at_utc':datetime.now(timezone.utc).isoformat(),
            'source_hashes':sources,'planned_scenario_count':40,'retry_allowed':False})
        result=assemble(docs,refs,compare); result['source_hashes']=sources; guard()
        digest=write_new(OUTPUT/'comparison.json',result); guard()
        publication={'schema':'TOPUP_REFERENCE_COMPARISON_PUBLICATION_V1','status':'PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION',
            'comparison_reference':{'path':str(OUTPUT/'comparison.json'),'sha256':digest},'source_hashes':sources,**FLAGS}
        pubsha=write_new(OUTPUT/'publication.json',publication); guard()
        require(sha((OUTPUT/'comparison.json').read_bytes())==digest and sha((OUTPUT/'publication.json').read_bytes())==pubsha
                and {p.name for p in OUTPUT.iterdir()}=={'comparison.json','publication.json','started.json'},'Final publication differs')
        return {'path':str(OUTPUT/'comparison.json'),'sha256':digest,'publication_sha256':pubsha,'scenario_count':40}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
