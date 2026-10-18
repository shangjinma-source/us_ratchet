"""Source-bound independent budget inspection; never call budget producer or fitter."""
from copy import deepcopy
from datetime import datetime,timezone
import hashlib,json,os,sys,types,builtins,re
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/multidecision_scoring_budget_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_scoring_budget_independent_readback_20261003_v1'
PLAN_SHA='f99843ce3d28829f6c258e608a7e3c2ee8605e2432eaaa890299dc1f9edb6d04'
PUBLICATION_SHA='e9b9108018332ec7260cbcabc00b2fb751bbb393b7a50930be6d7f0e32a75f82'
PRODUCER=ROOT/'scripts/ndx_multidecision_scoring_budget_20261003.py'
PRODUCER_SHA='824503180c71f7f5afe124fec915f1a84bf1a22895d07326079bf000d3a1b180'
INSPECTOR=ROOT/'backtest/ndx_multidecision_scoring_budget_inspection_research.py'
INSPECTOR_SHA='9744a88e0608ca657e72042b896c3fa5ebc8891485900a2a5d7bc19faf983a7e'
CORE_SHA='7d737ab866c189582576b811c9a84093fd23bcfd1da6780d71a3c2335c2a4ee5'
BOUND={'policy': ('E:\\Git\\us_ratchet\\research_contracts\\multidecision_conditional_scoring_policy_20261003_v1.json', '6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'), 'history_index': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_20261003_v1\\index.json', 'ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d'), 'history_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_20261003_v1\\publication.json', 'e413e1cb7c10b543042fb7cbc34eafda48c93cfab3f25cd4e5b9f798249e88b9'), 'history_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_independent_readback_20261003_v2\\independent_readback.json', 'a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a'), 'history_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_scoring_history_independent_readback_v2_20261003.py', '6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703'), 'mdv_result': ('E:\\Git\\us_ratchet\\tmp\\multidecision_liquidity_saved_probe_v2_20261003_v1\\result.json', '0da351a6cd1b12c435a8cb7e770f778e601059ebec20554e7a5ea1669a05d5b0'), 'mdv_report': ('E:\\Git\\us_ratchet\\tmp\\multidecision_liquidity_saved_probe_v2_20261003_v1\\report.json', '511600995408be6ef030a7af7bc8b71ded435f3a5b10efc906bdd1cf57f596e3'), 'original8_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_20261003_v1\\inputs.json', '92d3fef00a69028caaeaecf3ded659d81b0c081e4537ba1da6fa24afb8f77d51'), 'original8_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_20261003_v1\\publication.json', '1df61b4b66705ce783e1066a3a924a36c9a7c5348caa516f9677668d4c278de4'), 'original8_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_independent_readback_20261003_v1\\independent_readback.json', '9e7ba8a661f57327552d2a89948e980dc3efb98256ffc37fde07e52f4483aa43'), 'original8_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_original_eight_scoring_inputs_independent_readback_20261003.py', '32ee8696d9b89a967de7cf17f9fcc8ac3844791e5e113869fc438ebedc019e83'), 'target_index': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\index.json', '0bfe5f4ef9f52dedaeb6606208395bce4940159dd934e7121754ceb30528f8a7'), 'target_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\target_inputs.json', '02f4212a07438c433bb1e041597f0e39595692e21564f1b60dce48742a0b1a14'), 'target_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\publication.json', 'ef4be2ac7ae209479eb991f78fe4c4b19d46ed8b609dfe817d01358e62bd992c'), 'target_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_inputs_independent_readback_20261003_v1\\independent_readback.json', '73a7c4347afcf5d60872f4dcdb88961ec520349878c6325df34c03ca2242b947'), 'target_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_target_inputs_independent_readback_20261003.py', 'e0e01bf5da653dade8cf5eabd9234f1ec3b018025fae163d86bcaf376d301d7d'), 'fitter_container': ('E:\\Git\\us_ratchet\\data\\cache\\research\\bulk_all_k_plan_20261003_v1\\plan.json', '77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'), 'mapping': ('research_contracts/multidecision_budget_source_mapping_20261003_v1.json', '50284ab838de58084fa73643ec9e65db0cb1ac96bc7c2762ba4f11effccd98c0')}
ROLLING_MANIFEST_PATH='research_contracts/multidecision_rolling_scoring_fitter_sources_20261003_v1.json'
ROLLING_MANIFEST_SHA='ae4d8de451697348822de12ac4ab5cb7bf5d04f44971bc46aa6030d772a6feea'
MATH={'ndx_issuer_combination_index_research': 'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b', 'ndx_membership_cardinality_plan_research': '4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c', 'ndx_cardinality_search': 'cc5c25fa656564d462d2905ff343d4196820d5343b8f3858f47d432beb509117', 'ndx_membership_scope_research': '19eae33257ed44620484bd992bce630b3838490bfd190866a51ac080f87330c6', 'ndx_dynamic_cutoff_refit_research': '33e0f20d1541bc42344f84dd3eae4bc6d61bfaf703ecef07c5e78a5dd547e0bd'}

FLAGS=dict.fromkeys(('score_computed','fit_performed','account_executed','execution_authorized','score_dispatch_authorized','point_in_time_verified','promotion_allowed','complete_ndx_universe_verified','formal_eligibility_verified','economic_results_used_for_sampling','parent_artifact_hash_used_for_sampling','mode_selected_using_results','old_audit_repeated','raw_reconstructed','full_transitive_source_closure_reverified','runtime_binary_closure_verified','outer_lane_prior_resolved'),False)

def require(ok,message):
    if not ok:raise ValueError(message)
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):require(encoded(a)==encoded(b),m)
def ref(p,h):return dict(path=str(Path(p).resolve()),sha256=h)
def merge(s,r):
    require(set(r)=={'path','sha256'} and type(r['sha256']) is str and re.fullmatch('[a-f0-9]{64}',r['sha256']) is not None,'Exact reference')
    require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def read(r,s):
    p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent source')
    b=p.read_bytes();require(sha(b)==r['sha256'],'Source byte drift');merge(s,r);return b

def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader drift')
    require({p.name for p in PARENT.iterdir()}=={'started.json','raw_plan.json','plan.json','publication.json'},'Exact parent namespace')
    for p,h in s.items():read(ref(p,h),{})

def save(p,d):
    b=encoded(d)
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved bytes');return ref(p,sha(b))

def inspect_parent_links(d,refs):
    for role,key,pubkey,auditschema in [('history','history_index','index_reference','MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2'),('original8','original8_inputs','inputs_reference','ORIGINAL_EIGHT_SCORING_INPUTS_INDEPENDENT_READBACK_V1'),('target','target_index','index_reference','MULTIDECISION_TARGET_INPUTS_INDEPENDENT_READBACK_V1')]:
        parent=d[key];pub=d[role+'_publication'];audit=d[role+'_audit']
        require(audit['schema']==auditschema and audit['status']=='PASS','Saved audit state')
        require(audit['reader_sha256']==refs[role+'_reader']['sha256'],'Saved reader identity')
        exact(pub[pubkey],refs[key],'Publication reference');exact(audit[pubkey],refs[key],'Audit reference');exact(audit['publication_reference'],refs[role+'_publication'],'Audit publication')
        exact(pub['source_hashes'],parent['source_hashes'],'Parent preserved claims')
        for obj in (parent,pub,audit):require(obj['fit_performed'] is False and obj['point_in_time_verified'] is False,'Parent authority')
    exact(d['target_index']['target_inputs_reference'],refs['target_inputs'],'Target inputs link')
    exact(d['target_publication']['target_inputs_reference'],refs['target_inputs'],'Target published payload')
    require(d['target_audit']['source_hashes'][refs['target_inputs']['path']]==refs['target_inputs']['sha256'],'Target payload audited')
    mr=d['mdv_report'];require(mr['status']=='PASS_DRAFT_DIAGNOSTIC_ONLY' and mr['schema']=='SAVED_MULTIDECISION_LIQUIDITY_PROBE_V2','MDV diagnostic scope')
    exact(mr['result_reference'],refs['mdv_result'],'MDV source');require(type(mr['independently_checked_security_periods']) is int and mr['independently_checked_security_periods']==462,'MDV denominator')
    exact(d['mapping']['source_references'],{k:refs[k] for k in d['mapping']['source_references']},'Static mapping')
    baseline=d['fitter_container']['plan']['fitter_source_hashes'];exact(baseline,d['mapping']['fitter_source_hashes'],'Old baseline25')
    f=d['rolling_fitter_manifest'];require(f['schema']=='MULTIDECISION_ROLLING_SCORING_NUMERICAL_SOURCES_V1' and f['status']=='FROZEN_BEFORE_ACTUAL_PLAN_OR_SCORE_NOT_DISPATCH_AUTHORITY','New fitter identity')
    exact(f['policy_reference'],refs['policy'],'Fitter registered policy');require(len(f['source_hashes'])==len(baseline)==25,'Two distinct25 source domains')
    for name in ('ndx_multidecision_rolling_fit_research.py','ndx_multidecision_window_scoring_research.py'):require(str(ROOT/'backtest'/name) in f['source_hashes'],'Actual new adapter/reducer identity')
    for name in ('fit_performed','score_computed','execution_authorized','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'):require(f[name] is False,'Fitter not execution authority')
    exact(f['required_worker_environment'],dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),'Fee order worker environment')


def inspect_source_projection(plan,d,refs,channels):
    """Authenticate projection against saved metadata; never recompute prices or qualification."""
    inspect_parent_links(d,refs)
    h=d['history_index'];control=d['original8_inputs']['scoring_inputs'];target=d['target_inputs'];mdv=d['mdv_result']
    exact(plan['registration_preserved'],d['policy'],'Original registration');exact(plan['registration_reference_preserved'],refs['policy'],'Policy reference')
    exact(plan['full_universe_preserved'],[r['coordinate'] for r in h['rows']],'Original full77 order')
    require(len(h['rows'])==len(d['history_audit']['rows'])==77 and len(h['original_provenance_and_missing'])==101 and len(h['preserved_evidence_sidecars'])==7,'Full77/101/7')
    exact(mdv['original_provenance_and_missing'],h['original_provenance_and_missing'],'101 MDV provenance');exact(mdv['preserved_evidence_sidecars'],h['preserved_evidence_sidecars'],'Seven MDV sidecars')
    require(len(plan['decision_inputs_preserved'])==6,'Six source projections')
    for j,decision in enumerate(plan['decision_inputs_preserved']):
        dates=control['decisions'][j]['price_dates'];exact(decision['scoring_price_dates'],dates,'Control505 calendar')
        require(control['decisions'][j]['cutoff']==decision['cutoff']==mdv['periods'][j]['decision_date'],'Same cutoff parents')
        exact(decision['scoring_data_reference'],dict(refs['history_index'],json_pointer='/rows'),'History source role')
        exact(decision['incumbent_fee_reference'],dict(refs['original8_inputs'],json_pointer='/scoring_inputs/normalized_scoring_weights'),'Original8 fee role')
        exact(decision['fitter_source_reference'],refs['rolling_fitter_manifest'],'New fitter exact source')
        for m,mode in enumerate(decision['mode_sources']):
            original=target['modes'][m]['decisions'][j]
            exact(original['required_price_dates'],dates,'Target505 calendar')
            require(len(original['windows'])==13 and type(original['window_count']) is int and original['window_count']==13,'Target all13')
            complete=all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for w in original['windows'])
            require(original['complete_thirteen_window_numeric_supply'] is complete,'Original mode completion')
            exact(mode,dict(mode=target['modes'][m]['mode'],reference=dict(refs['target_inputs'],json_pointer=f'/modes/{m}/decisions/{j}'),complete_thirteen_windows=complete),'No mode substitution')
    count=0
    for i,channel in enumerate(channels):
        require(i<77,'Extra channel');count+=1;row=h['rows'][i];audit=d['history_audit']['rows'][i]
        exact(audit['coordinate'],row['coordinate'],'Audited coordinate');exact(audit['channel_reference'],row['channel_reference'],'Audited channel');exact(audit['decision_coverage'],row['decision_coverage'],'Audited six coverage')
        require(type(audit['index']) is int and type(row['index']) is int and audit['index']==row['index']==i,'Source row order')
        require(channel['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and channel['ticker']==row['coordinate']['ticker'] and audit['inspection']['status']=='PASS' and audit['inspection']['ticker']==channel['ticker'],'Channel coverage')
        require(channel['content_sha256']==sha(encoded({k:v for k,v in channel.items() if k!='content_sha256'})),'Channel digest')
        require(type(audit['inspection']['window_count']) is int and audit['inspection']['window_count']==78 and len(channel['decisions'])==6,'All78 windows audited')
        for j,decision in enumerate(plan['decision_inputs_preserved']):
            original=channel['decisions'][j];coverage=row['decision_coverage'][j];m=mdv['periods'][j]['rows'][i]
            exact(m['coordinate'],row['coordinate'],'Full liquidity coordinate');exact(m['required_dates'],decision['scoring_price_dates'][-63:],'Exact63 days')
            exact(original['required_price_dates'],decision['scoring_price_dates'],'Channel505 days')
            require(original['cutoff']==coverage['cutoff']==decision['cutoff'] and len(original['windows'])==13,'Same cutoff13windows')
            good=all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' and w['blocked_price_slots']==[] for w in original['windows'])
            require(original['complete_thirteen_window_numeric_supply'] is good and coverage['complete_thirteen_window_numeric_supply'] is good,'Preserved completeness')
            reasons=deepcopy(m['reasons'])
            if not good:reasons.append('SAVED_FULL13_HISTORY_CONTAINS_BLOCKED_WINDOWS')
            q=dict(security_id=row['coordinate']['security_id'],cutoff=decision['cutoff'],history_13_complete=good,mdv_available=m['status']=='CONDITIONAL_MDV_COMPUTABLE',liquidity_passed=m['conditional_numerical_threshold_passed'],conditional_member_scope_passed=True,history_reference=dict(row['channel_reference'],json_pointer=f'/decisions/{j}'),mdv_reference=dict(refs['mdv_result'],json_pointer=f'/periods/{j}/rows/{i}'),mdv_evidence=m,reasons=reasons)
            exact(decision['qualifications'][i],q,'Exact source-bound qualification')
    require(count==77,'No omitted channel')


def inspect_documents(document,publication,raw,started,refs,sources,parents):
    require(document['schema']=='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1' and publication['schema']=='MULTIDECISION_SCORING_BUDGET_PUBLICATION_V1','Output schemas')
    require(document['status']==publication['status']=='REGISTERED_BEFORE_CANDIDATE_SCORING_NOT_DISPATCH_AUTHORITY','Registration only')
    require(raw['schema']=='MULTIDECISION_SCORING_BUDGET_RAW_RETURN_V1' and raw['status']=='RETURNED_PENDING_VALIDATION_NOT_REGISTERED','Raw-first output')
    require(started['schema']=='MULTIDECISION_SCORING_BUDGET_STARTED_V1' and started['retry_allowed'] is False,'Attempt state')
    exact(publication['plan_reference'],refs['plan'],'Published plan');exact(publication['raw_plan_reference'],refs['raw'],'Published raw');exact(document['raw_plan_reference'],refs['raw'],'Raw-first binding');exact(raw['plan'],document['plan'],'Unmodified returned plan')
    parentrefs={k:v for k,v in refs.items() if k not in ('plan','raw','publication','started')}
    for obj in (document,publication,raw,started):
        exact(obj['source_hashes'],sources,'Independent full producer source closure');exact(obj['input_references'],parentrefs,'Full fixed input refs')
        for key in FLAGS:require(obj[key] is False,'No authority '+key)
    require(len(document['plan']['rows'])==6 and all(row['sampling']['complete'] is True for row in document['plan']['rows']),'Published complete selection only')
    exact(started['runtime'],document['runtime'],'Runtime declaration');exact(raw['runtime'],document['runtime'],'Raw runtime')
    for k,n in (('security_count',77),('issuer_count',76),('observed_security_count',101),('preserved_sidecar_count',7)):require(type(document[k]) is int and document[k]==n,'Full denominator')
    for key in ('original_provenance_and_missing','preserved_evidence_sidecars'):exact(document[key],parents['history_index'][key],'Original full evidence')
    exact(document['original_parent_source_hash_claims'],{k:parents[k]['source_hashes'] for k in ('history_index','original8_inputs','target_index')},'Unchanged source declarations')
    exact(document['mdv_diagnostic_report_preserved'],parents['mdv_report'],'Diagnostic original');exact(document['rolling_fitter_manifest_preserved'],parents['rolling_fitter_manifest'],'New fitter original');exact(document['original25_baseline_source_hashes_preserved'],parents['fitter_container']['plan']['fitter_source_hashes'],'Old baseline separate')
    require(document['conditional_membership_scope_only'] is True and document['numeric_source_readbacks_reused'] is True,'Conditional evidence role')


def private_inspector(sources):
    path=ROOT/'backtest/ndx_issuer_combination_index_research.py';blob=read(ref(path,MATH[path.stem]),sources)
    name='_private_budget_inspection_index';module=types.ModuleType(name);module.__file__=str(path);prior=sys.modules.get(name);sys.modules[name]=module
    try:exec(compile(blob,str(path),'exec'),module.__dict__)
    finally:
        if prior is None:sys.modules.pop(name,None)
        else:sys.modules[name]=prior
    original=builtins.__import__
    def importer(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest.ndx_issuer_combination_index_research':return module
        require(not name.startswith('backtest'),'Unexpected project dependency');return original(name,globals,locals,fromlist,level)
    m=types.ModuleType('_private_budget_inspector');m.__file__=str(INSPECTOR);m.__dict__['__builtins__']=dict(vars(builtins),__import__=importer)
    exec(compile(read(ref(INSPECTOR,INSPECTOR_SHA),sources),str(INSPECTOR),'exec'),m.__dict__);return m


def readback(*,execute=False):
    require(type(execute) is bool,'Execute boolean')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    require(type(PLAN_SHA) is str and len(PLAN_SHA)==64 and type(PUBLICATION_SHA) is str and len(PUBLICATION_SHA)==64,'Future output anchors pending')
    require(not OUTPUT.exists(),'No retry immutable namespace');sources={str(SOURCE):LOADED_SHA};producer_sources={};docs={};refs={}
    guard({})
    for role,(p,h) in BOUND.items():
        r=ref(ROOT/p,h);refs[role]=r;blob=read(r,producer_sources)
        if not role.endswith('_reader'):docs[role]=json.loads(blob)
    refs['rolling_fitter_manifest']=ref(ROOT/ROLLING_MANIFEST_PATH,ROLLING_MANIFEST_SHA);docs['rolling_fitter_manifest']=json.loads(read(refs['rolling_fitter_manifest'],producer_sources))
    for r in (ref(PRODUCER,PRODUCER_SHA),ref(ROOT/'backtest/ndx_multidecision_scoring_budget_research.py',CORE_SHA)):read(r,producer_sources)
    for name,h in MATH.items():read(ref(ROOT/'backtest'/f'{name}.py',h),producer_sources)
    for mapping in (docs['fitter_container']['plan']['fitter_source_hashes'],docs['rolling_fitter_manifest']['source_hashes']):
        for p,h in mapping.items():read(ref(p,h),producer_sources)
    refs['plan']=ref(PARENT/'plan.json',PLAN_SHA);refs['publication']=ref(PARENT/'publication.json',PUBLICATION_SHA)
    document=json.loads(read(refs['plan'],sources));publication=json.loads(read(refs['publication'],sources))
    refs['raw']=document['raw_plan_reference'];require(Path(refs['raw']['path'])==PARENT/'raw_plan.json','Fixed raw path');raw=json.loads(read(refs['raw'],sources))
    b=(PARENT/'started.json').read_bytes();refs['started']=ref(PARENT/'started.json',sha(b));merge(sources,refs['started']);started=json.loads(b)
    def channels():
        for i,row in enumerate(docs['history_index']['rows']):
            r=row['channel_reference'];require(Path(r['path'])==Path(refs['history_index']['path']).parent/f'channel_{i:03d}.json','Fixed channel path')
            yield json.loads(read(r,producer_sources))
    inspect_source_projection(document['plan'],docs,refs,channels())
    inspect_documents(document,publication,raw,started,refs,producer_sources,docs)
    for p,h in producer_sources.items():merge(sources,ref(p,h))
    oracle=private_inspector(sources);guard(sources)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        ownstart=save(OUTPUT/'started.json',dict(schema='MULTIDECISION_SCORING_BUDGET_READBACK_STARTED_V1',plan_reference=refs['plan'],publication_reference=refs['publication'],started_at_utc=datetime.now(timezone.utc).isoformat(),retry_allowed=False,**FLAGS))
        plan=document['plan'];detail=oracle.inspect_scoring_budget(registration=plan['registration_preserved'],registration_reference=plan['registration_reference_preserved'],universe=plan['full_universe_preserved'],decisions=plan['decision_inputs_preserved'],saved_plan=plan)
        report=save(OUTPUT/'independent_readback.json',dict(schema='MULTIDECISION_SCORING_BUDGET_INDEPENDENT_READBACK_V1',status='PASS',plan_reference=refs['plan'],publication_reference=refs['publication'],raw_plan_reference=refs['raw'],started_reference=refs['started'],started_externally_anchored=False,reader_sha256=LOADED_SHA,source_hashes=sources,arithmetic=detail,producer_called=False,plan_function_called=False,**FLAGS))
        guard(sources)
        for r in (ownstart,report):require(sha(Path(r['path']).read_bytes())==r['sha256'],'Readback output drift')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact readback namespace')
        return report
    except Exception as e:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS));raise

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
