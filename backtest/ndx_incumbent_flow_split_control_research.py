"""Fixed disclosed incumbent controls, two own accounts, USD flows and splits.

Private fixed bindings preserve original weights. No global monkeypatch, candidate
risk eligibility, fitting, strategy selection, or account reuse across tracks.
"""
from copy import deepcopy
from pathlib import Path
from types import FunctionType,SimpleNamespace
import hashlib,math
from backtest import ndx_dynamic_frozen_incumbent_control as control
from backtest import ndx_dynamic_fractional_flow_split_research_v2 as fractional
from backtest import ndx_dynamic_frozen_flow_split_research as whole

SOURCE=Path(__file__).resolve()
PATHS=[SOURCE,*[Path(m.__file__).resolve() for m in (control,fractional,whole)]]
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in PATHS}
RISK_KEYS=('max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')


def require(x,m):
 if not x:raise ValueError(m)
def guard():
 control._sources();whole._check_sources()
 for p,h in LOADED.items():require(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,'Loaded control source drift')
def bind(original,changes):
 namespace=dict(original.__globals__);namespace.update(changes)
 result=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__);result.__kwdefaults__=dict(original.__kwdefaults__ or {});return result

def observe(values,chains,constraints,slots):
 require(all(math.isfinite(v) and v>=0 for v in values.values()),'Finite nonnegative observation')
 active={s:v for s,v in values.items() if v>0};total=sum(active.values());common=dict(risk_is_order_gate=False,target_slot_count=len(slots),positive_holding_count=len(active),zero_share_security_ids=sorted(set(slots)-set(active)))
 if not active:return dict(common,checks={'ALL_CASH':False},all_passed=False,actual_weights={},effective_n=None)
 weights={s:v/total for s,v in active.items()};ordered=sorted(weights.values(),reverse=True);effective=1/sum(w*w for w in ordered);groups={}
 for s,w in weights.items():groups[chains[s]]=groups.get(chains[s],0.)+w
 checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=constraints['max_single_weight']+1e-9,MIN_SINGLE_WEIGHT=ordered[-1]>=constraints['min_single_weight']-1e-9,SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=constraints['top_weight_cap']+1e-9,MINIMUM_EFFECTIVE_N=effective>=constraints['minimum_effective_n_ratio']*len(active)-1e-9,RISK_CHAIN_TOP1_WEIGHT=max(groups.values())<=constraints['risk_chain_top1_cap']+1e-9)
 return dict(common,checks=checks,all_passed=all(checks.values()),actual_weights=weights,effective_n=effective,risk_chain_weights=groups)

def simulate_incumbent_flow_split_control(*,track,closes,opens,schedule,risk_chains_by_decision,corporate_actions,external_flows,initial_cash_usd,minimum_cash_buffer_usd,valuation_end_date,transaction_cost_bps=10.,max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55):
 """CONTINUOUS Open sizing or WHOLE_LOT Close-frozen basket, no risk gate.

Weights remain original literals within the inherited 1e-12 sum tolerance.
Call separately for each track and distinct complete flow/calendar identity.
"""
 guard();require(track in ('CONTINUOUS','WHOLE_LOT'),'Explicit matching control track');rows=deepcopy(list(schedule));require(rows and all(row['targets']==rows[0]['targets'] for row in rows),'Original fixed basket at all decisions')
 control._fixed_schedule_without_weight_normalization(rows)
 constraints=dict(max_single_weight=max_single_weight,min_single_weight=min_single_weight,top_weight_cap=top_weight_cap,minimum_effective_n_ratio=minimum_effective_n_ratio,risk_chain_top1_cap=risk_chain_top1_cap)
 for value in constraints.values():require(type(value)in(int,float) and math.isfinite(value) and 0<=value<=1,'Risk observation parameter')
 require(set(risk_chains_by_decision)=={r['decision_date'] for r in rows},'All original risk observations')
 slots=set(rows[0]['targets'])
 for chains in risk_chains_by_decision.values():require(set(chains)==slots and all(type(v)is str and v for v in chains.values()),'Full disclosed chain labels')
 common=dict(closes=closes,opens=opens,schedule=rows,corporate_actions=corporate_actions,external_flows=external_flows,initial_cash_usd=initial_cash_usd,minimum_cash_buffer_usd=minimum_cash_buffer_usd,valuation_end_date=valuation_end_date,transaction_cost_bps=transaction_cost_bps)
 if track=='CONTINUOUS':
  proxy=dict(vars(fractional.identity));proxy['_normalise_schedule']=control._fixed_schedule_without_weight_normalization
  execute=bind(fractional.simulate_dynamic_fractional_flow_split_research,{'identity':SimpleNamespace(**proxy)})
  result=execute(**common)
  observation_closes=fractional.frame(closes)
  for row in result['daily']:
   current=max(r['decision_date'] for r in rows if r['decision_date']<=row['session']);chains=risk_chains_by_decision[current]
   holdings=row.get('holdings',{});values={s:h['shares']*fractional.mark(observation_closes,fractional.day(row['session']),h['ticker']) for s,h in holdings.items()};row['risk']=observe(values,chains,constraints,slots)
 else:
  proxy=dict(vars(whole.identity));proxy['_normalise_schedule']=control._fixed_schedule_without_weight_normalization
  repair=dict(vars(whole.repair));repair['_risk_snapshot']=control._financial_snapshot
  execute=bind(whole.simulate_dynamic_frozen_flow_split_research,{'identity':SimpleNamespace(**proxy),'repair':SimpleNamespace(**repair),'projector':SimpleNamespace(project_whole_lot_rebalance=control._financial_projection)})
  result=control._restore_observations(execute(**common,risk_chains_by_decision=risk_chains_by_decision,**constraints))
  for row in result['daily']:row['risk']['risk_is_order_gate']=False
 result.update(schema='DYNAMIC_FIXED_INCUMBENT_USD_FLOW_SPLIT_CONTROL_V1',track=track,portfolio_track='fixed_incumbent_execution_control',original_targets=deepcopy(rows[0]['targets']),original_target_weights_modified=False,weights_normalized=False,risk_is_order_gate=False,candidate_eligibility_claimed=False,zero_share_target_slots_allowed=True,own_account_state=True,cross_track_execution_reused=False,benchmark_role='EXECUTABLE_FIXED_INCUMBENT_NOT_012922_NAV',formal_benchmark_passed=False,point_in_time_verified=False,promotion_allowed=False)
 result['source_hashes']={**getattr(whole,'_LOADED_SOURCES',{}),**LOADED};guard();return result
