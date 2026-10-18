import unittest,itertools,copy
from pathlib import Path
from unittest.mock import patch
from test_ndx_bulk_budgeted_search_schedule_research import args,plan,module
class ScheduleIndependentReview(unittest.TestCase):
 def test_multi_class_every_sid_cover_and_rank_against_tiny_oracle(self):
  settings=args(5);groups=[(f'I{i}',[f'S{i}A',f'S{i}B']) for i in range(5)]
  from scripts.bulk_all_k_plan_20261003 import prepare_lazy_plan
  p=settings['lazy_plan'];settings['lazy_plan']=prepare_lazy_plan(groups=groups,panel_reference=p['context']['panel_reference'],panel_audit_reference=p['context']['panel_audit_reference'],decision_cutoff=p['context']['decision_cutoff'],parameters=p['context']['parameters'],fitter_source_hashes=p['fitter_source_hashes'],previous_target_weights=None)
  settings['combinations_per_k']={4:12,5:12}
  for seed in ('0'*64,'f'*64):
   settings['seed_hex']=seed;result=module.plan_budgeted_positions(**settings);self.assertTrue(result['materialization_allowed'])
   for k in (4,5):
    oracle=[]
    for g in itertools.combinations(groups,k):
     oracle.extend(tuple(zip([x[0] for x in g],ss)) for ss in itertools.product(*[x[1] for x in g]))
    oracle.sort();positions=[x for x in result['positions'] if x['k']==k]
    self.assertEqual(len(positions),12);self.assertEqual(len({x['rank'] for x in positions}),12)
    self.assertEqual(set().union(*(set(x['prefix_security_ids']) for x in positions)),{s for _,ss in groups for s in ss})
    for pos in positions:self.assertEqual(pos['prefix_security_ids'],[s for _,s in oracle[pos['rank']]])
   self.assertFalse(result['uniform_combination_sampling_claimed']);self.assertFalse(result['global_optimum_proven'])
 def test_zero_budget_and_rehashed_proof_attack_failclosed(self):
  a=args();a['max_proposals']=0;r=module.plan_budgeted_positions(**a)
  self.assertEqual(r['positions'],[]);self.assertFalse(r['materialization_allowed']);self.assertEqual(r['status'],'INCOMPLETE_POINT_SELECTION')
  a=args();p=a['lazy_plan'];p['cardinalities'][0]['necessary_bound_certificates']=[];p.pop('content_sha256');p['content_sha256']=module.digest(p)
  with patch.object(module.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('early enumeration')):
   with self.assertRaises(ValueError):module.plan_budgeted_positions(**a)
 def test_strata_partition_and_bigint_no_domain_truncation(self):
  a=args(76);a['combinations_per_k']={k:32 for k in a['combinations_per_k']};r=module.plan_budgeted_positions(**a)
  self.assertEqual(len(r['positions']),544);self.assertTrue(any(x['rank']>2**53 for x in r['positions']))
  for k in a['combinations_per_k']:
   strata=[x for x in r['strata'] if x['k']==k];self.assertEqual(strata[0]['start'],0);self.assertEqual(strata[-1]['stop'],a['lazy_plan']['cardinalities'][k-1]['combination_count']);self.assertTrue(all(x['stop']==y['start'] for x,y in zip(strata,strata[1:])))
   cover=next(c for c in r['cardinality_coverage'] if c['k']==k);self.assertTrue(cover['all_security_ids_covered']);self.assertEqual(sum(cover['security_exposures'].values()),32*k)
  self.assertEqual(r['planned_canonical_task_count'],a['lazy_plan']['planned_canonical_task_count']);self.assertEqual(r['completed_task_count'],0)
if __name__=='__main__':unittest.main()
