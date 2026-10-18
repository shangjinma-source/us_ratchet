"""Complete forty signed-path inputs only. No selection, risk, accounting or IO."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json,re
CLOCKS=(('2023-04-28','2023-05-01',87),('2023-05-31','2023-06-01',65),('2023-06-30','2023-07-03',44),('2023-07-31','2023-08-01',24),('2023-08-31','2023-09-01',1))
LANES=('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE')
RULE='SELL_ALL_TWO_POSITIVE_OLD_BUY_TWO_NEW_JOINT_INTEGER_V1'
FLAGS=dict.fromkeys(('source_bytes_authenticated','selection_audit_authenticated','selection_reexecuted','risk_recomputed','fees_recomputed','account_executed','control_reexecuted','orders_executed','point_in_time_verified','promotion_allowed','future_returns_used','cross_family_winner_selected'),False)
def require(ok,msg):
 if not ok:raise ValueError(msg)
def encode(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(x):return sha256(encode(x)).hexdigest()
def exact(a,b,msg):require(encode(a)==encode(b),msg)
def integer(x):require(type(x)is int and 0<=x<=10**12,'Exact whole quantity/count');return x
def number(x):
 require(type(x)in(str,int)and 0<len(str(x))<=80,'Saved decimal literal')
 if type(x)is str:require(x.strip()==x,'Unpadded decimal literal')
 try:n=Decimal(x)
 except Exception as error:raise ValueError('Invalid decimal literal')from error
 require(n.is_finite()and len(n.as_tuple().digits)<=40 and abs(n.as_tuple().exponent)<=40,'Bounded finite literal')
 value=Fraction(n);require(0<=value<=10**40,'Nonnegative bounded accounting value');return value
def ref(r,pointer=False):
 require(type(r)is dict and set(r)==({'path','sha256','json_pointer'}if pointer else{'path','sha256'}),'Exact reference role')
 require(type(r['path'])is str and r['path'].strip()==r['path']and r['path'],'Source path')
 require(type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Source hash')
 if pointer:require(type(r['json_pointer'])is str and r['json_pointer'].startswith('/')and not re.search(r'~(?![01])',r['json_pointer']),'Canonical source pointer')
 return deepcopy(r)
def envelope(e,schema):
 require(type(e)is dict and set(e)=={'document','content_sha256'}and digest(e['document'])==e['content_sha256'],'Saved envelope integrity')
 require(e['document']['schema']==schema,'Saved schema');return e['document']
def prepare_double_replacement_path_requests(*,prepared,selection,old_paired_rows,source_references):
 p=envelope(prepared,'DOUBLE_REPLACEMENT_DOMAIN_PREPARATION_V1');s=selection;require(s['schema']=='DOUBLE_REPLACEMENT_STREAM_SELECTION_V1','Native double-stream selection')
 require(set(source_references)=={'prepared','selection','selection_audit','old_paired'},'Four explicit source roles');refs={k:ref(v)for k,v in source_references.items()}
 claims={}
 def merge(r):
  require(r['path']not in claims or claims[r['path']]==r['sha256'],'Conflicting source declarations');claims[r['path']]=r['sha256']
 for r in refs.values():merge(r)
 exact(s['prepared_content_sha256'],prepared['content_sha256'],'Selected prepared body')
 require(p['action_contract']['rule']==RULE,'Double replacement rule')
 require(s['full_domain_selected']is True,'Complete domain selection only')
 for obj in (p,s):
  for k in ('point_in_time_verified','account_executed','fit_executed','future_returns_used'):require(obj[k]is False,'No promoted source authority')
 require(type(old_paired_rows)is list and len(old_paired_rows)==len(p['cases'])==len(s['rows'])==40,'Complete forty rows')
 exact([x['scenario_id']for x in p['cases']],p['action_contract']['expected_scenario_ids'],'Prepared original order');require(len(set(p['action_contract']['expected_scenario_ids']))==40,'Unique forty')
 for k in ('scenario_count','pair_count','integer_count'):require(type(s[k])is int and type(p[k])is int and s[k]==p[k],'Whole domain counts')
 require(s['scenario_count']==40,'Full scenario denominator')
 out=[];coordinates=set();counts={'NEW_SIGNED_PATH_REQUIRED':0,'NO_FEASIBLE':0,'BLOCKED_TEMPLATE_PRICE_GAP':0};feasible=infeasible=0
 for i,(c,chosen,old)in enumerate(zip(p['cases'],s['rows'],old_paired_rows)):
  row=c['identity']['original_input_row'];sid=row['scenario_id'];event=row['cash_event'];ids=sorted(set(row['holdings'])|set(row['execution_prices']))
  require(type(c['scenario_index'])is int and c['scenario_index']==i and type(chosen['scenario_index'])is int and chosen['scenario_index']==i,'Exact ordered scenario slot')
  require(digest(c['identity'])==c['identity_sha256'],'Case identity digest');exact(c['identity']['action_contract'],p['action_contract'],'Case registered action')
  exact(chosen['scenario_id'],sid,'Chosen same scenario');exact(old['scenario_id'],sid,'Old same scenario')
  exact(old['input_row'],row,'Entire original input row');exact(old['topup_context']['input_row'],row,'Entire original old context')
  exact(old['input_reference'],c['identity']['input_reference'],'Original input reference');ref(old['input_reference'],True);merge(old['input_reference']);ref(old['topup_context_reference'],True);merge(old['topup_context_reference'])
  for obj in (row,old):
   for k in ('point_in_time_verified','orders_executed','promotion_allowed'):require(obj[k]is False,'Original conditional authority')
  mapping={k:v['ticker']for k,v in row['securities'].items()};exact(old['security_to_ticker'],mapping,'Preserved SID aliases');require(len(set(mapping.values()))==len(mapping),'No alias collapse')
  for q in row['holdings'].values():integer(q)
  coord=(row['lane'],event['decision_date'],event['execution_date'],event['amount_usd']);require(coord not in coordinates,'Unique scenario coordinate');coordinates.add(coord)
  expected_days={(a,b):n for a,b,n in CLOCKS};clock=(event['decision_date'],event['execution_date']);require(row['lane']in LANES and clock in expected_days and event['amount_usd']in('1000','10000'),'Original forty coordinate')
  template=old['paths']['candidate']['accounting_inputs'];require(set(template)=={'initial','sessions','transaction_cost_bps'},'Exact old accounting template')
  initial=template['initial'];sessions=template['sessions'];require(set(initial)=={'session','cash_usd','holdings','close_prices'},'Exact original initial')
  exact(initial['session'],event['decision_date'],'Initial decision Close');exact(initial['cash_usd'],row['starting_cash_usd'],'Initial cash unchanged');exact(initial['holdings'],row['holdings'],'Initial holdings including zero slots');exact(template['transaction_cost_bps'],row['transaction_cost_bps'],'Fee unchanged');require(number(template['transaction_cost_bps'])==10,'Original ten bps')
  number(initial['cash_usd']);number(row['starting_cash_usd'])
  exact(old['paths']['same_flow_zero_trade_control']['accounting_inputs']['initial'],initial,'Control same original initial')
  require(type(sessions)is list and len(sessions)==expected_days[clock],'Full original calendar length');days=[r['session']for r in sessions]
  require(days==sorted(set(days))and days[0]==event['execution_date']and days[-1]=='2023-09-01'and initial['session']<days[0],'Full original calendar endpoints')
  for d in [initial['session']]+days:require(type(d)is str and date.fromisoformat(d).isoformat()==d,'Canonical saved date')
  oldplan=old['selected_plan'];require(oldplan['feasible']is True,'Old saved path selected feasibility');integer(oldplan['supplied_plan_index']);exact(old['topup_context']['selected_candidate_index'],oldplan['supplied_plan_index'],'Old plan index')
  expected_oldref=dict(old['topup_context_reference'],json_pointer=old['topup_context_reference']['json_pointer']+'/evaluation/branches/0/evaluated_plans/'+str(oldplan['supplied_plan_index']));exact(old['selected_plan_reference'],expected_oldref,'Old plan pointer')
  gaps=[]
  def marks(values,wanted,location):
   require(type(values)is dict and set(values)<=set(wanted),'No foreign saved price SID')
   missing=sorted(set(wanted)-set(values))
   if missing:gaps.append(dict(reason='MISSING_SAVED_PRICE',location=location,security_ids=missing))
   require(all(number(v)>0 for v in values.values()),'Positive saved mark')
  marks(initial['close_prices'],row['holdings'],'initial.close_prices')
  for j,r in enumerate(sessions):
   require(set(r)=={'session','open_prices','close_prices','cash_injection_usd','buy_shares'},'Exact old session contract')
   marks(r['open_prices'],ids,f'sessions/{j}/open_prices');marks(r['close_prices'],ids,f'sessions/{j}/close_prices')
   exact(r['buy_shares'],oldplan['buy_shares']if j==0 else{},'Original one saved trade');require(number(r['cash_injection_usd'])==(number(event['amount_usd'])if j==0 else 0),'Exactly one original injection')
  for key,value in row['execution_prices'].items():
   if key in sessions[0]['open_prices']:require(number(sessions[0]['open_prices'][key])==number(value),'First Open same saved evaluation quote')
  for k in ('integer_count',):require(type(chosen[k])is int and chosen[k]==c[k],'Case domain denominator')
  fc=integer(chosen['feasible_count']);ic=integer(chosen['infeasible_count']);require(fc+ic==c['integer_count'],'Complete case selection partition');feasible+=fc;infeasible+=ic
  selected=chosen['selected'];request=None;expected=None
  if selected is None:require(chosen['status']=='NO_FEASIBLE'and fc==0,'No feasible is not a cash path');status='NO_FEASIBLE'
  else:
   require(chosen['status']=='SELECTED'and fc>0,'Native double selected state');raw=selected['raw'];task=raw['plan']['task'];identity=task['identity'];pi=integer(task['pair_index']);require(pi<len(c['pairs']),'Registered pair');pair=c['pairs'][pi]
   outgoing=pair['outgoing_security_ids'];incoming=pair['incoming_security_ids'];quantities=identity['buy_quantities']
   require(len(outgoing)==len(incoming)==len(quantities)==2 and len(set(outgoing+incoming))==4,'Two distinct sold and bought SIDs')
   for q in quantities:require(integer(q)>0,'Strictly positive double quantities')
   expected_identity=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=c['identity_sha256'],rule=RULE,outgoing_security_ids=outgoing,incoming_security_ids=incoming,sell_quantities=pair['sell_quantities'],buy_quantities=quantities)
   exact(identity,expected_identity,'Original outpair/inpair action identity');exact(task['task_id'],digest(identity),'Task hash');exact(task['scenario_index'],i,'Original selected scenario')
   ordinal=task['global_ordinal'];require(type(ordinal)is int and pair['first_global_ordinal']<=ordinal<pair['first_global_ordinal']+pair['enumerable_integer_count'],'Selected original pair interval');exact(raw['plan']['global_ordinal'],ordinal,'Original RAW ordinal')
   signed={k:0 for k in ids}
   for leg_sid in outgoing:require(pair['sell_quantities'][leg_sid]==row['holdings'][leg_sid]>0,'Sell all two positive old holdings');signed[leg_sid]=-row['holdings'][leg_sid]
   for leg_sid,q in zip(incoming,quantities):require(row['holdings'].get(leg_sid,0)==0,'Buy two new holdings');signed[leg_sid]=q
   holdings={k:row['holdings'].get(k,0)+signed[k]for k in ids};exact(task['signed_trade_quantities'],signed,'Complete four-leg signed vector');exact(task['proposed_holdings'],holdings,'Other holdings including zeros unchanged')
   evaluation=raw['evaluation'];require(raw['status']=='FEASIBLE'and evaluation['status']=='FEASIBLE'and evaluation['feasible']is True,'Original feasible saved double result');expected=deepcopy(evaluation)
   status='BLOCKED_TEMPLATE_PRICE_GAP'if gaps else'NEW_SIGNED_PATH_REQUIRED'
   if not gaps:
    request=deepcopy(template)
    for j,r in enumerate(request['sessions']):del r['buy_shares'];r['trade_shares']=deepcopy(signed)if j==0 else{}
  counts[status]+=1;base=dict(refs['old_paired'],json_pointer=f'/rows/{i}')
  out.append(dict(scenario_index=i,scenario_id=sid,status=status,accounting_request=request,expected_first_trade=expected,selection_row=deepcopy(chosen),prepared_case=deepcopy(c),old_paired_evidence=deepcopy(old),template_gaps=gaps,original_gaps=deepcopy(row.get('gaps',[])),selection_reference=dict(refs['selection'],json_pointer=f'/selection/rows/{i}'),control_path_reference=dict(base,json_pointer=base['json_pointer']+'/paths/same_flow_zero_trade_control'),reused_candidate_path_reference=None,**FLAGS))
 require(coordinates=={(l,d,e,a)for l in LANES for d,e,_ in CLOCKS for a in('1000','10000')},'Complete five dates/four lanes/two amounts')
 require(feasible+infeasible==s['integer_count'],'Full double denominator')
 return dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_REQUESTS_V1',rows=out,scenario_count=40,status_counts=counts,new_account_request_count=counts['NEW_SIGNED_PATH_REQUIRED'],input_references=refs,source_hash_claims=claims,no_feasible_is_cash_return=False,source_reference_semantics='DECLARATIONS_ONLY_EXTERNAL_READER_MUST_AUTHENTICATE_FULL_SELECTION',policy_asymmetry='CONDITIONAL_EXECUTION_OPEN_DOUBLE_REPLACEMENT_ONE_OFF;CONTROL_SAVED_REFERENCE_ONLY;NO_PRIOR_CLOSE_EXECUTABILITY_OR_CROSS_FAMILY_WINNER_CLAIM',**FLAGS)
