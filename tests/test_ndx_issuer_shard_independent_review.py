"""Synthetic counts and conservative boundary checks, never combinations or fits."""
from fractions import Fraction
import unittest
from unittest.mock import patch
import test_ndx_issuer_shard_prepare_research as fixture

m=fixture.m


class IndependentShardReview(unittest.TestCase):
    def test_multiple_certificates_exclude_each_combination_only_once(self):
        args=fixture.arguments();plan=m.prepare_issuer_shards(**args)
        multiplicities=[len(s) for _,s in args['groups']]
        product=1
        for n in multiplicities:product*=1+n
        self.assertEqual(plan['all_k_combination_count'],product-1)
        excluded=sum(c['combination_count'] for c in plan['cardinalities'] if c['necessary_bound_certificates'])
        self.assertEqual(plan['necessary_bound_excluded_combination_count'],excluded)
        self.assertGreater(len(plan['cardinalities'][0]['necessary_bound_certificates']),1)
        self.assertEqual(plan['remaining_canonical_task_count'],3*(product-1-excluded))

    def test_top3_rounding_padding_near_boundary_does_not_falsely_exclude(self):
        for cap,excluded in ((.75-1e-10,False),(.75-1e-6,True)):
            args=fixture.arguments();args['parameters']['top_weight_cap']=cap
            plan=m.prepare_issuer_shards(**args);row=next(c for c in plan['cardinalities'] if c['k']==4)
            top=[c for c in row['necessary_bound_certificates'] if c['reason']=='TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP']
            self.assertEqual(bool(top),excluded)
            if top:
                c=top[0];left=Fraction(int(c['left']['numerator']),int(c['left']['denominator']))
                right=Fraction(int(c['right']['numerator']),int(c['right']['denominator']))
                self.assertGreater(left,right)

    def test_prior_exited_class_is_retained_and_all_three_specs_remain(self):
        args=fixture.arguments();args['previous_target_weights']={'OLD_CLASS_A_EXITED':.6,'a1':.4}
        with (patch.object(m.indexing.IssuerCombinationIndex,'rank',side_effect=AssertionError('enumeration')),
              patch.object(m.indexing.IssuerCombinationIndex,'unrank',side_effect=AssertionError('enumeration'))):
            plan=m.prepare_issuer_shards(**args)
        for shard in plan['shards']:
            self.assertEqual(shard['previous_target_weights'],args['previous_target_weights'])
            self.assertEqual(shard['completed_canonical_task_count'],0)
            self.assertEqual(shard['remaining_canonical_task_count'],3*(shard['stop']-shard['start']))
        self.assertEqual(len(plan['context']['weight_specs']),3)
        self.assertFalse(plan['anchor_alias_equivalence_verified'])
        self.assertFalse(plan['risk_feasibility_proven'])

    def test_range_partition_and_context_bind_shard_size(self):
        args=fixture.arguments();a=m.prepare_issuer_shards(**args)
        args['shard_size']=2;b=m.prepare_issuer_shards(**args)
        self.assertNotEqual(a['plan_id'],b['plan_id'])
        for card in b['cardinalities']:
            shards=[s for s in b['shards'] if s['k']==card['k']]
            if not shards:continue
            self.assertEqual(shards[0]['start'],0);self.assertEqual(shards[-1]['stop'],card['combination_count'])
            self.assertTrue(all(x['stop']==y['start'] for x,y in zip(shards,shards[1:])))
            self.assertEqual(sum(s['combination_count'] for s in shards),card['combination_count'])


if __name__=='__main__':unittest.main()
