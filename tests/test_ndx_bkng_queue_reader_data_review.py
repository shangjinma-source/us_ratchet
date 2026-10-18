"""Independent synthetic BKNG queue adversarial tests; no actual34 reconstruction."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_bkng_combination_independent_readback_20260925 as owner
from scripts import ndx_new_cutoff_bkng_combination_independent_readback_20260925 as m

class Tests(unittest.TestCase):
    def test_final_actual_pins_bytes_only(self):
        for p,h in [(m.PRODUCER,m.PRODUCER_SHA),(m.CANDIDATE,m.CANDIDATE_SHA)]+[(m.BASE/p,h) for p,h in m.BOUND.values()]:
            self.assertEqual(m.codec.sha(p.read_bytes()),h)

    def test_k20_order_same_issuer_and_boolean_local_rank(self):
        for attack in ('reverse','alias','boolean'):
            a=owner.batch()
            if attack=='reverse':
                a['materializations'][-2:]=reversed(a['materializations'][-2:]);a['selections'][-2:]=reversed(a['selections'][-2:])
            elif attack=='alias':a['materializations'][-1]['combinations'][0]['prefix_security_ids'][1]='s00b'
            else:a['selections'][0]['forced_local_rank']=False
            with self.subTest(attack=attack),patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**a)

    def test_every_singleton_delegates_full_contract_with_exact_panel_and_sources(self):
        a=owner.batch()
        with patch.object(m.pure,'verify_materialized',return_value={}) as verify:m.validate_materializations(**a)
        self.assertEqual(verify.call_count,34)
        for call in verify.call_args_list:
            kwargs=call.kwargs
            self.assertIs(kwargs['panel'],a['panel']);self.assertIs(kwargs['plan'],a['plan'])
            self.assertIs(kwargs['expected_fitter_source_hashes'],a['plan']['fitter_source_hashes'])
            self.assertEqual(kwargs['stop'],kwargs['start']+1);self.assertEqual(kwargs['plan_reference'],m.ref('plan'))
        a=owner.batch();a['old_ids'][-1]=a['materializations'][-1]['combinations'][0]['tasks'][-1]['numerical_task_id']
        with patch.object(m.pure,'verify_materialized',return_value={}),self.assertRaises(ValueError):m.validate_materializations(**a)

    def test_sources_conflict_and_frozen_pure_guard(self):
        p=next(iter(m.LOADED))
        with self.assertRaises(ValueError):m.guard({p:'0'*64})
        with patch.object(m,'PURE_SHA','0'*64),patch.object(m.Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.guard({})
            read.assert_not_called()

if __name__=='__main__':unittest.main()
