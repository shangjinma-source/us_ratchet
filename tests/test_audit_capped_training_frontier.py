"""A post-ranking cap can reverse the ranking; this proves no future gain."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import unittest

from scripts.audit_capped_training_frontier import audit_selection, evaluate


def fixture():
    arguments = dict(entered_cash='100', fee_bps='0', minimum_cash_buffer='0',
        prices={'A': '10', 'B': '10'}, metadata={'A': {'ticker': 'A', 'issuer_id': 'a'},
                                             'B': {'ticker': 'B', 'issuer_id': 'b'}},
        training_scenarios=[{'A': '2', 'B': '9/5'}], scenario_dates=['2025-01-02'], decision_date='2025-01-02')
    def record(quantities):
        score = evaluate(quantities, arguments)
        return dict(quantities=quantities, notional=str(score['notional']), residual_cash=str(score['residual_cash']),
                    fees=str(score['notional'] * F(arguments['fee_bps']) / 10000),
                    training_mean_net_log_wealth=score['mean_log'], training_gross_growth_product=str(score['product']))
    chosen = record({'A': 10})
    binding = dict(decision_date='2025-01-02', state_revision='synthetic', available_cash='100',
        reserved_cash='0', shares={}, investable_equity='100', search_arguments=arguments,
        valuation_quotes={sid: dict(as_of='2025-01-02', price='10', source_references=['test-source'])
                          for sid in arguments['prices']}, source_hashes={'test-source': '1' * 64})
    identity = hashlib.sha256(json.dumps(binding, sort_keys=True, separators=(',', ':'),
                                         ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    return dict(target_quantities={'A': 5}, raw_selection=dict(decision_date='2025-01-02',
        decision_id=identity, research_id=identity[:24], state_revision='synthetic', available_cash='100',
        holding_market_values={}, investable_equity='100', target_quantities={'A': 10}, binding=binding,
        search_result=dict(decision_date='2025-01-02', selected=chosen,
                           objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
                           fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION', initial_positions={},
                           fee_bps='0', entered_cash='100', minimum_cash_buffer='0', scenario_dates=['2025-01-02'],
                           best_by_k={'0': record({}), '1': chosen, '2': record({'A': 5, 'B': 5})})))


class CappedFrontierTests(unittest.TestCase):
    def test_known_ranking_reversal_is_diagnostic_only(self):
        result = audit_selection(fixture())
        self.assertEqual(result['saved_stronger_capped_baskets'], 1)
        self.assertEqual(result['better_saved_capped_example']['quantities'], {'A': 5, 'B': 5})
        self.assertEqual(F(result['implemented_cash_fraction']), F(1, 2))
        self.assertIsNone(result['future_return'])
        self.assertEqual(result['new_generated_baskets'], 0)

    def test_saved_score_target_and_date_tampering_rejected(self):
        mutations = [lambda s: s['target_quantities'].update(A=6),
                     lambda s: s['raw_selection']['search_result']['best_by_k']['2'].update(training_gross_growth_product='2'),
                     lambda s: s['raw_selection']['binding']['search_arguments'].update(scenario_dates=['2026-01-01']),
                     lambda s: s['raw_selection']['binding']['search_arguments']['metadata']['B'].update(issuer_id='a')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                selection = deepcopy(fixture())
                mutate(selection)
                with self.assertRaises(ValueError):
                    audit_selection(selection)

    def test_scoring_respects_fees_and_residual_cash(self):
        arguments = fixture()['raw_selection']['binding']['search_arguments']
        arguments['fee_bps'] = '100'
        score = evaluate({'A': 5}, arguments)
        self.assertEqual(score['residual_cash'], F(99, 2))
        self.assertEqual(score['product'], F(299, 200))

    def test_provenance_and_cost_context_tampering_rejected(self):
        mutations = [lambda r: r['binding'].update(available_cash='1'),
                     lambda r: r.update(decision_id='0' * 64),
                     lambda r: r.update(investable_equity='1'),
                     lambda r: r['search_result'].update(fee_bps='999'),
                     lambda r: r['search_result'].update(scenario_dates=['2024-01-01']),
                     lambda r: r['search_result'].update(fee_scope='OTHER'),
                     lambda r: r['search_result']['selected'].update(fees='1')]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                selection = deepcopy(fixture())
                mutate(selection['raw_selection'])
                with self.assertRaises(ValueError):
                    audit_selection(selection)


if __name__ == '__main__':
    unittest.main()
