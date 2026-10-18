"""Create-only source-bound single-replacement domain; no point evaluation."""
import argparse,hashlib,json,os,shutil,types
from pathlib import Path
SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/single_replacement_preparation_20261003_v1'
BOUND={
 'policy':('research_contracts/single_replacement_cash_action_policy_20261003_v1.json','0a654c265f71b836b2fae3aff85dac0cb63da172a262e5322a1510e75c83de2c'),
 'inputs':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json','1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'),
 'input_publication':('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json','54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'),
 'input_producer':('scripts/ndx_remaining_standard_cash_inputs_20261002.py','6e262a1ec7707be706afa0e258b1087c68bb33823bb3b4cdabeb40cad8540ac8'),
 'inventory':('data/cache/research/conditional_new_cash_inventory_20260925_v2/inventory.json','f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'),
 'inventory_publication':('data/cache/research/conditional_new_cash_inventory_20260925_v2/publication.json','e18344ff2535d4cea735d57e5d1c5cd99e60da98c8990040055b2bab48aa53a7'),
 'scenarios':('data/cache/research/standard_cash_scenarios_20261002_v1/scenarios.json','5100a90a6b862492fadd2bd38f6596195cb6aba9dc08c37cb25552728469c5bf'),
 'historical_input_readback_note':('DYNAMIC_CASH_REPAIR_AND_REMAINING_INPUT_RESULT_20261002.md','29ba807e2f52838b6fc5ff19a95f4111de77a9c54dfb30908f6639d80f243524'),
 'historical_topup_audit_note':('DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md','40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec'),
 'historical_topup_reader':('scripts/ndx_old_holding_topup_independent_review_20261002.py','3bdb785c64d4ea5f7bcc8b97c8b246b7102766f4202ad1465d9feab4f29e5fe2'),
 'core':('backtest/ndx_single_replacement_domain_research.py','8df88963158ba8d3787c61705ca04f4a41ab481759701a291ccdbe75ae7505d7'),
 'risk_semantics':('backtest/ndx_conditional_new_cash_fork_research.py','5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
ACCOUNT_CLAIM=('data/cache/research/return_six_period_conditional_execution_20260923_v2/account.json','ed69a9de921d94f9a186d59a6ef16c09f46544ede388e4fff271c10a77f433e2')
FLAGS=dict.fromkeys(('point_in_time_verified','promotion_allowed','orders_executed','account_executed','fit_executed','risk_evaluated','point_evaluations_performed','economic_winner_selected','full_transitive_source_closure_reverified','old_audit_reexecuted','old_search_reexecuted','execution_authorized','future_independent_oos'),False)
PARENT_FLAGS=('cash_fork_called','search_called','account_rerun','fit_called','old_audit_rerun','point_in_time_verified','promotion_allowed','orders_executed','fork_executable','full_transitive_source_closure_reverified')
JSON_ROLES={'policy','inputs','input_publication','inventory','inventory_publication','scenarios'}
def require(ok,msg):
 if not ok:raise ValueError(msg)
def enc(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def refs():return {k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in BOUND.items()}
def inventories(r):
 return {str(Path(r['inputs']['path']).parent):{'inputs.json','publication.json'},str(Path(r['inventory']['path']).parent):{'inventory.json','publication.json'},str(Path(r['scenarios']['path']).parent):{'scenarios.json'}}
def guard(sources,r):
 require(sources.get(str(SOURCE))==LOADED,'Loaded publisher identity')
 for p,h in sources.items():require(sha(Path(p).read_bytes())==h,'Source drift')
 for p,names in inventories(r).items():require({x.name for x in Path(p).iterdir()}==names,'Exact parent namespace')
def resource(reserve=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+reserve,'Five GiB reserve before dispatch/write')
def save(name,value,emergency=False):
 b=enc(value)
 if not emergency:resource(len(b))
 p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved bytes');return dict(path=str(p),sha256=sha(b))
def project(d,r):
 p=d['policy'];x=d['inputs'];pub=d['input_publication']
 require(p['schema']=='SINGLE_REPLACEMENT_CASH_ACTION_POLICY_REGISTRATION_V1','Policy schema')
 require(p['status']=='ECONOMIC_DOMAIN_POLICY_FIXED_BEFORE_NEW_PREPARATION_NOT_EXECUTION_PERMISSION','Policy role')
 for k in ('source_preparation_authorized','evaluation_authorized','execution_authorized','point_in_time_verified','future_independent_oos','quantity_caps_computed','risk_evaluated'):require(p[k] is False,'Policy authority declaration')
 exact(p['original_inputs_reference'],r['inputs'],'Policy inputs');exact(p['domain_core_reference'],r['core'],'Policy core')
 require(x['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and type(x['scenario_count']) is int and x['scenario_count']==len(x['rows'])==64,'Original full64')
 require(pub['schema']=='REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1' and pub['status']=='INPUTS_ONLY_NOT_EXECUTED','Published input role')
 exact(pub['input_reference'],r['inputs'],'Parent published ref');exact(pub['source_hashes'],x['source_hashes'],'Parent source declarations')
 ip=d['inventory_publication'];require(ip['schema']=='CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1' and ip['status']=='SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY' and ip['fork_executed'] is False,'Inventory publication role')
 exact(ip['inventory_reference'],r['inventory'],'Inventory published reference')
 expected={r[k]['path']:r[k]['sha256'] for k in ('inventory','inventory_publication','scenarios','input_producer')}
 expected[str(ROOT/ACCOUNT_CLAIM[0])]=ACCOUNT_CLAIM[1]
 exact(x['source_hashes'],expected,'Fixed five original source declarations')
 for obj in (x,pub):
  for k in PARENT_FLAGS:require(obj[k] is False,'Conditional parent authority')
 rows=[dict(input_row=v,input_reference={**r['inputs'],'json_pointer':f'/rows/{i}'}) for i,v in enumerate(x['rows']) if v['branch_role']=='MAIN_LANE']
 require(len(rows)==40 and len({v['input_row']['scenario_id'] for v in rows})==40,'Complete main40')
 exact([v['input_row']['scenario_id'] for v in rows],p['action_policy']['expected_scenario_ids'],'Original scenario order')
 exact([dict(scenario_id=v['input_row']['scenario_id'],reference=v['input_reference']) for v in rows],p['original_row_references'],'Policy row coordinates')
 for item in rows:
  row=item['input_row'];exact(row['risk_parameters'],p['risk_policy']['original_parameters'],'Original five risk parameters')
  for key,role,body in [('scenario_reference','scenarios','original_scenario'),('inventory_row_reference','inventory','original_inventory_row')]:
   ref=row[key];pointer=ref['json_pointer'];require(pointer.startswith('/rows/') and pointer[6:].isdigit() and str(int(pointer[6:]))==pointer[6:],'Canonical row locator')
   exact({k:v for k,v in ref.items() if k!='json_pointer'},r[role],'Original row parent');exact(row[body],d[role]['rows'][int(pointer[6:])],'Complete original row copy')
 return rows,{**p['action_policy'],'domain_core_reference':r['core'],'action_contract_reference':r['policy']}
def load_inputs():
 r=refs();require(all(type(v['sha256']) is str and len(v['sha256'])==64 for v in r.values()),'Pending anchors')
 sources={str(SOURCE):LOADED};docs={};blobs={}
 for k,v in r.items():
  b=Path(v['path']).read_bytes();require(sha(b)==v['sha256'],'Same consumed bytes');sources[v['path']]=v['sha256'];blobs[k]=b
  if k in JSON_ROLES:docs[k]=decode(b)
 rows,contract=project(docs,r)
 core=types.ModuleType('_private_single_replacement_domain');exec(compile(blobs['core'],r['core']['path'],'exec'),core.__dict__)
 guard(sources,r);return docs,r,sources,rows,contract,core
def run(*,execute=False):
 require(execute is True,'Explicit preparation invocation');require(not OUTPUT.exists(),'No overwrite or retry')
 d,r,s,rows,c,core=load_inputs();resource();OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
 try:
  saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_STARTED_V1',input_references=r,source_hashes=s,**FLAGS)))
  guard(s,r);resource()
  try:raw=core.prepare_single_replacement_domain(rows,c)
  except BaseException as e:
   saved.append(save('raw_preparation.json',dict(schema='SINGLE_REPLACEMENT_RAW_PREPARATION_V1',returned=False,result=None,error_type=type(e).__name__,error=str(e),**FLAGS),True));raise
  try:enc(raw)
  except BaseException as serialization_error:
   try:representation=repr(raw)
   except BaseException as repr_error:representation='REPR_FAILED: '+type(repr_error).__name__
   saved.append(save('raw_preparation.json',dict(schema='SINGLE_REPLACEMENT_RAW_PREPARATION_V1',returned=True,result=None,result_preserved_as_json=False,result_representation=representation,serialization_error_type=type(serialization_error).__name__,**FLAGS),True));raise ValueError('Returned result is not JSON')
  saved.append(save('raw_preparation.json',dict(schema='SINGLE_REPLACEMENT_RAW_PREPARATION_V1',returned=True,result=raw,result_preserved_as_json=True,**FLAGS),True))
  guard(s,r);require(type(raw) is dict and set(raw)=={'document','content_sha256'},'Returned preparation shape');require(sha(json.dumps(raw['document'],sort_keys=True,separators=(',',':'),allow_nan=False).encode())==raw['content_sha256'],'Content integrity')
  body=raw['document'];require(type(body['scenario_count']) is int and body['scenario_count']==40,'Full40 result');exact(body['action_contract'],c,'Returned policy')
  for i,case in enumerate(body['cases']):exact(case['identity']['original_input_row'],rows[i]['input_row'],'Returned full original row');exact(case['identity']['input_reference'],rows[i]['input_reference'],'Returned row ref')
  require(len(body['cases'])==40 and body['integer_count']+body['structurally_excluded_integer_count']==body['financial_integer_count_before_issuer'],'Full denominator partition')
  for k in core.FLAGS:require(body[k] is False,'Returned authority')
  out=save('preparation.json',dict(schema='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1',preparation=raw,raw_preparation_reference=saved[-1],input_references=r,source_hashes=s,consumed_authenticated_sources=s,declared_parent_sources=d['inputs']['source_hashes'],old_holdings_reconstructed=False,historical_audit_role='SAVED_MARKDOWN_AND_CODE_REFERENCES_NOT_NEW_MACHINE_ATTESTATION',source_scope='DIRECT_INPUT_POLICY_CORE_AND_ORIGINAL_ROW_PARENTS_ONLY',**FLAGS));saved.append(out)
  guard(s,r);saved.append(save('publication.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_PUBLICATION_V1',status='PUBLISHED_UNEVALUATED_DOMAIN_ONLY',preparation_reference=out,raw_preparation_reference=saved[1],source_hashes=s,**FLAGS)))
  guard(s,r)
  for v in saved:require(sha(Path(v['path']).read_bytes())==v['sha256'],'Final output drift')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','raw_preparation.json','preparation.json','publication.json'},'Exact output namespace')
  return out
 except BaseException as e:
  save('failure.json',dict(status='FAILED_DO_NOT_RETRY_OR_CONSUME',error_type=type(e).__name__,error=str(e),saved_references=saved,**FLAGS),True);raise
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))
