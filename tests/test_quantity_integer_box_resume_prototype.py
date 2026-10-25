from copy import deepcopy
from hashlib import sha256
import json
from unittest.mock import patch
import unittest
from backtest.quantity_integer_box_certificate_prototype import solve,verify
from backtest.quantity_integer_box_resume_prototype import resume
from test_quantity_integer_box_certificate_prototype import fixture


def continue_result(parent,budget):
    raw=json.dumps(parent,sort_keys=True).encode()
    return resume(parent_raw=raw,expected_parent_sha256=sha256(raw).hexdigest(),expected_input_sha256=parent['input_sha256'],additional_node_budget=budget)


class ResumeTests(unittest.TestCase):
    def test_segmented_equals_one_run_without_solve_or_root_replay(self):
        for cuts in ((0,1,2,4),(1,4,8,1000),(0,0,0)):
            with self.subTest(cuts=cuts):
                result=solve(**fixture(),node_budget=cuts[0]);original=deepcopy(result)
                for budget in cuts[1:]:
                    parent=deepcopy(result)
                    with patch('backtest.quantity_integer_box_certificate_prototype.solve',side_effect=AssertionError('no solve')):result=continue_result(result,budget)
                    self.assertEqual(result['coverage_ledger'][:len(parent['coverage_ledger'])],parent['coverage_ledger'])
                full=solve(**fixture(),node_budget=sum(cuts))
                without_binding={k:v for k,v in result.items() if k!='resume_binding'}
                self.assertEqual(without_binding,full)
                self.assertEqual(len(result['resume_binding']['ancestor_raw_sha256']),len(cuts)-1)
                verify(result,expected_input_sha256=original['input_sha256'])

    def test_hash_input_frontier_and_ancestry_tamper_rejected(self):
        parent=solve(**fixture(),node_budget=1);raw=json.dumps(parent).encode();h=sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,'PARENT_RAW_HASH'):resume(parent_raw=raw+b' ',expected_parent_sha256=h,expected_input_sha256=parent['input_sha256'],additional_node_budget=1)
        with self.assertRaisesRegex(ValueError,'INPUT_BINDING'):resume(parent_raw=raw,expected_parent_sha256=h,expected_input_sha256='0'*64,additional_node_budget=1)
        broken=deepcopy(parent);broken['unsearched_frontier'].pop()
        with self.assertRaises(ValueError):continue_result(broken,1)
        next_result=continue_result(parent,1);next_result['resume_binding']['parent_processed_nodes']=False
        with self.assertRaises(ValueError):continue_result(next_result,1)
        with self.assertRaises(ValueError):continue_result(parent,True)

    def test_complete_parent_no_extra_work_and_zero_budget(self):
        parent=solve(**fixture(),node_budget=1000);result=continue_result(parent,3)
        self.assertEqual(result['resume_binding']['added_processed_nodes'],0)
        self.assertEqual(result['coverage_ledger'],parent['coverage_ledger'])
        self.assertTrue(result['objective_value_optimal'])

if __name__=='__main__':unittest.main()
