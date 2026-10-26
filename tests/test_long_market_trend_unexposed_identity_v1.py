import unittest
from copy import deepcopy
import test_long_market_trend_research_v1 as fixtures
from backtest.long_market_trend_research_v1 import run_trend
from backtest.long_market_trend_independent_review_v1 import review
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class UnexposedIdentityTests(unittest.TestCase):
    def fixture(self):
        signals, domain = fixtures.TrendTests().fixture()
        book = run_trend(signals=signals, signal_source_hashes={'qqq':'pinned'},
            assembled=domain, ohlc={}, initial_cash='1000', fee_bps='0', slippage_bps='5',
            max_new_searches=1, risk=MonthlyExitCoreResearchAdapter())
        action = dict(type='split_identity', date='2024-10-01', security_id='OLD',
            new_security_id='NEW', new_shares='10', old_shares='1', source_references=['official'])
        domain['actions'] = [action]
        domain['provider_actions'] = deepcopy(domain['actions'])
        return signals, domain, book

    def audit(self, signals, domain, book, **kwargs):
        return review(book, domain, {}, initial_cash='1000', dividend_events=[],
            signals=signals, signal_source_hashes={'qqq':'pinned'}, expected_fee_bps='0',
            expected_slippage_bps='5', **kwargs)

    def test_zero_exposure_is_not_liquidation(self):
        proof = self.audit(*self.fixture(), verify_selections=True, verify_risk_provider=True)
        self.assertEqual(proof['unexposed_identity_events_checked'], 1)
        self.assertEqual(proof['integer_identity_liquidations_checked'], 0)

    def test_related_buy_cannot_take_zero_exposure_shortcut(self):
        for sid in ('OLD', 'NEW'):
            signals, domain, book = self.fixture()
            book['provider_audit'][0]['orders'] = [dict(id='x', security_id=sid,
                active_date='2024-10-01', side='BUY', quantity=1)]
            with self.subTest(sid=sid), self.assertRaisesRegex(ValueError, 'IDENTITY_POSITION_CONFLICT'):
                self.audit(signals, domain, book, verify_selections=False)

    def test_existing_successor_position_rejected(self):
        signals, domain, book = self.fixture()
        domain['close_prices']['NEW'] = {'2024-09-30':'1'}
        with self.assertRaisesRegex(ValueError, 'IDENTITY_POSITION_CONFLICT'):
            self.audit(signals, domain, book, initial_shares={'NEW':1}, verify_selections=False)

    def test_old_identity_is_terminated_even_without_exposure(self):
        signals, domain, book = self.fixture()
        domain['session_dates'].append('2024-10-02')
        row = deepcopy(book['daily_ledger'][0]); row['date'] = '2024-10-02'
        book['daily_ledger'].append(row)
        audit = deepcopy(book['provider_audit'][0]); audit.pop('selection', None)
        audit['orders'] = [dict(id='bad', security_id='OLD', active_date='2024-10-02', side='BUY', quantity=1)]
        book['provider_audit'].append(audit)
        with self.assertRaisesRegex(ValueError, 'TERMINATED_ORDER_REAPPEARED'):
            self.audit(signals, domain, book, verify_selections=False)


if __name__ == '__main__':
    unittest.main()
