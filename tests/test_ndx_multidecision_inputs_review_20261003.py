"""Independent causal slice oracle, no saved inputs or fitting."""
from copy import deepcopy
from fractions import Fraction
from itertools import combinations
import unittest
from test_ndx_multidecision_training_inputs_research import fixture,m


def sync(channel):
 channel['training_returns']=deepcopy(channel['return_rows'][:126]);channel['evaluation_returns']=deepcopy(channel['return_rows'][126:])
 channel['training_returns_sha256']=m.digest(channel['training_returns']);channel['evaluation_returns_sha256']=m.digest(channel['evaluation_returns'])


class Tests(unittest.TestCase):
 def test_marked_returns_prove_126_predecessor_and_no_future(self):
  a=fixture();calendar=a['channels_document']['calendar253']
  for n,row in enumerate(a['channels_document']['rows']):
   ch=row['channel']
   for j,r in enumerate(ch['return_rows']):
    value=Fraction((n+1)*1000+j,1000000);r.update(split_only_return_exact=str(value),split_only_return_float=float(value))
   sync(ch)
  before=deepcopy(a);out=m.prepare_multidecision_inputs(**a);self.assertEqual(a,before)
  for period in out['periods']:
   cutoff=calendar.index(period['decision_date']);eligible=[r for r in a['channels_document']['rows'][0]['channel']['return_rows'] if r['session']<=period['decision_date']][-126:]
   self.assertEqual(len(eligible),126)
   ticker=a['channels_document']['rows'][0]['coordinate']['ticker'];column=period['returns']['columns'].index(ticker)
   self.assertEqual([r[column]for r in period['returns']['data']],[r['split_only_return_float']for r in eligible])
   self.assertEqual(period['training_price_predecessor'],eligible[0]['previous_session'])
   self.assertEqual(period['returns']['index'][-1],calendar[cutoff]+'T00:00:00')
   self.assertLess(period['decision_date'],period['execution_date'])
  ch=a['channels_document']['rows'][0]['channel'];ch['return_rows'][-1].update(split_only_return_exact='3/4',split_only_return_float=.75);sync(ch)
  after=m.prepare_multidecision_inputs(**a)
  self.assertEqual(out['periods'][0]['training_frame_sha256'],after['periods'][0]['training_frame_sha256'])

 def test_inventory_shareclasses_and_unresolved_prior_not_empty_weights(self):
  a=fixture();out=m.prepare_multidecision_inputs(**a);inv=a['expected_security_inventory']
  oracle=[sum(len({x['issuer_id']for x in combo})==k for combo in combinations(inv,k))for k in range(1,4)]
  self.assertEqual([r['combination_count']for r in out['all_k_issuer_unique_combination_counts']],oracle)
  self.assertEqual(out['security_count'],4);self.assertEqual(out['issuer_count'],3)
  for n,p in enumerate(out['periods']):
   self.assertIsNone(p['prior_dependency']['previous_target_weights']);self.assertIs(p['prior_dependency']['dependency_resolved'],n==0)
   self.assertIsNone(p['numerical_task_id']);self.assertFalse(p['task_materialization_allowed'])
  self.assertTrue(all(out[k]is False for k in m.FLAGS))

 def test_resigned_source_errors_and_invented_prior_rejected(self):
  for mode in ('predecessor','bool','prior','missing_sid','source_authority'):
   a=fixture();ch=a['channels_document']['rows'][0]['channel']
   if mode=='predecessor':ch['return_rows'][126]['previous_session']=ch['return_rows'][126]['session'];sync(ch)
   elif mode=='bool':ch['return_rows'][0]['split_only_return_float']=False;sync(ch)
   elif mode=='prior':a['decision_path_contract']['prior']={}
   elif mode=='missing_sid':a['expected_security_inventory'].pop()
   else:a['channels_document']['future_independent_oos']=0
   with self.subTest(mode=mode),self.assertRaises(ValueError):m.prepare_multidecision_inputs(**a)


if __name__=='__main__':unittest.main()
