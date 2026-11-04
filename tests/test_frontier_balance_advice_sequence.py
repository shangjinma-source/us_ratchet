"""Scaled synthetic cash changes through the proposal-aware daily composition.

No live account or network access; this is not production cash-button acceptance.
"""
from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from data.saved_frontier_daily_composition_v1 import SavedFrontierDailyComposition
from data.saved_frontier_cap_exit_reader import POLICY_ID, project_saved_frontier_cap_exit, clone_monthly_risk_store
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
import test_saved_frontier_isolated_pipeline as fixture


class BalanceAdviceSequenceTests(unittest.TestCase):
    def test_increase_withdraw_and_zero_balance_recompute_budget_without_reselection(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'tmp') as directory:
            case = fixture.IsolatedFrontierPipelineTests().case(directory, cash='100', cancel=True, fee='0')
            case['accounts'].clock = lambda: case['clock'][0]
            archive_saved_frontier_policy(research_root=case['root'], target=case['target'],
                proposal=case['proposal'], source_files=case['source_files'], enabled=True)
            original_target = deepcopy(case['target'])
            original_shares = deepcopy(case['accounts'].read()['shares'])
            original_risk = case['risk_path'].read_bytes()
            monthly = SimpleNamespace(accounts=case['accounts'], current=lambda: deepcopy(case['target']),
                snapshot_operation=nullcontext, validate_current_target_pins=lambda: None)
            calls = 0

            def proposal(**arguments):
                self.assertEqual(arguments['expected_proposal_id'], case['proposal']['proposal_id'])
                return deepcopy(case['proposal'])

            def reader(state, target, now, *, proposal):
                nonlocal calls
                calls += 1
                fixture.current_review(case)
                risk_path = clone_monthly_risk_store(research_root=case['root'],
                    source_path=case['risk_path'], source_sha256=fixture.digest(original_risk),
                    clone_name=f'balance-risk-{calls}.sqlite3')['path']
                return project_saved_frontier_cap_exit(research_root=case['root'], risk_path=risk_path,
                    target_id=target['target_id'], state=state, review_bytes=case['review_bytes'],
                    trusted_review_sha256=case['trusted_review_sha256'], files=case['files'],
                    now=now.isoformat(), enabled=True)

            service = SavedFrontierDailyComposition(monthly_service=monthly,
                monthly_view=SimpleNamespace(require_proposal=proposal), evidence_reader=reader,
                execution_provider=case['provider'].execution, clock=lambda: case['clock'][0],
                policy_execution_enabled=True, policy_id=POLICY_ID, fee_bps='0')

            def preview(revision):
                case['clock'][0] += timedelta(minutes=1)
                return service.preview(expected_revision=revision, target_id=case['target']['target_id'],
                    expected_proposal_id=case['proposal']['proposal_id'])

            quantities = {}
            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 patch('data.strategy_account_evidence_provider.compile_saved_training',
                       side_effect=AssertionError('RESELECTION_FORBIDDEN')):
                for index, amount in enumerate(('100', '300', '50', '0')):
                    before = case['accounts'].read()
                    event = dict(event_id=f'balance-sequence-{index}', kind='CASH_CONFIRM',
                        amount=amount, cash_basis='AVAILABLE_AFTER_RESERVATIONS')
                    case['accounts'].append(event, expected_revision=before['revision'])
                    confirmed = case['accounts'].read()
                    self.assertNotEqual(confirmed['revision'], before['revision'])
                    with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
                        preview(before['revision'])
                    first = preview(confirmed['revision'])
                    self.assertEqual(first['status'], 'READY')
                    buys = [order for order in first['new_orders'] if order['side'] == 'BUY']
                    quantities[amount] = sum(order['quantity'] for order in buys)
                    cost = -sum((Fraction(order['estimated_cash_change']) for order in buys), Fraction(0))
                    self.assertLessEqual(cost, Fraction(amount))
                    self.assertTrue(all(type(order['quantity']) is int and order['quantity'] > 0
                                        for order in first['new_orders']))
                    self.assertTrue(all(order['proposal_id'] == case['proposal']['proposal_id']
                                        for order in first['new_orders']))
                    repeated = preview(confirmed['revision'])
                    actions = lambda result: [(order['security_id'], order['side'], order['quantity'],
                                               order['limit_price']) for order in result['new_orders']]
                    self.assertEqual(actions(repeated), actions(first))
                    self.assertEqual(case['accounts'].read(), confirmed)
                    self.assertEqual(confirmed['shares'], original_shares)
                    self.assertEqual(case['target'], original_target)
                    self.assertEqual(case['risk_path'].read_bytes(), original_risk)
                    # A repeated identical cash event is idempotent, not a second deposit.
                    case['accounts'].append(event, expected_revision=before['revision'])
                    self.assertEqual(case['accounts'].read(), confirmed)
                self.assertGreater(quantities['100'], 0)
                self.assertGreater(quantities['300'], quantities['100'])
                self.assertEqual(quantities['50'], 0)
                self.assertEqual(quantities['0'], 0)
                self.assertTrue(any(order['side'] == 'SELL' for order in first['new_orders']))


if __name__ == '__main__':
    unittest.main()
