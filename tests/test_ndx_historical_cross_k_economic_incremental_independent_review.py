"""Adversarial prefix linkage checks, without opening historical ledgers."""
import copy
import unittest
from unittest.mock import patch

from scripts import ndx_historical_cross_k_economic_summary_incremental_20260923 as module


class IncrementalIndependentReview(unittest.TestCase):
    def fixture(self):
        details = [dict(task_id=str(index), result_reference={'path': str(index), 'sha256': str(index)},
                        raw_reference=None) for index in range(102)]
        previous = dict(details=copy.deepcopy(details[:101]))
        audit = dict(schema='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1',
                     completed_account_task_count=102, raw_marker_result_chain_verified=True,
                     details=copy.deepcopy(details), fit_prefix_audit_reference={'fit': 'same'})
        for key in ('plan_reference', 'shared_control_reference', 'shared_comparison_reference',
                    'external_completed_account_reference'):
            previous[key] = {'reference': key}
            audit[key] = copy.deepcopy(previous[key])
        for key in ('engine_called', 'fit_performed', 'point_in_time_verified', 'promotion_allowed',
                    'formal_dual_benchmark_admission', 'external_account_imported'):
            audit[key] = False
        index = dict(finalized_after_full_source_verification=True, completed_account_task_count=102,
                     entries=copy.deepcopy(details), plan_reference=audit['plan_reference'],
                     fit_prefix_audit_reference=audit['fit_prefix_audit_reference'])
        seed = dict(completed_account_count=101, rows=[{'task_id': str(index)} for index in range(101)],
                    audit_reference=dict(path=str(module.base.AUDIT), sha256=module.base.AUDIT_SHA))
        return seed, previous, audit, index

    def test_valid_extension_preserves_complete_prefix(self):
        self.assertEqual(module.validate_extension(*self.fixture()), 102)

    def test_prefix_change_rejected_even_if_new_index_agrees(self):
        arguments = self.fixture()
        arguments[2]['details'][0]['result_reference']['sha256'] = 'rewritten'
        arguments[3]['entries'][0]['result_reference']['sha256'] = 'rewritten'
        with self.assertRaises(ValueError):
            module.validate_extension(*arguments)

    def test_shared_benchmark_and_plan_mixing_rejected(self):
        for key in ('plan_reference', 'shared_control_reference', 'shared_comparison_reference',
                    'external_completed_account_reference'):
            arguments = self.fixture()
            arguments[2][key] = {'reference': 'other'}
            with self.assertRaises(ValueError):
                module.validate_extension(*arguments)

    def test_duplicate_and_false_completion_rejected(self):
        for mode in ('duplicate', 'missing', 'unfinalized', 'boolean_count', 'promoted'):
            arguments = self.fixture()
            audit, index = arguments[2:]
            if mode == 'duplicate':
                audit['details'][-1] = copy.deepcopy(audit['details'][0])
                index['entries'][-1] = copy.deepcopy(index['entries'][0])
            elif mode == 'missing':
                index['entries'].pop()
            elif mode == 'unfinalized':
                index['finalized_after_full_source_verification'] = False
            elif mode == 'boolean_count':
                audit['completed_account_task_count'] = True
            else:
                audit['promotion_allowed'] = True
            with self.assertRaises(ValueError):
                module.validate_extension(*arguments)

    def test_new_raw_result_reference_mismatch_rejected(self):
        for key in ('raw_reference', 'result_reference'):
            arguments = self.fixture()
            arguments[3]['entries'][-1][key] = {'different': True}
            with self.assertRaises(ValueError):
                module.validate_extension(*arguments)

    def test_unreviewed_self_signed_audit_rejected_before_io(self):
        with patch.object(module.base, 'read', side_effect=AssertionError('Unexpected file read')):
            with self.assertRaises(ValueError):
                module.build(str(module.base.AUDIT.parent / 'self_signed.json'), 'a' * 64)
            path, (checksum, _) = next(iter(module.AUTHORIZED_AUDITS.items()))
            with self.assertRaises(ValueError):
                module.build(path, 'b' * 64 if checksum != 'b' * 64 else 'c' * 64)


if __name__ == '__main__':
    unittest.main()
