"""Offline source/risk/provider integration of the explicit monthly proposal gate."""
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.saved_frontier_daily_composition_v1 import SavedFrontierDailyComposition
from data.saved_frontier_cap_exit_reader import POLICY_ID, project_saved_frontier_cap_exit, clone_monthly_risk_store
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
import test_saved_frontier_isolated_pipeline as fixture


class CompositionTests(unittest.TestCase):
    def run_case(self, cash, buy_data_missing=False):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as directory:
            case = fixture.IsolatedFrontierPipelineTests().case(directory, cash=cash, cancel=True)
            archive_saved_frontier_policy(research_root=case['root'], target=case['target'],
                proposal=case['proposal'], source_files=case['source_files'], enabled=True)
            original = deepcopy(case['target'])
            risk_path = clone_monthly_risk_store(research_root=case['root'],
                source_path=case['risk_path'], source_sha256=fixture.digest(case['risk_path'].read_bytes()),
                clone_name='composition-risk.sqlite3')['path']
            account_bytes = case['accounts'].path.read_bytes()
            monthly = SimpleNamespace(accounts=case['accounts'], current=lambda: deepcopy(case['target']),
                snapshot_operation=nullcontext, validate_current_target_pins=lambda: None)
            def proposal(**arguments):
                self.assertEqual(arguments['expected_proposal_id'], case['proposal']['proposal_id'])
                return deepcopy(case['proposal'])
            def reader(state, target, now, *, proposal):
                self.assertEqual(target, original)
                return project_saved_frontier_cap_exit(research_root=case['root'],
                    risk_path=risk_path, target_id=target['target_id'], state=state,
                    review_bytes=case['review_bytes'], trusted_review_sha256=case['trusted_review_sha256'],
                    files=case['files'], now=now.isoformat(), enabled=True)
            service = SavedFrontierDailyComposition(monthly_service=monthly,
                monthly_view=SimpleNamespace(require_proposal=proposal), evidence_reader=reader,
                execution_provider=case['provider'].execution, clock=lambda: case['clock'][0],
                policy_execution_enabled=True, policy_id=POLICY_ID, fee_bps='1')
            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 patch('data.strategy_account_evidence_provider.compile_saved_training',
                       side_effect=AssertionError('NEW_TRAINING_FORBIDDEN')), \
                 (patch('data.saved_frontier_daily_composition_v1.SavedFrontierPreviewService.preview',
                        side_effect=ValueError('MINUTE_GAP')) if buy_data_missing else nullcontext()):
                result = service.preview(expected_revision=case['accounts'].read()['revision'],
                    target_id=original['target_id'], expected_proposal_id=case['proposal']['proposal_id'])
            self.assertEqual(result['proposal_id'], case['proposal']['proposal_id'])
            self.assertEqual(original, case['target'])
            self.assertEqual(account_bytes, case['accounts'].path.read_bytes())
            self.assertTrue(result['risk_valid_until'])
            self.assertEqual(result['status'], 'READY')
            self.assertTrue(result['new_orders'])
            for order in result['new_orders']:
                self.assertEqual(order['proposal_id'], case['proposal']['proposal_id'])
            return result

    def test_positive_cash_real_execution_bridge(self):
        self.run_case('20000')

    def test_zero_cash_real_sell_only_bridge(self):
        result = self.run_case('0')
        self.assertTrue(all(order['side'] == 'SELL' for order in result['new_orders']))

    def test_buy_data_missing_preserves_real_sell_bridge(self):
        result = self.run_case('20000', buy_data_missing=True)
        self.assertEqual(result['buy_data_failure'], 'MINUTE_GAP')
        self.assertTrue(all(order['side'] == 'SELL' for order in result['new_orders']))


if __name__ == '__main__':
    unittest.main()
