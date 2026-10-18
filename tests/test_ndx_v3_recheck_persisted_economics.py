"""Independent persisted-ledger arithmetic audit; never runs an optimizer."""
import csv
import hashlib
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / 'data/cache/research/ndx_joint_weight_experiment_v2'
REPORTS = {
    0: 'b713a80cdf706534a1a23f29a9fed36d8923eebef0dc10a198090cbafa52c281',
    1: '51a3e53e0f9496f98a6d61432e6a476c2299ff1fbd647cec7d988f3f77012268',
    2: '7a9095e4186aaee4fa760c955d1946f4c189b5c3f9a57c4f7f4968cf5510e942',
    3: 'f81b857188e80c5e63419219e0bf484154de085671184171288f94abde96e06b',
}


def decode(value):
    if isinstance(value, dict):
        if set(value) == {'mapping'}:
            return {key: decode(item) for key, item in value['mapping'].items()}
        if set(value) == {'float_hex'}:
            return float.fromhex(value['float_hex'])
        if set(value) == {'timestamp'}:
            return value['timestamp'][:10]
        if set(value) == {'sequence_type', 'items'}:
            return [decode(item) for item in value['items']]
        raise ValueError('Unknown captured encoding')
    return value


class PersistedEconomicsTests(unittest.TestCase):
    def same_number(self, actual, expected):
        self.assertTrue(math.isfinite(actual) and math.isfinite(expected))
        self.assertLessEqual(abs(actual - expected), 1e-8)

    def read_bound(self, path, digest):
        raw = Path(path).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), digest)
        return raw

    def metrics(self, equity):
        peak, drawdown = equity[0], 0.
        for value in equity:
            peak = max(peak, value)
            drawdown = max(drawdown, 1 - value / peak)
        ratio = equity[-1] / equity[0]
        return ratio - 1, drawdown, ratio ** (252 / (len(equity) - 1)) - 1

    def audit(self, case_index, digest):
        report = json.loads(self.read_bound(
            REPORT_ROOT / f'v3_same_execution_case{case_index}_20260911.json', digest))
        self.assertEqual(report['case_index'], case_index)
        self.assertFalse(report['promotion_allowed'])
        self.assertFalse(report['portfolio_selection_precedes_execution'])
        self.assertEqual(report['corporate_actions'], [])
        prices = {}
        for item in report['nominal_bundle']['evidence']:
            raw = self.read_bound(item['path'], item['sha256'])
            self.read_bound(item['sidecar_path'], item['sidecar_sha256'])
            rows = list(csv.DictReader(raw.decode('utf-8-sig').splitlines()))
            self.assertEqual(len({row['Date'] for row in rows}), len(rows))
            prices[item['ticker']] = {row['Date']: float(row['Close']) for row in rows}
        calendar = report['calendar']
        self.assertEqual(len(calendar), len(set(calendar)))
        for role in ('candidate', 'incumbent'):
            path = report[role]
            names = sorted(path['terminal_shares'])
            shares = {ticker: 0 for ticker in names}
            cash = report['inherited_context_capital_usd']
            fees, equity = 0., []
            executions = {row['execution_date']: row for row in path['executions']}
            decisions = {row['decision_date']: row for row in path['decisions']}
            self.assertEqual(len(executions), len(path['executions']))
            self.assertEqual(len(decisions), len(path['decisions']))
            self.assertEqual(path['corporate_action_ledger'], [])
            self.assertEqual([row['date'] for row in path['daily']], calendar)
            for index, row in enumerate(path['daily']):
                date = row['date']
                if date in executions:
                    execution = executions[date]
                    decision = decisions[execution['decision_date']]
                    self.assertEqual(index, calendar.index(execution['decision_date']) + 1)
                    self.assertEqual(shares, execution['pretrade_shares'])
                    self.assertEqual(shares, decision['baseline_shares'])
                    self.same_number(cash, execution['pretrade_cash_usd'])
                    self.same_number(cash, decision['baseline_cash_usd'])
                    delta = execution['frozen_delta_shares']
                    self.assertEqual(delta, decision['delta_shares'])
                    for ticker in names:
                        self.same_number(execution['fill_prices'][ticker], prices[ticker][date])
                    amount = sum(abs(delta[ticker]) * prices[ticker][date] for ticker in names)
                    fee = amount * path['transaction_cost_bps'] / 10000
                    proposed = cash - sum(delta[ticker] * prices[ticker][date] for ticker in names) - fee
                    self.same_number(fee, execution['estimated_fill_fees_usd'])
                    self.same_number(proposed, execution['hypothetical_posttrade_cash_usd'])
                    if execution['status'] in ('FILLED', 'NO_TRADE_REQUIRED'):
                        self.assertGreaterEqual(proposed, path['minimum_cash_buffer_usd'] - 1e-9)
                        cash = proposed
                        shares = {ticker: shares[ticker] + delta[ticker] for ticker in names}
                        fees += fee
                        self.same_number(fee, execution['fees_usd'])
                        self.same_number(amount, execution['trade_notional_usd'])
                    else:
                        self.assertEqual(execution['status'], 'REJECTED_INSUFFICIENT_CASH_AT_FILL')
                        self.assertLess(proposed, path['minimum_cash_buffer_usd'] - 1e-9)
                        self.same_number(0., execution['fees_usd'])
                        self.same_number(0., execution['trade_notional_usd'])
                    self.assertEqual(shares, execution['posttrade_shares'])
                    self.same_number(cash, execution['posttrade_cash_usd'])
                self.assertEqual(shares, row['shares'])
                self.same_number(cash, row['cash_usd'])
                value = cash + sum(shares[ticker] * prices[ticker][date] for ticker in names)
                self.same_number(value, row['equity_usd'])
                equity.append(value)
                if date in decisions:
                    self.assertEqual(shares, decisions[date]['baseline_shares'])
                    self.same_number(cash, decisions[date]['baseline_cash_usd'])
                    for ticker in names:
                        self.same_number(prices[ticker][date], decisions[date]['decision_prices'][ticker])
            self.assertEqual(shares, path['terminal_shares'])
            self.same_number(cash, path['terminal_cash_usd'])
            self.same_number(fees, path['total_fees_usd'])
            self.same_number(equity[-1], path['terminal_equity_usd'])
            for actual, field in zip(self.metrics(equity),
                    ('path_return_net', 'path_max_drawdown', 'annualized_return_252_session')):
                self.same_number(actual, path[field])
        context_path = next(path for path in report['source_hashes'] if path.endswith('context.json'))
        context = json.loads(self.read_bound(context_path, report['preparation']['context_sha256']))
        target = decode(context['prepared_inputs']['target_returns']['payload'])
        returns = dict(zip(target['index'], target['column_values'][0]))
        equity = [1.]
        for date in calendar[1:]:
            equity.append(equity[-1] * (1 + returns[date]))
        self.assertEqual(equity, report['nav_benchmark']['equity_index'])
        for actual, field in zip(self.metrics(equity),
                ('path_return', 'path_max_drawdown', 'annualized_return_252_session')):
            self.same_number(actual, report['nav_benchmark'][field])

    def test_all_explicit_completed_reports(self):
        self.assertEqual(set(REPORTS), {0, 1, 2, 3})
        for index, digest in REPORTS.items():
            with self.subTest(case=index):
                self.audit(index, digest)


if __name__ == '__main__':
    unittest.main()
