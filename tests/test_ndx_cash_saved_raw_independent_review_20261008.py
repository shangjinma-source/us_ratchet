"""Saved raw counterexamples without evaluator dispatch or original-file writes."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from scripts import ndx_cash_neighbor_saved_raw_postcheck_20261008 as subject
from scripts import ndx_cash_topup_neighbor_shard_independent_readback_20261003 as reader
from backtest import ndx_cash_topup_neighbor_journal_research as journal
from test_ndx_cash_topup_neighbor_shard_independent_readback_20261003 import shard_fixture, seal


class IndependentSavedRawReview(unittest.TestCase):
    def inspect(self, data, raw=None, oracle=None):
        prepared, tasks, descriptor, start, rows, external, saved_oracle = data
        if raw is None:
            _, raw = seal(rows, descriptor)
        with patch.object(subject, 'TASK_ID', tasks[-1]['task_id']):
            return subject.inspect_saved_tail(journal_bytes=raw, tasks=tasks,
                prepared=prepared, descriptor=descriptor, context_sha256='c'*64,
                journal=journal, reader=reader,
                oracle=SimpleNamespace(independent_result=oracle or saved_oracle))

    def pending(self):
        data = list(shard_fixture()); data[4] = data[4][:-1]
        return data

    def test_exactly_one_oracle_call_no_mutation_and_original_l1(self):
        data = self.pending(); before = deepcopy(data[:-1]); calls = []
        def counted(arguments):
            calls.append(deepcopy(arguments))
            return data[-1](arguments)
        report = self.inspect(data, oracle=counted)
        self.assertEqual(len(calls), 1)
        self.assertEqual(data[:-1], before)
        expected = reader.expected_detail(data[0], data[4][-1]['payload']['result'])
        self.assertEqual(report['independent_postcheck'], expected)
        for key in subject.FLAGS:
            self.assertIs(report[key], False)

    def test_all_five_saved_risk_checks_rehashed_tampering_rejected(self):
        sample = self.pending()
        checks = sample[4][-1]['payload']['result']['branches'][0]['evaluated_plans'][0]['risk']['checks']
        self.assertEqual(len(checks), 5)
        for key in checks:
            data = self.pending()
            value = data[4][-1]['payload']['result']['branches'][0]['evaluated_plans'][0]['risk']['checks']
            value[key] = not value[key]
            with self.subTest(check=key), self.assertRaises(ValueError):
                self.inspect(data)

    def test_dispatch_link_fields_and_complete_raw_fields_rejected(self):
        for attack in ('task_reference', 'global_position', 'extra_result', 'raw_error', 'raw_count'):
            data = self.pending(); start, raw = data[4][-2:]
            if attack == 'task_reference':
                start['payload']['task_reference']['sha256'] = '0'*64
            elif attack == 'global_position':
                start['payload']['global_task_position'] += 1
            elif attack == 'extra_result':
                raw['payload']['result']['unregistered'] = False
            elif attack == 'raw_error':
                raw['payload']['error'] = {'type':'Error', 'message':'saved'}
            else:
                raw['payload']['explicit_evaluator_call_attempt_count'] = True
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                self.inspect(data)

    def test_truncated_or_corrupt_chain_rejected_before_oracle(self):
        data = self.pending(); _, raw = seal(data[4], data[2])
        for damaged in (raw[:-1], raw.replace(b'POSTCHECK', b'POSTCHECL', 1)):
            with self.subTest(size=len(damaged)), self.assertRaises(ValueError):
                self.inspect(data, raw=damaged, oracle=lambda _: self.fail('oracle called on corrupt evidence'))


if __name__ == '__main__':
    unittest.main()
