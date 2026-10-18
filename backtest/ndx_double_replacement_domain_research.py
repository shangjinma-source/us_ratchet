"""Complete conditional two-for-two positive-integer budget domain, without risk/search/account IO."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from backtest import ndx_two_positive_integer_budget_domain_research as budget_math

BUDGET_MATH_SHA256 = '081a1d3a72c78c3e4637fa25b3845853a610c33608bfd5b4b2ee8ccdca2dc5e1'
import json

RULE = 'SELL_ALL_TWO_POSITIVE_OLD_BUY_TWO_NEW_JOINT_INTEGER_V1'
SCOPE = 'SAVED_PRICE_UNION_CONDITIONAL_MIGRATION'
RISK_KEYS = ('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')
SEMANTICS = dict(schema='DOUBLE_REPLACEMENT_ACTION_CONTRACT_V1', rule=RULE, scope=SCOPE,
 information_set='SAVED_EXECUTION_OPEN_CONDITIONAL_NOT_PRIOR_CLOSE',
 outgoing_policy='ALL_UNORDERED_TWO_POSITIVE_OLD_SID_COMBINATIONS', incoming_policy='ALL_UNORDERED_TWO_ALLOWED_TARGET_MINUS_POSITIVE_OLD_COMBINATIONS',
 other_holdings_policy='UNCHANGED_INCLUDING_ZERO_KEYS', quantity_policy='ALL_POSITIVE_INTEGER_PAIRS_WITHIN_EXACT_JOINT_BUDGET',
 funding_policy='POOL_ALL_SELL_PROCEEDS_NO_OLD_WEIGHT_ASSIGNMENTS',
 quantity_order='Q1_Q2_CORRESPOND_TO_SORTED_INCOMING_SIDS_NOT_SORTED_QUANTITIES',
 issuer_policy='ALL_REMAINING_POSITIVE_OLD_PLUS_BOTH_INCOMING_UNIQUE',
 order='ORIGINAL_SCENARIO_ORDER_THEN_SORTED_OUT_PAIR_SORTED_IN_PAIR_Q1_Q2_LEX',
 fee_policy='SELL_AND_BUY_NOTIONAL_TIMES_SAME_BPS', transaction_cost_bps='10', minimum_cash_buffer_usd='100',
 ranking_policy='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_OUTPAIR_INPAIR_Q1_Q2',
 cross_family_ranking_registered=False, risk_evaluation_policy='UNCHANGED_FIVE_RISKS_NOT_EVALUATED_BY_PREPARER')
FLAGS = dict.fromkeys(('source_bytes_authenticated','point_in_time_verified','formal_eligibility_verified',
 'identity_gaps_resolved','risk_evaluated','financial_feasibility_evaluated','economic_winner_selected',
 'global_optimality_claimed','orders_executed','account_executed','fit_executed','old_evaluations_repeated',
 'target_weights_changed','future_returns_used','repair_performed','domain_registered_for_execution'), False)

def require(ok, message):
 if not ok: raise ValueError(message)

def encode(v): return json.dumps(v,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
def digest(v): return sha256(encode(v)).hexdigest()
def exact(a,b,message): require(encode(a)==encode(b),message)

def number(v):
 require(type(v) is str and 0<len(v)<=80 and v.strip()==v,'Saved exact decimal literal, not float/bool')
 n=Decimal(v)
 require(n.is_finite() and len(n.as_tuple().digits)<=40 and abs(n.as_tuple().exponent)<=40,'Finite bounded decimal encoding')
 return Fraction(n)

def identifier(v):
 require(type(v) is str and v and v.strip()==v,'Canonical identifier'); return v

def reference(r, pointer=False):
 require(type(r) is dict and set(r)==({'path','sha256','json_pointer'} if pointer else {'path','sha256'}),'Exact original reference')
 identifier(r['path']); h=r['sha256']; require(type(h) is str and len(h)==64 and set(h)<=set('0123456789abcdef'),'SHA256')
 if pointer:
  p=r['json_pointer']; require(type(p) is str and p.startswith('/rows/') and p[6:].isdigit() and str(int(p[6:]))==p[6:],'Canonical original row pointer')

def validate_contract(c, rows):
 require(type(c) is dict and set(c)==set(SEMANTICS)|{'expected_scenario_ids','domain_core_reference','action_contract_reference','budget_math_reference'},'Explicit full action contract')
 exact({k:c[k] for k in SEMANTICS},SEMANTICS,'No inferred economic choices')
 reference(c['domain_core_reference']); reference(c['action_contract_reference']); reference(c['budget_math_reference'])
 require(c['budget_math_reference']['sha256']==BUDGET_MATH_SHA256,'Frozen exact budget helper declaration')
 ids=c['expected_scenario_ids']; require(type(ids) is list and ids and len(ids)<=10000 and len(set(ids))==len(ids),'Explicit complete scenario order')
 for sid in ids: identifier(sid)
 exact([x['input_row']['scenario_id'] for x in rows],ids,'No scenario omitted, repeated or reordered')

def prepare_double_replacement_domain(original_rows, action_contract):
 """No actual source registration. Complete supplied scenario order is explicit.

 A production caller must bind all original40; small synthetic declared domains
 are allowed. Stores O(out-pair * in-pair) metadata, never enumerates quantities.
 """
 require(type(original_rows) is list and original_rows,'Explicit original rows')
 for x in original_rows: require(type(x) is dict and set(x)=={'input_row','input_reference'},'Original row envelope')
 validate_contract(action_contract,original_rows)
 cases=[]; total=0; all_financial=0; structural_total=0; seen_refs=set(); sources={}
 def merge(r):
  p,h=r['path'],r['sha256']; require(p not in sources or sources[p]==h,'Conflicting original source'); sources[p]=h
 for r in (action_contract['domain_core_reference'],action_contract['action_contract_reference'],action_contract['budget_math_reference']): merge(r)
 for ci,envelope in enumerate(original_rows):
  row=envelope['input_row']; ref=envelope['input_reference']; reference(ref,True); merge(ref)
  key=(ref['path'],ref['json_pointer']); require(key not in seen_refs,'Unique original source row'); seen_refs.add(key)
  require(row['branch_role']=='MAIN_LANE' and row['zero_buy_only'] is False and row['target_l1_applicable'] is True,'Original main lane')
  for k in ('point_in_time_verified','promotion_allowed','fork_executable','orders_executed'): require(row[k] is False,'Conditional source permissions')
  require(row['target_weights_normalized'] is False,'Original target literals')
  for k in ('scenario_reference','inventory_row_reference'): reference(row[k],True); merge(row[k])
  event=row['cash_event']; require(type(event) is dict and set(event)=={'decision_date','execution_date','amount_usd'},'Original cash timing')
  for k in ('decision_date','execution_date'): require(type(event[k]) is str and date.fromisoformat(event[k]).isoformat()==event[k],'Canonical source day')
  require(event['decision_date']<event['execution_date'],'Original next execution coordinate')
  holdings=row['holdings']; targets=row['target_weights']; securities=row['securities']; prices=row['execution_prices']
  require(all(type(x) is dict for x in (holdings,targets,securities,prices)) and holdings and targets,'Complete source maps')
  for s,q in holdings.items(): identifier(s); require(type(q) is int and 0<=q<=10**12,'Whole old quantity, bool rejected')
  old=sorted(s for s,q in holdings.items() if q>0); require(old,'Positive old holdings required')
  require(all(number(v)>0 for v in targets.values()),'Positive original targets')
  exact(row['allowed_buy_security_ids'],sorted(targets),'Original allowed target domain')
  union=set(old)|set(targets); require(set(prices)==set(securities)==union and len(union)<=256,'Exact saved priced identity union')
  for s in union:
   identifier(s)
   for k in ('ticker','issuer_id','risk_chain'): identifier(securities[s][k])
  marks={s:number(prices[s]) for s in union}; require(all(x>0 for x in marks.values()),'Positive nominal Open')
  risk=row['risk_parameters']; require(type(risk) is dict and set(risk)==set(RISK_KEYS),'All five original risk parameters preserved')
  for v in risk.values(): require(0<number(v)<=1,'Original risk parameter range')
  cash,amount,buffer,fee=[number(v) for v in (row['starting_cash_usd'],event['amount_usd'],row['minimum_cash_buffer_usd'],row['transaction_cost_bps'])]
  require(cash>=0 and amount>=0,'Nonnegative capital/inflow')
  require(buffer==number(action_contract['minimum_cash_buffer_usd']) and fee==number(action_contract['transaction_cost_bps']),'Original fee/buffer must match explicit action contract')
  incoming=sorted(set(targets)-set(old)); case_start=total; pairs=[]; financial=0; excluded=0
  scenario_identity=dict(schema='DOUBLE_REPLACEMENT_SCENARIO_IDENTITY_V1',action_contract=deepcopy(action_contract),input_reference=deepcopy(ref),original_input_row=deepcopy(row))
  for outgoing in combinations(old,2):
   for new in combinations(incoming,2):
    gross=sum((holdings[s]*marks[s] for s in outgoing),Fraction(0));sell_fee=gross*fee/10000
    available=cash+amount+gross-sell_fee-buffer
    costs=[marks[s]*(1+fee/10000)for s in new]
    financial_count=budget_math.count_points(a=costs[0],b=costs[1],budget=available)
    groups={}
    for sid in sorted((set(old)-set(outgoing))|set(new)):groups.setdefault(securities[sid]['issuer_id'],[]).append(sid)
    conflicts={issuer:ss for issuer,ss in sorted(groups.items())if len(ss)>1}
    count=0 if conflicts else financial_count
    pairs.append(dict(pair_index=len(pairs),outgoing_security_ids=list(outgoing),incoming_security_ids=list(new),sell_quantities={sid:holdings[sid]for sid in outgoing},
      quantity_order='SORTED_INCOMING_SID_Q1_Q2',quantity_min=[1,1],
      status='STRUCTURALLY_EXCLUDED'if conflicts else'EMPTY_FINANCIAL_DOMAIN'if count==0 else'JOINT_INTEGER_DOMAIN_NOT_EVALUATED',
      issuer_exclusion_certificate=dict(remaining_positive_security_ids=sorted(set(old)-set(outgoing)),incoming_security_ids=list(new),issuer_groups=groups,conflicts=conflicts,applies_to_all_positive_integer_pairs=True),
      financial_bound=dict(gross_sale_usd=str(gross),sell_fee_usd=str(sell_fee),joint_budget_usd=str(available),incoming_unit_costs_with_buy_fee_usd=[str(v)for v in costs],inequality='a*q1+b*q2<=B; q1>=1; q2>=1',quantity_domain_not_rectangular=True),
      first_global_ordinal=total,financial_integer_count=financial_count,enumerable_integer_count=count))
    total+=count;financial+=financial_count;excluded+=financial_count-count
  cases.append(dict(scenario_index=ci,scenario_id=row['scenario_id'],identity=scenario_identity,identity_sha256=digest(scenario_identity),pairs=pairs,first_global_ordinal=case_start,integer_count=total-case_start,pair_count=len(pairs),structurally_excluded_pair_count=sum(bool(p['issuer_exclusion_certificate']['conflicts'])for p in pairs),empty_financial_pair_count=sum(p['financial_integer_count']==0 for p in pairs),financial_integer_count_before_issuer=financial,structurally_excluded_integer_count=excluded))
  all_financial+=financial;structural_total+=excluded
 body=dict(schema='DOUBLE_REPLACEMENT_DOMAIN_PREPARATION_V1',action_contract=deepcopy(action_contract),cases=cases,scenario_count=len(cases),pair_count=sum(c['pair_count']for c in cases),integer_count=total,financial_integer_count_before_issuer=all_financial,structurally_excluded_integer_count=structural_total,source_hash_claims=sources,scope=SCOPE,source_role='CALLER_SUPPLIED_ORIGINAL_ROW_AND_REFS_NOT_BYTE_AUTHENTICATION',budget_helper_source_bytes_authenticated=False,**FLAGS)
 require(total+structural_total==all_financial,'Full retained/excluded integer partition')
 return dict(document=body,content_sha256=digest(body))

def checked(prepared):
 require(type(prepared)is dict and set(prepared)=={'document','content_sha256'}and digest(prepared['document'])==prepared['content_sha256'],'Prepared content integrity')
 require(prepared['document']['schema']=='DOUBLE_REPLACEMENT_DOMAIN_PREPARATION_V1','Double replacement schema')
 return prepared['document']

def _args(pair):
 b=pair['financial_bound'];a,c=map(Fraction,b['incoming_unit_costs_with_buy_fee_usd'])
 return dict(a=a,b=c,budget=Fraction(b['joint_budget_usd']))

def _task(d,ordinal):
 require(type(ordinal)is int and 0<=ordinal<d['integer_count'],'Exact bounded global rank')
 for c in d['cases']:
  if not c['first_global_ordinal']<=ordinal<c['first_global_ordinal']+c['integer_count']:continue
  for p in c['pairs']:
   if p['first_global_ordinal']<=ordinal<p['first_global_ordinal']+p['enumerable_integer_count']:
    quantities=list(budget_math.unrank_point(**_args(p),rank=ordinal-p['first_global_ordinal']))
    identity=dict(schema='DOUBLE_REPLACEMENT_INTEGER_TASK_IDENTITY_V1',scenario_identity_sha256=c['identity_sha256'],rule=RULE,outgoing_security_ids=deepcopy(p['outgoing_security_ids']),incoming_security_ids=deepcopy(p['incoming_security_ids']),sell_quantities=deepcopy(p['sell_quantities']),buy_quantities=quantities)
    row=c['identity']['original_input_row'];holdings=row['holdings'];after={sid:holdings.get(sid,0)for sid in sorted(set(holdings)|set(row['execution_prices']))};signed={sid:0 for sid in after}
    for sid in p['outgoing_security_ids']:signed[sid]=-holdings[sid];after[sid]=0
    for sid,q in zip(p['incoming_security_ids'],quantities):signed[sid]=q;after[sid]=q
    return dict(task_id=digest(identity),identity=identity,scenario_index=c['scenario_index'],pair_index=p['pair_index'],global_ordinal=ordinal,signed_trade_quantities=signed,proposed_holdings=after,evaluation_status='NOT_EVALUATED',**FLAGS)
 raise ValueError('Prepared rank partition inconsistent')

def unrank(prepared,ordinal):return _task(checked(prepared),ordinal)

def rank(prepared,*,scenario_index,outgoing_security_ids,incoming_security_ids,buy_quantities):
 d=checked(prepared);require(type(scenario_index)is int and 0<=scenario_index<len(d['cases']),'Exact case index')
 for ids in (outgoing_security_ids,incoming_security_ids):require(type(ids)is list and len(ids)==2 and all(type(s)is str for s in ids)and ids==sorted(set(ids)),'Canonical unordered SID pair')
 require(type(buy_quantities)is list and len(buy_quantities)==2,'Explicit incoming-ordered two quantities')
 for p in d['cases'][scenario_index]['pairs']:
  if(p['outgoing_security_ids'],p['incoming_security_ids'])==(outgoing_security_ids,incoming_security_ids):
   require(p['enumerable_integer_count']>0,'Excluded or empty pair')
   local=budget_math.rank_point(**_args(p),q1=buy_quantities[0],q2=buy_quantities[1]);require(local<p['enumerable_integer_count'],'Quantity domain')
   return p['first_global_ordinal']+local
 raise ValueError('Unknown pair')

def task_page(prepared,*,start,limit):
 d=checked(prepared);require(type(start)is int and 0<=start<=d['integer_count']and type(limit)is int and 1<=limit<=10000,'Engineering page bound; no domain truncation')
 stop=min(start+limit,d['integer_count'])
 return dict(full_integer_count=d['integer_count'],start=start,stop=stop,tasks=[_task(d,n)for n in range(start,stop)],has_more=stop<d['integer_count'],domain_truncated=False)

def shard_page(prepared,*,shard_size,shard_start,shard_stop):
 d=checked(prepared);require(type(shard_size)is int and 1<=shard_size<=1000000,'Engineering shard size')
 n=(d['integer_count']+shard_size-1)//shard_size
 require(type(shard_start)is int and type(shard_stop)is int and 0<=shard_start<=shard_stop<=n and shard_stop-shard_start<=1000,'Engineering descriptor page')
 rows=[]
 for i in range(shard_start,shard_stop):
  identity=dict(schema='DOUBLE_REPLACEMENT_SHARD_V1',preparation_sha256=prepared['content_sha256'],ordinal=i,start=i*shard_size,stop=min((i+1)*shard_size,d['integer_count']))
  rows.append(dict(identity=identity,shard_id=digest(identity)))
 return dict(full_integer_count=d['integer_count'],full_shard_count=n,shards=rows)
