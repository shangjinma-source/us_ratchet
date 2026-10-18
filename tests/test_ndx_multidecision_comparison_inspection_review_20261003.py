from copy import deepcopy
from decimal import Decimal,localcontext,Inexact
from fractions import Fraction
import hashlib,json,unittest
from unittest.mock import patch
from test_ndx_multidecision_path_comparison_inspection_research import sample,independent as r,producer


class Review(unittest.TestCase):
 def test_closed_form_all_pairs_and_no_producer_or_helper_call(self):
  measured=r.independently_measure(['2026-03-31','2026-04-01','2026-04-02'],[Fraction(1),Fraction(1,2),Fraction(4)])
  self.assertEqual(measured['maximum_drawdown'],{'numerator':'1','denominator':'2'})
  self.assertEqual(Decimal(measured['annualized_return_diagnostic_decimal']),Decimal(4**126-1))
  args,saved=sample()
  with patch.object(producer,'compare_multidecision_paths',side_effect=AssertionError('producer')),patch.object(producer,'account_twr_metrics',side_effect=AssertionError('metrics')):
   with localcontext() as context:
    context.prec=2;context.traps[Inexact]=True
    report=r.inspect_multidecision_comparison(saved_comparison=saved,**args)
  self.assertEqual(report['track_count'],16)
  for mutate in (lambda x:x['rows'][0]['candidate']['evidence'].update(reason='changed reason'),lambda x:x['rows'][8]['candidate']['saved_execution_diagnostics']['summary'].update(chained_twr=9),lambda x:x.update(coordinate_count=True)):
   bad=deepcopy(saved);mutate(bad)
   with self.assertRaises(ValueError):r.inspect_multidecision_comparison(saved_comparison=bad,**args)

 def test_source_flow_trace_identity_and_boundary_cannot_be_changed(self):
  args,_=sample();day=args['control_prepared']['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['closes']['index'][2]
  event=dict(session=day,amount_usd=0.,currency='USD',timing='BEFORE_OPEN',source_reference=dict(path='synthetic/zero-event',sha256='a'*64))
  trace=dict(event=event,event_id=hashlib.sha256(json.dumps(event,sort_keys=True,separators=(',',':')).encode()).hexdigest(),performance_boundary='AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_REBALANCE')
  for role in ('candidate','control'):
   args[role+'_prepared']['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['external_flows']=[deepcopy(event)]
   args[role+'_slots'][8]['result']['external_flows']=[deepcopy(trace)]
  saved=producer.compare_multidecision_paths(**args)
  self.assertEqual(r.inspect_multidecision_comparison(saved_comparison=saved,**args)['status'],'PASS')
  for key,value in [('event_id','b'*64),('performance_boundary','BEFORE_OLD_HOLDINGS_OPEN_MARK')]:
   bad=deepcopy(args);bad['candidate_slots'][8]['result']['external_flows'][0][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):r.inspect_multidecision_comparison(saved_comparison=saved,**bad)


if __name__=='__main__':unittest.main()
