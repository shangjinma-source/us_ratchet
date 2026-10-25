from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import unittest

from backtest.saved_frontier_tail_gate_audit import audit
from scripts.audit_capped_training_frontier import evaluate
from test_capped_frontier_independent_review import raw_fixture


def fixture(tail='3/5', fee='0', alternative=True):
    raw = raw_fixture()
    arguments = raw['binding']['search_arguments']
    arguments['fee_bps'] = fee
    arguments['training_scenarios'] = [{'A': '3', 'B': '6/5'}] * 11 + [{'A': tail, 'B': '1'}]
    arguments['scenario_dates'] = [f'2024-{month:02d}-01' for month in range(1, 13)]
    result = raw['search_result']
    baskets = {'0': {}, '1': {'A': 199}}
    if alternative:
        baskets['2'] = {'A': 20, 'B': 99}
    records = {}
    for key, quantities in baskets.items():
        score = evaluate(quantities, arguments)
        records[key] = dict(quantities=quantities, actual_k=len(quantities),
            notional=str(score['notional']), fees=str(score['notional'] * F(fee) / 10000),
            residual_cash=str(score['residual_cash']), training_mean_net_log_wealth=score['mean_log'],
            training_gross_growth_product=str(score['product']))
    result.update(best_by_k=records, selected=records['1'], fee_bps=fee,
                  scenario_dates=arguments['scenario_dates'])
    raw['target_quantities'] = records['1']['quantities']
    raw['decision_id'] = sha256(json.dumps(raw['binding'], sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return raw


def branch_fixture(baskets, stable_relative):
    """Synthetic equal-price domain; A wins growth but fails the tail floor."""
    raw = fixture(tail='1/2', alternative=False)
    arguments = raw['binding']['search_arguments']
    securities = sorted({sid for basket in baskets.values() for sid in basket})
    arguments['prices'] = {sid: '100' for sid in securities}
    arguments['metadata'] = {sid: dict(ticker=sid, issuer_id=sid) for sid in securities}
    arguments['training_scenarios'] = [
        {sid: ('3' if sid == 'A' else stable_relative) for sid in securities}
        for _ in range(11)
    ] + [{sid: ('1/2' if sid == 'A' else stable_relative) for sid in securities}]
    raw['binding']['valuation_quotes'] = {
        sid: dict(price='100', as_of=raw['decision_date'], price_basis='SYNTHETIC_USD',
                  source_references=['synthetic']) for sid in securities}
    records = {}
    for key, quantities in baskets.items():
        score = evaluate(quantities, arguments)
        records[key] = dict(quantities=quantities, actual_k=len(quantities),
            notional=str(score['notional']), fees='0', residual_cash=str(score['residual_cash']),
            training_mean_net_log_wealth=score['mean_log'],
            training_gross_growth_product=str(score['product']))
    raw['search_result'].update(best_by_k=records, selected=records['1'])
    raw['decision_id'] = sha256(json.dumps(raw['binding'], sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return raw


class SavedTailAuditTests(unittest.TestCase):
    def test_exact_boundary_preserves_incumbent_and_input(self):
        raw = fixture()
        before = deepcopy(raw)
        result = audit(raw)
        self.assertFalse(result['changed'])
        self.assertEqual(result['target_quantities'], {'A': 100})
        self.assertEqual(result['incumbent']['worst_wealth_multiple'], '4/5')
        self.assertEqual(raw, before)

    def test_cost_moves_boundary_and_selects_existing_alternative(self):
        result = audit(fixture(fee='1'))
        self.assertTrue(result['changed'])
        self.assertEqual(result['target_quantities'], {'A': 20, 'B': 99})
        self.assertLess(F(result['incumbent']['worst_wealth_multiple']), F(4, 5))
        self.assertEqual(result['new_search_calls'], 0)

    def test_no_eligible_stock_keeps_cash_and_no_terminal_fee(self):
        result = audit(fixture(tail='1/2', alternative=False))
        self.assertEqual(result['target_quantities'], {})
        self.assertEqual(result['selected']['residual_cash'], '20000')
        self.assertEqual(result['selected']['scenario_wealth_multiples'], ['1'] * 12)

    def test_rejects_tampered_account_and_saved_frontier(self):
        for mutate in (lambda raw: raw['binding'].update(available_cash='1'),
                       lambda raw: raw['search_result']['best_by_k']['2'].update(fees='99')):
            raw = fixture()
            mutate(raw)
            with self.assertRaises(ValueError):
                audit(raw)

    def test_rejects_non_twelve_scenarios(self):
        with self.assertRaisesRegex(ValueError, 'TWELVE'):
            audit(raw_fixture())

    def test_two_eligible_tied_baskets_use_original_lexicographic_rule(self):
        raw = branch_fixture({'0': {}, '1': {'A': 199},
                              '2': {'B': 30, 'C': 30},
                              '3': {'B': 20, 'C': 20, 'D': 20}}, '6/5')
        result = audit(raw)
        self.assertEqual(result['eligible_stock_baskets'], 2)
        evidence = [row for row in result['candidate_evidence'] if row['quantities']
                    and row['passes']]
        self.assertEqual(evidence[0]['product_sha256'], evidence[1]['product_sha256'])
        self.assertEqual(evidence[0]['residual_cash'], evidence[1]['residual_cash'])
        self.assertEqual(result['target_quantities'], {'B': 30, 'C': 30})
        self.assertEqual(result['changed_reason'], 'INCUMBENT_FAILS_SELECT_SAVED_ELIGIBLE')

    def test_saved_cash_outranks_passing_but_losing_stock_basket(self):
        raw = branch_fixture({'0': {}, '1': {'A': 199}, '2': {'B': 30, 'C': 30}}, '9/10')
        result = audit(raw)
        self.assertEqual(result['eligible_stock_baskets'], 1)
        self.assertEqual(result['target_quantities'], {})
        self.assertEqual(result['changed_reason'], 'SAVED_CASH_OUTRANKS_ELIGIBLE_STOCKS')
        self.assertEqual(result['selected']['scenario_wealth_multiples'], ['1'] * 12)

    def test_missing_saved_cash_still_allows_explicit_cash_fallback(self):
        raw = branch_fixture({'1': {'A': 199}}, '1')
        self.assertNotIn('0', raw['search_result']['best_by_k'])
        result = audit(raw)
        self.assertEqual(result['target_quantities'], {})
        self.assertEqual(result['changed_reason'], 'NO_ELIGIBLE_STOCK_BASKET_CASH')
        self.assertEqual(result['selected']['residual_cash'], '20000')
        self.assertEqual(result['selected']['scenario_wealth_multiples'], ['1'] * 12)


if __name__ == '__main__':
    unittest.main()
