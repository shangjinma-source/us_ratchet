"""Independent ORLY queue metadata attacks, no actual queue reconstruction."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_orly_combination_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_orly_combination_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_k20_class_collapse_and_rehashed_location_alias(self):
        for attack in ('collapse','alias','boollocal','order'):
            a=owner.batch()
            if attack=='collapse':
                a['materializations'][-1]=deepcopy(a['materializations'][-2]);a['selections'][-1]=deepcopy(a['selections'][-2])
            elif attack=='alias':a['materializations'][-1]['combinations'][0]['tasks'][0]['location_id']=a['materializations'][0]['combinations'][0]['tasks'][0]['location_id']
            elif attack=='boollocal':a['selections'][0]['forced_local_rank']=False
            else:a['materializations'][0],a['materializations'][1]=a['materializations'][1],a['materializations'][0]
            with self.subTest(attack=attack),patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**a)
    def test_exact_target_late_issuer_and_dualclass_prefix(self):
        groups=[dict(issuer_id='A',security_ids=['a','aa']),dict(issuer_id='B',security_ids=['b']),dict(issuer_id='C',security_ids=['target'])]
        self.assertEqual([m.forced_rank(groups,s,'target') for s in [['a','target'],['aa','target'],['b','target']]],[0,1,2])
        self.assertEqual(m.forced_rank(groups,['aa','b','target'],'target'),1)
        for prefix in (['a','aa','target'],['target','a'],['a','b']):
            with self.assertRaises(ValueError):m.forced_rank(groups,prefix,'target')
    def test_pure_validator_is_authority_for_matrix_and_fullprior(self):
        a=owner.batch()
        with patch.object(m.pure,'verify_materialized',side_effect=ValueError('matrix or full prior changed')) as check:
            with self.assertRaises(ValueError):m.validate_materializations(**a)
            self.assertEqual(check.call_count,1)
            call=check.call_args.kwargs
            self.assertEqual(call['plan_reference'],m.ref('plan'))
            self.assertIs(call['expected_fitter_source_hashes'],a['plan']['fitter_source_hashes'])
            self.assertEqual(call['stop'],call['start']+1)
    def test_final_byte_pins_conflicts_and_old300_count(self):
        self.assertEqual(m.codec.sha(m.PRODUCER.read_bytes()),m.PRODUCER_SHA)
        self.assertEqual(m.codec.sha(m.CANDIDATE.read_bytes()),m.CANDIDATE_SHA)
        with self.assertRaises(ValueError):m.guard({next(iter(m.LOADED)):'0'*64})
        a=owner.batch();a['old_ids']=a['old_ids'][:198]
        with patch.object(m.pure,'verify_materialized') as check:
            with self.assertRaises(ValueError):m.validate_materializations(**a)
            check.assert_not_called()

if __name__=='__main__':unittest.main()
