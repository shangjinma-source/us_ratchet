"""Saved-only independent same-flow comparison readback. No producer imports."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,Context,localcontext
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data/cache/research/topup_same_flow_comparison_20261002_v1'
RESULT_SHA='53e99a06b926fef2c6bc7b761ad03d3fefabdf43b5bf70b09b6829294bcf5a8c'
PUBLICATION_SHA='b5947018e6b96596ed3cbdb7d3cade2f53399dee06b7df77454f9385435bb650'
PAIRED_SHA='7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'
INCUMBENT_SHA='d1ac38ebe7674756d67cdc390938a6dffbe0d4f45c25e7b10726fab5642dc36a'
FLAGS=('formal_dual_benchmark_admission','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','cross_window_ranking_performed','win_rate_calculated','account_simulation_called','saved_candidates_reselected','source_bytes_authenticated_by_this_pure_module','full_transitive_source_closure_reverified','historical_price_identity_certified','fx_equivalence_verified','total_return_claimed','candidate_decision_time_executability_verified','decision_information_sets_equivalent','execution_policies_equivalent','executable_strategy_advantage_claimed')
ASYMMETRY={'candidate_quantity_information':'HISTORICAL_CONDITIONAL_SEARCH_USING_EXECUTION_OPEN_PRICES','incumbent_quantity_information':'PRIOR_DECISION_CLOSE_FROZEN_NO_OPEN_REPLAN','candidate_later_policy':'ONE_OFF_TOPUP_THEN_FIXED_HOLDINGS','incumbent_later_policy':'ORIGINAL_SCHEDULE_REBALANCES_USING_COUNTERFACTUAL_OWN_STATE','scope':'MATCHED_INITIAL_STATE_AND_FLOW_DO_NOT_CERTIFY_MATCHED_INFORMATION_OR_EXECUTABLE_ADVANTAGE'}
def load(path,digest):
 raw=Path(path).read_bytes(); assert hashlib.sha256(raw).hexdigest()==digest; return json.loads(raw)
def ratio(x): return F(int(x['numerator']),int(x['denominator']))
def ptr(ref,path): return dict(ref,json_pointer=path)
def run():
 assert RESULT_SHA is not None and PUBLICATION_SHA is not None,'Pending actual pins'
 out=load(OUTPUT/'comparison.json',RESULT_SHA); pub=load(OUTPUT/'publication.json',PUBLICATION_SHA)
 assert {p.name for p in OUTPUT.iterdir()}=={'started.json','comparison.json','publication.json'}
 assert pub['comparison_reference']==dict(path=str(OUTPUT/'comparison.json'),sha256=RESULT_SHA)
 assert pub['source_hashes']==out['source_hashes'] and pub['status']=='PUBLISHED_CONDITIONAL_DIAGNOSTIC_COMPARISON'
 sources=out['source_hashes']; refs=out['input_references']; assert len(sources)==7 and len(refs)==6
 for p,h in sources.items(): assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
 for ref in refs.values(): assert sources[ref['path']]==ref['sha256']
 assert refs['paired_accounts']['sha256']==PAIRED_SHA and refs['incumbent_accounts']['sha256']==INCUMBENT_SHA
 paired=load(refs['paired_accounts']['path'],PAIRED_SHA); inc=load(refs['incumbent_accounts']['path'],INCUMBENT_SHA)
 for prefix in ('paired','incumbent'):
  receipt=load(refs[prefix+'_publication']['path'],refs[prefix+'_publication']['sha256']); parent=paired if prefix=='paired' else inc
  assert receipt['account_reference']==refs[prefix+'_accounts'] and receipt['source_hashes']==parent['source_hashes']
 assert out['scenario_count']==40 and out['incumbent_path_count']==10 and len(out['rows'])==40
 assert out['policy_asymmetry']==ASYMMETRY
 for k in FLAGS: assert out[k] is False
 assert out['wealth_arithmetic']=='SAVED_CUMULATIVE_TWR_PLUS_ONE_NOT_ACCOUNT_EQUITY_RATIO'
 mapping={r['scenario_id']:(i,r) for i,r in enumerate(inc['scenario_mappings'])}; paths={r['path_id']:(i,r) for i,r in enumerate(inc['paths'])}
 assert len(mapping)==40 and len(paths)==10; counts=0; maxerr=Decimal(0); maxdifferr=Decimal(0)
 for i,(row,parent) in enumerate(zip(out['rows'],paired['rows'])):
  mi,mp=mapping[parent['scenario_id']]; pi,path=paths[mp['path_id']]; ca=parent['paths']['candidate']; ia=path['account']; event=parent['input_row']['cash_event']
  assert row['scenario_id']==parent['scenario_id'] and row['input_row']==parent['input_row']==mp['original_input_row']
  assert row['original_input_reference']==parent['input_reference']==mp['input_reference']
  assert row['candidate_paired_row_reference']==ptr(refs['paired_accounts'],f'/rows/{i}')
  assert row['incumbent_path_reference']==ptr(refs['incumbent_accounts'],f'/paths/{pi}')
  assert row['incumbent_mapping_reference']==ptr(refs['incumbent_accounts'],f'/scenario_mappings/{mi}') and row['incumbent_mapping_preserved']==mp
  assert row['candidate_selected_plan_reference']==parent['selected_plan_reference'] and row['candidate_topup_context']==parent['topup_context']
  left=ca['accounting_inputs']['initial']; right=ia['initial']
  assert row['candidate_initial_state']==left and row['incumbent_initial_state']==right
  assert left['session']==right['session']==event['decision_date'] and left['holdings']==right['holdings']
  assert F(left['cash_usd'])==F(right['cash_usd']) and {s:F(p) for s,p in left['close_prices'].items()}=={s:F(p) for s,p in right['close_prices'].items()}
  assert F(ca['accounting_inputs']['transaction_cost_bps'])==F(ia['transaction_cost_bps'])
  cd=ca['account']['rows']; idaily=ia['daily']; days=[x['session'] for x in cd]
  assert days==[x['session'] for x in idaily] and row['calendar']==[left['session']]+days and days[0]==event['execution_date']
  calendar=row['calendar']; n=len(days); assert calendar==sorted(set(calendar))
  assert ca['account']['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES'
  assert ia['cash_event_timing']=='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_SIGNED_TRADES_AND_FEES'
  for j,(l,r) in enumerate(zip(cd,idaily)): assert F(l['cash_injection_usd'])==F(r['cash_injection_usd'])==(F(event['amount_usd']) if j==0 else 0)
  metrics={}; annual={}
  for role,daily,ref,base in [('candidate',cd,refs['paired_accounts'],f'/rows/{i}/paths/candidate/account/rows'),('same_flow_incumbent',idaily,refs['incumbent_accounts'],f'/paths/{pi}/account/daily')]:
   assert row['observations'][role]==[dict(reference=ptr(ref,f'{base}/{j}'),source_row=d) for j,d in enumerate(daily)]
   wealth=[F(1)]+[1+ratio(d['cumulative_twr']) for d in daily]; assert all(v>0 for v in wealth)
   peak=F(1); dd=F(0)
   for v in wealth: peak=max(peak,v); dd=max(dd,1-v/peak)
   metric=row['metrics'][role]; metrics[role]=(wealth[-1]-1,dd)
   assert ratio(metric['cumulative_return'])==wealth[-1]-1 and ratio(metric['maximum_drawdown'])==dd
   assert metric['interval_count']==n and metric['observation_count']==n+1 and metric['initial_one_in_drawdown'] is True
   assert metric['wealth']==[dict(session=day,normalized_wealth=dict(numerator=str(v.numerator),denominator=str(v.denominator))) for day,v in zip(calendar,wealth)]
   spec=metric['annualization']; assert spec['sessions_per_year']==252 and spec['interval_count']==n and spec['decimal_precision']==80 and spec['rounding']=='ROUND_HALF_EVEN' and spec['formal_admission_allowed'] is False and spec['annualization_is_historical_diagnostic'] is True
   with localcontext(Context(prec=110)):
    exact=( (Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator)).ln()*Decimal(252)/Decimal(n)).exp()-1
    saved=Decimal(metric['annualized_return_diagnostic_decimal']); error=abs(saved-exact)/max(Decimal(1),abs(exact)); assert error<Decimal('1e-70'); maxerr=max(maxerr,error); annual[role]=exact
   counts+=1
  diff=row['candidate_minus_incumbent']; assert ratio(diff['cumulative_return'])==metrics['candidate'][0]-metrics['same_flow_incumbent'][0]
  assert ratio(diff['maximum_drawdown'])==metrics['candidate'][1]-metrics['same_flow_incumbent'][1]
  with localcontext(Context(prec=110)):
   expected=annual['candidate']-annual['same_flow_incumbent']; actual=Decimal(diff['annualized_return_diagnostic_decimal'])
   error=abs(actual-expected)/max(Decimal(1),abs(annual['candidate']),abs(annual['same_flow_incumbent'])); assert error<Decimal('1e-70'); maxdifferr=max(maxdifferr,error)
  assert diff['annual_difference_precision']==80 and diff['annual_difference_is_historical_diagnostic'] is True
  assert row['policy_asymmetry']==ASYMMETRY
  for k in FLAGS: assert row[k] is False
 for p,h in sources.items(): assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h
 assert hashlib.sha256((OUTPUT/'comparison.json').read_bytes()).hexdigest()==RESULT_SHA and hashlib.sha256((OUTPUT/'publication.json').read_bytes()).hexdigest()==PUBLICATION_SHA
 return dict(scenarios=40,metrics=counts,differences=40,max_annual_scaled_error=str(maxerr),max_annual_difference_scaled_error=str(maxdifferr),direct_sources=len(sources),formal_admission=False)
if __name__=='__main__': print(json.dumps(run(),indent=2))
