"""Independent requests and signed-ledger readback; no account or selector dispatch.

The final source adapter explicitly identifies any shared authenticated byte
parser. Request projection and saved ledger arithmetic are independently checked.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from hashlib import sha256
import json

FALSE_FIELDS=('source_bytes_authenticated','selection_audit_authenticated','selection_reexecuted','risk_recomputed','fees_recomputed','account_executed','control_reexecuted','orders_executed','point_in_time_verified','promotion_allowed','future_returns_used','cross_family_winner_selected')
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')

def require(value,message):
 if not value:raise ValueError(message)

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(value):return sha256(encode(value)).hexdigest()
def exact(actual,expected,message):require(encode(actual)==encode(expected),message)
def flags():return dict.fromkeys(FALSE_FIELDS,False)

def inspect_requests(*,saved_requests,prepared,selection,old_paired_rows,source_references):
 """Rebuild all forty saved request rows from original authenticated roles.

No fee evaluation or winner search. The already independently audited selection
provides each signed task; original paired rows provide the entire price path.
"""
 require(set(source_references)=={'prepared','selection','selection_audit','old_paired'},'Four input roles')
 p=prepared['document'];s=selection['document']
 exact(digest(p),prepared['content_sha256'],'Prepared envelope');exact(digest(s),selection['content_sha256'],'Selection envelope')
 require(p['schema']=='SINGLE_REPLACEMENT_DOMAIN_PREPARATION_V1' and s['schema']=='SINGLE_REPLACEMENT_COMPLETE_DOMAIN_SELECTION_V1','Input schemas')
 exact(s['preparation_reference'],source_references['prepared'],'Preparation source identity')
 exact(s['prepared_content_sha256'],prepared['content_sha256'],'Prepared body identity')
 exact(s['action_contract'],p['action_contract'],'Action policy')
 require(s['all_registered_points_consumed'] is True and type(old_paired_rows)is list and len(old_paired_rows)==len(p['cases'])==len(s['rows'])==40,'Complete full selection')
 rows=[];claims={};counts=dict(NEW_SIGNED_PATH_REQUIRED=0,NO_FEASIBLE=0,BLOCKED_TEMPLATE_PRICE_GAP=0);coordinates=set()
 def merge(r):
  require(type(r)is dict and type(r.get('path'))is str and type(r.get('sha256'))is str and len(r['sha256'])==64,'Source role')
  require(r['path']not in claims or claims[r['path']]==r['sha256'],'Conflicting references');claims[r['path']]=r['sha256']
 for r in source_references.values():merge(r)
 for i,(case,chosen,old)in enumerate(zip(p['cases'],s['rows'],old_paired_rows)):
  original=case['identity']['original_input_row'];sid=original['scenario_id'];event=original['cash_event']
  require(type(case['scenario_index'])is int and case['scenario_index']==i and type(chosen['scenario_index'])is int and chosen['scenario_index']==i,'Typed original ordinal')
  exact(chosen['scenario_id'],sid,'Selected scenario');exact(old['scenario_id'],sid,'Paired scenario')
  exact(old['input_row'],original,'Entire original row');exact(old['topup_context']['input_row'],original,'Original context')
  exact(old['input_reference'],case['identity']['input_reference'],'Original input location')
  merge(old['input_reference']);merge(old['topup_context_reference'])
  template=old['paths']['candidate']['accounting_inputs'];initial=template['initial'];sessions=template['sessions']
  require(set(template)=={'initial','sessions','transaction_cost_bps'},'Original template keys')
  exact(initial['holdings'],original['holdings'],'Original holdings');exact(initial['cash_usd'],original['starting_cash_usd'],'Original capital')
  exact(initial['session'],event['decision_date'],'Initial Close')
  coordinate=(original['lane'],event['decision_date'],event['execution_date'],event['amount_usd']);require(coordinate not in coordinates,'Unique coordinates');coordinates.add(coordinate)
  lengths={(d,e):n for d,e,n in CLOCKS};require((event['decision_date'],event['execution_date'])in lengths,'Original clock')
  require(len(sessions)==lengths[(event['decision_date'],event['execution_date'])],'Full original dates')
  days=[r['session']for r in sessions];require(days==sorted(set(days)) and days[0]==event['execution_date'] and days[-1]=='2023-09-01','Original complete calendar')
  for day in [initial['session']]+days:require(type(day)is str and date.fromisoformat(day).isoformat()==day,'Canonical dates')
  ids=set(original['holdings'])|set(original['execution_prices']);gaps=[]
  def missing(values,required,location):
   require(type(values)is dict and set(values)<=set(required),'No foreign price columns')
   absent=sorted(set(required)-set(values))
   if absent:gaps.append(dict(reason='MISSING_SAVED_PRICE',location=location,security_ids=absent))
  missing(initial['close_prices'],original['holdings'],'initial.close_prices')
  for j,session in enumerate(sessions):
   require(set(session)=={'session','open_prices','close_prices','cash_injection_usd','buy_shares'},'Original daily fields')
   missing(session['open_prices'],ids,f'sessions/{j}/open_prices');missing(session['close_prices'],ids,f'sessions/{j}/close_prices')
   require(Fraction(session['cash_injection_usd'])==(Fraction(event['amount_usd'])if j==0 else 0),'Single original injection')
  selected=chosen['selected'];request=None;expected=None
  if selected is None:
   require(chosen['status']=='NO_FEASIBLE' and type(chosen['feasible_count'])is int and chosen['feasible_count']==0,'Absent is not cash');status='NO_FEASIBLE'
  else:
   require(chosen['status']=='SELECTED_REQUIRES_NEW_SIGNED_PATH','Signed selected state')
   task=selected['task'];identity=task['identity'];require(task['task_id']==digest(identity),'Task identity')
   outgoing=identity['outgoing_security_id'];incoming=identity['incoming_security_id'];q=identity['buy_quantity'];sold=identity['sell_quantity']
   require(type(q)is int and q>0 and type(sold)is int and outgoing!=incoming and sold==original['holdings'][outgoing]>0 and original['holdings'].get(incoming,0)==0,'One full old sell and new buy')
   signed={key:0 for key in sorted(ids)};signed[outgoing]=-sold;signed[incoming]=q
   exact(task['signed_trade_quantities'],signed,'Full signed vector');exact(task['proposed_holdings'],{key:original['holdings'].get(key,0)+signed[key]for key in sorted(ids)},'All remaining holdings frozen')
   require(selected['evaluation']['feasible']is True and selected['evaluation']['status']=='FEASIBLE','Audited feasible selection')
   expected=deepcopy(selected['evaluation']);status='BLOCKED_TEMPLATE_PRICE_GAP'if gaps else'NEW_SIGNED_PATH_REQUIRED'
   if not gaps:
    request=dict(initial=deepcopy(initial),transaction_cost_bps=deepcopy(template['transaction_cost_bps']),sessions=[])
    for j,session in enumerate(sessions):request['sessions'].append(dict(session=session['session'],open_prices=deepcopy(session['open_prices']),close_prices=deepcopy(session['close_prices']),cash_injection_usd=deepcopy(session['cash_injection_usd']),trade_shares=deepcopy(signed)if j==0 else{}))
  counts[status]+=1
  rows.append(dict(scenario_index=i,scenario_id=sid,status=status,accounting_request=request,expected_first_trade=expected,selection_row=deepcopy(chosen),prepared_case=deepcopy(case),old_paired_evidence=deepcopy(old),template_gaps=gaps,original_gaps=deepcopy(original.get('gaps',[])),selection_reference=dict(source_references['selection'],json_pointer=f'/selection/document/rows/{i}'),control_path_reference=dict(source_references['old_paired'],json_pointer=f'/rows/{i}/paths/same_flow_zero_trade_control'),reused_candidate_path_reference=None,**flags()))
 require(coordinates=={(lane,d,e,a)for lane in LANES for d,e,_ in CLOCKS for a in('1000','10000')},'Full forty domain')
 expected=dict(schema='SINGLE_REPLACEMENT_SIGNED_PATH_REQUESTS_V1',rows=rows,scenario_count=40,status_counts=counts,new_account_request_count=counts['NEW_SIGNED_PATH_REQUIRED'],input_references=deepcopy(source_references),source_hash_claims=claims,no_feasible_is_cash_return=False,source_reference_semantics='DECLARATIONS_ONLY_EXTERNAL_READER_MUST_AUTHENTICATE_FULL_SELECTION',policy_asymmetry='CONDITIONAL_EXECUTION_OPEN_SINGLE_REPLACEMENT_ONE_OFF;CONTROL_SAVED_REFERENCE_ONLY;NO_PRIOR_CLOSE_EXECUTABILITY_OR_CROSS_FAMILY_WINNER_CLAIM',**flags())
 exact(saved_requests,expected,'Independent complete forty request reconstruction')
 return expected

def inspect_first_trade(pure_row,result):
 first=result['rows'][0];selected=pure_row['selection_row']['selected'];evaluation=selected['evaluation'];task=selected['task']
 for result_key,evaluation_key in (('gross_buy_usd','gross_buy_usd'),('gross_sell_usd','gross_sell_usd'),('fees_usd','total_fee_usd'),('cash_after_usd','cash_after_usd'),('post_trade_open_equity_usd','equity_after_usd')):
  require(Fraction(first[result_key])==Fraction(evaluation[evaluation_key]),'Original selected Open evaluation '+evaluation_key)
 exact(first['holdings_after'],task['proposed_holdings'],'Original complete selected positions');exact(first['trade_shares'],task['signed_trade_quantities'],'Original selected signed quantities')
 require(Fraction(first['post_trade_open_equity_usd'])-Fraction(first['post_flow_pre_fee_open_equity_usd'])==-Fraction(first['fees_usd']),'Open loss is bilateral fees, not daily PnL')

# Fixed code identity is filled only after the independent publisher review.
from pathlib import Path
from types import ModuleType
import os,sys
ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED=sha256(SOURCE.read_bytes()).hexdigest()
PUBLISHER_SHA='e02ae44a4862dc538405933aa7ef89af4a10b66b2e9f5224d969e29465677ef7'
INSPECTOR_PATH=ROOT/'backtest/ndx_signed_cash_flow_account_inspection_research.py'
INSPECTOR_SHA='49697feb352c70c20dd344c81bcf62131a7d0041d2fdcfad2cf60cd9fef0dcbd'
OUTPUT=ROOT/'data/cache/research/single_replacement_signed_paths_independent_readback_20261003_v1'
REPORT_FALSE=dict.fromkeys(('account_called','request_producer_called','selector_called','risk_recomputed','control_reexecuted','point_in_time_verified','promotion_allowed','orders_executed','full_transitive_original_paired_sources_reaudited','automatic_retry_allowed'),False)

def external_reference(r):
 require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path'] and type(r['sha256'])is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Explicit reference before IO')

def save(name,value):
 raw=encode(value);path=OUTPUT/name
 with path.open('xb')as f:f.write(raw);f.flush();os.fsync(f.fileno())
 require(path.read_bytes()==raw,'Saved readback bytes')
 return dict(path=str(path),sha256=sha256(raw).hexdigest())

def load_adapter():
 require(type(PUBLISHER_SHA)is str and len(PUBLISHER_SHA)==64,'Pending frozen shared parser')
 if str(ROOT)not in sys.path:sys.path.insert(0,str(ROOT))
 from scripts import ndx_single_replacement_signed_paths_20261003 as source
 require(source.LOADED==PUBLISHER_SHA and source.filehash(source.SOURCE)==PUBLISHER_SHA,'Frozen shared source adapter')
 return source

def stream_original_paired(source,c):
 r=c['refs']['paired'];old=[];locations=[]
 with Path(r['path']).open('rb')as f:
  stream=c['modules']['stream'].JsonRowsStream(f,max_row_bytes=8*1024**2)
  for token in stream:
   require(type(token['row_index'])is int and token['row_index']==len(old)<40,'Original full row sequence')
   old.append(token['value']);locations.append(dict(source_reference=r,**{k:token[k]for k in ('row_index','byte_start','byte_stop','sha256')}))
  summary=stream.summary
 require(summary['complete_document_consumed']is True and len(old)==40 and summary['sha256']==r['sha256'],'All original paired bytes and EOF')
 metadata=summary['metadata'];require(metadata['schema']=='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1','Original paired schema')
 exact(metadata['scenario_count'],40,'Original forty');exact(metadata['new_account_path_count'],80,'Original eighty')
 exact(metadata['source_hashes'],c['docs']['paired_publication']['source_hashes'],'Original declarations retained')
 source.merge(c['sources'],r)
 return old,locations,summary

def inspect_selected_raw_sources(source,c,requests):
 """Consume selected RAW_RETURNED bytes only, not a search or new evaluation."""
 audit=c['docs']['selection_audit'];checked=set()
 for row in requests['rows']:
  selected=row['selection_row']['selected']
  if selected is None:continue
  sr=selected['source_reference'];jr=sr['journal_reference'];loc=sr['record_locator'];external_reference(jr)
  require(audit['source_hashes'].get(jr['path'])==jr['sha256'],'Journal identity consumed by selection audit')
  require(sr['json_pointer']=='/body/payload/result' and loc['stage']=='RAW_RETURNED','Exact selected original raw role')
  require(all(type(loc[k])is int and loc[k]>=0 for k in ('sequence','byte_start','byte_stop','global_ordinal')) and loc['byte_stop']>loc['byte_start'],'Typed journal span')
  require(loc['global_ordinal']==selected['global_ordinal'],'Selected raw global index')
  if jr['path']not in checked:
   require(source.filehash(jr['path'])==jr['sha256'],'Selected journal original complete byte hash');source.merge(c['sources'],jr);checked.add(jr['path'])
   parent=Path(jr['path']).parent;c['dirs'][str(parent)]=source.inventory(parent)
  with Path(jr['path']).open('rb')as f:f.seek(loc['byte_start']);raw=f.read(loc['byte_stop']-loc['byte_start'])
  require(len(raw)==loc['byte_stop']-loc['byte_start'] and raw.endswith(b'\n'),'Actual selected complete raw span')
  record=source.decode(raw);body=record['body']
  require(digest(body)==record['record_sha256']==loc['record_sha256'] and type(body['sequence'])is int and body['sequence']==loc['sequence'],'Actual record canonical body hash/sequence')
  require(body['payload']['returned']is True and body['payload']['error']is None,'Selected raw returned fact')
  require(body['stage']=='RAW_RETURNED' and type(body['global_ordinal'])is int and body['global_ordinal']==selected['global_ordinal'] and body['task_id']==selected['task']['task_id'],'Selected raw record identity')
  exact(body['payload']['result'],selected['evaluation'],'Selected actual saved evaluation')


def readback(*,registration_reference=None,result_reference=None,publication_reference=None,execute=False):
 require(execute is True,'Explicit independent readback')
 for r in (registration_reference,result_reference,publication_reference):external_reference(r)
 source=load_adapter();c=source.load_inputs(registration_reference,compile_numerical=False)
 for ref,name in ((result_reference,'result.json'),(publication_reference,'publication.json')):require(ref['path']==str(source.OUTPUT/name),'Fixed new signed account namespace')
 base_before_stream=dict(c['sources']);old,locations,summary=stream_original_paired(source,c);base=dict(c['sources'])
 consumed={};refs=[]
 def get(r,name=None):
  external_reference(r)
  if name is not None:require(r['path']==str(source.OUTPUT/name),'Exact output role path')
  value=source.decode(source.take(r,consumed));refs.append(r);return value
 result=get(result_reference,'result.json');pub=get(publication_reference,'publication.json')
 require(result['schema']=='SINGLE_REPLACEMENT_SIGNED_PATHS_RESULT_V1' and result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK' and result['failure']is None,'Only completed full source result can PASS')
 require(pub['schema']=='SINGLE_REPLACEMENT_SIGNED_PATHS_PUBLICATION_V1' and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_SOURCE_READBACK','Complete publication')
 for obj in (result,pub):
  source.flags(obj);exact(obj['source_hashes'],base,'Exact publication source closure');exact(obj['input_references'],c['refs'],'Thirteen original roles');exact(obj['registration_reference'],registration_reference,'Source registration')
 exact(pub['result_reference'],result_reference,'Published result bytes')
 for key in ('requests_index_reference','raw_requests_reference'):exact(pub[key],result[key],'Root artifact linking')
 started=get(pub['started_reference'],'started.json');source.flags(started)
 require(started['schema']=='SINGLE_REPLACEMENT_SIGNED_PATHS_STARTED_V1' and started['paired_eof_required_before_dispatch']is True and started['paired_readback_evidence_scope']=='WHOLE_MARKDOWN_REPORT','Original START scope')
 exact(started['source_hashes'],base_before_stream,'Original pre-EOF source identities');exact(started['input_references'],c['refs'],'START roles');exact(started['registration_reference'],registration_reference,'START registration')
 index=get(result['requests_index_reference'],'requests_index.json');source.flags(index)
 require(index['schema']=='SINGLE_REPLACEMENT_SIGNED_PATH_REQUESTS_INDEX_V1','Full request index')
 for obj in (index,result):exact(obj['scenario_count'],40,'Typed forty denominator');require(type(obj['rows'])is list and len(obj['rows'])==40,'All forty slots')
 exact(index['source_hashes'],base,'Index source closure');exact(index['input_references'],c['refs'],'Index sources');exact(index['registration_reference'],registration_reference,'Index registration');exact(index['raw_requests_reference'],result['raw_requests_reference'],'Raw request role');exact(index['paired_stream_summary'],summary,'Full paired EOF certificate')
 raw_requests=get(result['raw_requests_reference'],'raw_requests.json')
 exact(sorted(raw_requests),sorted(('call_invoked','call_count','returned','result','error','result_preserved_as_json')),'Complete original request return shape')
 require(raw_requests['call_invoked']is True and type(raw_requests['call_count'])is int and raw_requests['call_count']==1 and raw_requests['returned']is True and raw_requests['result_preserved_as_json']is True and raw_requests['error']is None,'Original complete request return')
 args=dict(prepared=c['docs']['prepared']['preparation'],selection=c['docs']['selection']['selection'],old_paired_rows=old,source_references={k:c['refs'][v]for k,v in [('prepared','prepared'),('selection','selection'),('selection_audit','selection_audit'),('old_paired','paired')]})
 require(not OUTPUT.exists(),'Create-only independent attempt');OUTPUT.mkdir(parents=True,exist_ok=False);saved=[];reports=[]
 try:
  saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_SIGNED_PATHS_READBACK_STARTED_V1',registration_reference=registration_reference,result_reference=result_reference,publication_reference=publication_reference,**REPORT_FALSE)))
  expected=inspect_requests(saved_requests=raw_requests['result'],**args);exact(index['status_counts'],expected['status_counts'],'Full request status counts')
  inspect_selected_raw_sources(source,c,expected)
  code=INSPECTOR_PATH.read_bytes();require(sha256(code).hexdigest()==INSPECTOR_SHA,'Exact independent arithmetic bytes')
  inspector=ModuleType('_independent_signed_ledger');inspector.__file__=str(INSPECTOR_PATH);exec(compile(code,str(INSPECTOR_PATH),'exec'),inspector.__dict__)
  expected_outcomes=dict.fromkeys(('ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK','NO_FEASIBLE','BLOCKED_TEMPLATE_PRICE_GAP','ACCOUNT_EXCEPTION','VALIDATION_FAILURE','UNRESOLVED_DISPATCH','UNDISPATCHED'),0)
  expected_files={'started.json','raw_requests.json','requests_index.json','result.json','publication.json'}
  for i,(row,entry,initial_entry)in enumerate(zip(expected['rows'],result['rows'],index['rows'])):
   folder=f'scenario-{i:02d}';request=get(entry['request_reference'],folder+'/request.json');source.flags(request)
   wanted=dict(schema='SINGLE_REPLACEMENT_SIGNED_PATH_REQUEST_V1',scenario_index=i,scenario_id=row['scenario_id'],prepared_request=row,paired_row_byte_reference=locations[i],raw_requests_reference=result['raw_requests_reference'],input_references=c['refs'],source_hashes=base,**source.FLAGS)
   exact(request,wanted,'Full case source request and actual byte locator')
   basic=dict(scenario_index=i,scenario_id=row['scenario_id'],input_status=row['status'],request_reference=entry['request_reference'],outcome=row['status']if row['status']!='NEW_SIGNED_PATH_REQUIRED'else'UNDISPATCHED',account_call_invoked=False,account_call_returned=False,control_reference=row['control_path_reference'])
   exact(initial_entry,basic,'Original index slot');expected_files.add(folder+'/request.json')
   if row['status']!='NEW_SIGNED_PATH_REQUIRED':
    exact(entry,basic,'Blocked/absent has no account or cash path');expected_outcomes[row['status']]+=1;reports.append(dict(scenario_index=i,scenario_id=row['scenario_id'],status=row['status'],account_inspection=None));continue
   require(entry['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK' and entry['account_call_invoked']is True and entry['account_call_returned']is True,'Completed signed account facts')
   cs=get(entry['started_reference'],folder+'/started.json');raw=get(entry['raw_reference'],folder+'/raw_result.json');inspection=get(entry['inspection_reference'],folder+'/inspection.json');post=get(entry['postcheck_reference'],folder+'/postcheck.json')
   numerical=digest(dict(request=row['accounting_request'],task_id=row['selection_row']['selected']['task']['task_id'],account_source=source.ref(source.ROOT/source.CODE['account'][0],source.CODE['account'][1])))
   exact(cs,dict(schema='SINGLE_REPLACEMENT_SIGNED_PATH_STARTED_V1',scenario_index=i,scenario_id=row['scenario_id'],request_reference=entry['request_reference'],registration_reference=registration_reference,numerical_id=numerical,**source.FLAGS),'Started numerical identity')
   exact(sorted(raw),sorted(('call_invoked','call_count','returned','result','error','result_preserved_as_json')),'Successful raw full shape')
   require(raw['call_invoked']is True and type(raw['call_count'])is int and raw['call_count']==1 and raw['returned']is True and raw['error']is None and raw['result_preserved_as_json']is True,'Original returned account object')
   actual_inspection=inspector.inspect_saved_signed_account(**row['accounting_request'],saved_result=raw['result']);exact(inspection,actual_inspection,'Independent saved ledger check');inspect_first_trade(row,raw['result'])
   exact(post,dict(schema='SINGLE_REPLACEMENT_SIGNED_PATH_POSTCHECK_V1',scenario_index=i,scenario_id=row['scenario_id'],outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK',request_reference=entry['request_reference'],started_reference=entry['started_reference'],raw_reference=entry['raw_reference'],inspection_reference=entry['inspection_reference'],validation_error=None,**source.FLAGS),'Exact successful postcheck')
   wanted_entry=dict(basic,outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK',account_call_invoked=True,account_call_returned=True,**{k:entry[k]for k in ('started_reference','raw_reference','inspection_reference','postcheck_reference')});exact(entry,wanted_entry,'Complete successful slot identity')
   expected_files.update(folder+'/'+name for name in ('started.json','raw_result.json','inspection.json','postcheck.json'));expected_outcomes[entry['outcome']]+=1
   reports.append(dict(scenario_index=i,scenario_id=row['scenario_id'],status='PASS',raw_reference=entry['raw_reference'],inspection=actual_inspection))
  exact(result['outcome_counts'],expected_outcomes,'Exact typed complete outcome partition');exact(result['original_paired_source_claims_preserved'],c['docs']['paired_publication']['source_hashes'],'Old declared references remain unverified')
  def guard():
   source.guard(c);require(sha256(SOURCE.read_bytes()).hexdigest()==LOADED and sha256(INSPECTOR_PATH.read_bytes()).hexdigest()==INSPECTOR_SHA,'Reader and numerical source bytes')
   require(not (source.OUTPUT/'failure.json').exists(),'Failed producer namespace')
   actual={p.relative_to(source.OUTPUT).as_posix()for p in source.OUTPUT.rglob('*')if p.is_file()};exact(sorted(actual),sorted(expected_files),'Exact complete producer inventory')
   directories=sorted(p.relative_to(source.OUTPUT).as_posix()for p in source.OUTPUT.rglob('*')if p.is_dir());exact(directories,[f'scenario-{i:02d}'for i in range(40)],'Only forty case directories')
   for path,h in consumed.items():require(source.filehash(path)==h,'Original producer bytes remain unchanged')
  guard()
  source_hashes=dict(c['sources']);source_hashes.update(consumed);source_hashes[str(SOURCE)]=LOADED;source_hashes[str(INSPECTOR_PATH)]=INSPECTOR_SHA
  saved.append(save('independent_readback.json',dict(schema='SINGLE_REPLACEMENT_SIGNED_PATHS_INDEPENDENT_READBACK_V1',status='PASS',registration_reference=registration_reference,result_reference=result_reference,publication_reference=publication_reference,reader_sha256=LOADED,source_hashes=source_hashes,scenario_count=40,account_checked_count=expected_outcomes['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],outcome_counts=expected_outcomes,rows=reports,shared_source_parser_reference=source.ref(source.SOURCE,PUBLISHER_SHA),scope='INDEPENDENT_FULL_REQUEST_PROJECTION_AND_SIGNED_LEDGER_SHARED_AUTHENTICATED_SOURCE_AND_JSON_ROWS_PARSER',source_bytes_authenticated=True,all_paired_rows_and_eof_verified=True,original_paired_declared_parent_sources=c['docs']['paired_publication']['source_hashes'],**REPORT_FALSE)))
  guard()
  for r in saved:require(source.filehash(r['path'])==r['sha256'],'Final reader output bytes')
  exact(sorted(p.name for p in OUTPUT.iterdir()),['independent_readback.json','started.json'],'Exact independent readback namespace')
  return saved[-1]
 except BaseException as e:
  save('failure.json',dict(schema='SINGLE_REPLACEMENT_SIGNED_PATHS_READBACK_FAILURE_V1',error=source.diagnostic(e),completed_case_count=len(reports),completed_case_inspections=reports,saved_references=saved,registration_reference=registration_reference,result_reference=result_reference,publication_reference=publication_reference,**REPORT_FALSE));raise

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser()
 parser.add_argument('--execute',action='store_true')
 for role in ('registration','result','publication'):
  parser.add_argument('--'+role);parser.add_argument('--'+role+'-sha')
 options=parser.parse_args()
 parameters={role+'_reference':dict(path=getattr(options,role),sha256=getattr(options,role+'_sha'))for role in ('registration','result','publication')}
 print(json.dumps(readback(**parameters,execute=options.execute)))
