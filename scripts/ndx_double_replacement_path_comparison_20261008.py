"""Saved signed replacement comparison only. No accounts, selection or fit.

External twenty-role registration precedes IO; the frozen signed publisher is
privately loaded only as its source parser (compile_numerical=False).
"""
import argparse,builtins,hashlib,json,os,re,types
from copy import deepcopy
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/double_replacement_path_comparison_20261008_v1'
PARENT=ROOT/'data/cache/research/double_replacement_signed_paths_20261008_v1'
OLD_BOUND={
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
BOUND={k:v for k,v in OLD_BOUND.items()if k not in ('selected_result','selected_publication','selected_audit','selected_reader','pure')}
BOUND['pure']=(str(ROOT/'backtest/ndx_double_replacement_path_comparison_research.py'),None)
BOUND['signed_producer']=(str(ROOT/'scripts/ndx_double_replacement_signed_paths_20261008.py'),None)
BOUND['signed_reader']=(str(ROOT/'scripts/ndx_double_replacement_signed_paths_independent_readback_20261008.py'),None)
FUTURE_PATHS={'signed_result':str(PARENT/'result.json'),'signed_publication':str(PARENT/'publication.json'),'signed_audit':str(ROOT/'data/cache/research/double_replacement_signed_paths_independent_readback_20261008_v1/independent_readback.json')}
FLAGS=dict.fromkeys(('account_executed','controls_executed','old_audits_reexecuted','fit_executed','selection_reexecuted','risk_recomputed','source_authenticated_by_pure','point_in_time_verified','promotion_allowed','formal_dual_benchmark_admission','fresh_oos_claimed','economic_winner_selected','currency_fx_equivalence_verified','automatic_retry_allowed'),False)
AUDIT_FALSE=('account_called','request_producer_called','selector_called','risk_recomputed','control_reexecuted','point_in_time_verified','promotion_allowed','orders_executed','full_transitive_original_paired_sources_reaudited','automatic_retry_allowed')
STREAMED=('sameflow','reference')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg='Exact source mismatch'):require(enc(a)==enc(b),msg)
def ref(path,h):return dict(path=str(path),sha256=h)
def pointer(r,p):return dict(r,json_pointer=p)
def markdown(r):return dict(r,document_scope='WHOLE_MARKDOWN_REPORT')
def reference(r):
 require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit external reference before IO')
 p=Path(r['path']);require(p.is_absolute()and str(p)==r['path']and '..'not in p.parts,'Canonical absolute reference');return r
def merge(s,r):
 reference(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source collision');s[r['path']]=r['sha256']
def decode(b):
 def pairs(items):
  result={}
  for k,v in items:require(k not in result,'Duplicate key');result[k]=v
  return result
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def take(r,s):
 merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Exact consumed bytes');return b
def filehash(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def private(r,metrics=None):
 b=take(r,{})
 m=types.ModuleType('_private_signed_comparison_dependency');m.__file__=r['path']
 if metrics is not None:
  def importer(name,globals=None,locals=None,fromlist=(),level=0):
   if name=='backtest':
    require(tuple(fromlist)==('ndx_cash_fork_reference_window_research',)and level==0,'Only frozen metrics import');return types.SimpleNamespace(ndx_cash_fork_reference_window_research=metrics)
   return builtins.__import__(name,globals,locals,fromlist,level)
  m.__dict__['__builtins__']={**vars(builtins),'__import__':importer}
 exec(compile(b,r['path'],'exec'),m.__dict__);return m
def load_adapter(r):return private(r)
def flags(obj):require(all(obj[k]is False for k in FLAGS),'Comparison authority false')
def guard(c):
 c['adapter'].guard(c['signed_context'])
 require(filehash(SOURCE)==LOADED,'Loaded comparison source')
 for p,h in c['sources'].items():require(filehash(p)==h,'Source drift '+p)
 for p,names in c['dirs'].items():exact(c['adapter'].inventory(p),names,'Exact source directory drift')
def save(path,value,adapter,emergency=False):
 b=enc(value)
 if not emergency:adapter.resource(encoded_bytes=len(b))
 with Path(path).open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(Path(path).read_bytes()==b,'Durable exact bytes');return ref(path,sha(b))

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

def load_inputs(registration_reference,*,compile_comparison=True):
 reference(registration_reference);sources={str(SOURCE):LOADED};registration=decode(take(registration_reference,sources))
 require(registration['schema']=='DOUBLE_REPLACEMENT_COMPARISON_SOURCE_REGISTRATION_V1'and registration['status']=='REGISTERED_SAVED_SIGNED_PATH_COMPARISON_ONLY','Explicit comparison registration');flags(registration)
 require(type(registration['scenario_count'])is int and registration['scenario_count']==40,'Full forty registration')
 refs=registration['input_references'];require(set(refs)==set(BOUND)|set(FUTURE_PATHS)|{'signed_registration'} and len(refs)==20,'Twenty unique source roles')
 for r in refs.values():reference(r)
 for k,(p,h)in BOUND.items():exact(refs[k],ref(p,h),'Fixed existing source role '+k)
 for k,p in FUTURE_PATHS.items():require(refs[k]['path']==p,'Fixed future signed artifact role')
 adapter=load_adapter(refs['signed_producer']);sc=adapter.load_inputs(refs['signed_registration'],compile_numerical=False)
 require(set(sc['modules'])=={'stream'},'Source adapter must not compile request/account/inspector')
 exact(sc['refs']['paired'],refs['paired'],'Same immutable original paired');exact(sc['refs']['paired_publication'],refs['paired_publication'],'Same original publication')
 adapter.resource(metadata_bytes=sum(Path(r['path']).stat().st_size for r in refs.values()))
 old,locations,summary=adapter.read_paired(sc)
 for path,h in sc['sources'].items():merge(sources,ref(path,h))
 docs={};dirs=dict(sc['dirs']);stream=sc['modules']['stream'];consumed={}
 def get(r,name=None):
  if name is not None:require(r['path']==str(Path(refs['signed_result']['path']).parent/name),'Exact signed output role path')
  value=decode(take(r,consumed));merge(sources,r);return value
 for k,r in refs.items():
  if k in ('paired',)+STREAMED:continue
  if k in ('pure','metrics','stream','signed_producer','signed_reader')or k.endswith('_audit')and Path(r['path']).suffix=='.md':take(r,sources)
  else:docs[k]=decode(take(r,sources))
 result,pub,audit=docs['signed_result'],docs['signed_publication'],docs['signed_audit']
 require(result['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATHS_RESULT_V1'and result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK'and result['failure']is None,'No failed signed parent treated as complete')
 require(pub['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATHS_PUBLICATION_V1'and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_SOURCE_READBACK','Signed publication')
 require(audit['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATHS_INDEPENDENT_READBACK_V1'and audit['status']=='PASS'and audit['source_bytes_authenticated']is True and audit['all_paired_rows_and_eof_verified']is True,'Signed full source/account independent readback')
 require(audit['scope']=='INDEPENDENT_FULL_REQUEST_PROJECTION_AND_SIGNED_LEDGER_SHARED_AUTHENTICATED_SOURCE_AND_JSON_ROWS_PARSER','Signed reader declared scope')
 for k in AUDIT_FALSE:require(audit[k]is False,'Signed independent authority false')
 exact(audit['reader_sha256'],refs['signed_reader']['sha256'],'Signed reader source identity');exact(audit['shared_source_parser_reference'],refs['signed_producer'],'Signed shared source parser')
 for doc in (result,pub):
  adapter.flags(doc);exact(doc['registration_reference'],refs['signed_registration'],'Signed external registration');exact(doc['input_references'],sc['refs'],'Signed nine native double roles');exact(doc['source_hashes'],sc['sources'],'Signed complete original source set')
 exact(pub['result_reference'],refs['signed_result'],'Published signed result');exact(audit['result_reference'],refs['signed_result'],'Audited signed result');exact(audit['publication_reference'],refs['signed_publication'],'Audited signed publication');exact(audit['registration_reference'],refs['signed_registration'],'Audited signed registration')
 for r in (refs['signed_result'],refs['signed_publication']):merge(consumed,r)
 started=get(pub['started_reference'],'started.json');adapter.flags(started)
 require(started['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATHS_STARTED_V1'and started['paired_eof_required_before_dispatch']is True,'Original signed START')
 for key in ('registration_reference','input_references'):exact(started[key],result[key],'START binding')
 expected_pre=dict(sc['sources']);expected_pre.pop(refs['paired']['path'],None);exact(started['source_hashes'],expected_pre,'START before paired EOF source map')
 index=get(result['requests_index_reference'],'requests_index.json');rawrequests=get(result['raw_requests_reference'],'raw_requests.json');adapter.flags(index)
 for key in ('requests_index_reference','raw_requests_reference'):exact(pub[key],result[key],'Signed root linkage')
 require(index['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUESTS_INDEX_V1','Signed request index');exact(index['paired_stream_summary'],summary,'Whole paired EOF')
 for key in ('source_hashes','registration_reference','input_references'):exact(index[key],result[key],'Index source binding')
 exact(index['raw_requests_reference'],result['raw_requests_reference'],'Original request raw link')
 require(rawrequests['call_invoked']is True and type(rawrequests['call_count'])is int and rawrequests['call_count']==1 and rawrequests['returned']is True and rawrequests['error']is None and rawrequests['result_preserved_as_json']is True,'Actual saved request return')
 requested=rawrequests['result'];require(requested['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUESTS_V1','Signed request pure schema')
 for doc,key in ((result,'rows'),(index,'rows'),(audit,'rows'),(requested,'rows')):
  require(type(doc['scenario_count'])is int and doc['scenario_count']==40 and type(doc[key])is list and len(doc[key])==40,'Every signed role full typed forty')
 expected_files={'started.json','raw_requests.json','requests_index.json','result.json','publication.json'};candidates=[];counts=dict.fromkeys(('ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK','NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP','ACCOUNT_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED'),0)
 for i,(entry,ar,original)in enumerate(zip(result['rows'],audit['rows'],old)):
  folder=f'scenario-{i:02d}';request=get(entry['request_reference'],folder+'/request.json');adapter.flags(request);row=request['prepared_request'];expected_files.add(folder+'/request.json')
  require(request['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUEST_V1','Exact signed request schema')
  for obj in (entry,ar,request,row):require(type(obj['scenario_index'])is int and obj['scenario_index']==i and obj['scenario_id']==original['scenario_id'],'Signed case identity')
  exact(row,requested['rows'][i],'Original prepared request');exact(row['old_paired_evidence'],original,'Entire original paired case');exact(request['paired_row_byte_reference'],locations[i],'Actual old paired byte location')
  exact(request['raw_requests_reference'],result['raw_requests_reference'],'Original preparation return');exact(request['source_hashes'],sc['sources'],'Request original source closure');exact(request['input_references'],sc['refs'],'Request original roles')
  exact(row['selection_reference'],pointer(sc['refs']['selection'],f'/selection/rows/{i}'),'Actual selection object pointer');exact(row['selection_row'],sc['docs']['selection']['selection']['rows'][i],'Actual selected object');exact(row['prepared_case'],sc['docs']['prepared']['preparation']['document']['cases'][i],'Original prepared domain case')
  exact(entry['input_status'],row['status'],'Original requested status');exact(entry['control_reference'],pointer(refs['paired'],f'/rows/{i}/paths/same_flow_zero_trade_control'),'Original zero-control only reference')
  expected_entry=dict(scenario_index=i,scenario_id=row['scenario_id'],input_status=row['status'],request_reference=entry['request_reference'],outcome=row['status']if row['status']!='NEW_SIGNED_PATH_REQUIRED'else'UNDISPATCHED',account_call_invoked=False,account_call_returned=False,control_reference=entry['control_reference'])
  exact(index['rows'][i],expected_entry,'Pre-dispatch index row')
  candidate=dict(status=row['status'],reason=None,account=None,account_reference=None,accounting_inputs=None,inputs_reference=None,account_inspection=None,inspection_reference=None,evidence_reference=pointer(refs['signed_audit'],f'/rows/{i}'),selection_reference=row['selection_reference'])
  if row['status']in ('NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP'):
   exact(entry,expected_entry,'Missing is not cash');exact(ar,dict(scenario_index=i,scenario_id=row['scenario_id'],status=row['status'],account_inspection=None),'Actual absent audit');require(row['accounting_request']is None,'Blocked request cannot carry account');candidate['reason']=row['status'];counts[row['status']]+=1
  else:
   require(row['status']=='NEW_SIGNED_PATH_REQUIRED'and entry['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'and entry['account_call_invoked']is True and entry['account_call_returned']is True,'Only new independently audited signed account')
   raw=get(entry['raw_reference'],folder+'/raw_result.json');inspection=get(entry['inspection_reference'],folder+'/inspection.json');post=get(entry['postcheck_reference'],folder+'/postcheck.json');cs=get(entry['started_reference'],folder+'/started.json')
   for obj in (post,cs):adapter.flags(obj);require(type(obj['scenario_index'])is int and obj['scenario_index']==i and obj['scenario_id']==row['scenario_id'],'Actual signed attempt identity')
   require(cs['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_STARTED_V1'and post['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATH_POSTCHECK_V1'and post['outcome']==entry['outcome']and post['validation_error']is None,'Successful original signed postcheck')
   exact(cs['request_reference'],entry['request_reference'],'Started original request');exact(cs['registration_reference'],refs['signed_registration'],'Started registration')
   for key in ('request_reference','started_reference','raw_reference','inspection_reference'):exact(post[key],entry[key],'Post saved role binding')
   require(set(raw)=={'call_invoked','call_count','returned','result','error','result_preserved_as_json'}and raw['call_invoked']is True and type(raw['call_count'])is int and raw['call_count']==1 and raw['returned']is True and raw['error']is None and raw['result_preserved_as_json']is True,'Complete signed original raw return')
   exact(ar,dict(scenario_index=i,scenario_id=row['scenario_id'],status='PASS',raw_reference=entry['raw_reference'],inspection=inspection),'Actual source audit ledger row')
   require(inspection['saved_result_content_sha256']==sha(enc(raw['result'])),'Signed full result digest')
   exact(raw['result']['rows'][0]['trade_shares'],row['selection_row']['selected']['raw']['plan']['task']['signed_trade_quantities'],'Actual selected signed legs')
   expected_entry.update(outcome=entry['outcome'],account_call_invoked=True,account_call_returned=True,**{k:entry[k]for k in ('started_reference','raw_reference','inspection_reference','postcheck_reference')});exact(entry,expected_entry,'Exact successful slot')
   expected_files.update(folder+'/'+n for n in ('started.json','raw_result.json','inspection.json','postcheck.json'));counts[entry['outcome']]+=1
   candidate.update(status='AVAILABLE_NEW_SIGNED',account=raw['result'],account_reference=pointer(entry['raw_reference'],'/result'),accounting_inputs=row['accounting_request'],inputs_reference=pointer(entry['request_reference'],'/prepared_request/accounting_request'),account_inspection=inspection,inspection_reference=pointer(refs['signed_audit'],f'/rows/{i}/inspection'))
  candidates.append(candidate)
 exact(result['outcome_counts'],counts,'Signed complete outcome partition');exact(audit['outcome_counts'],counts,'Audited full partition');require(type(audit['account_checked_count'])is int and audit['account_checked_count']==counts['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],'All actual signed accounts inspected')
 expected_audit_sources=dict(sc['sources']);expected_audit_sources.update(consumed);expected_audit_sources[refs['signed_reader']['path']]=refs['signed_reader']['sha256'];expected_audit_sources[str(adapter.ROOT/adapter.CODE['inspector'][0])]=adapter.CODE['inspector'][1]
 exact(audit['source_hashes'],expected_audit_sources,'Independent source audit complete consumed closure')
 signed_folder=Path(refs['signed_result']['path']).parent
 expected_names=sorted(expected_files|{f'scenario-{i:02d}'for i in range(40)})
 exact([v.replace('\\','/')for v in adapter.inventory(signed_folder)],expected_names,'Complete signed namespace including all forty directories');dirs[str(signed_folder)]=adapter.inventory(signed_folder)
 af=Path(refs['signed_audit']['path']).parent;exact(adapter.inventory(af),['independent_readback.json','started.json'],'Exact independent signed audit namespace');dirs[str(af)]=adapter.inventory(af)
 audit_start=af/'started.json';audit_start_ref=ref(audit_start,filehash(audit_start));ast=decode(take(audit_start_ref,sources))
 require(ast['schema']=='DOUBLE_REPLACEMENT_SIGNED_PATHS_READBACK_STARTED_V1','Audit START');exact(ast['result_reference'],refs['signed_result']);exact(ast['publication_reference'],refs['signed_publication']);exact(ast['registration_reference'],refs['signed_registration'])
 contracts={'paired':('OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1','PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS'),'sameflow':('TOPUP_SAME_FLOW_COMPARISON_PUBLICATION_V1','PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON'),'reference':('TOPUP_REFERENCE_COMPARISON_PUBLICATION_V1','PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION'),'incumbent':('INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V1','PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS')}
 for role,(schema,status)in contracts.items():
  d=docs[role+'_publication'];require(d['schema']==schema and d['status']==status,'Saved reference publication role');require(all(d[k]is False for k in ('orders_executed','point_in_time_verified','promotion_allowed')),'Reference scope false');exact(d['comparison_reference'if role in STREAMED else'account_reference'],refs[role],'Reference publication hash')
  folder=Path(refs[role]['path']).parent;dirs[str(folder)]=adapter.inventory(folder)
 exact(docs['incumbent_publication']['source_hashes'],docs['incumbent']['source_hashes'],'Incumbent saved claims')
 cases=[];summaries={'paired':summary}
 with Path(refs['sameflow']['path']).open('rb')as sf,Path(refs['reference']['path']).open('rb')as nf:
  streams={'sameflow':stream.JsonRowsStream(sf,max_row_bytes=8*1024**2),'reference':stream.JsonRowsStream(nf,max_row_bytes=8*1024**2)}
  for i,(original,candidate)in enumerate(zip(old,candidates)):
   st=next(streams['sameflow'],None);nt=next(streams['reference'],None);require(st is not None and nt is not None and type(st['row_index'])is int and type(nt['row_index'])is int and st['row_index']==nt['row_index']==i,'Full ordered reference rows')
   cases.append(build_case(original,st['value'],nt['value'],docs['incumbent'],refs,i,candidate))
  for role,s in streams.items():
   require(next(s,None)is None,'No extra reference rows');su=s.summary;require(su['complete_document_consumed']is True and su['row_count']==40 and su['sha256']==refs[role]['sha256'],'Complete reference EOF/hash');exact(su['metadata']['source_hashes'],docs[role+'_publication']['source_hashes'],'Reference declared source linkage');summaries[role]=su;merge(sources,refs[role])
 c=dict(refs=refs,docs=docs,sources=sources,cases=cases,expected_scenario_ids=[row['scenario_id']for row in old],dirs=dirs,adapter=adapter,signed_context=sc,registration_reference=registration_reference,pure=None,stream_summaries=summaries)
 guard(c)
 if compile_comparison:c['pure']=private(refs['pure'],private(refs['metrics']))
 return c


def output_guard(saved):
 for r in saved:require(filehash(r['path'])==r['sha256'],'Final output bytes')
 require({p.name for p in OUTPUT.iterdir()}=={Path(r['path']).name for r in saved},'Exact output inventory')

def run(*,registration_reference=None,execute=False):
 require(execute is True,'Explicit saved comparison invocation');reference(registration_reference)
 c=load_inputs(registration_reference);require(not OUTPUT.exists(),'Create-only no retry');adapter=c['adapter'];adapter.resource();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
 try:
  saved.append(save(OUTPUT/'started.json',dict(schema='DOUBLE_REPLACEMENT_COMPARISON_STARTED_V1',registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],**FLAGS),adapter))
  guard(c);adapter.resource()
  raw,rawref=adapter.preserve_call(OUTPUT/'raw_comparison.json',c['pure'].compare_selected_double_replacement_paths,dict(cases=c['cases'],expected_scenario_ids=c['expected_scenario_ids']));saved.append(rawref)
  require(raw['returned']is True and raw['result_preserved_as_json']is True and type(raw['result'])is dict,'Comparison original returned object preserved before validation');result=raw['result'];guard(c)
  require(result['schema']=='DOUBLE_REPLACEMENT_SIGNED_REFERENCE_COMPARISON_V1'and type(result['scenario_count'])is int and result['scenario_count']==40 and len(result['rows'])==40,'Complete new signed comparison')
  for key in c['pure'].FLAGS:require(result[key]is False,'No economic authority')
  out=save(OUTPUT/'comparison.json',dict(schema='SOURCE_BOUND_DOUBLE_REPLACEMENT_PATH_COMPARISON_V1',comparison=result,raw_reference=rawref,registration_reference=registration_reference,input_references=c['refs'],source_hashes=c['sources'],stream_summaries=c['stream_summaries'],old_reference_metrics_recomputed=False,shared_source_parser_role='AUTHENTICATED_SIGNED_PUBLISHER_IO_ONLY_COMPILE_NUMERICAL_FALSE',old_reference_source_claims_reaudited=False,audit_started_externally_anchored=False,**FLAGS),adapter);saved.append(out)
  pub=save(OUTPUT/'publication.json',dict(schema='DOUBLE_REPLACEMENT_PATH_COMPARISON_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',comparison_reference=out,raw_reference=rawref,started_reference=saved[0],registration_reference=registration_reference,source_hashes=c['sources'],**FLAGS),adapter);saved.append(pub)
  guard(c);output_guard(saved);return dict(comparison=out,publication=pub)
 except BaseException as e:
  save(OUTPUT/'failure.json',dict(schema='DOUBLE_REPLACEMENT_COMPARISON_FAILURE_V1',error=adapter.diagnostic(e),saved_references=saved,registration_reference=registration_reference,**FLAGS),adapter,True);raise

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--registration');parser.add_argument('--sha256');a=parser.parse_args();print(json.dumps(run(registration_reference=ref(a.registration,a.sha256),execute=a.execute)))
