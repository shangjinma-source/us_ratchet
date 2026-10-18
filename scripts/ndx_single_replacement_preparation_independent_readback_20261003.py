"""Independent saved single-replacement domain/source inspection; no evaluator calls."""
import hashlib
import json
import os
from fractions import Fraction
from decimal import Decimal
from pathlib import Path

SOURCE=Path(__file__).resolve()
ROOT=SOURCE.parents[1]
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/single_replacement_preparation_20261003_v1'
OUTPUT=ROOT/'data/cache/research/single_replacement_preparation_independent_readback_20261003_v1'
PREPARATION_SHA='510a150834c82a9d68b2979d43c57c808d47800d0f1fc7258896fe7010ecedf6'
PUBLICATION_SHA='e7a16bafeb236dd3e023c6c8f983041ac7a4236fb898124c20142d9bf4484c4c'
PRODUCER=ROOT/'scripts/ndx_single_replacement_preparation_20261003.py'
PRODUCER_SHA='b582b5754d30e51a29bb00ed3e201830f2f65208f336afc436b518e65073c38a'
BOUND={'policy': ('research_contracts/single_replacement_cash_action_policy_20261003_v1.json', '0a654c265f71b836b2fae3aff85dac0cb63da172a262e5322a1510e75c83de2c'), 'inputs': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/inputs.json', '1143482cc4d610c6bd3976f846730b98ef1f11148e3b1f5eb008135a5faea1e5'), 'input_publication': ('data/cache/research/remaining_standard_cash_inputs_20261002_v1/publication.json', '54d6f6d2771dc4caf85c07b2b8a28e33e1a50a3aace1df99308c012ae1ad5dc1'), 'input_producer': ('scripts/ndx_remaining_standard_cash_inputs_20261002.py', '6e262a1ec7707be706afa0e258b1087c68bb33823bb3b4cdabeb40cad8540ac8'), 'inventory': ('data/cache/research/conditional_new_cash_inventory_20260925_v2/inventory.json', 'f8b88fc72c6a3906440d4ddc83b5614e2a0a009a8843603a6028b713f62cb626'), 'inventory_publication': ('data/cache/research/conditional_new_cash_inventory_20260925_v2/publication.json', 'e18344ff2535d4cea735d57e5d1c5cd99e60da98c8990040055b2bab48aa53a7'), 'scenarios': ('data/cache/research/standard_cash_scenarios_20261002_v1/scenarios.json', '5100a90a6b862492fadd2bd38f6596195cb6aba9dc08c37cb25552728469c5bf'), 'historical_input_readback_note': ('DYNAMIC_CASH_REPAIR_AND_REMAINING_INPUT_RESULT_20261002.md', '29ba807e2f52838b6fc5ff19a95f4111de77a9c54dfb30908f6639d80f243524'), 'historical_topup_audit_note': ('DYNAMIC_OLD_HOLDING_TOPUP_INDEPENDENT_READBACK_20261002.md', '40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec'), 'historical_topup_reader': ('scripts/ndx_old_holding_topup_independent_review_20261002.py', '3bdb785c64d4ea5f7bcc8b97c8b246b7102766f4202ad1465d9feab4f29e5fe2'), 'core': ('backtest/ndx_single_replacement_domain_research.py', '8df88963158ba8d3787c61705ca04f4a41ab481759701a291ccdbe75ae7505d7'), 'risk_semantics': ('backtest/ndx_conditional_new_cash_fork_research.py', '5bb17d621b42707cfe312676279d59b565c3e97900bf3bdd6f9335df65aa0c5f')}
ACCOUNT_CLAIM=('data/cache/research/return_six_period_conditional_execution_20260923_v2/account.json', 'ed69a9de921d94f9a186d59a6ef16c09f46544ede388e4fff271c10a77f433e2')


FLAGS=('point_in_time_verified','promotion_allowed','orders_executed','account_executed','fit_executed','risk_evaluated','point_evaluations_performed','economic_winner_selected','full_transitive_source_closure_reverified','old_audit_reexecuted','old_search_reexecuted','execution_authorized','future_independent_oos')
PARENT_FLAGS=('cash_fork_called','search_called','account_rerun','fit_called','old_audit_rerun','point_in_time_verified','promotion_allowed','orders_executed','fork_executable','full_transitive_source_closure_reverified')
DOMAIN_FLAGS=('source_bytes_authenticated','point_in_time_verified','formal_eligibility_verified','identity_gaps_resolved','risk_evaluated','financial_feasibility_evaluated','economic_winner_selected','global_optimality_claimed','orders_executed','account_executed','fit_executed','old_evaluations_repeated','target_weights_changed','future_returns_used','repair_performed','domain_registered_for_execution')
SEMANTICS=dict(schema='SINGLE_REPLACEMENT_ACTION_CONTRACT_V1',rule='SELL_ALL_ONE_POSITIVE_OLD_BUY_ONE_NEW_INTEGER_V1',scope='SAVED_PRICE_UNION_CONDITIONAL_MIGRATION',information_set='SAVED_EXECUTION_OPEN_CONDITIONAL_NOT_PRIOR_CLOSE',outgoing_policy='ALL_POSITIVE_OLD_HOLDINGS',incoming_policy='ALLOWED_TARGET_MINUS_POSITIVE_OLD',other_holdings_policy='UNCHANGED_INCLUDING_ZERO_KEYS',quantity_policy='ALL_INTEGERS_ONE_THROUGH_EXACT_FINANCIAL_CAP',issuer_policy='REMAINING_POSITIVE_OLD_PLUS_INCOMING_UNIQUE',order='ORIGINAL_SCENARIO_ORDER_THEN_OUT_SID_IN_SID_Q_ASCENDING',fee_policy='SELL_AND_BUY_NOTIONAL_TIMES_SAME_BPS',transaction_cost_bps='10',minimum_cash_buffer_usd='100',ranking_policy='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_PAIR_Q',cross_family_ranking_registered=False,risk_evaluation_policy='UNCHANGED_FIVE_RISKS_NOT_EVALUATED_BY_PREPARER')

def require(ok,message):
 if not ok:raise ValueError(message)

def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def digest(x):return hashlib.sha256(encode(x)).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def flags(x,keys=FLAGS):require(all(x[k] is False for k in keys),'Strict false authority')
def reference(r):
 require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and Path(r['path']).is_absolute(),'Exact absolute reference')
 require(type(r['sha256']) is str and len(r['sha256'])==64 and set(r['sha256'])<=set('0123456789abcdef'),'Immutable SHA256 anchor')
 return r
def decode(b):
 def unique(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=unique,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))
def rational(text):
 require(type(text) is str and text and text.strip()==text,'Original decimal text')
 n=Decimal(text);require(n.is_finite(),'Finite original number')
 return Fraction(n)
def location(ref,parent,rows):
 require(type(ref) is dict and set(ref)=={'path','sha256','json_pointer'},'Original row reference')
 exact({k:ref[k] for k in ('path','sha256')},parent,'Original row parent')
 token=ref['json_pointer'];require(type(token) is str and token.startswith('/rows/'),'Original row location')
 value=token[6:];require(value.isdigit() and str(int(value))==value and int(value)<len(rows),'Canonical row offset')
 return rows[int(value)]

def inspect_domain(*,documents,references,saved_preparation):
 """Independent exact rational domain oracle; never enumerates or evaluates q."""
 d,r=documents,references;p=d['policy'];x=d['inputs'];pub=d['input_publication'];ip=d['inventory_publication']
 require(p['schema']=='SINGLE_REPLACEMENT_CASH_ACTION_POLICY_REGISTRATION_V1' and p['status']=='ECONOMIC_DOMAIN_POLICY_FIXED_BEFORE_NEW_PREPARATION_NOT_EXECUTION_PERMISSION','Registered policy role')
 for key in ('source_preparation_authorized','evaluation_authorized','execution_authorized','point_in_time_verified','future_independent_oos','quantity_caps_computed','risk_evaluated'):require(p[key] is False,'Policy authority')
 exact(p['domain_core_reference'],r['core'],'Original core role');exact(p['original_inputs_reference'],r['inputs'],'Policy original inputs')
 require(x['schema']=='REMAINING_STANDARD_CASH_INPUTS_V1' and type(x['scenario_count']) is int and x['scenario_count']==64==len(x['rows']),'Original64 retained')
 require(pub['schema']=='REMAINING_STANDARD_CASH_INPUTS_PUBLICATION_V1' and pub['status']=='INPUTS_ONLY_NOT_EXECUTED','Original input receipt')
 exact(pub['input_reference'],r['inputs'],'Original input reference');flags(x,PARENT_FLAGS);flags(pub,PARENT_FLAGS)
 claims={r[k]['path']:r[k]['sha256'] for k in ('inventory','inventory_publication','scenarios','input_producer')};claims[str(ROOT/ACCOUNT_CLAIM[0])]=ACCOUNT_CLAIM[1]
 exact(x['source_hashes'],claims,'Five declared parent sources');exact(pub['source_hashes'],claims,'Parent declared closure')
 require(ip['schema']=='CONDITIONAL_CASH_INVENTORY_V2_PUBLICATION_RECEIPT_V1' and ip['status']=='SOURCE_LOCKED_INVENTORY_ONLY_NOT_FORK_READY' and ip['fork_executed'] is False,'Inventory receipt')
 exact(ip['inventory_reference'],r['inventory'],'Inventory role')
 selected=[(i,row) for i,row in enumerate(x['rows']) if row['branch_role']=='MAIN_LANE']
 require(len(selected)==40 and len({row['scenario_id'] for _,row in selected})==40,'Complete main40')
 expected_policy={**SEMANTICS,'expected_scenario_ids':[row['scenario_id'] for _,row in selected]}
 exact(p['action_policy'],expected_policy,'Fixed economics without self reference')
 expected_refs=[dict(scenario_id=row['scenario_id'],reference={**r['inputs'],'json_pointer':f'/rows/{i}'}) for i,row in selected]
 exact(p['original_row_references'],expected_refs,'Registered original row order')
 contract={**expected_policy,'domain_core_reference':r['core'],'action_contract_reference':r['policy']}
 expected_cases=[];offset=0;financial_total=0;excluded_total=0;sources={r[k]['path']:r[k]['sha256'] for k in ('core','policy','inputs','scenarios','inventory')}
 for ci,((source_i,row),rowref) in enumerate(zip(selected,expected_refs)):
  exact(row['original_scenario'],location(row['scenario_reference'],r['scenarios'],d['scenarios']['rows']),'Full original scenario')
  exact(row['original_inventory_row'],location(row['inventory_row_reference'],r['inventory'],d['inventory']['rows']),'Full original inventory row')
  exact(row['risk_parameters'],p['risk_policy']['original_parameters'],'Original five risk values')
  require(row['zero_buy_only'] is False and row['target_l1_applicable'] is True and row['target_weights_normalized'] is False,'Main lane original target semantics')
  flags(row,('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'))
  holdings=row['holdings'];targets=row['target_weights'];old=[]
  for sid,q in holdings.items():
   require(type(q) is int and 0<=q<=10**12,'Exact old integer holdings')
   if q:old.append(sid)
  old.sort();require(old,'Positive original holding required')
  exact(row['allowed_buy_security_ids'],sorted(targets),'Full target union')
  require(all(rational(v)>0 for v in targets.values()),'Positive original weights')
  required=set(old)|set(targets)
  require(set(row['execution_prices'])==required==set(row['securities']),'Saved priced domain')
  prices={k:rational(v) for k,v in row['execution_prices'].items()};require(all(v>0 for v in prices.values()),'Positive prices')
  cash=rational(row['starting_cash_usd']);flow=rational(row['cash_event']['amount_usd']);fee=rational(row['transaction_cost_bps'])/10000;buffer=rational(row['minimum_cash_buffer_usd'])
  require(cash>=0 and flow>=0 and fee==Fraction(1,1000) and buffer==100,'Fixed fee, buffer, nonnegative capital')
  incoming=sorted(set(targets)-set(old));pairs=[];begin=offset;financial=0;excluded=0
  identity=dict(schema='SINGLE_REPLACEMENT_SCENARIO_IDENTITY_V1',action_contract=contract,input_reference=rowref['reference'],original_input_row=row)
  for out_sid in old:
   for in_sid in incoming:
    sale=Fraction(holdings[out_sid])*prices[out_sid];cost=sale*fee;available=cash+flow+sale-cost-buffer;unit=prices[in_sid]*(1+fee)
    quotient=available/unit;floor=quotient.numerator//quotient.denominator;cap=max(0,floor)
    groups={}
    for sid in sorted((set(old)-{out_sid})|{in_sid}):groups.setdefault(row['securities'][sid]['issuer_id'],[]).append(sid)
    conflicts={issuer:sids for issuer,sids in sorted(groups.items()) if len(sids)>1}
    count=0 if conflicts else cap
    pair=dict(pair_index=len(pairs),outgoing_security_id=out_sid,incoming_security_id=in_sid,sell_quantity=holdings[out_sid],financial_cap_floor=floor,financial_quantity_count=cap,quantity_min=1,quantity_max=cap,status='STRUCTURALLY_EXCLUDED' if conflicts else 'EMPTY_FINANCIAL_DOMAIN' if cap==0 else 'INTEGER_DOMAIN_NOT_EVALUATED',issuer_exclusion_certificate=dict(remaining_positive_security_ids=sorted(set(old)-{out_sid}),incoming_security_id=in_sid,issuer_groups=groups,conflicts=conflicts,applies_to_all_positive_integer_buys=True),financial_bound=dict(gross_sale_usd=str(sale),sell_fee_usd=str(cost),cash_available_after_sale_fee_and_buffer_usd=str(available),incoming_unit_cost_with_buy_fee_usd=str(unit),quantity_cap_formula='floor((C+A+Qout*Pout*(1-fee)-buffer)/(Pin*(1+fee)))'),first_global_ordinal=offset,enumerable_quantity_count=count)
    pairs.append(pair);offset+=count;financial+=cap
    if conflicts:excluded+=cap
  expected_cases.append(dict(scenario_index=ci,scenario_id=row['scenario_id'],identity=identity,identity_sha256=digest(identity),pairs=pairs,first_global_ordinal=begin,integer_count=offset-begin,pair_count=len(pairs),structurally_excluded_pair_count=sum(bool(a['issuer_exclusion_certificate']['conflicts']) for a in pairs),empty_financial_pair_count=sum(a['financial_quantity_count']==0 for a in pairs),financial_integer_count_before_issuer=financial,structurally_excluded_integer_count=excluded))
  financial_total+=financial;excluded_total+=excluded
 body=dict(schema='SINGLE_REPLACEMENT_DOMAIN_PREPARATION_V1',action_contract=contract,cases=expected_cases,scenario_count=40,pair_count=sum(c['pair_count'] for c in expected_cases),integer_count=offset,financial_integer_count_before_issuer=financial_total,structurally_excluded_integer_count=excluded_total,source_hash_claims=sources,scope='SAVED_PRICE_UNION_CONDITIONAL_MIGRATION',source_role='CALLER_SUPPLIED_ORIGINAL_ROW_AND_REFS_NOT_BYTE_AUTHENTICATION',**{k:False for k in DOMAIN_FLAGS})
 exact(saved_preparation,dict(document=body,content_sha256=digest(body)),'Independent full rational domain and original evidence')
 return dict(scenario_count=40,original_input_count=64,unselected_control_count=24,pair_count=body['pair_count'],integer_count=offset,financial_integer_count_before_issuer=financial_total,structurally_excluded_integer_count=excluded_total,scope='SAVED_CONDITIONAL_PRICE_UNION_NOT_FULL_NDX',risk_recomputed=False,quantity_points_evaluated=False)

def preflight():
 refs={k:dict(path=str(ROOT/p),sha256=h) for k,(p,h) in BOUND.items()}
 external={'preparation':dict(path=str(PARENT/'preparation.json'),sha256=PREPARATION_SHA),'publication':dict(path=str(PARENT/'publication.json'),sha256=PUBLICATION_SHA),'producer':dict(path=str(PRODUCER),sha256=PRODUCER_SHA)}
 for r in [*refs.values(),*external.values()]:reference(r)
 return refs,external
def read(ref,sources):
 reference(ref);require(ref['path'] not in sources or sources[ref['path']]==ref['sha256'],'Source collision')
 b=Path(ref['path']).read_bytes();require(hashlib.sha256(b).hexdigest()==ref['sha256'],'Same consumed source bytes');sources[ref['path']]=ref['sha256'];return b
def namespaces(refs):
 return {str(PARENT):{'started.json','raw_preparation.json','preparation.json','publication.json'},str(Path(refs['inputs']['path']).parent):{'inputs.json','publication.json'},str(Path(refs['inventory']['path']).parent):{'inventory.json','publication.json'},str(Path(refs['scenarios']['path']).parent):{'scenarios.json'}}
def guard(sources,dirs):
 require(hashlib.sha256(SOURCE.read_bytes()).hexdigest()==LOADED,'Loaded reader identity')
 for p,h in sources.items():require(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Final source drift')
 for p,names in dirs.items():require({v.name for v in Path(p).iterdir()}==names,'Exact source namespace')
def save(name,value):
 b=encode(value);p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved report bytes');return dict(path=str(p),sha256=hashlib.sha256(b).hexdigest())
def readback(*,execute=False):
 require(execute is True,'Explicit independent readback');refs,external=preflight()
 require(not OUTPUT.exists(),'No overwrite or retry');sources={str(SOURCE):LOADED};dirs=namespaces(refs)
 read(external['producer'],sources)
 d={};json_roles={'policy','inputs','input_publication','inventory','inventory_publication','scenarios'}
 for k,r in refs.items():
  b=read(r,sources)
  if k in json_roles:d[k]=decode(b)
 out=decode(read(external['preparation'],sources));pub=decode(read(external['publication'],sources))
 raw_ref=out['raw_preparation_reference'];exact(raw_ref['path'],str(PARENT/'raw_preparation.json'),'Fixed raw location')
 raw=decode(read(raw_ref,sources));started_path=PARENT/'started.json';started_bytes=started_path.read_bytes();started_ref=dict(path=str(started_path),sha256=hashlib.sha256(started_bytes).hexdigest());sources[str(started_path)]=started_ref['sha256'];started=decode(started_bytes)
 expected_sources={str(PRODUCER):PRODUCER_SHA,**{r['path']:r['sha256'] for r in refs.values()}}
 require(out['schema']=='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1' and pub['schema']=='SINGLE_REPLACEMENT_PREPARATION_PUBLICATION_V1' and pub['status']=='PUBLISHED_UNEVALUATED_DOMAIN_ONLY','Saved output roles')
 require(started['schema']=='SINGLE_REPLACEMENT_PREPARATION_STARTED_V1','Saved started role')
 for obj in (out,pub,started):flags(obj);exact(obj['source_hashes'],expected_sources,'Exact12 direct sources plus producer')
 exact(out['input_references'],refs,'Exact preparation roles');exact(started['input_references'],refs,'Exact started roles')
 exact(pub['preparation_reference'],external['preparation'],'Published preparation');exact(pub['raw_preparation_reference'],raw_ref,'Published original return')
 flags(raw);require(raw['schema']=='SINGLE_REPLACEMENT_RAW_PREPARATION_V1' and raw['returned'] is True and raw['result_preserved_as_json'] is True,'Complete actual saved return')
 exact(raw['result'],out['preparation'],'Same complete raw result')
 exact(out['consumed_authenticated_sources'],expected_sources,'Direct authentication scope');exact(out['declared_parent_sources'],d['inputs']['source_hashes'],'Preserved parent claims')
 require(out['old_holdings_reconstructed'] is False and out['historical_audit_role']=='SAVED_MARKDOWN_AND_CODE_REFERENCES_NOT_NEW_MACHINE_ATTESTATION' and out['source_scope']=='DIRECT_INPUT_POLICY_CORE_AND_ORIGINAL_ROW_PARENTS_ONLY','No original account/audit replay')
 guard(sources,dirs);OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
 try:
  saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_INDEPENDENT_STARTED_V1',input_references={**external,'original_sources':refs},source_hashes=sources,**{k:False for k in FLAGS})))
  inspection=inspect_domain(documents=d,references=refs,saved_preparation=out['preparation'])
  guard(sources,dirs)
  report=save('independent_readback.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',preparation_reference=external['preparation'],publication_reference=external['publication'],raw_preparation_reference=raw_ref,producer_started_reference=started_ref,producer_started_has_separate_external_anchor=False,reader_sha256=LOADED,input_references=refs,source_hashes=sources,consumed_authenticated_sources=expected_sources,declared_parent_sources=d['inputs']['source_hashes'],inspection=inspection,producer_called=False,domain_core_called=False,risk_evaluator_called=False,original_account_reopened=False,scope='INDEPENDENT_FRACTION_DOMAIN_AND_DIRECT_SOURCE_BINDING_NOT_RISK_EVALUATION_OR_FULL_NDX',**{k:False for k in FLAGS}));saved.append(report)
  guard(sources,dirs)
  for r in saved:require(hashlib.sha256(Path(r['path']).read_bytes()).hexdigest()==r['sha256'],'Final output bytes')
  require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact reader output namespace')
  return report
 except BaseException as e:
  save('failure.json',dict(status='FAILED_DO_NOT_RETRY_OR_CONSUME',error_type=type(e).__name__,error=str(e),saved_references=saved,**{k:False for k in FLAGS}));raise

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=parser.parse_args().execute)))