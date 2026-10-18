from copy import deepcopy
import unittest
from unittest.mock import patch
from scripts import ndx_cash_topup_neighbor_full_independent_readback_20261003 as reader


def one_saved_shard():
    contract = {'fee': '0.5'}
    contract_hash = reader.digest(contract)
    identity = dict(scenario_contract_sha256=contract_hash, buy_shares={'A': 3})
    task_id = reader.digest(identity)
    descriptor = dict(global_task_start=900, global_task_stop=901, shard={'start': 5})
    journal = dict(path='sealed-journal', sha256='a' * 64)
    started_ref = dict(path='sealed-start', sha256='b' * 64)
    counts = dict(FEASIBLE=0, INFEASIBLE=1, EVALUATION_EXCEPTION=0,
                  VALIDATION_FAILURE=0, EXTERNALLY_REFERENCED=0)
    report = dict(source_hashes={'fixed': 'c' * 64}, journal_reference=journal,
        started_reference=started_ref, detail=dict(task_count=1, new_arithmetic_checked_count=1,
        task_results=[dict(task_id=task_id)], outcome_counts=counts, record_count=3,
        journal_sha256=journal['sha256']))
    completion = dict(schema='CASH_NEIGHBOR_SHARD_COMPLETION_V1',
        status='COMPLETE_SAVED_DIAGNOSTICS_NOT_INDEPENDENTLY_AUDITED', descriptor=descriptor,
        context_sha256='context', journal_reference=journal, started_reference=started_ref,
        task_count=1, outcome_counts=counts, new_evaluator_call_count=1, record_count=3)
    started = dict(schema='CASH_NEIGHBOR_SHARD_STARTED_V1', descriptor=descriptor,
        context_sha256='context', contract_sha256=contract_hash, ordered_task_ids=[task_id])
    return report, dict(completion=completion, started=started,
        prepared=dict(contract=contract, contract_sha256=contract_hash),
        tasks=[dict(identity=identity, task_id=task_id, scenario_candidate_ordinal=5)],
        descriptor=descriptor, expected_sources={'fixed': 'c' * 64}, execution_context_sha256='context')


class Tests(unittest.TestCase):
    def test_metadata_reuse_does_not_invoke_arithmetic_and_rejects_wrong_slot(self):
        report, arguments = one_saved_shard()
        with patch.object(reader, 'fresh_helper', side_effect=AssertionError('No arithmetic')):
            reader.validate_reused_metadata(report, **arguments)
        for key in ('ordinal', 'identity', 'contract', 'record_bool'):
            item = deepcopy(arguments)
            if key == 'ordinal': item['tasks'][0]['scenario_candidate_ordinal'] = 0
            elif key == 'identity': item['tasks'][0]['identity']['buy_shares']['A'] = 4
            elif key == 'contract': item['prepared']['contract']['fee'] = '0'
            else: item['completion']['record_count'] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                reader.validate_reused_metadata(report, **item)

    def test_request_no_new_shard_boundary_and_exact_permissions(self):
        names = ('fit_performed', 'account_executed', 'orders_executed', 'point_in_time_verified',
            'promotion_allowed', 'full_integer_domain_exhausted', 'economic_winner_selected',
            'target_weights_changed', 'holdings_sold', 'runtime_binary_closure_verified',
            'continuous_source_monitoring_claimed', 'automatic_retry_allowed')
        request = dict(context_sha256='c', max_new_shards=1, full_shard_count=324,
            full_task_count=301657, **dict.fromkeys(names, False))
        result = dict(context_sha256='c', new_completed_shard_count=0, completed_shard_references=[{}])
        reader.validate_request_link(result, request, 1)
        for key, value in [('automatic_retry_allowed', 0), ('max_new_shards', True), ('full_task_count', 301656)]:
            bad = deepcopy(request); bad[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                reader.validate_request_link(result, bad, 1)

    def test_future_gate_before_files_and_boolean_audit_limit(self):
        with patch.object(reader, 'fresh_helper', side_effect=AssertionError('No source load')):
            with self.assertRaises(ValueError): reader.run(result_reference={}, execute=True)
            with patch.multiple(reader, RESULT_PATH='result', RESULT_SHA='a'*64, REQUEST_SHA='b'*64):
                with self.assertRaises(ValueError):
                    reader.run(result_reference=reader.reference('result','a'*64), execute=True, max_shards=True)


if __name__ == '__main__':
    unittest.main()
