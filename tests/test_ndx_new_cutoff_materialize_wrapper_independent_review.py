"""Incomplete plan stub + saved typed metadata; no actual bounded slice."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_bounded_materialize_20260924 as fixture
m=fixture.module

class IndependentBoundedWrapperReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixture.Tests.setUpClass();cls.docs=fixture.Tests.documents;cls.sources=fixture.Tests.numerical

    def test_first_nonexcluded_and_unique_first_shard_are_required(self):
        for attack in ('earlier','excluded4','duplicate'):
            docs=deepcopy(self.docs);plan=docs['plan']['plan']
            if attack=='earlier':plan['cardinalities'][2]['necessary_bound_certificates']=[]
            elif attack=='excluded4':plan['cardinalities'][3]['necessary_bound_certificates']=['bad']
            else:plan['shards'].append(deepcopy(plan['shards'][0]))
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs(docs,self.sources)

    def test_projection_keeps_all20_and_none_prior_without_auditing(self):
        with patch.object(m.materializer,'materialize_slice',side_effect=AssertionError('real slice')),patch.object(m.codec,'build',side_effect=AssertionError('audit')):
            result=m.inputs(self.docs,self.sources)
        self.assertIsNone(result['plan']['context']['previous_target_weights'])
        self.assertEqual(len(result['panel']['returns']),126)
        self.assertTrue(all(len(row)==20 for row in result['panel']['returns']))
        google=[r for r in result['panel']['universe'] if r['issuer_id']=='issuer:0001652044']
        self.assertEqual(len(google),2);self.assertEqual(len({r['security_id'] for r in google}),2)

    def test_old_plan_or_wrong_audited_source_cannot_supply_new_inputs(self):
        for attack in ('schema','audit_producer','numerical'):
            docs=deepcopy(self.docs);sources=deepcopy(self.sources)
            if attack=='schema':docs['plan']['schema']='SOURCE_BOUND_NEW_CUTOFF_SHARD_PREPARE_V1'
            elif attack=='audit_producer':docs['audit']['producer_reference']['sha256']='0'*64
            else:sources[next(iter(sources))]='0'*64
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.inputs(docs,sources)

    def test_corrupt_consumed_blob_fails_before_materializer(self):
        bound=deepcopy(m.BOUND);bound['plan']=(bound['plan'][0],'a'*64)
        with patch.object(m,'BOUND',bound),patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m.materializer,'materialize_slice') as materialize:
            with self.assertRaisesRegex(ValueError,'Consumed source bytes'):m.build()
            materialize.assert_not_called()

    def test_loaded_source_hash_conflict_is_not_overwritten(self):
        with self.assertRaisesRegex(ValueError,'conflict'):m.guard({str(m.SOURCE):'0'*64})

if __name__=='__main__':unittest.main()
