"""Saved metadata with mocked pure readback; never audits actual materialization."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_materialization_independent_readback_20260924 as m

class IndependentReadbackWrapperReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs={k:m.codec.loads(Path(m.ref(k)['path']).read_bytes()) for k in m.BOUND}

    def candidate_stub(self):
        return dict(schema='SOURCE_BOUND_NEW_CUTOFF_BOUNDED_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_TASK_INPUTS_NOT_EXECUTION',
            materialization={'explicit_incomplete_test_stub':True},input_references={k:m.ref(k) for k in m.BOUND},source_hashes=m.producer_sources(self.docs),
            selected_slice_reason='FIRST_LEXICOGRAPHIC_COMBINATION_OF_FIRST_NONEXCLUDED_K_FOR_INTERFACE_VALIDATION_NOT_SCORE_SELECTION',
            external_direct_source_bytes_verified=True,materializer_invocation_count=1,combination_enumeration_performed=True,enumerated_combination_count=1,
            actual_fitter_invocation_count=0,**dict.fromkeys(m.FALSE,False))

    def test_full_outer_contract_exact_before_mock_pure_reader(self):
        for attack in ('complete','countbool','source','reason'):
            candidate=self.candidate_stub()
            if attack=='complete':candidate['all_plan_tasks_completed']=True
            elif attack=='countbool':candidate['actual_fitter_invocation_count']=False
            elif attack=='source':candidate['source_hashes'].pop(next(iter(candidate['source_hashes'])))
            else:candidate['selected_slice_reason']='WINNER'
            with self.subTest(attack=attack),patch.object(m.reader,'verify_materialized') as verify:
                with self.assertRaises(ValueError):m.verify_document(candidate,self.docs)
                verify.assert_not_called()

    def test_request_projection_is_exact_without_numerical_audit(self):
        with patch.object(m.codec,'build',side_effect=AssertionError('repeat panel audit')),patch.object(m.reader,'verify_materialized',return_value={'synthetic':True}) as verify:
            m.verify_document(self.candidate_stub(),self.docs)
        args=verify.call_args.kwargs
        self.assertEqual((args['start'],args['stop'],args['max_materialized_combinations']),(0,1,1))
        self.assertEqual(len(args['panel']['columns']),20);self.assertEqual(len(args['expected_fitter_source_hashes']),25)

    def test_merge_source_conflict_is_rejected(self):
        mapping={'path':'a'*64}
        with self.assertRaises(ValueError):m.merge(mapping,{'path':'b'*64})

    def test_orphan_or_consumed_blob_stops_before_independent_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);(p/'materialized.json').write_text('{}');(p/'orphan').write_text('x')
            with patch.object(m,'OUTPUT',p/'audit.json'),patch.object(m,'build') as build:
                with self.assertRaises(ValueError):m.publish()
                build.assert_not_called()
        with patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m,'verify_document') as verify:
            with self.assertRaises(ValueError):m.build()
            verify.assert_not_called()

if __name__=='__main__':unittest.main()
