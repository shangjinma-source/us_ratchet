"""Source-bound forty candidate comparisons; no account or old-audit execution."""
import argparse,hashlib,json,os,types,shutil
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_neighbor_combined_path_comparison_20261008_v1'
PARENT=ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_20261008_v1'
BOUND={
 'selected_result':(str(PARENT/'result.json'),'ad6bb89625173932ff75dac6244543c78d267563532761171d5f84d7ab33d705'),
 'selected_publication':(str(PARENT/'publication.json'),'f6db71240f378cf3cf93bc849163fc359aa75a24839b1c53f5822e57d66b469d'),
 'selected_audit':(str(ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_independent_readback_20261008_v1/independent_readback.json'),'e616f9408e163891b0b59db518079fdc49c5f3a884cffa6c42bbf83c4a25cf50'),
 'selected_reader':(str(ROOT/'scripts/ndx_cash_neighbor_combined_selected_paths_independent_readback_20261008.py'),'77373a364eb1c6cc79aec821b6b522d73bb882ad4546a581d1b37378336a5213'),
 'pure':(str(ROOT/'backtest/ndx_cash_neighbor_path_comparison_research.py'),'6e90e961456c468a91a4c41ee89d2c3acdb182fe0be533b4ee8514c5ab3431f5'),
 'metrics':(str(ROOT/'backtest/ndx_cash_fork_reference_window_research.py'),'0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163'),
 'stream':(str(ROOT/'backtest/ndx_research_json_rows_stream.py'),'b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c'),
 'paired':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'),'7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json'),'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'sameflow':(str(ROOT/'data/cache/research/topup_same_flow_comparison_20261002_v1/comparison.json'),'53e99a06b926fef2c6bc7b761ad03d3fefabdf43b5bf70b09b6829294bcf5a8c'),
 'sameflow_publication':(str(ROOT/'data/cache/research/topup_same_flow_comparison_20261002_v1/publication.json'),'b5947018e6b96596ed3cbdb7d3cade2f53399dee06b7df77454f9385435bb650'),
 'sameflow_audit':(str(ROOT/'DYNAMIC_TOPUP_SAME_FLOW_INDEPENDENT_READBACK_20261002.md'),'275150a07ddfc09a85808259dc24c921d0dc6cb79da384e8196fae88863da88c'),
 'reference':(str(ROOT/'data/cache/research/topup_reference_comparison_20261002_v1/comparison.json'),'169eeb4158e95829240263c05d04285695151db98000356f3b05b00ca8e5553f'),
 'reference_publication':(str(ROOT/'data/cache/research/topup_reference_comparison_20261002_v1/publication.json'),'2c048cdfb7357a0df844226d2bef6fd54b501fa7da91b1b4a789d476827157b7'),
 'reference_audit':(str(ROOT/'DYNAMIC_TOPUP_REFERENCE_INDEPENDENT_READBACK_20261002.md'),'fa3e6e89b7d67524bc65dd9de7ef68f41935886fe22a8c618457f1baea816e50'),
 'incumbent':(str(ROOT/'data/cache/research/incumbent_cash_flow_paths_20261002_v1/accounts.json'),'d1ac38ebe7674756d67cdc390938a6dffbe0d4f45c25e7b10726fab5642dc36a'),
 'incumbent_publication':(str(ROOT/'data/cache/research/incumbent_cash_flow_paths_20261002_v1/publication.json'),'2abc2d2bbe9e03e6f7c84f11f6c9c9a422d81624a291c9494349c58950ede1bd'),
 'incumbent_audit':(str(ROOT/'DYNAMIC_INCUMBENT_CASH_FLOW_INDEPENDENT_READBACK_20261002.md'),'1c368e421c06b6ba5f4e05116a5ee9dd82ce330a6ca4a9180784aedcb5ebc023'),
}
FLAGS=dict.fromkeys(('account_executed','old_accounts_reexecuted','old_audits_reexecuted','source_authenticated_by_pure','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','fresh_oos_claimed','economic_winner_selected','cross_window_ranking_performed','currency_fx_equivalence_verified'),False)
PARENT_FALSE=('risk_recomputed','selection_reexecuted','controls_executed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','independent_account_readback_passed','full_transitive_source_closure_reverified')
def parent_flags(doc):
    require(all(doc[k]is False for k in PARENT_FALSE),'Selected parent authority')
STREAMED=('sameflow','reference','paired')

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(enc(a)==enc(b),'Exact saved source mismatch')
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def ref(p,h):return dict(path=str(p),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and type(r['sha256'])is str and len(r['sha256'])==64 and all(c in '0123456789abcdef'for c in r['sha256']),'Pending source anchor');return r
def pointer(r,p):return dict(r,json_pointer=p)
def markdown(r):return dict(r,document_scope='WHOLE_MARKDOWN_REPORT')
def merge(s,r):valid(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def read(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Source bytes');return json.loads(b)
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Wrapper drift')
    for p,h in s.items():
        require(file_sha(p)==h,'Source drift '+p)
        require(not (Path(p).parent/'failure.json').exists(),'Source namespace failure marker')
def resource_check(path,byte_count=0):
    require(type(byte_count)is int and byte_count>=0,'Exact encoded byte count')
    require(shutil.disk_usage(path).free>=5*1024**3+byte_count,'RESOURCE_STOP: preserve 5 GiB plus encoded output bytes')
def save(p,v,*,failure_evidence=False):
    b=enc(v)
    if not failure_evidence:resource_check(p.parent,len(b))
    with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved bytes');return ref(p,sha(b))
def private_module(r,metrics=None):
    import builtins
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Immediate code hash');m=types.ModuleType('_private_cash_compare')
    if metrics is not None:
        def importer(name,globals=None,locals=None,fromlist=(),level=0):
            if name=='backtest':
                require(tuple(fromlist)==('ndx_cash_fork_reference_window_research',),'Only pinned metrics dependency');return types.SimpleNamespace(ndx_cash_fork_reference_window_research=metrics)
            return builtins.__import__(name,globals,locals,fromlist,level)
        m.__dict__['__builtins__']=dict(vars(builtins),__import__=importer)
    exec(compile(b,r['path'],'exec'),m.__dict__);return m

def build_case(old,same,nav,incumbent,refs,index,candidate):
    candidate=deepcopy(candidate);sid=old['scenario_id'];require(same['scenario_id']==nav['scenario_id']==sid,'Three old row identities')
    exact(same['input_row'],old['input_row']);exact(nav['input_row'],old['input_row']);exact(same['original_input_reference'],old['input_reference']);exact(same['calendar'],nav['comparison']['calendar'])
    exact(same['candidate_paired_row_reference'],pointer(refs['paired'],f'/rows/{index}'));exact(nav['paired_row_reference'],pointer(refs['paired'],f'/rows/{index}'))
    matches=[(i,m)for i,m in enumerate(incumbent['scenario_mappings'])if m['scenario_id']==sid];require(len(matches)==1,'Unique scenario ID join');mi,mapping=matches[0];paths=[(i,p)for i,p in enumerate(incumbent['paths'])if p['path_id']==mapping['path_id']];require(len(paths)==1,'Unique incumbent path');pi,path=paths[0]
    exact(same['incumbent_mapping_reference'],pointer(refs['incumbent'],f'/scenario_mappings/{mi}'));exact(same['incumbent_path_reference'],pointer(refs['incumbent'],f'/paths/{pi}'));exact(same['incumbent_mapping_preserved'],mapping)
    for j,ob in enumerate(same['observations']['same_flow_incumbent']):exact(ob['reference'],pointer(refs['incumbent'],f'/paths/{pi}/account/daily/{j}'));exact(ob['source_row'],path['account']['daily'][j])
    require(len(same['observations']['same_flow_incumbent'])==len(path['account']['daily']),'Whole incumbent observations')
    zero=old['paths']['same_flow_zero_trade_control']
    for j,ob in enumerate(nav['observations']['same_flow_zero_trade_control']):exact(ob['reference'],pointer(refs['paired'],f'/rows/{index}/paths/same_flow_zero_trade_control/account/rows/{j}'));exact(ob['source_row'],zero['account']['rows'][j])
    require(len(nav['observations']['same_flow_zero_trade_control'])==len(zero['account']['rows']),'Whole zero-control observations')
    navrows=[]
    for ob in nav['observations']['fund_nav']:
        require(ob['encoding']=='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE' and ob['value_field']=='nav','Original NAV encoding');r=ob['source_row'];require(type(r['nav'])is float,'Saved NAV float literal');navrows.append(dict(session=r['session'],nav_date=r['nav_date'],value=str(r['nav']),reference=ob['reference'],encoding=ob['encoding'],source_row=r))
    metrics={}
    for role in ('same_flow_zero_trade_control','fund_012922_cny_nav_reference'):metrics[role]=dict(metrics=nav['comparison']['roles'][role],reference=pointer(refs['reference'],f'/rows/{index}/comparison/roles/{role}'),evidence_reference=markdown(refs['reference_audit']))
    metrics['same_flow_incumbent']=dict(metrics=same['metrics']['same_flow_incumbent'],reference=pointer(refs['sameflow'],f'/rows/{index}/metrics/same_flow_incumbent'),evidence_reference=markdown(refs['sameflow_audit']))
    return dict(scenario_id=sid,input_row=old['input_row'],input_reference=old['input_reference'],selection_reference=candidate.pop('selection_reference'),calendar=same['calendar'],calendar_reference=pointer(refs['sameflow'],f'/rows/{index}/calendar'),candidate=candidate,zero_trade_control=dict(account=zero['account'],account_reference=pointer(refs['paired'],f'/rows/{index}/paths/same_flow_zero_trade_control/account'),accounting_inputs=zero['accounting_inputs'],inputs_reference=pointer(refs['paired'],f'/rows/{index}/paths/same_flow_zero_trade_control/accounting_inputs'),evidence_reference=markdown(refs['reference_audit'])),incumbent=dict(account=path['account'],account_reference=pointer(refs['incumbent'],f'/paths/{pi}/account'),evidence_reference=markdown(refs['incumbent_audit']),mapping=mapping,mapping_reference=same['incumbent_mapping_reference']),nav_rows=navrows,nav_evidence_reference=markdown(refs['reference_audit']),saved_reference_metrics=metrics,saved_original_reference_metadata=dict(sameflow_limits={k:v for k,v in same.items()if k not in ('metrics','observations')},nav_limits={k:v for k,v in nav.items()if k not in ('comparison','observations')}))

def selected_candidate(entry,audit,refs,index,old,sources,audited_sources):
    exact(entry['scenario_index'],index);exact(audit['scenario_index'],index);exact(entry['scenario_id'],old['scenario_id']);exact(audit['scenario_id'],old['scenario_id']);exact(audit['outcome'],entry['outcome']);rr=entry['request_reference'];exact(audit['request_reference'],rr);require(audited_sources.get(rr['path'])==rr['sha256'],'Request independently audited bytes');request_doc=read(rr,sources);parent_flags(request_doc);request=request_doc['request'];exact(request['old_paired_evidence'],old);exact(request['scenario_id'],old['scenario_id']);exact(entry['status'],request['status']);exact(audit['control_reference'],request['control_path_reference']);exact(entry['control_reference'],request['control_path_reference'])
    evidence=pointer(refs['selected_audit'],f'/cases/{index}');selection=request['input_references']['selection_reference']
    if entry['outcome']=='REUSE_EXISTING_PAIRED_PATH':
        oldref=pointer(refs['paired'],f'/rows/{index}/paths/candidate');exact(entry['candidate_reference'],oldref);exact(audit['candidate_reference'],oldref);exact(request['reused_candidate_path_reference'],oldref);require(request['accounting_request']is None and audit['detail']is None,'Reference-only reuse');path=old['paths']['candidate']
        return dict(status='AVAILABLE_REUSED',reason=None,account=path['account'],account_reference=pointer(refs['paired'],f'/rows/{index}/paths/candidate/account'),accounting_inputs=path['accounting_inputs'],inputs_reference=pointer(refs['paired'],f'/rows/{index}/paths/candidate/accounting_inputs'),evidence_reference=evidence,selection_reference=selection)
    require(entry['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK' and entry['status']=='NEW_PATH_REQUIRED','Published new path only');rawref=entry['raw_reference'];exact(audit['raw_reference'],rawref);require(audit['detail']['independent_saved_quote_arithmetic_verified']is True,'Independent new account arithmetic');postref=entry['postcheck_reference'];require(all(audited_sources.get(r['path'])==r['sha256']for r in (rawref,postref)),'New account raw/post independently audited bytes');raw=read(rawref,sources);post=read(postref,sources);parent_flags(raw);parent_flags(post);exact(raw['request_reference'],rr);exact(post['raw_reference'],rawref);require(raw['error']is None and post['validation_error']is None and post['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK','No technical failure converted to cash')
    return dict(status='AVAILABLE_NEW',reason=None,account=raw['account'],account_reference=pointer(rawref,'/account'),accounting_inputs=request['accounting_request'],inputs_reference=pointer(rr,'/request/accounting_request'),evidence_reference=evidence,selection_reference=selection)

def load():
    refs={k:valid(ref(*v))for k,v in BOUND.items()};sources={str(SOURCE):LOADED};docs={}
    for role,r in refs.items():
        if role in STREAMED:continue
        merge(sources,r)
        if role.endswith('_audit') and Path(r['path']).suffix=='.md':continue
        if role in ('pure','metrics','stream','selected_reader'):continue
        docs[role]=read(r,sources)
    guard(sources)
    publication_contracts={
      'paired':('OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'),
      'incumbent':('INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS'),
      'sameflow':('TOPUP_SAME_FLOW_COMPARISON_PUBLICATION_V1','PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON'),
      'reference':('TOPUP_REFERENCE_COMPARISON_PUBLICATION_V1','PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION')}
    for role,(schema,status)in publication_contracts.items():
        d=docs[role+'_publication'];require(d['schema']==schema and d['status']==status,'Original publication role/schema');require(all(d[k]is False for k in ('orders_executed','point_in_time_verified','promotion_allowed')),'Original reference authority')
    for role,key in [('sameflow','comparison_reference'),('reference','comparison_reference'),('incumbent','account_reference'),('paired','account_reference')]:exact(docs[role+'_publication'][key],refs[role])
    result,pub,audit=docs['selected_result'],docs['selected_publication'],docs['selected_audit'];require(result['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1' and result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK' and result['failure']is None,'Complete selected path result');require(audit['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_INDEPENDENT_READBACK_V1' and audit['status']=='PASS_SAVED_PATH_ARITHMETIC','Actual selected arithmetic audit');exact(audit['result_reference'],refs['selected_result']);exact(audit['publication_reference'],refs['selected_publication']);exact(audit['reader_sha256'],refs['selected_reader']['sha256']);exact(pub['result_reference'],refs['selected_result']);exact(pub['source_hashes'],result['source_hashes']);require(pub['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_PUBLICATION_V1' and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK','Selected publication schema/status');require(all(audit['source_hashes'].get(refs[k]['path'])==refs[k]['sha256']for k in ('selected_result','selected_publication','selected_reader')),'Independent audit fixed source linkage');require(len(result['completed_rows'])==len(audit['cases'])==40 and result['undispatched_scenario_ids']==result['unresolved_scenario_ids']==[],'All forty accounted cases')
    for doc in (result,pub,audit):parent_flags(doc)
    exact(docs['incumbent_publication']['source_hashes'],docs['incumbent']['source_hashes'])
    for role in ('selected_result','selected_audit','sameflow_publication','reference_publication','incumbent_publication','paired_publication'):require(not (Path(refs[role]['path']).parent/'failure.json').exists(),'Failed parent namespace')
    metrics=private_module(refs['metrics']);pure=private_module(refs['pure'],metrics);stream=private_module(refs['stream']);return docs,refs,sources,pure,stream

def run(*,execute=False):
    require(execute is True,'Explicit execution');require(not OUTPUT.exists(),'Create-only no retry');docs,refs,sources,pure,stream_core=load();resource_check(OUTPUT.parent);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(input_references=refs,source_hashes=sources,planned_scenario_count=40,**FLAGS));records=[];groups={};coordinates=set();statuses={};consumed={};offset=0;digest=hashlib.sha256()
        with Path(refs['paired']['path']).open('rb')as pf,Path(refs['sameflow']['path']).open('rb')as sf,Path(refs['reference']['path']).open('rb')as nf,(OUTPUT/'cases.jsonl').open('xb')as target:
            streams={k:stream_core.JsonRowsStream(f)for k,f in [('paired',pf),('sameflow',sf),('reference',nf)]}
            for i,token in enumerate(streams['paired']):
                require(i<40,'No extra old row');same=next(streams['sameflow'],None);nav=next(streams['reference'],None);require(same is not None and nav is not None and same['row_index']==nav['row_index']==i,'Aligned full source rows');local={};entry=docs['selected_result']['completed_rows'][i];audit=docs['selected_audit']['cases'][i];candidate=selected_candidate(entry,audit,refs,i,token['value'],local,docs['selected_audit']['consumed_case_sources']);case=build_case(token['value'],same['value'],nav['value'],docs['incumbent'],refs,i,candidate);require(case['scenario_id']==entry['scenario_id'],'Exact original order');result=pure.compare_case(case,i,groups);e=case['input_row']['cash_event'];coordinates.add((case['input_row']['lane'],e['decision_date'],e['execution_date'],e['amount_usd']));statuses[result['candidate_status']]=statuses.get(result['candidate_status'],0)+1;guard(local);guard(sources)
                for p,h in local.items():merge(consumed,ref(p,h))
                raw=enc(result)+b'\n';resource_check(OUTPUT,len(raw));target.write(raw);digest.update(raw);records.append(dict(scenario_index=i,scenario_id=case['scenario_id'],candidate_status=result['candidate_status'],byte_start=offset,byte_stop=offset+len(raw),row_sha256=sha(raw)));offset+=len(raw)
            for role in ('sameflow','reference'):require(next(streams[role],None)is None,'No extra reference rows')
            summaries={}
            for role,s in streams.items():
                summary=s.summary;require(summary['row_count']==40 and summary['complete_document_consumed']is True,'Full source EOF');exact(summary['sha256'],refs[role]['sha256']);exact(summary['metadata']['source_hashes'],docs[role+'_publication']['source_hashes']);summaries[role]=summary;merge(sources,refs[role])
            target.flush();os.fsync(target.fileno())
        require(len(records)==40 and coordinates=={(l,d,e,a)for l in pure.LANES for d,e,_ in pure.CLOCKS for a in ('1000','10000')},'Full original forty domain');require(len(groups)==10 and all(sorted(v['lanes'])==sorted(pure.LANES)for v in groups.values()),'All ten shared controls');guard(sources);guard(consumed)
        jr=dict(path=str(OUTPUT/'cases.jsonl'),sha256=digest.hexdigest(),record_count=40,byte_count=offset);index=save(OUTPUT/'index.json',dict(schema='SOURCE_BOUND_CASH_NEIGHBOR_PATH_COMPARISON_V1',scenario_count=40,cases=records,candidate_status_counts=statuses,case_jsonl_reference=jr,input_references=refs,source_hashes=sources,consumed_candidate_sources=consumed,streamed_source_summaries=summaries,metrics_dependency=refs['metrics'],old_reference_metrics_recomputed=False,**FLAGS));pub=save(OUTPUT/'publication.json',dict(schema='CASH_NEIGHBOR_PATH_COMPARISON_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',index_reference=index,source_hashes=sources,**FLAGS));guard(sources);guard(consumed);require(all(sha(Path(r['path']).read_bytes())==r['sha256']for r in (index,pub)),'Final index/publication bytes');require(file_sha(jr['path'])==jr['sha256'],'Final JSONL bytes');require({p.name for p in OUTPUT.iterdir()}=={'started.json','cases.jsonl','index.json','publication.json'},'Exact output files');return index
    except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS),failure_evidence=True);raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
