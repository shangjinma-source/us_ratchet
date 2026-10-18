"""Source-bound six-cutoff conditional budgets; no score, fit or dispatch."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import types

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1]
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_scoring_budget_20261003_v1'
CORE=ROOT/'backtest/ndx_multidecision_scoring_budget_research.py'
CORE_SHA='7d737ab866c189582576b811c9a84093fd23bcfd1da6780d71a3c2335c2a4ee5'
BOUND={'policy': ('E:\\Git\\us_ratchet\\research_contracts\\multidecision_conditional_scoring_policy_20261003_v1.json', '6cc7f67093ba996b7cad0c6e24acbc3691a457930103872b8105b6a44c38424f'), 'history_index': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_20261003_v1\\index.json', 'ce4fd8a1a8f7f0c9c1ddd20cd4136c1c078e4aae81b37e61c9a1b0aae981ff2d'), 'history_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_20261003_v1\\publication.json', 'e413e1cb7c10b543042fb7cbc34eafda48c93cfab3f25cd4e5b9f798249e88b9'), 'history_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_scoring_history_independent_readback_20261003_v2\\independent_readback.json', 'a338dbbdfa4bc7ffdc6e83ee93bc6e55802201dd7f18049d398ae394029a5b1a'), 'history_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_scoring_history_independent_readback_v2_20261003.py', '6ae5ca2c757badd0ebfa2fa35bf3550584b4a989155e44e7d7fd120ca61f6703'), 'mdv_result': ('E:\\Git\\us_ratchet\\tmp\\multidecision_liquidity_saved_probe_v2_20261003_v1\\result.json', '0da351a6cd1b12c435a8cb7e770f778e601059ebec20554e7a5ea1669a05d5b0'), 'mdv_report': ('E:\\Git\\us_ratchet\\tmp\\multidecision_liquidity_saved_probe_v2_20261003_v1\\report.json', '511600995408be6ef030a7af7bc8b71ded435f3a5b10efc906bdd1cf57f596e3'), 'original8_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_20261003_v1\\inputs.json', '92d3fef00a69028caaeaecf3ded659d81b0c081e4537ba1da6fa24afb8f77d51'), 'original8_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_20261003_v1\\publication.json', '1df61b4b66705ce783e1066a3a924a36c9a7c5348caa516f9677668d4c278de4'), 'original8_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\original_eight_scoring_inputs_independent_readback_20261003_v1\\independent_readback.json', '9e7ba8a661f57327552d2a89948e980dc3efb98256ffc37fde07e52f4483aa43'), 'original8_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_original_eight_scoring_inputs_independent_readback_20261003.py', '32ee8696d9b89a967de7cf17f9fcc8ac3844791e5e113869fc438ebedc019e83'), 'target_index': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\index.json', '0bfe5f4ef9f52dedaeb6606208395bce4940159dd934e7121754ceb30528f8a7'), 'target_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\target_inputs.json', '02f4212a07438c433bb1e041597f0e39595692e21564f1b60dce48742a0b1a14'), 'target_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_scoring_inputs_20261003_v1\\publication.json', 'ef4be2ac7ae209479eb991f78fe4c4b19d46ed8b609dfe817d01358e62bd992c'), 'target_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_target_inputs_independent_readback_20261003_v1\\independent_readback.json', '73a7c4347afcf5d60872f4dcdb88961ec520349878c6325df34c03ca2242b947'), 'target_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_target_inputs_independent_readback_20261003.py', 'e0e01bf5da653dade8cf5eabd9234f1ec3b018025fae163d86bcaf376d301d7d'), 'fitter_container': ('E:\\Git\\us_ratchet\\data\\cache\\research\\bulk_all_k_plan_20261003_v1\\plan.json', '77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'), 'mapping': ('research_contracts/multidecision_budget_source_mapping_20261003_v1.json', '50284ab838de58084fa73643ec9e65db0cb1ac96bc7c2762ba4f11effccd98c0')}
ROLLING_MANIFEST_PATH='research_contracts/multidecision_rolling_scoring_fitter_sources_20261003_v1.json'
ROLLING_MANIFEST_SHA='ae4d8de451697348822de12ac4ab5cb7bf5d04f44971bc46aa6030d772a6feea'
ROLLING_MANIFEST_SCHEMA='MULTIDECISION_ROLLING_SCORING_NUMERICAL_SOURCES_V1'
FLAGS=dict.fromkeys(('score_computed','fit_performed','account_executed','execution_authorized','score_dispatch_authorized','point_in_time_verified','promotion_allowed','complete_ndx_universe_verified','formal_eligibility_verified','economic_results_used_for_sampling','parent_artifact_hash_used_for_sampling','mode_selected_using_results','old_audit_repeated','raw_reconstructed','full_transitive_source_closure_reverified','runtime_binary_closure_verified','outer_lane_prior_resolved'),False)
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX']


def require(ok,message):
    if not ok:raise ValueError(message)
def sha(blob):return hashlib.sha256(blob).hexdigest()
def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,message):require(encoded(a)==encoded(b),message)
def loads(blob):
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    def reject(value):raise ValueError('Nonfinite JSON '+value)
    return json.loads(blob,object_pairs_hook=pairs,parse_constant=reject)
def valid_sha(value):return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None
def reference(path,h):return dict(path=str(Path(path).resolve()),sha256=h)
def merge(sources,path,h):
    path=str(Path(path).resolve());require(valid_sha(h),'Canonical source SHA')
    require(path not in sources or sources[path]==h,'Conflicting source hash');sources[path]=h
def read(path,h,sources):
    path=Path(path).resolve();require(not (path.parent/'failure.json').exists(),'Parent failure marker')
    blob=path.read_bytes();require(sha(blob)==h,'Source bytes differ: '+str(path));merge(sources,path,h);return blob
def guard(sources):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded wrapper changed')
    for path,h in sources.items():read(path,h,{})
def runtime():return dict(python=sys.version,executable=str(Path(sys.executable).resolve()),implementation=platform.python_implementation())
def space(size):
    p=OUTPUT.parent
    while not p.exists():p=p.parent
    require(shutil.disk_usage(p).free>=5*1024**3+size,'5GiB reserve plus encoded bytes')
def save(path,value,failure=False):
    blob=encoded(value)
    if not failure:space(len(blob))
    with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==blob,'Saved output bytes');return reference(path,sha(blob))


SIDECARS=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection','bulk_incremental_evidence_and_projection')
MATH={
 'ndx_issuer_combination_index_research':'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',
 'ndx_membership_cardinality_plan_research':'4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c',
 'ndx_cardinality_search':'cc5c25fa656564d462d2905ff343d4196820d5343b8f3858f47d432beb509117',
 'ndx_membership_scope_research':'19eae33257ed44620484bd992bce630b3838490bfd190866a51ac080f87330c6',
 'ndx_dynamic_cutoff_refit_research':'33e0f20d1541bc42344f84dd3eae4bc6d61bfaf703ecef07c5e78a5dd547e0bd'}


def false_fields(value,keys):
    for key in keys:require(value[key] is False,'Original authority '+key)


def validate_parents(docs,refs):
    h=docs['history_index'];a=docs['history_audit'];mdv=docs['mdv_result'];mr=docs['mdv_report'];o=docs['original8_inputs'];t=docs['target_inputs']
    require(h['schema']=='MULTIDECISION_SCORING_HISTORY_AGGREGATE_V1','History schema')
    require(o['schema']=='ORIGINAL_EIGHT_SCORING_INPUTS_DOCUMENT_V1','Control schema')
    require(docs['target_index']['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_DOCUMENT_V1' and t['schema']=='MULTIDECISION_TARGET_SCORING_INPUTS_V1','Target schemas')
    for role,parent,pubkey,auditkey,pubschema,auditschema,status in (
      ('history',h,'index_reference','index_reference','MULTIDECISION_SCORING_HISTORY_PUBLICATION_V1','MULTIDECISION_SCORING_HISTORY_INDEPENDENT_READBACK_V2','PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK'),
      ('original8',o,'inputs_reference','inputs_reference','ORIGINAL_EIGHT_SCORING_INPUTS_PUBLICATION_V1','ORIGINAL_EIGHT_SCORING_INPUTS_INDEPENDENT_READBACK_V1','PUBLISHED_FIXED_DAILY_WEIGHT_RETURNS_PENDING_INDEPENDENT_READBACK'),
      ('target',docs['target_index'],'index_reference','index_reference','MULTIDECISION_TARGET_SCORING_INPUTS_PUBLICATION_V1','MULTIDECISION_TARGET_INPUTS_INDEPENDENT_READBACK_V1','PUBLISHED_CONDITIONAL_INPUTS_PENDING_INDEPENDENT_READBACK')):
        key=role+('_inputs' if role=='original8' else '_index');pub=docs[role+'_publication'];audit=docs[role+'_audit']
        require(pub['schema']==pubschema and pub['status']==parent['status']==status,'Parent publication state')
        require(audit['schema']==auditschema and audit['status']=='PASS' and audit['reader_sha256']==refs[role+'_reader']['sha256'],'Saved independent readback')
        exact(pub[pubkey],refs[key],'Publication object');exact(audit[auditkey],refs[key],'Audited object');exact(audit['publication_reference'],refs[role+'_publication'],'Audited publication')
        exact(parent['source_hashes'],pub['source_hashes'],'Preserved parent source claims')
        for value in (parent,pub,audit):false_fields(value,('fit_performed','point_in_time_verified'))
    exact(docs['target_index']['target_inputs_reference'],refs['target_inputs'],'Actual target payload reference');exact(docs['target_publication']['target_inputs_reference'],refs['target_inputs'],'Published target payload')
    require(docs['target_audit']['source_hashes'][refs['target_inputs']['path']]==refs['target_inputs']['sha256'],'Audit target payload bytes')
    for k,n in (('security_count',77),('issuer_count',76),('observed_security_count',101),('preserved_sidecar_count',7)):
        require(type(h[k]) is int and h[k]==n and type(a[k]) is int and a[k]==n,'Full inventory denominator '+k)
    require(len(h['rows'])==len(a['rows'])==77 and len(h['original_provenance_and_missing'])==101 and set(h['preserved_evidence_sidecars'])==set(SIDECARS),'Full77/101/7 inventory')
    require(mdv['schema']=='CONDITIONAL_MULTIDECISION_LIQUIDITY_INPUTS_V2' and mdv['status']=='PREPARED_CONDITIONAL_LIQUIDITY_NOT_ELIGIBILITY','Saved conditional MDV')
    require(mr['schema']=='SAVED_MULTIDECISION_LIQUIDITY_PROBE_V2' and mr['status']=='PASS_DRAFT_DIAGNOSTIC_ONLY','MDV diagnostic is not formal audit')
    exact(mr['result_reference'],refs['mdv_result'],'Saved MDV result link')
    require(type(mr['prepare_calls']) is int and mr['prepare_calls']==1 and type(mr['independently_checked_security_periods']) is int and mr['independently_checked_security_periods']==462,'Complete conditional MDV diagnostic')
    false_fields(mr,('decision_contract_registered','fit_performed','point_in_time_verified','selection_performed'));false_fields(mdv,('historical_liquidity_qualified','historical_pool_eligibility_verified','point_in_time_verified','fit_performed','execution_authorized'))
    exact(mdv['original_provenance_and_missing'],h['original_provenance_and_missing'],'Original101 preserved');exact(mdv['preserved_evidence_sidecars'],h['preserved_evidence_sidecars'],'Seven sidecars preserved')
    control=o['scoring_inputs'];ca=docs['original8_audit']['arithmetic']
    require(control['schema']=='ORIGINAL_EIGHT_FIXED_DAILY_WEIGHT_SCORING_INPUTS_V1' and ca['status']=='PASS' and type(ca['return_slot_count']) is int and ca['return_slot_count']==3024 and type(ca['window_count']) is int and ca['window_count']==78,'Complete saved original8 reference')
    false_fields(control,('entry_fee_applied','fit_performed','score_computed','point_in_time_verified'))
    require(len(mdv['periods'])==len(control['decisions'])==6 and [m['mode'] for m in t['modes']]==MODES,'Complete six periods and two modes')
    baseline=docs['fitter_container']['plan']['fitter_source_hashes'];require(len(baseline)==25,'Full original25 baseline closure');exact(baseline,docs['mapping']['fitter_source_hashes'],'Baseline immutable mapping')
    exact(docs['mapping']['source_references'],{k:refs[k] for k in docs['mapping']['source_references']},'Fixed source field map')
    return h,mdv,control,t,baseline


def project_inputs(docs,refs,channels):
    h,mdv,control,target,baseline=validate_parents(docs,refs)
    universe=[deepcopy(r['coordinate']) for r in h['rows']]
    require(len({r['security_id'] for r in universe})==77 and len({r['issuer_id'] for r in universe})==76 and len({r['ticker'] for r in universe})==77,'Unique full inventory')
    exact(mdv['full_inventory'],[{k:r[k] for k in ('security_id','issuer_id','ticker')} for r in universe],'MDV full inventory order')
    decisions=[]
    for j,cutoff in enumerate(CUTOFFS):
        period=mdv['periods'][j];controlperiod=control['decisions'][j]
        require(period['decision_date']==cutoff and controlperiod['cutoff']==cutoff and len(period['rows'])==77,'Same actual cutoff and77MDV')
        dates=controlperiod['price_dates'];require(len(dates)==505 and dates[-1]==cutoff,'Full505 source window')
        modes=[]
        for m,mode in enumerate(MODES):
            d=target['modes'][m]['decisions'][j];require(d['cutoff']==cutoff and len(d['windows'])==13 and type(d['window_count']) is int and d['window_count']==13,'Saved target13windows')
            exact(d['required_price_dates'],dates,'Target and control calendar');false_fields(d,('partial_window_pooling_allowed','scoring_allowed'))
            good=all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' for w in d['windows']);require(d['complete_thirteen_window_numeric_supply'] is good,'Target complete13 state')
            modes.append(dict(mode=mode,reference=dict(refs['target_inputs'],json_pointer=f'/modes/{m}/decisions/{j}'),complete_thirteen_windows=good))
        decisions.append(dict(cutoff=cutoff,scoring_price_dates=deepcopy(dates),scoring_data_reference=dict(refs['history_index'],json_pointer='/rows'),fitter_source_reference=deepcopy(refs['rolling_fitter_manifest']),incumbent_fee_reference=dict(refs['original8_inputs'],json_pointer='/scoring_inputs/normalized_scoring_weights'),qualifications=[],mode_sources=modes))
    count=0
    for i,channel in enumerate(channels):
        require(i<77,'Unexpected extra history channel');count+=1;row=h['rows'][i];audit=docs['history_audit']['rows'][i]
        require(type(row['index']) is int and type(audit['index']) is int and row['index']==audit['index']==i,'Full original channel order')
        exact(audit['coordinate'],row['coordinate'],'Audit coordinate');exact(audit['channel_reference'],row['channel_reference'],'Audit channel bytes');exact(audit['decision_coverage'],row['decision_coverage'],'Audited decision coverage')
        require(channel['schema']=='MULTIDECISION_SCORING_HISTORY_CHANNEL_V1' and channel['ticker']==row['coordinate']['ticker'] and len(channel['decisions'])==6,'History channel schema/ticker')
        require(channel['content_sha256']==sha(encoded({k:v for k,v in channel.items() if k!='content_sha256'})),'Saved channel internal digest')
        false_fields(channel,('point_in_time_verified','fit_performed','score_computed','missing_or_blocked_slots_dropped','unequal_window_pooling_allowed'))
        require(audit['inspection']['status']=='PASS' and audit['inspection']['ticker']==channel['ticker'] and type(audit['inspection']['window_count']) is int and audit['inspection']['window_count']==78,'Full78 audited channel windows')
        for j,decision in enumerate(decisions):
            d=channel['decisions'][j];coverage=row['decision_coverage'][j];m=mdv['periods'][j]['rows'][i]
            require(d['cutoff']==decision['cutoff'] and len(d['windows'])==13 and type(d['window_count']) is int and d['window_count']==13,'Full causal13history')
            exact(d['required_price_dates'],decision['scoring_price_dates'],'All77 same505 calendar');exact(m['coordinate'],row['coordinate'],'Full MDV coordinate unchanged');exact(m['required_dates'],decision['scoring_price_dates'][-63:],'Causal63 MDV dates')
            good=all(w['status']=='CONDITIONAL_NUMERIC_WINDOW' and w['blocked_price_slots']==[] for w in d['windows'])
            require(d['complete_thirteen_window_numeric_supply'] is good and coverage['complete_thirteen_window_numeric_supply'] is good and coverage['cutoff']==decision['cutoff'],'Complete history matches saved summary')
            require(type(coverage['blocked_window_count']) is int and coverage['blocked_window_count']==sum(w['status']=='BLOCKED_WINDOW' for w in d['windows']),'Blocked windows retained')
            available=m['status']=='CONDITIONAL_MDV_COMPUTABLE';reasons=deepcopy(m['reasons'])
            if not good:reasons.append('SAVED_FULL13_HISTORY_CONTAINS_BLOCKED_WINDOWS')
            decision['qualifications'].append(dict(security_id=row['coordinate']['security_id'],cutoff=decision['cutoff'],history_13_complete=good,mdv_available=available,liquidity_passed=m['conditional_numerical_threshold_passed'],conditional_member_scope_passed=True,history_reference=dict(row['channel_reference'],json_pointer=f'/decisions/{j}'),mdv_reference=dict(refs['mdv_result'],json_pointer=f'/periods/{j}/rows/{i}'),mdv_evidence=deepcopy(m),reasons=reasons))
    require(count==77,'Missing history channel; no inventory compression')
    return dict(registration=deepcopy(docs['policy']),registration_reference=deepcopy(refs['policy']),universe=universe,decisions=decisions)



def validate_fitter(document,baseline,policy_reference):
    require(document['schema']==ROLLING_MANIFEST_SCHEMA and document['status']=='FROZEN_BEFORE_ACTUAL_PLAN_OR_SCORE_NOT_DISPATCH_AUTHORITY','New rolling algorithm identity')
    exact(document['policy_reference'],policy_reference,'Fitter policy binding')
    false_fields(document,('execution_authorized','fit_performed','score_computed','point_in_time_verified','promotion_allowed','outer_cutoff_refit_substitution_allowed'))
    exact(document['required_worker_environment'],dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0),'Future worker must set process hash seed before start')
    require(document['inner_prior']=='FIRST_NONE_THEN_SAME_CANDIDATE_PREVIOUS_TARGET' and document['first_anchored_fit_none_interpretation']=='LEGACY_EQUAL_WEIGHT_ANCHOR' and type(document['first_anchored_fit_strength']) is float and document['first_anchored_fit_strength']==.25,'Inner None is equal anchor with strength retained')
    sources=document['source_hashes'];require(type(sources) is dict and len(sources)==25,'Registered new25 source closure')
    for p,h in sources.items():require(Path(p).is_absolute() and valid_sha(h),'Source shape');require(p not in baseline or baseline[p]==h,'Overlapping old/new source conflict')
    require(str(ROOT/'backtest/ndx_multidecision_rolling_fit_research.py') in sources and str(ROOT/'backtest/ndx_multidecision_window_scoring_research.py') in sources,'Actual inner rolling adapter and reducer required')
    require(set(document['runtime_versions'])=={'python','numpy','pandas','scipy'},'Required future worker runtime preserved')
    return sources


def private_budget(sources):
    # Authenticate and privately compile only the mathematics used for this plan.
    # No producer, fitter, scoring reducer or saved-result reader is imported.
    import builtins
    private={};original_import=builtins.__import__
    def restricted_import(name,globals=None,locals=None,fromlist=(),level=0):
        if name=='backtest' and fromlist:
            require(all(k in private for k in fromlist),'Unexpected mathematical dependency')
            return types.SimpleNamespace(**{k:private[k] for k in fromlist})
        return original_import(name,globals,locals,fromlist,level)
    def compile_one(name,path,h):
        blob=read(path,h,sources);module=types.ModuleType('_budget_private_'+name);module.__file__=str(path)
        module.__dict__['__builtins__']=dict(vars(builtins),__import__=restricted_import)
        # dataclasses requires its defining module during class construction.
        previous=sys.modules.get(module.__name__);sys.modules[module.__name__]=module
        try:exec(compile(blob,str(path),'exec'),module.__dict__)
        finally:
            if previous is None:sys.modules.pop(module.__name__,None)
            else:sys.modules[module.__name__]=previous
        private[name]=module;return module
    for name in ('ndx_cardinality_search','ndx_membership_scope_research','ndx_issuer_combination_index_research','ndx_membership_cardinality_plan_research'):
        compile_one(name,ROOT/'backtest'/f'{name}.py',MATH[name])
    read(ROOT/'backtest/ndx_dynamic_cutoff_refit_research.py',MATH['ndx_dynamic_cutoff_refit_research'],sources)
    core=compile_one(CORE.stem,CORE,CORE_SHA)
    exact(core.MATH_SOURCES,dict(issuer_index=MATH['ndx_issuer_combination_index_research'],necessary_bounds=MATH['ndx_membership_cardinality_plan_research']),'Original exact bound source hashes')
    return core


def load_inputs():
    # All final external anchors must be fixed before any filesystem access.
    require(valid_sha(CORE_SHA) and type(ROLLING_MANIFEST_PATH) is str and valid_sha(ROLLING_MANIFEST_SHA) and type(ROLLING_MANIFEST_SCHEMA) is str and BOUND and all(valid_sha(h) for p,h in BOUND.values()),'Final sources pending')
    sources={str(SOURCE):LOADED_SHA};docs={};refs={}
    for role,(path,h) in BOUND.items():
        p=(ROOT/path).resolve();blob=read(p,h,sources);refs[role]=reference(p,h)
        if not role.endswith('_reader'):docs[role]=loads(blob)
    p=(ROOT/ROLLING_MANIFEST_PATH).resolve();refs['rolling_fitter_manifest']=reference(p,ROLLING_MANIFEST_SHA);docs['rolling_fitter_manifest']=loads(read(p,ROLLING_MANIFEST_SHA,sources))
    _,_,_,_,baseline=validate_parents(docs,refs)
    new_sources=validate_fitter(docs['rolling_fitter_manifest'],baseline,refs['policy'])
    for mapping in (baseline,new_sources):
        for path,h in mapping.items():read(path,h,sources)
    def channels():
        for i,row in enumerate(docs['history_index']['rows']):
            r=row['channel_reference'];require(Path(r['path'])==Path(refs['history_index']['path']).parent/f'channel_{i:03d}.json','Fixed channel filename and namespace')
            yield loads(read(r['path'],r['sha256'],sources))
    args=project_inputs(docs,refs,channels());core=private_budget(sources);guard(sources)
    return docs,refs,sources,args,core


def validate_result(result,args):
    require(result['schema']=='MULTIDECISION_SCORING_BUDGET_PLAN_V1','Budget output schema')
    require(result['content_sha256']==sha(encoded({k:v for k,v in result.items() if k!='content_sha256'})),'Budget internal digest')
    exact(result['full_universe_preserved'],args['universe'],'Full inventory preserved');exact(result['decision_inputs_preserved'],args['decisions'],'Exact registered inputs');exact(result['registration_preserved'],args['registration'],'Policy unchanged')
    false_fields(result,('source_bytes_authenticated','point_in_time_verified','complete_ndx_universe_verified','qualification_evidence_authenticated','sector_filter_applied','economic_results_used_for_sampling','parent_artifact_hash_used_for_sampling','mode_selected_using_results','score_computed','fit_performed','account_executed','execution_authorized','promotion_allowed','outer_lane_prior_resolved'))
    require(len(result['rows'])==6,'Six decisions')
    for row,cutoff in zip(result['rows'],CUTOFFS):
        require(row['cutoff']==cutoff and len(row['domain_coverage'])==76 and len(row['universe_preserved'])==77,'Full cutoffs and allk retained')
        require(row['sampling']['complete'] is True,'Incomplete sampling may not publish an executable-looking plan')
        exact([m['mode'] for m in row['mode_plans']],MODES,'Both target modes')
        for mode in row['mode_plans']:
            require(type(mode['task_count']) is int and mode['task_count']==len(mode['tasks']) and mode['score_dispatch_authorized'] is False,'No score dispatch authority')


def run(*,execute=False):
    require(type(execute) is bool,'Exact execute')
    if not execute:return dict(status='NOT_EXECUTED',output=str(OUTPUT))
    require(valid_sha(ROLLING_MANIFEST_SHA),'Rolling fitter identity pending')
    require(not OUTPUT.exists(),'Immutable namespace already exists')
    docs,refs,sources,args,core=load_inputs();space(0);OUTPUT.mkdir(parents=True,exist_ok=False);written=[];execution_runtime=runtime()
    try:
        written.append(save(OUTPUT/'started.json',dict(schema='MULTIDECISION_SCORING_BUDGET_STARTED_V1',started_at_utc=datetime.now(timezone.utc).isoformat(),input_references=refs,source_hashes=deepcopy(sources),runtime=execution_runtime,retry_allowed=False,**FLAGS)))
        guard(sources)
        plan=core.plan_multidecision_scoring_budget(**args)
        raw=save(OUTPUT/'raw_plan.json',dict(schema='MULTIDECISION_SCORING_BUDGET_RAW_RETURN_V1',status='RETURNED_PENDING_VALIDATION_NOT_REGISTERED',plan=plan,input_references=refs,source_hashes=deepcopy(sources),runtime=execution_runtime,**FLAGS));written.append(raw)
        validate_result(plan,args);guard(sources)
        document=dict(schema='MULTIDECISION_SCORING_BUDGET_DOCUMENT_V1',status='REGISTERED_BEFORE_CANDIDATE_SCORING_NOT_DISPATCH_AUTHORITY',plan=plan,raw_plan_reference=raw,input_references=refs,source_hashes=deepcopy(sources),runtime=execution_runtime,security_count=77,issuer_count=76,observed_security_count=101,preserved_sidecar_count=7,original_provenance_and_missing=deepcopy(docs['history_index']['original_provenance_and_missing']),preserved_evidence_sidecars=deepcopy(docs['history_index']['preserved_evidence_sidecars']),original_parent_source_hash_claims={k:deepcopy(docs[k]['source_hashes']) for k in ('history_index','original8_inputs','target_index')},mdv_diagnostic_report_preserved=deepcopy(docs['mdv_report']),rolling_fitter_manifest_preserved=deepcopy(docs['rolling_fitter_manifest']),original25_baseline_source_hashes_preserved=deepcopy(docs['fitter_container']['plan']['fitter_source_hashes']),conditional_membership_scope_only=True,numeric_source_readbacks_reused=True,**FLAGS)
        out=save(OUTPUT/'plan.json',document);written.append(out)
        written.append(save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_SCORING_BUDGET_PUBLICATION_V1',status=document['status'],plan_reference=out,raw_plan_reference=raw,input_references=refs,source_hashes=deepcopy(sources),**FLAGS)))
        guard(sources);exact(runtime(),execution_runtime,'Runtime changed')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','raw_plan.json','plan.json','publication.json'},'Exact immutable output namespace')
        for r in written:require(sha(Path(r['path']).read_bytes())==r['sha256'],'Final output drift')
        return out
    except Exception as exc:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(exc).__name__,error=str(exc),saved_references=written,retry_allowed=False,**FLAGS),failure=True);raise


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
