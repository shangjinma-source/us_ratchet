"""Synthetic two-stock accounts; real news risk, original risk and fill kernels."""
from fractions import Fraction
import unittest

from backtest.guidance_cash_next_open_book_research_v1 import run_next_open_book
from backtest.historical_dividend_next_open_book_research import run_next_open_book as baseline_book
from backtest.guidance_news_risk_research_v1 import GuidanceNewsRiskAdapter
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


class BuyBlockCashAllocationTests(unittest.TestCase):
    def run_account(self, *, blocked=False, fee='0', cash=None, shares=None,
                    targets=None, baseline=False):
        days = ['2026-01-28', '2026-01-29', '2026-01-30']
        targets = targets or {'A': 10, 'B': 10}
        initial = dict(shares or {})
        buy_price = Fraction(10) * Fraction('1.0005')
        cash = Fraction(cash) if cash is not None else 10 * buy_price * (1 + Fraction(fee)/10000)
        bars = {sid: {day: dict(open='10', high='10', low='10', close='10') for day in days}
                for sid in ('A', 'B')}
        events = [dict(id='synthetic-cut', classification='CUT', security_id='A',
                       comparison_key='synthetic-period', available_at='2026-01-28T20:00:00Z',
                       period_end='2026-12-31', source_hashes=['synthetic'], review_reference='synthetic-only')] if blocked else []
        base = MonthlyExitCoreResearchAdapter()
        risk = base if baseline else GuidanceNewsRiskAdapter(base, events=events,
            session_closes={day: day+'T21:00:00Z' for day in days}, action_policy='BLOCK_NEW_BUYS')
        decisions = []

        def provider(*, decision_date, active_date, state):
            arguments = dict(day=decision_date, month=days[0], target=dict(targets),
                             closes={'A': '10', 'B': '10'})
            if not baseline:
                arguments['shares'] = dict(state['shares'])
            effective, diagnostics = risk.apply(**arguments)
            decisions.append(dict(target=effective, shares=dict(state['shares'])))
            orders = []
            for sid in sorted(set(effective) | set(state['shares'])):
                delta = effective.get(sid, 0) - state['shares'].get(sid, 0)
                if delta:
                    orders.append(dict(id=decision_date+':'+sid, security_id=sid,
                        side='BUY' if delta > 0 else 'SELL', quantity=abs(delta),
                        decision_mark='10', decision_date=decision_date, active_date=active_date))
            return dict(status='READY', orders=orders, target_decision_date=days[0],
                        news_sale_fractions={}, risk_overlay=diagnostics)

        arguments = dict(session_dates=days, ohlc=bars, initial_cash=str(cash),
                         initial_shares=initial, fee_bps=fee, slippage_bps='5', order_provider=provider)
        if not baseline:
            arguments['news_allocation_dates'] = [days[0]]
        result = (baseline_book if baseline else run_next_open_book)(**arguments)
        self.assertEqual(result['status'], 'COMPLETE', result.get('reason'))
        fills = [r for r in result['order_log'] if r.get('event') == 'ASSUMED_NEXT_OPEN_FILLED']
        expected_cash = cash
        expected_shares = dict(initial)
        fees = Fraction(0)
        for fill in fills:
            quantity, price, charged = fill['quantity'], Fraction(fill['price']), Fraction(fill['fee'])
            self.assertIs(type(quantity), int)
            self.assertGreater(quantity, 0)
            self.assertEqual(charged, quantity * price * Fraction(fee)/10000)
            sign = 1 if fill['side'] == 'BUY' else -1
            expected_cash -= sign * quantity * price + charged
            expected_shares[fill['security_id']] = expected_shares.get(fill['security_id'], 0) + sign*quantity
            fees += charged
        self.assertEqual(Fraction(result['cash']), expected_cash)
        self.assertEqual(Fraction(result['fees']), fees)
        self.assertGreaterEqual(expected_cash, 0)
        for sid in ('A', 'B'):
            self.assertEqual(result['shares'].get(sid, 0), expected_shares.get(sid, 0))
        for row in result['daily_ledger']:
            self.assertEqual(Fraction(row['equity']), Fraction(row['cash']) + sum(row['shares'].values())*10)
            self.assertEqual(Fraction(row.get('news_reserved_cash', '0')), 0)
        return result, decisions, fills

    def test_buy_block_increases_other_fill_without_increasing_target(self):
        for fee in ('0', '10'):
            with self.subTest(fee=fee):
                control, _, _ = self.run_account(fee=fee)
                blocked, decisions, fills = self.run_account(blocked=True, fee=fee)
                self.assertEqual(control['daily_ledger'][0]['shares'], {'A': 5, 'B': 5})
                self.assertEqual(blocked['shares'].get('A', 0), 0)
                self.assertEqual(blocked['shares']['B'], 10)
                self.assertTrue(all(row['target']['B'] == 10 for row in decisions))
                self.assertTrue(all(row['target']['A'] == 0 for row in decisions))
                self.assertFalse(any(r['side'] == 'SELL' for r in fills))
                self.assertEqual(Fraction(blocked['cash']), 0)

    def test_no_event_matches_original_baseline(self):
        old, _, old_fills = self.run_account(baseline=True, fee='10', cash='105')
        new, _, new_fills = self.run_account(fee='10', cash='105')
        for key in ('cash', 'shares', 'fees'):
            self.assertEqual(old[key], new[key])
        self.assertEqual(old_fills, new_fills)
        self.assertEqual(old['daily_ledger'], [{k:v for k,v in row.items() if not k.startswith('news_')}
                                             for row in new['daily_ledger']])
        self.assertGreater(Fraction(new['cash']), 0)  # Integer-floor residue is not redistributed.

    def test_original_sell_is_preserved_and_funds_other_buy(self):
        parameters = dict(fee='10', cash='0', shares={'A': 10}, targets={'A': 5, 'B': 10})
        control, _, control_fills = self.run_account(**parameters)
        blocked, decisions, fills = self.run_account(blocked=True, **parameters)
        self.assertEqual(fills, control_fills)
        self.assertEqual(fills[0]['side'], 'SELL')
        self.assertEqual(fills[0]['security_id'], 'A')
        self.assertEqual(fills[0]['quantity'], 5)
        self.assertTrue(any(r['side'] == 'BUY' and r['security_id'] == 'B' for r in fills))
        self.assertEqual(blocked['shares']['A'], 5)
        self.assertTrue(all(row['target']['A'] == 5 for row in decisions))
        self.assertEqual(blocked['cash'], control['cash'])
        self.assertFalse(any(r['event'] == 'NEWS_NET_PROCEEDS_RESERVED' for r in blocked['order_log']))


if __name__ == '__main__':
    unittest.main()
