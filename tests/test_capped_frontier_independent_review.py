"""Hand-computable ranking plus real wrapper/kernel with a fixed saved frontier."""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import math
import unittest
from unittest.mock import patch

from backtest.capped_frontier_independent_review import review_book, review_selection
from backtest.capped_frontier_rerank_research import rerank
from backtest.frontier_capped_next_open_research import run_frontier_capped_next_open
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter


def record(quantities, arguments):
    cash = F(arguments['entered_cash'])
    notional = sum((F(arguments['prices'][sid]) * quantity for sid, quantity in quantities.items()), F(0))
    fee = notional * F(arguments['fee_bps']) / 10000
    residual = cash - notional - fee
    relatives = arguments['training_scenarios'][0]
    growth = (residual + sum((F(arguments['prices'][sid]) * quantity * F(relatives[sid])
                             for sid, quantity in quantities.items()), F(0))) / cash
    return dict(quantities=quantities, actual_k=len(quantities), notional=str(notional), fees=str(fee),
                residual_cash=str(residual), training_mean_net_log_wealth=math.log(float(growth)),
                training_gross_growth_product=str(growth), actual_weights={sid: str(F(arguments['prices'][sid]) * quantity / cash)
                                                                          for sid, quantity in quantities.items()},
                exact_product_comparison=True, large_exact_product_serialization_omitted=False,
                cash_fraction=str(residual / cash), issuer_unique=True, budget_conservation_exact=True)


def raw_fixture(arguments=None, *, tie=False):
    decision = '2025-01-02'
    prices = {'A': '100', 'B': '100'}
    args = dict(prices=prices, metadata={sid: dict(ticker=sid, issuer_id=sid) for sid in prices},
                entered_cash='20000', fee_bps='1', minimum_cash_buffer='0',
                training_scenarios=[{'A': '2', 'B': '2' if tie else '9/5'}],
                scenario_dates=[decision], decision_date=decision, max_objective_evaluations=8192, fixed_seed='synthetic')
    sources = {'synthetic': '0' * 64}
    quotes = {sid: dict(price=price, as_of=decision, price_basis='SYNTHETIC_USD', source_references=['synthetic'])
              for sid, price in prices.items()}
    state = dict(revision='synthetic-book:' + decision, cash='20000', shares={})
    if arguments is not None:
        decision = arguments['decision_date']
        args = deepcopy(arguments['search_arguments'])
        args.pop('quote_as_of')
        args.pop('price_basis')
        state = arguments['account_state']
        quotes = {quote['security_id']: {key: quote[key] for key in ('price', 'as_of', 'price_basis', 'source_references')}
                  for quote in arguments['valuation_quotes']}
        sources = arguments['source_hashes']
        args['entered_cash'] = str(F(state['cash']) + sum(F(quotes[sid]['price']) * quantity for sid, quantity in state['shares'].items()))
    original = record({'A': 199}, args)
    pair = record({'A': 50, 'B': 50} if tie else {'A': 99, 'B': 99}, args)
    result = dict(method_version='FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1',
                  decision_date=decision, scenario_dates=args['scenario_dates'], entered_cash=args['entered_cash'],
                  fee_bps=args['fee_bps'], minimum_cash_buffer=args['minimum_cash_buffer'],
                  objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
                  fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION', selected=original,
                  best_by_k={'0': record({}, args), '1': original, '2': pair})
    binding = dict(schema='CAPITAL_DECISION_CONTINUOUS_GUIDED_EXPERIMENT_V1', decision_date=decision,
                   state_revision=state['revision'], available_cash=state['cash'], reserved_cash='0',
                   shares=deepcopy(state['shares']), valuation_quotes=quotes,
                   investable_equity=args['entered_cash'], search_arguments=args, source_hashes=sources,
                   continuous_iterations=32, selection_method=result['method_version'])
    identifier = sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                                  allow_nan=False).encode()).hexdigest()
    return dict(method=result['method_version'], decision_date=decision, decision_id=identifier,
                available_cash=state['cash'], state_revision=state['revision'], investable_equity=args['entered_cash'],
                target_quantities=original['quantities'], binding=binding, search_result=result)


def inputs():
    raw = raw_fixture()
    args = dict(raw['binding']['search_arguments'], quote_as_of='2025-01-02', price_basis='SYNTHETIC_USD')
    plan = dict(decision_date='2025-01-02', active_date='2025-01-03', search_arguments=args,
                valuation_quotes=[dict(security_id=sid, **quote) for sid, quote in raw['binding']['valuation_quotes'].items()],
                source_hashes=raw['binding']['source_hashes'])
    sessions = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08']
    closes = {'A': dict(zip(sessions, ['100', '150', '120', '130', '140'])),
              'B': dict(zip(sessions, ['100'] * len(sessions)))}
    bars = {sid: {day: dict(open=('119' if sid == 'A' and day == '2025-01-07' else '100'),
                           high='150', low='90', close=close) for day, close in rows.items()}
            for sid, rows in closes.items()}
    assembled = dict(session_dates=sessions, monthly_inputs=[plan], close_prices=closes,
                     provider_actions=[], actions=[], distribution_events=[], cash_stock_merger_events=[],
                     fractional_settlements={}, price_source_references={}, distribution_fractional_cash_values={})
    return assembled, bars


def book_fixture():
    assembled, bars = inputs()
    with patch('backtest.frontier_capped_next_open_research.decide_continuous_guided_for_account',
               side_effect=lambda **arguments: raw_fixture(arguments)) as selector:
        book = run_frontier_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='20000',
            fee_bps='1', slippage_bps='10', risk=MonthlyExitCoreResearchAdapter([]), max_new_searches=1)
    assert selector.call_count == 1 and book['status'] == 'COMPLETE', book.get('reason')
    return book, assembled, bars


class IndependentFrontierReviewTests(unittest.TestCase):
    def test_hand_computable_strict_improvement_and_exact_tie_keeps_original(self):
        selected = rerank(raw_fixture())
        result = review_selection(selected, rerank_enabled=True)
        self.assertEqual(result['target_quantities'], {'A': 99, 'B': 99})
        self.assertTrue(result['strict_improvement'])
        self.assertEqual(F(selected['rerank_audit']['selected_residual_cash']), F(9901, 50))
        self.assertAlmostEqual(selected['rerank_audit']['base_training_mean_log'], math.log(29999 / 20000))
        self.assertAlmostEqual(selected['rerank_audit']['selected_training_mean_log'], math.log(1890901 / 1000000))
        tie = rerank(raw_fixture(tie=True))
        self.assertEqual(review_selection(tie, rerank_enabled=True)['target_quantities'], {'A': 100})
        self.assertFalse(tie['rerank_audit']['strict_improvement'])

    def test_frontier_ranking_source_financial_and_audit_tampering_rejected(self):
        selected = rerank(raw_fixture())
        mutations = [
            lambda s: s['target_quantities'].update(A=100),
            lambda s: s['base_capped_target_quantities'].update(A=99),
            lambda s: s['rerank_audit'].update(strict_improvement=False),
            lambda s: s['rerank_audit'].update(source_cardinality=1),
            lambda s: s['rerank_audit'].update(selected_product_sha256='0' * 64),
            lambda s: s['rerank_audit'].update(additional_scored_baskets=4),
            lambda s: s.update(rerank_decision_id='0' * 64),
            lambda s: s['rerank_binding'].update(original_raw_selection_sha256='0' * 64),
            lambda s: s['raw_selection']['binding'].update(available_cash='1'),
            lambda s: s['raw_selection']['search_result'].update(fee_bps='999'),
            lambda s: s['raw_selection']['search_result']['best_by_k']['2'].update(fees='0'),
            lambda s: s['raw_selection']['search_result']['best_by_k']['2']['quantities'].update(B=101),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = deepcopy(selected)
                mutate(bad)
                with self.assertRaises(ValueError):
                    review_selection(bad, rerank_enabled=True)
        bad = deepcopy(selected)
        bad['target_quantities'] = {'A': 100}
        bad['rerank_binding']['target_quantities'] = {'A': 100}
        bad['rerank_decision_id'] = sha256(json.dumps(bad['rerank_binding'], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, 'RERANK_TARGET_MISMATCH'):
            review_selection(bad, rerank_enabled=True)

    def test_real_wrapper_replayed_cash_and_twenty_percent_exit(self):
        book, assembled, bars = book_fixture()
        receipt = review_book(book, assembled, bars, rerank_enabled=True)
        self.assertEqual(receipt['rerank_months'], ['2025-01-02'])
        self.assertEqual(receipt['fills'], 3)
        self.assertEqual(book['daily_ledger'][0]['shares'], {'A': 99, 'B': 99})
        self.assertEqual(book['daily_ledger'][-1]['shares']['A'], 0)
        self.assertEqual(book['provider_audit'][2]['target_shares'], {'A': 0, 'B': 99})
        self.assertEqual(book['provider_audit'][3]['target_shares'], {'A': 0, 'B': 99})
        prefix = [dict(arguments=book['selection_account_states'][0],
                       raw_selection=book['provider_audit'][0]['selection']['raw_selection'])]
        with patch('backtest.frontier_capped_next_open_research.decide_continuous_guided_for_account',
                   side_effect=AssertionError('NO_NEW_SEARCH_ALLOWED')):
            replay = run_frontier_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='20000',
                fee_bps='1', slippage_bps='10', risk=MonthlyExitCoreResearchAdapter([]), verified_prefix=prefix)
        self.assertEqual(review_book(replay, assembled, bars, rerank_enabled=True)['final_equity'], receipt['final_equity'])
        self.assertEqual(replay['new_searches'], 0)
        self.assertEqual(replay['reused_searches'], 1)

    def test_account_execution_risk_and_context_tampering_rejected(self):
        book, assembled, bars = book_fixture()
        mutations = [
            lambda b: b['daily_ledger'][0].update(cash='1'),
            lambda b: next(row for row in b['order_log'] if row['event'] == 'ASSUMED_NEXT_OPEN_FILLED').update(price='100'),
            lambda b: b['provider_audit'][2]['risk_overlay']['state'].update(exited=[]),
            lambda b: b['provider_audit'][3]['target_shares'].update(A=99),
            lambda b: b['selection_account_states'][0]['source_hashes'].update(synthetic='1' * 64),
            lambda b: b['provider_audit'][0].update(drift_overlay={}),
            lambda b: b.update(total_return='1'),
            lambda b: b.update(fees='0'),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                bad = deepcopy(book)
                mutate(bad)
                with self.assertRaises((AssertionError, ValueError)):
                    review_book(bad, assembled, bars, rerank_enabled=True)

    def test_changed_branch_arguments_cannot_reuse_cache_or_exceed_search_cap(self):
        book, assembled, bars = book_fixture()
        prefix = [dict(arguments=deepcopy(book['selection_account_states'][0]),
                       raw_selection=book['provider_audit'][0]['selection']['raw_selection'])]
        prefix[0]['arguments']['account_state']['cash'] = '19999'
        with patch('backtest.frontier_capped_next_open_research.decide_continuous_guided_for_account',
                   side_effect=AssertionError('CACHE_MISMATCH_MUST_NOT_FALL_BACK_TO_SEARCH')) as selector:
            rejected = run_frontier_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='20000',
                fee_bps='1', slippage_bps='10', risk=MonthlyExitCoreResearchAdapter([]),
                verified_prefix=prefix, max_new_searches=1)
        self.assertNotEqual(rejected['status'], 'COMPLETE')
        self.assertIn('SAVED_SELECTION_INPUT_MISMATCH', str(rejected))
        selector.assert_not_called()
        with patch('backtest.frontier_capped_next_open_research.decide_continuous_guided_for_account',
                   side_effect=AssertionError('ZERO_BUDGET_MUST_NOT_START_SEARCH')) as selector:
            stopped = run_frontier_capped_next_open(assembled=assembled, ohlc=bars, initial_cash='20000',
                fee_bps='1', slippage_bps='10', risk=MonthlyExitCoreResearchAdapter([]), max_new_searches=0)
        self.assertNotEqual(stopped['status'], 'COMPLETE')
        self.assertIn('FRESH_MONTHLY_SEARCH_LIMIT_EXCEEDED', str(stopped))
        selector.assert_not_called()

    def test_unexposed_wait_preserves_target_risk_and_cash(self):
        book, assembled, bars = book_fixture()
        cash, shares = book['cash'], dict(book['shares'])
        final_row = deepcopy(book['daily_ledger'][-1])
        event = dict(event_id='UNRELATED', effective_date='2025-01-08', timing='AFTER_CLOSE',
                     parent_sid='P', post_parent_sid='P', child_sid='C', source_references=['synthetic'])
        assembled['distribution_events'] = [event]
        book['after_close_records'] = [dict(date='2025-01-08', phase='AFTER_CLOSE_UNVALUED_STATE',
            post_event_equity=None, cash=cash, shares=shares, distribution_rights=[])]
        for decision, day, waiting in [('2025-01-08', '2025-01-09', True), ('2025-01-09', '2025-01-10', False)]:
            assembled['session_dates'].append(day)
            for sid, close in [('A', '140'), ('B', '100')]:
                assembled['close_prices'][sid][day] = close
                bars[sid][day] = dict(open=close, high=close, low=close, close=close)
            audit = deepcopy(book['provider_audit'][-1])
            audit.update(action='WAIT_POST_ACTION_MARK' if waiting else 'NO_ACTION', orders=[], selection=None)
            audit['risk_overlay']['state'].update(session_date=decision, last_closes={'A': '140', 'B': '100'})
            if waiting:
                audit['post_close_review'] = dict(status='UNEXPOSED_RISK_DOMAIN_UNCHANGED',
                    decision_date=decision, orders_permitted=False, event_ids=['UNRELATED'])
            book['provider_audit'].append(audit)
            book['daily_ledger'].append(dict(final_row, date=day))
        book['state_date'] = book['last_valued_date'] = '2025-01-10'
        self.assertEqual(review_book(book, assembled, bars, rerank_enabled=True)['fills'], 3)
        for mutate in [lambda b: b['after_close_records'][0].update(cash='1'),
                       lambda b: b['provider_audit'][-2]['orders'].append(dict(security_id='A', side='BUY', quantity=99)),
                       lambda b: b['provider_audit'][-1]['target_shares'].update(A=99)]:
            bad = deepcopy(book)
            mutate(bad)
            with self.assertRaises((AssertionError, ValueError)):
                review_book(bad, assembled, bars, rerank_enabled=True)


if __name__ == '__main__':
    unittest.main()
