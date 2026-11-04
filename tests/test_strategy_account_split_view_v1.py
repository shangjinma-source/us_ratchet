from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from api.strategy_account import StrategyAccountService
from api.strategy_account_split_v1 import SplitStrategyAccountService


class SplitViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.service = SplitStrategyAccountService(database_path=Path(self.directory.name)/'account.sqlite3',
            account_id='test', resolver=lambda ticker: None,
            clock=lambda: datetime.fromisoformat('2026-11-20T16:00:00+00:00'))
        self.state = self.service.store.initialize('test', operation_id='init')
        self.append(dict(event_id='buy', kind='DIRECT_FILL', security_id='S', side='BUY', quantity=14,
            price='1000', fees='14', executed_at='2026-11-02T15:00:00Z'))
        self.split = dict(event_id='split', kind='SPLIT_CONFIRMED', action_id='action', security_id='S',
            ratio=8, effective_at='2026-11-20T14:30:00Z', broker_confirmed_at='2026-11-20T14:31:00Z',
            old_unit_id='old', new_unit_id='new', evidence_sha256='a'*64)

    def append(self, event):
        self.state, _ = self.service.store.append(event, expected_revision=self.state['revision'])

    def test_unchanged_legacy_view_before_split(self):
        self.assertEqual(self.service.project(self.state), StrategyAccountService.project(self.service, self.state))

    def test_split_preserves_cost_and_original_fills(self):
        before = self.service.read()['account']
        self.append(self.split)
        after = self.service.read()['account']
        self.assertEqual(after['fills'], before['fills'])
        self.assertEqual(after['holding_costs'][0]['total_cost'], '14014')
        self.assertEqual(after['holding_costs'][0]['quantity'], 112)
        self.assertEqual(Fraction(after['holding_costs'][0]['average_cost']), Fraction(1001, 8))
        self.assertEqual(len(after['corporate_actions']), 1)
        self.assertEqual(after['cash_summary']['recorded_fill_cash_delta_since_confirmation'],
                         before['cash_summary']['recorded_fill_cash_delta_since_confirmation'])

    def test_post_split_partial_and_full_sales_keep_average_cost(self):
        self.append(self.split)
        self.append(dict(event_id='sell', kind='DIRECT_FILL', security_id='S', side='SELL', quantity=8,
            price='150', fees='1', executed_at='2026-11-20T15:00:00Z'))
        account = self.service.read()['account']
        self.assertEqual(account['holding_costs'][0]['total_cost'], '13013')
        self.assertEqual(Fraction(account['holding_costs'][0]['average_cost']), Fraction(1001, 8))
        self.append(dict(event_id='sell-rest', kind='DIRECT_FILL', security_id='S', side='SELL', quantity=104,
            price='150', fees='1', executed_at='2026-11-20T15:01:00Z'))
        self.assertEqual(self.service.read()['account']['holding_costs'], [])

    def test_browser_cannot_submit_split_authority(self):
        before = deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'EVENT_FIELDS'):
            self.service.append(dict(expected_revision=self.state['revision'], event=self.split))
        self.assertEqual(self.service.store.read(), before)
