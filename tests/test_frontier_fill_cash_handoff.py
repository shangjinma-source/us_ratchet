"""Synthetic ledger -> proposal-aware composition handoff; no real account access.

Uses the production composition with the existing isolated source/risk adapter.
It does not certify the production mount, live capture or broker execution.
"""
from contextlib import nullcontext
from copy import deepcopy
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from data.saved_frontier_daily_composition_v1 import SavedFrontierDailyComposition
from data.saved_frontier_cap_exit_reader import POLICY_ID, project_saved_frontier_cap_exit, clone_monthly_risk_store
from data.saved_frontier_policy_archive import archive_saved_frontier_policy
import test_saved_frontier_isolated_pipeline as fixture


class FrontierFillCashHandoffTests(unittest.TestCase):
    def test_sell_requires_cash_confirmation_and_refresh_does_not_repeat_fill(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'tmp') as directory:
            case = fixture.IsolatedFrontierPipelineTests().case(directory, cash='0', cancel=True)
            case['accounts'].clock = lambda: case['clock'][0]
            archive_saved_frontier_policy(research_root=case['root'], target=case['target'],
                proposal=case['proposal'], source_files=case['source_files'], enabled=True)
            original_target = deepcopy(case['target'])
            original_risk = case['risk_path'].read_bytes()
            monthly = SimpleNamespace(accounts=case['accounts'], current=lambda: deepcopy(case['target']),
                snapshot_operation=nullcontext, validate_current_target_pins=lambda: None)
            count = 0

            def proposal(**arguments):
                self.assertEqual(arguments['expected_proposal_id'], case['proposal']['proposal_id'])
                return deepcopy(case['proposal'])

            def reader(state, target, now, *, proposal):
                nonlocal count
                count += 1
                # Rebind explicit synthetic evidence after each ledger change.
                # Each projection starts with the same immutable source risk store.
                fixture.current_review(case)
                risk_path = clone_monthly_risk_store(research_root=case['root'],
                    source_path=case['risk_path'], source_sha256=fixture.digest(original_risk),
                    clone_name=f'handoff-risk-{count}.sqlite3')['path']
                return project_saved_frontier_cap_exit(research_root=case['root'], risk_path=risk_path,
                    target_id=target['target_id'], state=state, review_bytes=case['review_bytes'],
                    trusted_review_sha256=case['trusted_review_sha256'], files=case['files'],
                    now=now.isoformat(), enabled=True)

            service = SavedFrontierDailyComposition(monthly_service=monthly,
                monthly_view=SimpleNamespace(require_proposal=proposal), evidence_reader=reader,
                execution_provider=case['provider'].execution, clock=lambda: case['clock'][0],
                policy_execution_enabled=True, policy_id=POLICY_ID, fee_bps='1')

            def preview(revision=None):
                return service.preview(expected_revision=revision or case['accounts'].read()['revision'],
                    target_id=case['target']['target_id'], expected_proposal_id=case['proposal']['proposal_id'])

            with patch('socket.socket.connect', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 patch('data.strategy_account_evidence_provider.compile_saved_training',
                       side_effect=AssertionError('NEW_TRAINING_FORBIDDEN')):
                before = case['accounts'].read()
                orders = preview()['new_orders']
                self.assertEqual([(o['security_id'], o['side'], o['quantity']) for o in orders], [('D', 'SELL', 3)])
                identity = dict(security_id='D', ticker='D', source_references=['ledger-identity.json'],
                    source_hashes={'ledger-identity.json': fixture.digest(case['files']['ledger-identity.json'])})
                case['accounts'].append(dict(event_id='synthetic-sell', kind='DIRECT_FILL',
                    security_id='D', side='SELL', quantity=3, price='50', fees='0',
                    executed_at=case['clock'][0].isoformat(), identity_evidence=identity),
                    expected_revision=before['revision'])
                sold = case['accounts'].read()
                self.assertEqual(sold['shares'].get('D', 0), 0)
                self.assertFalse(sold['cash_confirmation_valid'])
                with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
                    preview(before['revision'])
                with self.assertRaisesRegex(ValueError, 'CASH_RECONFIRMATION_REQUIRED'):
                    preview()

                case['accounts'].append(dict(event_id='synthetic-cash-after-sale', kind='CASH_CONFIRM',
                    amount='150', cash_basis='TOTAL_UNINVESTED'), expected_revision=sold['revision'])
                confirmed = case['accounts'].read()
                first = preview()
                case['clock'][0] += timedelta(minutes=1)
                repeated = preview()
                actions = lambda result: [(o['security_id'], o['side'], o['quantity'], o['limit_price'])
                                          for o in result['new_orders']]
                self.assertEqual(actions(first), actions(repeated))
                self.assertEqual(first['status'], 'READY')
                self.assertTrue(first['new_orders'])
                self.assertTrue(all(o['side'] == 'BUY' and o['security_id'] == 'B' for o in first['new_orders']))
                self.assertLessEqual(-sum((Fraction(o['estimated_cash_change']) for o in first['new_orders']), Fraction(0)), 150)
                self.assertTrue(all(o['proposal_id'] == case['proposal']['proposal_id'] for o in first['new_orders']))
                self.assertEqual(case['accounts'].read(), confirmed)
                self.assertEqual(case['target'], original_target)
                self.assertEqual(case['risk_path'].read_bytes(), original_risk)


if __name__ == '__main__':
    unittest.main()
