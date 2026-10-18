import copy
import unittest
from unittest.mock import patch
from scripts import ndx_historical_cross_k_accounts_incremental_audit_20260923 as module


class IncrementalAuditTests(unittest.TestCase):
    def fixture(self):
        rows = [dict(task_id=str(index), result_reference={'path': str(index), 'sha256': str(index)},
                     raw_reference=None) for index in range(5001)]
        seed = dict(schema='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1',
                    completed_account_task_count=111, details=copy.deepcopy(rows[:111]),
                    raw_marker_result_chain_verified=True, fit_prefix_audit_reference={'old': True},
                    shared_control_reference=module.independent.CONTROL,
                    shared_comparison_reference=module.independent.COMPARISON,
                    external_completed_account_reference=module.independent.EXTERNAL)
        previous = dict(completed_account_task_count=111, entries=copy.deepcopy(rows[:111]),
                        fit_prefix_audit_reference=seed['fit_prefix_audit_reference'])
        current = dict(completed_account_task_count=121, entries=copy.deepcopy(rows[:121]),
                       finalized_after_full_source_verification=True, fit_prefix_audit_reference=module.FIT)
        fit = dict(schema='HISTORICAL_CROSS_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1',
                   completed_new_count=5001, details=copy.deepcopy(rows),
                   complete_marker_raw_checkpoint_chain_verified=True)
        fit_index = dict(completed_new_count=5001, entries=copy.deepcopy(rows),
                         finalized_after_full_source_verification=True)
        arguments = (seed, previous, current, fit, fit_index)
        for document in arguments:
            document['plan_reference'] = module.independent.PLAN
        return arguments

    def test_complete_prefix_accepted(self):
        module.validate_prefix(*self.fixture())

    def test_old_rows_or_shared_reference_cannot_change(self):
        for field in ('prefix', 'detail', 'benchmark'):
            arguments = self.fixture()
            if field == 'prefix':
                arguments[2]['entries'][0]['result_reference']['sha256'] = 'changed'
            elif field == 'detail':
                arguments[0]['details'][0]['raw_reference'] = {'new': 'raw'}
            else:
                arguments[0]['shared_control_reference'] = {'other': 'control'}
            with self.assertRaises(ValueError):
                module.validate_prefix(*arguments)

    def test_fake_finalized_duplicate_and_missing_entries_rejected(self):
        for field in ('finalized', 'duplicate', 'missing'):
            arguments = self.fixture()
            if field == 'finalized':
                arguments[2]['finalized_after_full_source_verification'] = False
            elif field == 'duplicate':
                arguments[2]['entries'][-1]['task_id'] = '0'
            else:
                arguments[2]['entries'].pop()
            with self.assertRaises(ValueError):
                module.validate_prefix(*arguments)

    def test_source_closure_must_be_exact(self):
        previous = dict(historical_expected_source_hashes={'old': 'oldsha'})
        reference = dict(path='prior_index', sha256='indexsha')
        current = dict(entries=[{}]*111 + [dict(started_reference={'path':'new', 'sha256':'newsha'},
                                              raw_reference=None, result_reference=None)],
                       historical_expected_source_hashes={'old':'oldsha','prior_index':'indexsha','auth':'authsha','new':'newsha'})
        module.exact_closure(current, previous, reference, {'auth':'authsha'})
        for key in ('old', 'new', 'auth'):
            changed = copy.deepcopy(current)
            del changed['historical_expected_source_hashes'][key]
            with self.assertRaises(ValueError):
                module.exact_closure(changed, previous, reference, {'auth':'authsha'})
        current['historical_expected_source_hashes']['unindexed'] = 'extra'
        with self.assertRaises(ValueError):
            module.exact_closure(current, previous, reference, {'auth':'authsha'})

    def test_cli_publication_builds_only_once(self):
        value = dict(archive_resolution={}, historical_expected_source_hashes={})
        with patch.object(module, 'build', return_value=value) as build, \
                patch.object(module.independent.archive, 'load_contract', return_value={}), \
                patch.object(module.independent.archive, 'verify_expected_sources', return_value={}), \
                patch.object(module.independent, 'publish', return_value={'path':'x','sha256':'h'}), \
                patch.object(module.independent, 'read', return_value=value):
            module.build_and_publish('unused')
            build.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
