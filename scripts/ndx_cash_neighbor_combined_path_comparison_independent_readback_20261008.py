"""Independent source-bound forty-case comparison readback; no producer execution."""
import argparse,hashlib,json,os,types
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_20261008_v1'
COMPARISON=ROOT/'data/cache/research/cash_neighbor_combined_path_comparison_20261008_v1'
OUTPUT=ROOT/'data/cache/research/cash_neighbor_combined_path_comparison_independent_readback_20261008_v1'
BOUND={'index':(str(COMPARISON/'index.json'),'d36303c57eb4643c841d019fca5dbf0caa95e964961b327fa4aa49bdaa4d7fb9'),'publication':(str(COMPARISON/'publication.json'),'2477e5eeea1014dcee9886e34cc1dedd69e269b9b6cf63a92ea4d73e26b4f0d0'),
 'producer':(str(ROOT/'scripts/ndx_cash_neighbor_combined_path_comparison_20261008.py'),'83282bac64c1b201e0163619b4ac09253c50e797fbbf75a41628346e2537f71f'),
 'inspection':(str(ROOT/'backtest/ndx_cash_neighbor_path_comparison_inspection_research.py'),'e5885e125f0be6efadcd905842d45ab931fd503a48edbda0de262823f0ba88d5')}
INPUT_BOUND={
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
FALSE=('account_executed','old_accounts_reexecuted','old_audits_reexecuted','source_authenticated_by_pure','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','fresh_oos_claimed','economic_winner_selected','cross_window_ranking_performed','currency_fx_equivalence_verified')
PARENT_FALSE=('risk_recomputed','selection_reexecuted','controls_executed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','independent_account_readback_passed','full_transitive_source_closure_reverified')
STREAMED=('paired','sameflow','reference')
ROLES=('same_flow_zero_trade_control','same_flow_incumbent','fund_012922_cny_nav_reference')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(enc(a)==enc(b),'Exact saved value/type mismatch')
def integer(v,n):require(type(v)is int and v==n,'Exact integer')
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p,h):
 require(type(p)is str and p and p.strip()==p and type(h)is str and len(h)==64 and all(c in '0123456789abcdef'for c in h),'Pending external anchor');return dict(path=p,sha256=h)
def configured(bound):return {k:ref(*v)for k,v in bound.items()}
def ptr(r,p):return dict(r,json_pointer=p)
def md(r):return dict(r,document_scope='WHOLE_MARKDOWN_REPORT')
def merge(s,r):
 exact(sorted(r),['path','sha256']);ref(r['path'],r['sha256']);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def flags(d,keys=FALSE):
 for k in keys:require(d[k]is False,'False authority '+k)
def loads(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))
def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(r,s):
 merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Exact input bytes');return loads(b)
def guard(s):
 require(sha(SOURCE.read_bytes())==LOADED,'Reader runtime changed')
 for p,h in s.items():require(not (Path(p).parent/'failure.json').exists(),'Failed source namespace');require(hashfile(p)==h,'Source drift')
def namespace(p,names):
 items=list(p.iterdir());exact(sorted(v.name for v in items),sorted(names));require(all(v.is_file()and not v.is_symlink()for v in items),'Regular exact namespace')
def module(r):
 b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Immediate inspector/decoder source');m=types.ModuleType('_independent_saved_comparison');exec(compile(b,r['path'],'exec'),m.__dict__);return m
def save(p,v):
 b=enc(v)
 with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved readback');return ref(str(p),sha(b))

def validate_parents(d,r):
 result,pub,audit=(d[k]for k in ('selected_result','selected_publication','selected_audit'))
 exact(result['schema'],'CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1');exact(result['status'],'COMPLETE_PENDING_INDEPENDENT_READBACK');require(result['failure']is None,'No failed selection paths');integer(result['scenario_count'],40);integer(len(result['completed_rows']),40)
 exact(result['undispatched_scenario_ids'],[]);exact(result['unresolved_scenario_ids'],[])
 exact(pub['schema'],'CASH_NEIGHBOR_SELECTED_PATHS_PUBLICATION_V1');exact(pub['status'],'PUBLISHED_PENDING_INDEPENDENT_READBACK');exact(pub['result_reference'],r['selected_result']);exact(pub['source_hashes'],result['source_hashes'])
 exact(audit['schema'],'CASH_NEIGHBOR_SELECTED_PATHS_INDEPENDENT_READBACK_V1');exact(audit['status'],'PASS_SAVED_PATH_ARITHMETIC');exact(audit['result_reference'],r['selected_result']);exact(audit['publication_reference'],r['selected_publication']);exact(audit['reader_sha256'],r['selected_reader']['sha256']);integer(len(audit['cases']),40)
 for key in ('selected_result','selected_publication','selected_reader'):require(audit['source_hashes'].get(r[key]['path'])==r[key]['sha256'],'Selected audit external binding')
 for v in (result,pub,audit):flags(v,PARENT_FALSE)
 specs={'paired':('OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS','account_reference'),'incumbent':('INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS','account_reference'),'sameflow':('TOPUP_SAME_FLOW_COMPARISON_PUBLICATION_V1','PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON','comparison_reference'),'reference':('TOPUP_REFERENCE_COMPARISON_PUBLICATION_V1','PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION','comparison_reference')}
 for role,(schema,status,key)in specs.items():
  p=d[role+'_publication'];exact(p['schema'],schema);exact(p['status'],status);exact(p[key],r[role]);flags(p,('orders_executed','point_in_time_verified','promotion_allowed'))
 exact(d['incumbent_publication']['source_hashes'],d['incumbent']['source_hashes'])

def check_case_evidence(case,old,same,nav,incumbent,refs,i):
 """Bind supplied case to original source rows, joining incumbent by scenario ID."""
 sid=old['scenario_id'];exact(same['scenario_id'],sid);exact(nav['scenario_id'],sid);exact(case['scenario_id'],sid)
 for v in (case,same,nav):exact(v['input_row'],old['input_row'])
 exact(case['input_reference'],old['input_reference']);exact(same['original_input_reference'],old['input_reference'])
 exact(same['candidate_paired_row_reference'],ptr(refs['paired'],f'/rows/{i}'));exact(nav['paired_row_reference'],ptr(refs['paired'],f'/rows/{i}'));exact(case['calendar'],same['calendar']);exact(case['calendar'],nav['comparison']['calendar']);exact(case['calendar_reference'],ptr(refs['sameflow'],f'/rows/{i}/calendar'))
 maps=[(j,m)for j,m in enumerate(incumbent['scenario_mappings'])if m['scenario_id']==sid];integer(len(maps),1);mi,mapping=maps[0]
 paths=[(j,p)for j,p in enumerate(incumbent['paths'])if p['path_id']==mapping['path_id']];integer(len(paths),1);pi,path=paths[0]
 expected_inc=dict(account=path['account'],account_reference=ptr(refs['incumbent'],f'/paths/{pi}/account'),evidence_reference=md(refs['incumbent_audit']),mapping=mapping,mapping_reference=ptr(refs['incumbent'],f'/scenario_mappings/{mi}'));exact(case['incumbent'],expected_inc)
 exact(same['incumbent_mapping_reference'],expected_inc['mapping_reference']);exact(same['incumbent_mapping_preserved'],mapping);exact(same['incumbent_path_reference'],ptr(refs['incumbent'],f'/paths/{pi}'))
 exact(same['observations']['same_flow_incumbent'],[dict(reference=ptr(refs['incumbent'],f'/paths/{pi}/account/daily/{j}'),source_row=v)for j,v in enumerate(path['account']['daily'])])
 z=old['paths']['same_flow_zero_trade_control'];exact(case['zero_trade_control'],dict(account=z['account'],account_reference=ptr(refs['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control/account'),accounting_inputs=z['accounting_inputs'],inputs_reference=ptr(refs['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control/accounting_inputs'),evidence_reference=md(refs['reference_audit'])))
 exact(nav['observations']['same_flow_zero_trade_control'],[dict(reference=ptr(refs['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control/account/rows/{j}'),source_row=v)for j,v in enumerate(z['account']['rows'])])
 expectednav=[]
 for ob in nav['observations']['fund_nav']:
  exact(ob['encoding'],'SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE');exact(ob['value_field'],'nav');v=ob['source_row'];require(type(v['nav'])is float,'Original NAV saved float')
  expectednav.append(dict(session=v['session'],nav_date=v['nav_date'],value=str(v['nav']),reference=ob['reference'],encoding=ob['encoding'],source_row=v))
 exact(case['nav_rows'],expectednav);exact(case['nav_evidence_reference'],md(refs['reference_audit']))
 metrics={role:dict(metrics=nav['comparison']['roles'][role],reference=ptr(refs['reference'],f'/rows/{i}/comparison/roles/{role}'),evidence_reference=md(refs['reference_audit']))for role in (ROLES[0],ROLES[2])}
 metrics[ROLES[1]]=dict(metrics=same['metrics'][ROLES[1]],reference=ptr(refs['sameflow'],f'/rows/{i}/metrics/{ROLES[1]}'),evidence_reference=md(refs['sameflow_audit']));exact(case['saved_reference_metrics'],metrics)
 exact(case['saved_original_reference_metadata'],dict(sameflow_limits={k:v for k,v in same.items()if k not in ('metrics','observations')},nav_limits={k:v for k,v in nav.items()if k not in ('comparison','observations')}))

def check_candidate(case,old,entry,audit,refs,i,authenticated,local):
 for obj in (entry,audit):integer(obj['scenario_index'],i);exact(obj['scenario_id'],old['scenario_id'])
 exact(audit['outcome'],entry['outcome']);rr=entry['request_reference'];exact(audit['request_reference'],rr)
 def consume(r):require(authenticated.get(r['path'])==r['sha256'],'Independent path audit source required');return read(r,local)
 requestdoc=consume(rr);flags(requestdoc,PARENT_FALSE);req=requestdoc['request'];exact(req['old_paired_evidence'],old);exact(req['scenario_id'],old['scenario_id']);exact(req['status'],entry['status']);exact(case['selection_reference'],req['input_references']['selection_reference']);exact(audit['control_reference'],req['control_path_reference']);exact(entry['control_reference'],req['control_path_reference'])
 c=case['candidate'];exact(c['evidence_reference'],ptr(refs['selected_audit'],f'/cases/{i}'));require(c['reason']is None,'Complete saved paths cannot invent absent reason')
 if entry['outcome']=='REUSE_EXISTING_PAIRED_PATH':
  path=old['paths']['candidate'];expected=ptr(refs['paired'],f'/rows/{i}/paths/candidate');exact(entry['candidate_reference'],expected);exact(audit['candidate_reference'],expected);exact(req['reused_candidate_path_reference'],expected);require(req['accounting_request']is None and audit['detail']is None,'Reference-only reuse')
  exact(c['status'],'AVAILABLE_REUSED');exact(c['account'],path['account']);exact(c['accounting_inputs'],path['accounting_inputs']);exact(c['account_reference'],ptr(refs['paired'],f'/rows/{i}/paths/candidate/account'));exact(c['inputs_reference'],ptr(refs['paired'],f'/rows/{i}/paths/candidate/accounting_inputs'))
 else:
  exact(entry['outcome'],'ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK');exact(entry['status'],'NEW_PATH_REQUIRED');exact(audit['raw_reference'],entry['raw_reference']);require(audit['detail']['independent_saved_quote_arithmetic_verified']is True,'Independently verified new path')
  raw=consume(entry['raw_reference']);post=consume(entry['postcheck_reference']);flags(raw,PARENT_FALSE);flags(post,PARENT_FALSE)
  exact(raw['request_reference'],rr);exact(post['raw_reference'],entry['raw_reference']);require(raw['error']is None and post['validation_error']is None,'No technical failure');exact(post['outcome'],'ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK')
  exact(c['status'],'AVAILABLE_NEW');exact(c['account'],raw['account']);exact(c['accounting_inputs'],req['accounting_request']);exact(c['account_reference'],ptr(entry['raw_reference'],'/account'));exact(c['inputs_reference'],ptr(rr,'/request/accounting_request'))
 exact(sorted(c),sorted(('status','reason','account','account_reference','accounting_inputs','inputs_reference','evidence_reference')))

def inspect_line(raw,descriptor,i,start):
 require(raw.endswith(b'\n')and len(raw)<=32*1024*1024,'Complete bounded JSONL row');integer(descriptor['scenario_index'],i);integer(descriptor['byte_start'],start);integer(descriptor['byte_stop'],start+len(raw));exact(descriptor['row_sha256'],sha(raw));v=loads(raw);require(raw==enc(v)+b'\n','Canonical output JSONL bytes');integer(v['scenario_index'],i);exact(v['scenario_id'],descriptor['scenario_id']);exact(v['candidate_status'],descriptor['candidate_status']);return v

def readback(*,execute=False):
 require(execute is True,'Explicit readback');bound=configured(BOUND);refs=configured(INPUT_BOUND) # every future pin before IO
 require(not OUTPUT.exists(),'Create-only no retry');namespace(COMPARISON,('started.json','cases.jsonl','index.json','publication.json'))
 base={str(SOURCE):LOADED};index=read(bound['index'],base);pub=read(bound['publication'],base)
 for k in ('producer','inspection'):merge(base,bound[k])
 expected_sources={bound['producer']['path']:bound['producer']['sha256']}
 for r in refs.values():merge(expected_sources,r)
 exact(index['schema'],'SOURCE_BOUND_CASH_NEIGHBOR_PATH_COMPARISON_V1');integer(index['scenario_count'],40);integer(len(index['cases']),40);flags(index);require(index['old_reference_metrics_recomputed']is False,'No old metrics rerun');exact(index['input_references'],refs);exact(index['source_hashes'],expected_sources);exact(index['metrics_dependency'],refs['metrics'])
 exact(pub['schema'],'CASH_NEIGHBOR_PATH_COMPARISON_PUBLICATION_V1');exact(pub['status'],'PUBLISHED_PENDING_INDEPENDENT_READBACK');exact(pub['index_reference'],bound['index']);exact(pub['source_hashes'],expected_sources);flags(pub)
 startedbytes=(COMPARISON/'started.json').read_bytes();started=loads(startedbytes);startedref=ref(str(COMPARISON/'started.json'),sha(startedbytes));merge(base,startedref);exact(started['input_references'],refs);integer(started['planned_scenario_count'],40);flags(started);exact(started['source_hashes'],{p:h for p,h in expected_sources.items()if p not in {refs[k]['path']for k in STREAMED}})
 jr=index['case_jsonl_reference'];exact(sorted(jr),['byte_count','path','record_count','sha256']);exact(jr['path'],str(COMPARISON/'cases.jsonl'));integer(jr['record_count'],40);ref(jr['path'],jr['sha256'])
 docs={}
 for k,r in refs.items():
  if k in STREAMED:continue
  merge(base,r)
  if k not in ('pure','metrics','stream','selected_reader')and not k.endswith('_audit')or k=='selected_audit':docs[k]=read(r,base)
 guard(base);validate_parents(docs,refs);core=module(bound['inspection']);streamcore=module(refs['stream'])
 OUTPUT.mkdir(parents=True,exist_ok=False)
 try:
  save(OUTPUT/'started.json',dict(index_reference=bound['index'],publication_reference=bound['publication'],source_hashes=base))
  summaries={};reports=[];consumed={};offset=0;h=hashlib.sha256();groups={};coordinates=set();counts={};ids=[]
  with Path(refs['paired']['path']).open('rb')as pf,Path(refs['sameflow']['path']).open('rb')as sf,Path(refs['reference']['path']).open('rb')as nf,Path(jr['path']).open('rb')as cf:
   streams={k:streamcore.JsonRowsStream(v)for k,v in zip(STREAMED,(pf,sf,nf))}
   for i,descriptor in enumerate(index['cases']):
    token={k:next(v,None)for k,v in streams.items()};require(all(v is not None for v in token.values()),'All original source rows')
    for v in token.values():integer(v['row_index'],i)
    old,same,nav=(token[k]['value']for k in STREAMED);raw=cf.readline(32*1024*1024+1);row=inspect_line(raw,descriptor,i,offset);h.update(raw);offset+=len(raw);case=row['original_case_evidence'];check_case_evidence(case,old,same,nav,docs['incumbent'],refs,i)
    local={};check_candidate(case,old,docs['selected_result']['completed_rows'][i],docs['selected_audit']['cases'][i],refs,i,docs['selected_audit']['consumed_case_sources'],local);guard(local)
    for p,x in local.items():merge(consumed,ref(p,x))
    reports.append(core.inspect_case(case=case,comparison_row=row,scenario_index=i));ids.append(case['scenario_id']);counts[row['candidate_status']]=counts.get(row['candidate_status'],0)+1;e=case['input_row']['cash_event'];lane=case['input_row']['lane'];coordinates.add((lane,e['decision_date'],e['execution_date'],e['amount_usd']));inc=case['incumbent'];key=inc['mapping']['path_id'];signature=sha(enc(dict(account=inc['account'],reference=inc['account_reference'])))
    if key in groups:exact(groups[key]['signature'],signature);groups[key]['lanes'].append(lane)
    else:groups[key]=dict(signature=signature,lanes=[lane])
   require(cf.read(1)==b'','No extra comparison row');integer(offset,jr['byte_count']);exact(h.hexdigest(),jr['sha256'])
   for k,stream in streams.items():
    require(next(stream,None)is None,'No omitted old source row');summary=stream.summary;integer(summary['row_count'],40);require(summary['complete_document_consumed']is True,'Full JSON EOF');exact(summary['sha256'],refs[k]['sha256']);exact(summary['metadata']['source_hashes'],docs[k+'_publication']['source_hashes']);exact(summary,index['streamed_source_summaries'][k]);summaries[k]=summary;merge(base,refs[k])
  integer(len(set(ids)),40);integer(len(groups),10)
  for v in groups.values():exact(sorted(v['lanes']),sorted(core.LANES))
  exact(coordinates=={(l,d,e,a)for l in core.LANES for d,e,_ in core.CLOCKS for a in ('1000','10000')},True);exact(counts,index['candidate_status_counts']);exact(consumed,index['consumed_candidate_sources']);merge(base,ref(jr['path'],jr['sha256']));guard(base);guard(consumed)
  report=dict(schema='CASH_NEIGHBOR_PATH_COMPARISON_INDEPENDENT_READBACK_V1',status='PASS',index_reference=bound['index'],publication_reference=bound['publication'],reader_sha256=LOADED,source_hashes=base,consumed_candidate_sources=consumed,scenario_count=40,cases=reports,candidate_status_counts=counts,incumbent_path_count=10,streamed_source_summaries=summaries,started_current_bytes_reference=startedref,started_externally_anchored=False,old_reference_metrics_recomputed=False,producer_called=False,old_audits_reexecuted=False,account_executed=False,point_in_time_verified=False,formal_dual_benchmark_admission=False,fresh_oos_claimed=False)
  rr=save(OUTPUT/'independent_readback.json',report);guard(base);guard(consumed);namespace(COMPARISON,('started.json','cases.jsonl','index.json','publication.json'));namespace(OUTPUT,('started.json','independent_readback.json'));require(hashfile(rr['path'])==rr['sha256'],'Final report bytes');return rr
 except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(e),retry_allowed=False));raise

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
