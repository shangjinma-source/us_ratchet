"""Independent algebraic oracle, not historical or forward acceptance evidence."""
import copy
import itertools
import unittest

import pandas as pd

from backtest.ndx_dynamic_envelope_policy import evaluate_componentwise_envelope_candidates


DIMENSIONS = ('return_p50', 'return_p10', 'max_drawdown_p50', 'max_drawdown_p90')
FUND = ('return_p50_vs_012922', 'return_p10_vs_012922',
        'max_drawdown_p50_vs_012922', 'max_drawdown_p90_vs_012922')
INCUMBENT = ('paired_return_p50_vs_incumbent', 'paired_return_p10_vs_incumbent',
             'paired_drawdown_cost_p50_vs_incumbent', 'paired_drawdown_cost_p90_vs_incumbent')


def candidate(identifier='A', count=1):
    tickers = [f'T{i}' for i in range(count)]
    return dict(source_batch='independent_fixture', universe_track='strict_technology',
                selection_date='2024-06-03', decision_data_end='2024-05-31',
                portfolio_id=identifier, holding_count=count, weight_spec='equal_weight',
                tickers=';'.join(tickers), security_ids=';'.join(f'security:S{i}' for i in range(count)),
                issuer_ids=';'.join(f'issuer:I{i}' for i in range(count)),
                risk_chains=';'.join('fixture_chain' for _ in tickers),
                weights=';'.join(f'{t}:{1/count:.12f}' for t in tickers),
                declared_constraints_passed=True, fit_strictly_before_evaluation=True,
                return_p50=.2, return_p10=.1, max_drawdown_p50=.1, max_drawdown_p90=.2,
                last_fit_evaluation_boundary='2024-01-01<2024-05-31', rolling_fit_window_count=10,
                return_basis='NET_OF_MODELED_ENTRY_TURNOVER_COST',
                **{key: 0.0 for key in FUND + INCUMBENT})


class IndependentEnvelopeOracle(unittest.TestCase):
    def evaluate(self, rows):
        return evaluate_componentwise_envelope_candidates(pd.DataFrame(rows))['groups'][0]

    def test_all_sign_patterns_match_independent_deficit_oracle(self):
        rows = []
        for number, values in enumerate(itertools.product((-0.125, 0.0, 0.125), repeat=4)):
            row = candidate(str(number))
            row.update(dict(zip(FUND, values)))
            # Quantiles of paired deltas must be ordered; fund marginal
            # quantile differences need not be ordered in this way.
            paired = (max(values[:2]), min(values[:2]), min(values[2:]), max(values[2:]))
            row.update(dict(zip(INCUMBENT, paired)))
            rows.append(row)
        output = {r['portfolio_id']: r for r in self.evaluate(rows)['candidates']}
        for source in rows:
            row = output[source['portfolio_id']]
            for benchmark, fields in (('fund', FUND), ('incumbent', INCUMBENT)):
                expected = [max(0.0, -source[k] if i < 2 else source[k]) for i, k in enumerate(fields)]
                self.assertEqual([row[benchmark]['deficits'][k] for k in DIMENSIONS], expected)
                self.assertEqual(row[benchmark]['componentwise_noninferior'], not any(expected))

    def test_k_and_input_order_do_not_break_economic_ties(self):
        rows = [candidate('one', 1), candidate('nine', 9)]
        for row in rows:
            row.update(dict(zip(FUND, (.1, .1, -.1, -.1))))
            row.update(dict(zip(INCUMBENT, (.1, .1, -.1, -.1))))
        original = copy.deepcopy(rows)
        result = self.evaluate(rows)
        self.assertEqual(set(result['dual_benchmark_qualified_ids']), {'one', 'nine'})
        self.assertEqual(set(result['deficit_pareto_ids']), {'one', 'nine'})
        self.assertEqual(result, self.evaluate(list(reversed(rows))))
        self.assertEqual(rows, original)

    def test_no_qualified_row_is_explicit_and_not_a_global_infeasibility_claim(self):
        result = self.evaluate([candidate()])
        self.assertEqual(result['qualification_status'], 'NO_COMPONENTWISE_FEASIBLE_CANDIDATE')
        self.assertEqual(result['feasibility_scope'], 'SUPPLIED_RESEARCH_CANDIDATES_ONLY')
        self.assertFalse(result['global_infeasibility_proven'])
        self.assertEqual(len(result['candidates']), 1)

    def test_equal_weight_label_cannot_hide_unequal_weights(self):
        row = candidate(count=2)
        row['weights'] = 'T0:.8;T1:.2'
        with self.assertRaises(ValueError):
            self.evaluate([row])


if __name__ == '__main__':
    unittest.main()
