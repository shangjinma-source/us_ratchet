"""Independent synthetic expected metrics; never calls production metrics/compare."""
import copy,types,unittest
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,Context,localcontext,Inexact
from backtest import ndx_cash_neighbor_path_comparison_inspection_research as m
ROOT=Path(__file__).resolve().parents[1]
def q(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def metric(cal,w):
 n=len(cal)-1;peak=w[0];dd=F(0)
 for x in w:peak=max(peak,x);dd=max(dd,1-x/peak)
 with localcontext(Context(prec=80)):annual=str((Decimal(w[-1].numerator)/Decimal(w[-1].denominator))**(Decimal(252)/n)-1)
 return dict(observation_count=len(cal),interval_count=n,wealth=[dict(session=d,normalized_wealth=q(v))for d,v in zip(cal,w)],cumulative_return=q(w[-1]-1),maximum_drawdown=q(dd),initial_one_in_drawdown=True,annualized_return_calculated=True,annualized_return_diagnostic_decimal=annual,annualization=dict(formula='terminal_normalized_wealth ** (252 / interval_count) - 1',sessions_per_year=252,interval_count=n,decimal_precision=80,rounding='ROUND_HALF_EVEN',arithmetic='DECIMAL80_POWER_FROM_EXACT_TERMINAL_FRACTION_NOT_EXACT_RATIONAL_ANNUALIZATION',annualization_is_historical_diagnostic=True,short_window_below_252_intervals=n<252,short_window_limitation='SHORT_WINDOW_COMPOUNDING_CAN_MAGNIFY_SMALL_MOVES_NOT_LONG_TERM_EVIDENCE',formal_admission_allowed=False))
def fixture():
 # Reuse only the author's synthetic case-shape construction; intercept its sole metric call.
 code=(ROOT/'tests/test_ndx_cash_neighbor_path_comparison_research.py').read_text()
 code=code[:code.index('class Tests')].replace('from backtest import ndx_cash_neighbor_path_comparison_research as m','')
 ns={'m':types.SimpleNamespace(LANES=m.LANES,CLOCKS=m.CLOCKS,ratio=q,metrics_core=types.SimpleNamespace(metrics=metric))};exec(compile(code,'synthetic_cases','exec'),ns);a=ns['fixture']();rows=[]
 for i,c in enumerate(a['cases']):
  cal=c['calendar'];wealth=[F(1)]*len(cal)
  if i==0:wealth[1]=F(2);wealth[2]=F(1,2);wealth[-1]=F(11,10)
  for j,v in enumerate(wealth[1:]):c['candidate']['account']['rows'][j]['cumulative_twr']=q(v-1)
  c['candidate']['account']['chained_twr']=q(wealth[-1]-1)
  metrics={r:copy.deepcopy(c['saved_reference_metrics'][r]['metrics'])for r in m.ROLES};metrics['candidate']=metric(cal,wealth)
  for r,d in metrics.items():d.update(currency_label='CNY'if r==m.ROLES[2]else 'USD',currency_label_is_saved_conditional_assumption=True,uses_saved_chained_twr=r!=m.ROLES[2],formal_admission_allowed=False)
  ca=metrics['candidate'];ann=ca['annualized_return_diagnostic_decimal'];dd=ca['maximum_drawdown'];diff={r:dict(cumulative_return=ca['cumulative_return'],maximum_drawdown=dd,annualized_return_diagnostic_decimal=ann,annual_arithmetic='DECIMAL80_DIFFERENCE_OF_SAVED_DIAGNOSTICS',formal_gate=False)for r in m.ROLES}
  with localcontext(Context(prec=80)):ann=str(Decimal(ann)-Decimal(metrics[m.ROLES[2]]['annualized_return_diagnostic_decimal']));zero=str(Decimal(metrics[m.ROLES[0]]['annualized_return_diagnostic_decimal'])-Decimal(metrics[m.ROLES[2]]['annualized_return_diagnostic_decimal']))
  for v in diff.values():v['annualized_return_diagnostic_decimal']=ann
  distances={r:dict(annualized_return_absolute_distance_diagnostic_decimal=ann if r=='candidate'else zero,maximum_drawdown_absolute_distance=dd if r=='candidate'else q(F(0)),currency_scope='NORMALIZED_ORIGINAL_CURRENCY_DIAGNOSTIC_NOT_USD_EQUIVALENT_NAV',formal_gate=False)for r in ('candidate',m.ROLES[1],m.ROLES[0])}
  rows.append(dict(scenario_index=i,scenario_id=c['scenario_id'],original_case_evidence=copy.deepcopy(c),calendar=cal,metrics=metrics,candidate_status='AVAILABLE_NEW',candidate_absence_reason=None,nav_observation_lags=[dict(session=v['session'],nav_date=v['nav_date'],calendar_day_lag=0,publication_time=None,publication_time_verified=False,source_reference=copy.deepcopy(v['reference']))for v in c['nav_rows']],nav_absolute_distance_diagnostics=distances,candidate_minus_references=diff,candidate_minus_incumbent_nav_distance=dict(annualized_absolute_distance_difference_diagnostic_decimal=ann,maximum_drawdown_absolute_distance_difference=dd,formal_noninferiority=False),policy_asymmetry=m.ASYMMETRY,nav_currency='CNY',saved_reference_metrics_recomputed=False,nav_is_same_flow_executable_account=False,short_and_unequal_windows_not_aggregated=True,**dict.fromkeys(m.FLAGS,False)))
 out=dict(schema='CASH_NEIGHBOR_PER_CASE_REFERENCE_COMPARISON_V1',scenario_count=40,rows=rows,incumbent_path_count=10,candidate_status_counts={k:40 if k=='AVAILABLE_NEW'else 0 for k in m.STATUSES},reference_metrics_dependency_sha256='0d21fb1cf1580de186ad684b98f0e7704ae63ebc592bc166f1741860d7aea163',policy_asymmetry=m.ASYMMETRY,source_scope='CALLER_SUPPLIED_SAVED_PATHS_AND_REFERENCES_NOT_BYTE_AUTHENTICATION',formal_cohort_statistics_computed=False,annualization_is_historical_diagnostic=True,**dict.fromkeys(m.FLAGS,False))
 return a,out
class Review(unittest.TestCase):
 def test_midwindow_peak_valley_and_forty_order(self):
  a,out=fixture();self.assertEqual(out['rows'][0]['metrics']['candidate']['maximum_drawdown'],q(F(3,4)))
  with localcontext()as c:c.prec=2;c.traps[Inexact]=True;self.assertEqual(m.inspect_comparison(**a,comparison=out)['scenario_count'],40)
  for mode in ('dd','order','count','flow','role'):
   b,v=copy.deepcopy((a,out))
   if mode=='dd':v['rows'][0]['metrics']['candidate']['maximum_drawdown']=q(F(0))
   elif mode=='order':v['rows'][0],v['rows'][1]=v['rows'][1],v['rows'][0]
   elif mode=='count':v['scenario_count']=True
   elif mode=='flow':b['cases'][0]['candidate']['account']['rows'][1]['cash_injection_usd']='1000';v['rows'][0]['original_case_evidence']=copy.deepcopy(b['cases'][0])
   else:v['rows'][0]['metrics'][m.ROLES[2]]['currency_label']='USD'
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_comparison(**b,comparison=v)
 def test_annual_tolerance_reference_and_absence(self):
  cal=['2023-08-31','2023-09-01'];w=[F(1),F(101,100)];d=metric(cal,w);d.update(currency_label='USD',currency_label_is_saved_conditional_assumption=True,uses_saved_chained_twr=True,formal_admission_allowed=False)
  m.candidate_metrics(d,cal,w)
  with localcontext(Context(prec=160)):d['annualized_return_diagnostic_decimal']=str(Decimal(d['annualized_return_diagnostic_decimal'])+Decimal('1e-60'))
  with self.assertRaises(ValueError):m.candidate_metrics(d,cal,w)
  a,out=fixture();c=a['cases'][0];r=out['rows'][0];c['candidate'].update(status='TECHNICAL_FAILURE',reason='saved exception',account=None,account_reference=None,accounting_inputs=None,inputs_reference=None);r.update(original_case_evidence=copy.deepcopy(c),candidate_status='TECHNICAL_FAILURE',candidate_absence_reason='saved exception',candidate_minus_references=None,candidate_minus_incumbent_nav_distance=None);r['metrics']['candidate']=None;r['nav_absolute_distance_diagnostics']['candidate']=None
  self.assertFalse(m.inspect_case(case=c,comparison_row=r,scenario_index=0)['candidate_metrics_reconstructed'])
  r['metrics']['candidate']=metric(c['calendar'],[F(1)]*len(c['calendar']))
  with self.assertRaises(ValueError):m.inspect_case(case=c,comparison_row=r,scenario_index=0)
 def test_source_roles_shared_paths_and_false_authority(self):
  a,out=fixture()
  for mode in ('pointer','shared','navfuture','scope','countbool'):
   b,v=copy.deepcopy((a,out));c=b['cases'][0];r=v['rows'][0]
   if mode=='pointer':c['candidate']['account_reference']['json_pointer']='not-a-pointer'
   elif mode=='shared':c['incumbent']['account_reference']['sha256']='f'*64
   elif mode=='navfuture':c['nav_rows'][0]['nav_date']='2023-05-01'
   elif mode=='scope':r['nav_is_same_flow_executable_account']=True
   else:v['candidate_status_counts']['TECHNICAL_FAILURE']=False
   r['original_case_evidence']=copy.deepcopy(c)
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_comparison(**b,comparison=v)
if __name__=='__main__':unittest.main()
