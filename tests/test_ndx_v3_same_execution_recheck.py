import copy
from contextlib import ExitStack
import unittest
from unittest.mock import patch

import pandas as pd

from scripts import ndx_v3_same_execution_recheck as probe


class V3ExecutionRecheckTests(unittest.TestCase):
    def test_import_source_drift_rejected_before_preparation(self):
        with patch.object(probe, '_LOADED', {str(probe._PATHS[0]): '0'*64}), patch.object(probe, 'prepare_case') as prepare:
            with self.assertRaisesRegex(ValueError, 'changed since import'):
                probe.run()
            prepare.assert_not_called()

    def test_case_index_strict(self):
        for value in (True, -1, 4, '0', None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'case index'):
                probe.run(value)

    def test_export_outside_research_rejected_before_run(self):
        with patch.object(probe, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'research directory'):
                probe.run_and_export(output_path=probe.ROOT/'config/probe.json')
            run.assert_not_called()

    def test_existing_export_rejected_before_run(self):
        with patch.object(probe, 'run') as run, patch.object(probe.Path, 'exists', return_value=True):
            with self.assertRaisesRegex(ValueError, 'already exists'):
                probe.run_and_export(output_path=probe.ROOT/'data/cache/research/existing.json')
            run.assert_not_called()

    def test_nav_excludes_first_return_and_recomputes_drawdown(self):
        dates = pd.bdate_range('2023-01-02', periods=3)
        result = probe.nav_path(pd.Series([9., .1, -.2], index=dates), dates)
        self.assertEqual(result['equity_index'], [1., 1.1, .8800000000000001])
        self.assertAlmostEqual(result['path_max_drawdown'], .2)
        self.assertAlmostEqual(result['path_return'], -.12)
        for value in (float('nan'), float('inf'), -1.01, True):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Invalid NAV'):
                probe.nav_path(pd.Series([0., value, 0.], index=dates, dtype=object), dates)
        with self.assertRaisesRegex(ValueError, 'calendar'):
            probe.nav_path(pd.Series([0., 0.], index=dates[:2]), dates)

    def fixture(self):
        dates = pd.bdate_range('2023-01-02', periods=4)
        prices = pd.DataFrame(10., index=dates, columns=list('ABC'))
        weights = dict(A=1/3, B=1/3, C=1/3)
        contract = dict(portfolio_cash_usd=100., minimum_cash_buffer_usd=5., transaction_cost_bps=10.,
            max_single_weight=.8, min_single_weight=.1, top_weight_cap=1.,
            minimum_effective_n_ratio=.5, risk_chain_top1_cap=.8)
        source = {str(probe._PATHS[0]): probe._LOADED[str(probe._PATHS[0])]}
        prepared = dict(summary=dict(source_hashes=source, date_start='2023-01-02',
            date_end='2023-01-05', context_sha256='a'*64, job_id='b'*64), prices=prices,
            inputs=dict(contract=contract, incumbent_weights=weights,
                universe=pd.DataFrame(dict(ticker=list('ABC'), risk_chain=list('ABC'))),
                target_returns=pd.Series(0., index=dates)),
            clock=dict(schedule=[dict(execution_date='2023-01-02', weights=weights)]))
        bundle = dict(prices=prices.copy(), inventory_path=str(probe._PATHS[0]),
            inventory_sha256=probe._LOADED[str(probe._PATHS[0])], evidence=[])
        risk = dict(provenance=dict(source_hashes=source), risk_chain_by_ticker=dict(zip('ABC', 'ABC')))
        return prepared, bundle, risk

    def run_fixture(self, unmatched=False, mismatch=False):
        prepared, bundle, risk = self.fixture()
        if mismatch:
            bundle['prices'].iloc[0, 0] = 11.
        with ExitStack() as stack:
            stack.enter_context(patch.object(probe, 'prepare_case', return_value=prepared))
            stack.enter_context(patch.object(probe, 'load_execution_nominal_bundle', return_value=bundle))
            stack.enter_context(patch.object(probe, 'load_incumbent_risk_overlay', return_value=risk))
            if unmatched:
                stack.enter_context(patch.object(probe, 'diagnose_nominal_events',
                    return_value=dict(unmatched_jumps=[{'ticker': 'A'}])))
                candidate = stack.enter_context(patch.object(probe, 'simulate_next_session_execution_research_v2'))
                with self.assertRaisesRegex(ValueError, 'Unmatched nominal jump'):
                    probe.run()
                candidate.assert_not_called()
                return
            return probe.run()

    def test_small_real_simulations_full_ledgers_and_compact_nonmutation(self):
        report = self.run_fixture()
        for role in ('candidate', 'incumbent'):
            self.assertEqual(len(report[role]['daily']), 4)
            self.assertEqual(len(report[role]['decisions']), 1)
            self.assertEqual(len(report[role]['executions']), 1)
            self.assertEqual(report[role]['initial_equity_usd'], 100.)
        self.assertEqual(report['candidate']['daily'], report['incumbent']['daily'])
        self.assertFalse(report['corporate_action_coverage_verified'])
        self.assertFalse(report['portfolio_selection_precedes_execution'])
        self.assertFalse(report['fresh_oos_consumed'])
        before = copy.deepcopy(report)
        result = probe.compact(report)
        self.assertEqual(report, before)
        self.assertEqual(result['full_report_sha256'], probe.encoding._sha(report))
        self.assertFalse(result['full_report_persisted_by_cli'])

    def test_unmatched_jump_stops_before_simulation(self):
        self.run_fixture(unmatched=True)

    def test_nominal_overlap_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError, 'prices differ'):
            self.run_fixture(mismatch=True)


if __name__ == '__main__':
    unittest.main()
