from fractions import Fraction
from copy import deepcopy
from unittest.mock import patch
import unittest
from backtest import guidance_frontier_research_v1 as candidate
from backtest import historical_dividend_frontier_research as baseline
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from backtest.guidance_news_risk_research_v1 import GuidanceNewsRiskAdapter
import test_historical_dividend_frontier_research as fixtures
from backtest.guidance_cash_independent_review_v1 import review_news_cash


class GuidanceFrontierTests(unittest.TestCase):
    def run_book(self, module, news_events=()):
        assembled, bars, dividend = fixtures.FrontierWiringTests().fixture()
        base = MonthlyExitCoreResearchAdapter()
        risk = GuidanceNewsRiskAdapter(base, events=news_events, session_closes={day: day+'T21:00:00Z' for day in assembled['session_dates']}) if module is candidate else base
        def select(**kwargs):
            account = kwargs['account_state']
            equity = Fraction(account['cash']) + account['shares'].get('A', 0)*10
            return dict(target_quantities={'A': int(equity/11)}, investable_equity=str(equity))
        # Only selection scoring is stubbed. Provider, original risk, news risk,
        # incremental attribution, fills and dividends execute real code.
        with patch.object(module, 'decide_continuous_guided_for_account', side_effect=select), patch.object(module, 'rerank', side_effect=lambda value: value):
            return module.run_frontier_capped_next_open(assembled=assembled, ohlc=bars,
                initial_cash='110', fee_bps='0', slippage_bps='5', risk=risk, max_new_searches=3, dividend_events=[dividend])

    def test_no_news_matches_original_financial_path(self):
        old, new = self.run_book(baseline), self.run_book(candidate)
        self.assertEqual(new['status'], 'COMPLETE')
        for field in ('cash', 'shares', 'fees', 'total_return', 'selection_account_states', 'drawdown', 'dividend_ledger'):
            self.assertEqual(new[field], old[field], field)
        rows = [{key: value for key, value in row.items() if not key.startswith('news_')} for row in new['daily_ledger']]
        self.assertEqual(rows, old['daily_ledger'])
        self.assertEqual(review_news_cash(new)['status'], 'CASH_ATTRIBUTION_REVIEW_PASS')

    def test_news_exit_reaches_fill_and_next_selection_real_state(self):
        event = dict(id='cut', classification='CUT', security_id='A', comparison_key='FY2020-revenue',
                     available_at='2020-01-31T20:00:00Z', period_end='2020-12-31',
                     source_hashes=['synthetic'], review_reference='synthetic')
        result = self.run_book(candidate, [event])
        self.assertEqual(result['status'], 'COMPLETE')
        reservations = [row for row in result['order_log'] if row['event'] == 'NEWS_NET_PROCEEDS_RESERVED']
        self.assertEqual(len(reservations), 1)
        self.assertEqual(reservations[0]['fraction'], '1')
        self.assertGreater(Fraction(result['daily_ledger'][1]['news_reserved_cash']), 0)
        self.assertEqual(result['daily_ledger'][2]['news_reserved_cash'], '0')
        state = result['selection_account_states'][1]['account_state']
        self.assertEqual(state['shares'].get('A', 0), 0)
        self.assertEqual(state['cash'], result['daily_ledger'][1]['cash'])
        self.assertEqual(review_news_cash(result)['reservations'], 1)
        altered = deepcopy(result)
        next(row for row in altered['order_log'] if row['event'] == 'NEWS_NET_PROCEEDS_RESERVED')['amount'] = '0'
        with self.assertRaisesRegex(ValueError, 'NET_PROCEEDS_MISMATCH'):
            review_news_cash(altered)
        altered = deepcopy(result)
        altered['daily_ledger'][1]['news_reserved_cash'] = '0'
        with self.assertRaisesRegex(ValueError, 'DAILY_NEWS_CASH_MISMATCH'):
            review_news_cash(altered)

    def test_mixed_sale_attribution(self):
        def attribute(original, news, quantity):
            return candidate.attribute_news_sales(shares={'A': 10}, original_target={'A': original}, news_target={'A': news},
                orders=[dict(id='sale', side='SELL', security_id='A', quantity=quantity)])
        self.assertEqual(attribute(5, 0, 10), {'sale': '1/2'})
        self.assertEqual(attribute(0, 0, 10), {})
        with self.assertRaises(ValueError):
            attribute(5, 0, 9)

    def test_empty_risk_state_survives_unexposed_wait_callback(self):
        assembled, bars, _ = fixtures.FrontierWiringTests().fixture()
        days = assembled['session_dates'][:4]
        assembled['session_dates'] = days
        assembled['monthly_inputs'] = assembled['monthly_inputs'][:1]
        assembled['distribution_events'] = [dict(event_id='unexposed', effective_date=days[1], timing='AFTER_CLOSE',
            parent_sid='X', post_parent_sid='X', child_sid='Y', source_references=['synthetic'])]
        risk = GuidanceNewsRiskAdapter(MonthlyExitCoreResearchAdapter(), events=[], session_closes={day:day+'T21:00:00Z' for day in days})
        def provider(**kwargs):
            return dict(status='READY', orders=[], target_shares={}, target_decision_date=days[0],
                        action='WAIT_POST_ACTION_MARK' if kwargs['decision_date'] == days[1] else 'NO_ACTION')
        results = []
        def exercise_callbacks(**kwargs):
            for previous, active in zip(days, days[1:]):
                results.append(kwargs['order_provider'](decision_date=previous, active_date=active,
                    state=dict(shares={}, cash='110', distribution_rights=[], merger_entitlements=[])))
            return dict(status='COMPLETE', daily_ledger=[])
        # Narrow callback test: real original/news risk and unexposed review;
        # kernel corporate-action accounting is not certified by this fixture.
        with patch.object(candidate, 'build_cost_monthly_quantity_provider', return_value=provider), patch.object(candidate, 'run_next_open_book', side_effect=exercise_callbacks):
            candidate.run_frontier_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='110', fee_bps='0', slippage_bps='5', risk=risk)
        self.assertTrue(all(row['status'] == 'READY' for row in results))
        self.assertEqual(results[1]['action'], 'WAIT_POST_ACTION_MARK')
        self.assertEqual(results[1]['orders'], [])
        self.assertIsNone(risk.state)
