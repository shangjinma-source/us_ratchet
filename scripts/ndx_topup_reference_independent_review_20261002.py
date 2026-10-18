"""Read saved four-role comparisons independently; no production module imports."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,Context,localcontext
from datetime import date
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'data/cache/research/topup_reference_comparison_20261002_v1'
RESULT_SHA='169eeb4158e95829240263c05d04285695151db98000356f3b05b00ca8e5553f'
PUBLICATION_SHA='2c048cdfb7357a0df844226d2bef6fd54b501fa7da91b1b4a789d476827157b7'
PINS={'accounts': ('data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json', '7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'), 'publication': ('data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json', 'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'), 'benchmark': ('data/cache/research/return_six_period_benchmarks_20260923_v1/benchmarks.json', 'ef7ccdbe45a95fdf616d1b681bf9cd5c431db01585d30cf979e5cd4f2d45b423'), 'currency_manifest': ('data/cache/research/fund_012922_currency_source_20261002_v1/manifest.json', 'ff4f51f7463f0c805f6ae0542aea46883ba2476b416364d293d93d7026a5b284'), 'currency_html': ('data/cache/research/fund_012922_currency_source_20261002_v1/issuer_listing.html', '89f8a7a02aa843193bbfab8acd3a273ff7053d69fcc4256f242eb453dc43d292'), 'pure': ('backtest/ndx_cash_fork_reference_window_research.py', '0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163')}
def load(path,h):
 raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==h;return json.loads(raw)
def ratio(x):return F(int(x['numerator']),int(x['denominator']))
def ref(role,pointer=None):
 path,h=PINS[role];v=dict(path=str(ROOT/path),sha256=h)
 if pointer is not None:v['json_pointer']=pointer
 return v

def run():
 result=load(OUTPUT/'comparison.json',RESULT_SHA);pub=load(OUTPUT/'publication.json',PUBLICATION_SHA)
 docs={r:load(ROOT/p,h) for r,(p,h) in PINS.items() if r not in ('pure','currency_html')}
 assert pub['comparison_reference']==dict(path=str(OUTPUT/'comparison.json'),sha256=RESULT_SHA)
 assert pub['source_hashes']==result['source_hashes'] and pub['status']=='PUBLISHED_FOUR_ROLE_DIAGNOSTICS_NOT_FORMAL_ADMISSION'
 for path,h in result['source_hashes'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 assert len(result['source_hashes'])==7
 for r,(p,h) in PINS.items():
  assert result['input_references'][r]==ref(r) and result['source_hashes'][str(ROOT/p)]==h
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
 assert result['currency_manifest_preserved']==docs['currency_manifest']
 assert docs['currency_manifest']['source_reference']==ref('currency_html')
 benchmark=docs['benchmark'];accounts=docs['accounts'];calendar=benchmark['calendar']
 assert result['benchmark_metadata_without_saved_paths']=={k:v for k,v in benchmark.items() if k not in ('incumbent','nav')}
 assert result['incumbent_metadata_without_path']=={k:v for k,v in benchmark['incumbent'].items() if k!='daily'}
 assert result['nav_metadata_without_path']=={k:v for k,v in benchmark['nav'].items() if k!='rows'}
 flags=('old_accounts_reexecuted','old_benchmark_reexecuted','nav_producer_called','formal_dual_benchmark_admission','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','cross_window_ranking_performed','full_transitive_source_closure_reverified','nav_dataset_currency_binding_certified','historical_2023_class_continuity_verified','currency_fx_equivalence_verified','nav_publication_time_verified','same_flow_incumbent_policy_modelled')
 for f in flags:assert result[f] is pub[f] is False
 assert result['annualized_return_calculated'] is pub['annualized_return_calculated'] is True
 assert len(result['rows'])==len(accounts['rows'])==40 and result['comparison_role_count']==4
 count=0;max_relative=Decimal(0);max_absolute=Decimal(0);max_lag=0;summary=[]
 for i,(row,parent) in enumerate(zip(result['rows'],accounts['rows'])):
  source=parent['input_row'];event=source['cash_event'];start=calendar.index(event['decision_date']);window=calendar[start:];days=window[1:];n=len(days)
  assert row['input_row']==source and row['scenario_id']==parent['scenario_id'] and row['cash_event']==event
  assert row['paired_row_reference']==ref('accounts',f'/rows/{i}')
  assert row['saved_topup_context']==parent['topup_context'] and row['saved_selected_plan_reference']==parent['selected_plan_reference']
  assert row['saved_initial_state']==parent['paths']['candidate']['accounting_inputs']['initial']
  assert row['initial_reference']==ref('accounts',f'/rows/{i}/paths/candidate/accounting_inputs/initial')
  comparison=row['comparison'];assert comparison['calendar']==window
  values={};metrics={};flows={}
  for role in ('candidate','same_flow_zero_trade_control'):
   path=parent['paths'][role];daily=path['account']['rows'];assert [r['session'] for r in daily]==days
   values[role]=[F(1)]+[1+ratio(r['cumulative_twr']) for r in daily]
   assert row['observations'][role]==[dict(reference=ref('accounts',f'/rows/{i}/paths/{role}/account/rows/{j}'),source_row=r) for j,r in enumerate(daily)]
   flows[role]=[dict(session=r['session'],amount_usd=r['cash_injection_usd'],timing=path['account']['cash_event_timing']) for r in daily if F(r['cash_injection_usd'])]
  assert flows['candidate']==flows['same_flow_zero_trade_control']==comparison['candidate_flow_events']==comparison['control_flow_events']
  assert len(flows['candidate'])==1 and flows['candidate'][0]['session']==event['execution_date'] and F(flows['candidate'][0]['amount_usd'])==F(event['amount_usd'])
  for role,observations,key,field in [('saved_incumbent_different_flow_reference','saved_incumbent','incumbent','total_value_usd'),('fund_012922_cny_nav_reference','fund_nav','nav','nav')]:
   parent_rows=benchmark[key]['daily' if key=='incumbent' else 'rows'];subset=parent_rows[start:]
   assert [r['session'] for r in subset]==window
   literals=[F(str(r[field])) for r in subset];assert all(type(r[field]) is float for r in subset)
   values[role]=[x/literals[0] for x in literals]
   assert row['observations'][observations]==[dict(reference=ref('benchmark',f'/{key}/{"daily" if key=="incumbent" else "rows"}/{start+j}'),source_row=r,value_field=field,encoding='SAVED_JSON_FLOAT_TO_STR_NO_PRECISION_UPGRADE') for j,r in enumerate(subset)]
  lags=[];same_nav={}
  for r in benchmark['nav']['rows'][start:]:
   assert r['nav_date']<=r['session'];v=F(str(r['nav']))
   assert r['nav_date'] not in same_nav or same_nav[r['nav_date']]==v;same_nav[r['nav_date']]=v
   lag=(date.fromisoformat(r['session'])-date.fromisoformat(r['nav_date'])).days
   lags.append(dict(session=r['session'],nav_date=r['nav_date'],calendar_day_lag=lag,publication_time=None,publication_time_verified=False,tradable_at_us_open_verified=False))
  assert comparison['nav_observation_lags']==lags and comparison['nav_max_calendar_day_lag']==max(x['calendar_day_lag'] for x in lags)
  max_lag=max(max_lag,comparison['nav_max_calendar_day_lag'])
  assert set(values)==set(comparison['roles'])
  for role,wealth in values.items():
   assert wealth[0]==1 and all(v>0 for v in wealth);peak=F(1);dd=F(0)
   for v in wealth:peak=max(peak,v);dd=max(dd,1-v/peak)
   metrics[role]=(wealth[-1]-1,dd);saved=comparison['roles'][role]
   assert saved['observation_count']==n+1 and saved['interval_count']==n
   assert ratio(saved['cumulative_return'])==wealth[-1]-1 and ratio(saved['maximum_drawdown'])==dd
   assert [x['session'] for x in saved['wealth']]==window and [ratio(x['normalized_wealth']) for x in saved['wealth']]==wealth
   assert saved['initial_one_in_drawdown'] is True and saved['formal_admission_allowed'] is False
   assert saved['currency_label']==('CNY' if role=='fund_012922_cny_nav_reference' else 'USD')
   assert saved['flow_equivalent_to_candidate'] is (role=='same_flow_zero_trade_control')
   assert saved['uses_saved_chained_twr'] is (role in ('candidate','same_flow_zero_trade_control'))
   annual=saved['annualization'];assert annual['sessions_per_year']==252 and annual['interval_count']==n and annual['decimal_precision']==80
   assert annual['short_window_below_252_intervals'] is (n<252) and annual['formal_admission_allowed'] is False
   assert annual['annualization_is_historical_diagnostic'] is True and saved['annualized_return_calculated'] is True
   with localcontext(Context(prec=110)):
    terminal=Decimal(wealth[-1].numerator)/Decimal(wealth[-1].denominator)
    expected=(terminal.ln()*Decimal(252)/Decimal(n)).exp()-1
    reported=Decimal(saved['annualized_return_diagnostic_decimal']);error=abs(reported-expected);relative=error/max(Decimal(1),abs(expected))
    assert relative<=Decimal('1e-70'),(i,role,error)
    max_relative=max(max_relative,relative);max_absolute=max(max_absolute,error)
   count+=1
  for role,entry in comparison['comparisons'].items():
   assert ratio(entry['candidate_minus_reference_return'])==metrics['candidate'][0]-metrics[role][0]
   assert ratio(entry['candidate_minus_reference_drawdown'])==metrics['candidate'][1]-metrics[role][1]
   assert entry['formal_benchmark_gate'] is False
   assert entry['scope']==('SAME_FLOW_LOCAL_ZERO_TRADE_CONTROL' if role=='same_flow_zero_trade_control' else 'RETROSPECTIVE_REFERENCE_DIFFERENT_FLOW_OR_CURRENCY')
  for f in ('formal_dual_benchmark_admission','point_in_time_verified','promotion_allowed','orders_executed','economic_winner_selected','cross_window_ranking_performed','currency_fx_equivalence_verified','nav_publication_time_verified','subscription_execution_equivalence_verified','nav_dataset_currency_binding_certified','incumbent_same_injection_response_modelled'):assert comparison[f] is False
  for f in flags:assert row[f] is False
  assert comparison['missing_observation_count']==0
  summary.append(dict(scenario=row['scenario_id'],intervals=n,nav_max_lag=comparison['nav_max_calendar_day_lag']))
 assert count==160
 assert hashlib.sha256((OUTPUT/'comparison.json').read_bytes()).hexdigest()==RESULT_SHA and hashlib.sha256((OUTPUT/'publication.json').read_bytes()).hexdigest()==PUBLICATION_SHA
 for r,(p,h) in PINS.items():assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h
 return dict(windows=40,roles=160,annualization_checks=count,max_annualization_absolute_error=str(max_absolute),max_annualization_scaled_error=str(max_relative),nav_max_calendar_day_lag=max_lag,rows=summary)
if __name__=='__main__':print(json.dumps(run(),indent=2))
