import copy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

from scripts import ndx_cash_rejection_replan_probe as probe
import test_ndx_v3_same_execution_recheck as prior_tests


class ReplanProbeTests(unittest.TestCase):
    def report(self):
        return prior_tests.V3ExecutionRecheckTests().run_fixture()

    def test_unchanged_input_comparison_is_zero(self):
        report = self.report()
        before = copy.deepcopy(report)
        result = probe.compare_reports(report, copy.deepcopy(report))
        self.assertEqual(before, report)
        for role in ('candidate', 'incumbent'):
            self.assertTrue(all(value == 0 for value in result[role]['delta'].values()))
            self.assertEqual(result[role]['baseline']['all_cash_days'], 1)
            self.assertEqual(result[role]['baseline']['first_filled_session'], '2023-01-03')

    def test_rejects_changed_capital_calendar_targets_or_nav(self):
        before = self.report()
        for key, value in (
            ('inherited_context_capital_usd', 101.), ('calendar', []),
            ('periodic_clock', {}), ('nav_benchmark', {}), ('preparation', {})):
            after = copy.deepcopy(before)
            after[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'A/B input differs'):
                probe.compare_reports(before, after)

    def test_both_role_execution_contracts_preserved(self):
        before = self.report()
        for role in ('candidate', 'incumbent'):
            for key in ('minimum_cash_buffer_usd', 'transaction_cost_bps', 'domain_radius'):
                after = copy.deepcopy(before)
                after[role][key] += 1
                with self.subTest(role=role, key=key), self.assertRaisesRegex(ValueError, 'contract differs'):
                    probe.compare_reports(before, after)

    def test_invalid_case_before_file_access(self):
        for value in (True, -1, 4, '0', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'case index'):
                probe.read_baseline(value)

    def test_baseline_hash_rejects_before_simulation(self):
        with patch.object(probe.Path, 'read_bytes', return_value=b'{}'):
            with self.assertRaisesRegex(ValueError, 'Baseline report identity differs'):
                probe.read_baseline(0)

    def test_loaded_probe_source_drift_before_reading_baseline(self):
        with patch.object(probe, '_LOADED', {str(probe._SOURCE): '0'*64}), \
                patch.object(probe, 'read_baseline') as read:
            with self.assertRaisesRegex(ValueError, 'changed since import'):
                probe.run()
            read.assert_not_called()

    def test_existing_output_does_not_start_simulation(self):
        with patch.object(probe, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                probe.run_and_export(0, probe.ROOT/'data/cache/research/ndx_joint_weight_experiment_v2/v3_same_execution_case0_20260911.json')
            run.assert_not_called()

    def test_private_binding_real_small_simulations_preserve_baseline_globals(self):
        before = self.report()
        prepared, bundle, risk = prior_tests.V3ExecutionRecheckTests().fixture()
        baseline_path = probe.ROOT/'data/cache/research/ndx_joint_weight_experiment_v2/v3_same_execution_case0_20260911.json'
        with ExitStack() as stack:
            stack.enter_context(patch.object(probe, 'read_baseline', return_value=(before, baseline_path)))
            stack.enter_context(patch.object(probe.baseline, 'prepare_case', return_value=prepared))
            stack.enter_context(patch.object(probe.baseline, 'load_execution_nominal_bundle', return_value=bundle))
            stack.enter_context(patch.object(probe.baseline, 'load_incumbent_risk_overlay', return_value=risk))
            original_globals = dict(probe.baseline.__dict__)
            result = probe.run()
            for key, value in original_globals.items():
                self.assertIs(probe.baseline.__dict__[key], value)
        for role in ('candidate', 'incumbent'):
            self.assertEqual(result[role]['daily'], before[role]['daily'])
            self.assertEqual(result['comparison'][role]['one_replan']['supplemental_decision_count'], 0)
        self.assertFalse(result['baseline_recomputed'])


if __name__ == '__main__':
    unittest.main()
