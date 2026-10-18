import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path
from scripts import ndx_cash_neighbor_saved_raw_postcheck_20261008 as m
from scripts import ndx_cash_topup_neighbor_shard_independent_readback_20261003 as reader
from backtest import ndx_cash_topup_neighbor_journal_research as journal
from test_ndx_cash_topup_neighbor_shard_independent_readback_20261003 import shard_fixture, seal

class Tests(unittest.TestCase):
    def run_saved(self, data):
        prepared,tasks,descriptor,start,records,external,oracle = data
        _,raw=seal(records,descriptor)
        with patch.object(m,'TASK_ID',tasks[-1]['task_id']):
            return m.inspect_saved_tail(journal_bytes=raw,tasks=tasks,prepared=prepared,descriptor=descriptor,context_sha256='c'*64,journal=journal,reader=reader,oracle=SimpleNamespace(independent_result=oracle))

    def test_saved_raw_finance_risk_and_score_independently_verified(self):
        data=list(shard_fixture());expected=data[4][-1]['payload'];data[4]=data[4][:-1]
        result=self.run_saved(data)
        self.assertEqual(result['independent_postcheck'],expected)
        self.assertTrue(result['saved_arithmetic_independently_verified'])
        self.assertFalse(result['original_postcheck_existed'])
        self.assertFalse(result['evaluator_called'])
        self.assertEqual(result['raw_record_reference']['sequence'],4)

    def test_self_consistent_rehash_cannot_hide_finance_risk_argument_mutation(self):
        for attack in ('fee','risk','argument','count'):
            data=list(shard_fixture());data[4]=data[4][:-1];rows=data[4]
            if attack=='fee':rows[-1]['payload']['result']['branches'][0]['evaluated_plans'][0]['fees_usd']='999'
            elif attack=='risk':rows[-1]['payload']['result']['branches'][0]['evaluated_plans'][0]['risk']['all_passed']=False
            elif attack=='argument':rows[-2]['payload']['evaluation_argument_sha256']='0'*64
            else:rows[-1]['payload']['returned_evaluation_count']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):self.run_saved(data)

    def test_complete_or_only_started_is_not_pending_raw(self):
        data=list(shard_fixture())
        with self.assertRaises(ValueError):self.run_saved(data)
        data[4]=data[4][:-2]
        with self.assertRaises(ValueError):self.run_saved(data)

    def test_exception_not_converted_to_economic_outcome(self):
        data=list(shard_fixture());data[4]=data[4][:-1]
        data[4][-1]['stage']='RAW_EXCEPTION'
        data[4][-1]['payload']=dict(result=None,error={'type':'Error'},explicit_evaluator_call_attempt_count=1,returned_evaluation_count=0)
        with self.assertRaises(ValueError):self.run_saved(data)

    def test_pending_partition_pin_blocks_before_io(self):
        with patch.object(m,'PARTITION_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):m.publish(execute=True)
            read.assert_not_called()

if __name__=='__main__':unittest.main()
