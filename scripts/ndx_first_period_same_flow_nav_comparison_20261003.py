"""Create-only first-eight comparison; consumes sealed accounts, never executes them."""
import argparse
import builtins
import hashlib
import json
import os
import sys
import types
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/first_period_same_flow_nav_comparison_20261003_v1'
PINS={'candidate_accounts': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/accounts.json', '4112089be89d196405da8df2e1a6266eb7ad95baad992b0759e28c7c8800c792'), 'candidate_publication': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/publication.json', 'd841df9120aead6a9cc8c0e6d003c5e4d48beed380d31fbe0d69daa032145ec9'), 'candidate_review_report': ('DYNAMIC_FIRST_PERIOD_CASH_BUY_HOLD_INDEPENDENT_READBACK_20261002.md', '95cb53e82b7f7c120659ffcebced7bd9a74e2899b2c03fd8a94c554e53005f3f'), 'candidate_reader': ('scripts/ndx_first_period_cash_buy_hold_independent_review_20261002.py', '023cb1ebfd5d3c0e15606c13f2eb279e5e27fc67734e93ad65fd71648412e70b'), 'incumbent_accounts': ('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v2/accounts.json', '7a9514dbe38b30196302453d833d31552ab3da62bd3fabc142e7c75e6a606d8a'), 'incumbent_publication': ('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v2/publication.json', '9ce38205f97506b300a6fada34652308a87cd3f882a350d8336ad646b3412204'), 'incumbent_audit': ('data/cache/research/first_period_incumbent_cash_flow_independent_readback_20261003_v2/independent_readback.json', '10b4e93693163fb7d49fd115d71754588ad592edce4b927496c38214b8ff2872'), 'incumbent_reader': ('scripts/ndx_first_period_incumbent_cash_flow_independent_readback_20261003.py', '2a3b07741eef36b822c2c357935fe992fc708e01bda94fe2bfcd39387215d745'), 'benchmark': ('data/cache/research/return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'), 'currency_manifest': ('data/cache/research/fund_012922_currency_source_20261002_v1/manifest.json', 'ff4f51f7463f0c805f6ae0542aea46883ba2476b416364d293d93d7026a5b284'), 'currency_html': ('data/cache/research/fund_012922_currency_source_20261002_v1/issuer_listing.html', '89f8a7a02aa843193bbfab8acd3a273ff7053d69fcc4256f242eb453dc43d292'), 'core': ('backtest/ndx_first_period_same_flow_comparison_research.py', 'b4c95cf965f449747ef6a9845aa59cde0386ac678c8a3d23d3d0b88f4a0423c6'), 'metrics': ('backtest/ndx_cash_fork_reference_window_research.py', '0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163')}
FLAGS=dict.fromkeys(('orders_executed','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','economic_winner_selected','account_simulation_called','full_transitive_source_closure_reverified','candidate_decision_time_executability_verified'),False)
JSON_ROLES={'candidate_accounts','candidate_publication','incumbent_accounts','incumbent_publication','incumbent_audit','benchmark','currency_manifest'}

def require(ok,message):
    if not ok:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()
def exact(a,b,message):require(json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False),message)
def guard(sources):
    require(sources.get(str(SOURCE))==LOADED_SHA,'Loaded wrapper binding')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Source drift '+path)

def validate_documents(d,r):
    for role,schema,status in [('candidate','FIRST_PERIOD_CASH_BUY_HOLD_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS'),('incumbent','FIRST_PERIOD_INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V2','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS')]:
        a=d[role+'_accounts'];p=d[role+'_publication']
        require(p['schema']==schema and p['status']==status,'Publication schema/status')
        exact(p['account_reference'],r[role+'_accounts'],'Account publication link')
        exact(p['source_hashes'],a['source_hashes'],'Publication sources')
        for flag in ('orders_executed','point_in_time_verified','promotion_allowed'):require(a[flag] is False and p[flag] is False,'Parent authority')
    a=d['incumbent_audit']
    require(a['schema']=='FIRST_PERIOD_INCUMBENT_CASH_FLOW_INDEPENDENT_READBACK_V1' and a['status']=='PASS','Saved incumbent audit')
    exact(a['accounts_reference'],r['incumbent_accounts'],'Audit account link');exact(a['publication_reference'],r['incumbent_publication'],'Audit publication link')
    require(a['reader_sha256']==r['incumbent_reader']['sha256'] and a['source_hashes'].get(r['incumbent_reader']['path'])==r['incumbent_reader']['sha256'],'Audit reader link')
    for role in ('incumbent_accounts','incumbent_publication'):require(a['source_hashes'].get(r[role]['path'])==r[role]['sha256'],'Audit source link')
    for k,n in {'paths':2,'daily':212,'decisions':12,'mappings':8}.items():require(type(a['counts'][k]) is int and a['counts'][k]==n,'Saved audit scope')
    for flag in ('formal_admission','point_in_time_verified','promotion_allowed','production_functions_called','old_experiments_reexecuted'):require(a[flag] is False,'Saved audit limitations')
    text=d['candidate_review_report'].decode('utf-8');code=d['candidate_reader'].decode('utf-8')
    for role in ('candidate_accounts','candidate_publication'):require(r[role]['sha256'] in text and r[role]['sha256'] in code,'Saved candidate review source link')
    require(r['candidate_reader']['sha256'] in text,'Saved candidate review reader')
    c=d['currency_manifest'];require(c['schema']=='FUND_CURRENCY_ISSUER_LISTING_CAPTURE_V1' and c['fund_code']=='012922' and c['currency']=='CNY','Conditional currency label')
    exact(c['source_reference'],r['currency_html'],'Currency html reference')
    for k in ('nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','fx_rates_supplied','point_in_time_verified','promotion_allowed','subscription_terms_verified'):require(c[k] is False,'Currency limitation')

def private_compare(blobs,refs):
    names=('backtest.ndx_first_period_same_flow_comparison_research','backtest.ndx_cash_fork_reference_window_research')
    require(all(n not in sys.modules for n in names),'Cached dependency rejected; fresh process required')
    for role in ('core','metrics'):require(sha(blobs[role])==refs[role]['sha256'],'Exact consumed dependency bytes')
    metric=types.ModuleType('_first_cash_private_metrics');metric.__file__=refs['metrics']['path']
    exec(compile(blobs['metrics'],metric.__file__,'exec'),metric.__dict__)
    original_import=builtins.__import__
    def private_import(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest':
            require(tuple(fromlist)==('ndx_cash_fork_reference_window_research',) and level==0,'Only declared local dependency')
            return types.SimpleNamespace(ndx_cash_fork_reference_window_research=metric)
        return original_import(name,globals,locals,fromlist,level)
    module=types.ModuleType('_first_cash_private_compare');module.__file__=refs['core']['path']
    module.__dict__['__builtins__']={**vars(builtins),'__import__':private_import}
    exec(compile(blobs['core'],module.__file__,'exec'),module.__dict__)
    require(module.window is metric and module.REFERENCE_METRICS_SOURCE_SHA256==refs['metrics']['sha256'],'Private metric dependency exact')
    return module.compare_first_period_paths

def write_new(path,value):
    raw=(json.dumps(value,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    require(path.read_bytes()==raw,'Saved bytes readback');return dict(path=str(path),sha256=sha(raw))

def run(*,execute=False):
    require(execute is True,'Explicit execute')
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    require(all(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef') for _,h in PINS.values()),'Pending pins')
    sources={str(SOURCE):LOADED_SHA};refs={};docs={};blobs={};guard(sources)
    for role,(rel,h) in PINS.items():
        path=ROOT/rel;blob=path.read_bytes();require(sha(blob)==h,'Consumed source '+role)
        require(str(path) not in sources or sources[str(path)]==h,'Source conflict')
        sources[str(path)]=h;refs[role]=dict(path=str(path),sha256=h);blobs[role]=blob
        docs[role]=json.loads(blob) if role in JSON_ROLES else blob
    for role in ('candidate','incumbent'):
        directory=Path(refs[role+'_accounts']['path']).parent
        require(Path(refs[role+'_publication']['path']).parent==directory and {p.name for p in directory.iterdir()}=={'started.json','accounts.json','publication.json'},'Successful account namespace')
    validate_documents(docs,refs);compare=private_compare(blobs,refs);guard(sources)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',dict(schema='FIRST_PERIOD_SAME_FLOW_NAV_COMPARISON_STARTED_V1',started_at_utc=datetime.now(timezone.utc).isoformat(),source_hashes=sources,input_references=refs,retry_allowed=False,**FLAGS))
        result=compare(candidate_accounts=docs['candidate_accounts'],incumbent_accounts=docs['incumbent_accounts'],benchmark_document=docs['benchmark'],candidate_reference=refs['candidate_accounts'],incumbent_reference=refs['incumbent_accounts'],benchmark_reference=refs['benchmark'])
        require(result['schema']=='FIRST_PERIOD_EIGHT_SAME_FLOW_NAV_REFERENCE_COMPARISON_V1' and type(result['scenario_count']) is int and result['scenario_count']==8 and len(result['rows'])==8,'Complete first-eight result')
        for flag in FLAGS:require(result[flag] is False,'Output authority')
        result.update(source_hashes=sources,input_references=refs,candidate_audit_evidence_type='SAVED_REVIEW_REPORT_AND_READER_NOT_NEW_MACHINE_ATTESTATION',benchmark_numeric_audit_reperformed=False,currency_manifest_preserved=docs['currency_manifest'],parent_source_hashes_preserved_not_reaudited={role:docs[role].get('source_hashes',{}) for role in ('candidate_accounts','incumbent_accounts','benchmark')})
        guard(sources);out=write_new(OUTPUT/'comparison.json',result);guard(sources)
        pub=write_new(OUTPUT/'publication.json',dict(schema='FIRST_PERIOD_SAME_FLOW_NAV_COMPARISON_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON',comparison_reference=out,source_hashes=sources,**FLAGS))
        guard(sources)
        for ref in (out,pub):require(sha(Path(ref['path']).read_bytes())==ref['sha256'],'Final output drift')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','comparison.json','publication.json'},'Exact success namespace')
        return dict(comparison_reference=out,publication_reference=pub)
    except Exception as error:
        write_new(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(error),retry_allowed=False));raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args();print(json.dumps(run(execute=args.execute)))
