"""Hand-accounted tiny sale and rejection of inconsistent saved evidence."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from scripts.analyze_drift_cap_trade_burden import analyze


class TradeBurdenTest(unittest.TestCase):
    def evidence(self):
        # Five shares rise from $100 to $120, then one share sells with 10bp slip
        # and 1bp fee. Hand amounts: sale $119.88, fee $0.011988.
        sid = 'stock'
        fee = Fraction('0.011988')
        order = dict(id='sale', active_date='2024-01-04', security_id=sid, side='SELL', quantity=1)
        book = dict(status='COMPLETE', external_flows='0', slippage_bps='10', fees=str(fee),
                    selection_account_states=[dict(valuation_quotes=[dict(security_id=sid, ticker='ABC')])],
                    provider_audit=[dict(orders=[order], monthly_ceiling={sid: 5},
                        risk_overlay=dict(state=dict(session_date='2024-01-03'), effective_target_quantities={sid: 5}),
                        drift_overlay=dict(reductions=[dict(security_id=sid, before=5, after=4)]))],
                    order_log=[dict(date='2024-01-04', id='sale', security_id=sid, side='SELL',
                        quantity=1, price='119.88', fee=str(fee), event='ASSUMED_NEXT_OPEN_FILLED')],
                    daily_ledger=[dict(date='2024-01-02', shares={sid: 5}, cash='500', stock_value='500', equity='1000'),
                        dict(date='2024-01-03', shares={sid: 5}, cash='500', stock_value='600', equity='1100'),
                        dict(date='2024-01-04', shares={sid: 4}, cash='619.868012', stock_value='480', equity='1099.868012')])
        bars = dict(ohlc={sid: {'2024-01-02': dict(open='100', close='100'),
                              '2024-01-03': dict(open='120', close='120'),
                              '2024-01-04': dict(open='120', close='120')}})
        return book, bars

    def run_evidence(self, book, bars):
        with tempfile.TemporaryDirectory() as directory:
            book_path, bars_path = Path(directory) / 'book.json', Path(directory) / 'bars.json'
            book_path.write_text(json.dumps(book), encoding='utf-8')
            bars_path.write_text(json.dumps(bars), encoding='utf-8')
            return analyze(book_path, bars_path)

    def test_hand_calculated_single_share_trim(self):
        report = self.run_evidence(*self.evidence())
        self.assertEqual(report['days_largest_exceeds_50'], 1)
        self.assertEqual(report['days_largest_exceeds_55'], 0)
        self.assertEqual(report['fill_categories'], {'drift_reduction': 1})
        self.assertEqual(report['drift_trim_quantity_frequency'], {1: 1})
        self.assertEqual(Fraction(report['gross_buy_sell_notional']), Fraction('119.88'))
        self.assertEqual(Fraction(report['modeled_fees']), Fraction('0.011988'))
        self.assertEqual(Fraction(report['modeled_adverse_slippage']), Fraction('0.12'))

    def test_inconsistent_marks_or_fee_rejected(self):
        book, bars = self.evidence()
        changed = deepcopy(bars)
        changed['ohlc']['stock']['2024-01-03']['close'] = '121'
        with self.assertRaisesRegex(ValueError, 'RECONCILIATION_FAILED'):
            self.run_evidence(book, changed)
        book['fees'] = '0'
        with self.assertRaisesRegex(ValueError, 'FEE_RECONCILIATION_FAILED'):
            self.run_evidence(book, bars)

    def test_fill_bound_to_real_order(self):
        book, bars = self.evidence()
        book['order_log'][0]['date'] = '2024-01-03'
        with self.assertRaisesRegex(ValueError, 'FILL_ORDER_IDENTITY_MISMATCH'):
            self.run_evidence(book, bars)


if __name__ == '__main__':
    unittest.main()
