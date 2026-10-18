import random
import unittest
from unittest.mock import patch

from backtest.ndx_incumbent_integer_control_research import search_incumbent_integer_control_domain as old_search
from backtest.ndx_incumbent_integer_control_research_v2 import search_incumbent_integer_control_domain_v2 as new_search
from backtest.ndx_incumbent_execution_control_research import simulate_fixed_weight_incumbent_control as old_simulate
from backtest.ndx_incumbent_execution_control_research_v2 import simulate_fixed_weight_incumbent_control_v2 as new_simulate
from backtest import ndx_incumbent_execution_control_research_v2 as wrapper
from backtest import ndx_next_session_execution_research_v2 as candidate
from test_ndx_incumbent_integer_control_research import fixture
from test_ndx_next_session_execution_research import fixture as simulation_fixture


class IncumbentControlV2OverlapTests(unittest.TestCase):
    def compare(self, inputs):
        old, new = old_search(**inputs), new_search(**inputs)
        self.assertEqual(new.pop('schema'), 'ndx_incumbent_integer_control_research_v2')
        old.pop('schema')
        self.assertEqual(new, old)

    def test_one_hundred_random_small_domains_full_result_exact(self):
        randomizer = random.Random(19254)
        for _ in range(100):
            inputs = fixture()
            inputs.update(prices={t: randomizer.uniform(1, 30) for t in 'AB'},
                          current_shares={t: randomizer.randrange(8) for t in 'AB'},
                          current_cash=randomizer.uniform(1, 100),
                          transaction_cost_bps=randomizer.choice([0., 10., 100.]),
                          share_domains={t: list(range(8)) for t in 'AB'},
                          max_evaluations=randomizer.choice([1, 20, 100]))
            self.compare(inputs)

    def test_symmetric_ties_and_domain_order_preserved(self):
        inputs = fixture()
        inputs.update(transaction_cost_bps=0., share_domains={'A': [3, 2, 1, 0], 'B': [3, 2, 1, 0]})
        self.compare(inputs)
        inputs['current_cash'] = 5.
        inputs['minimum_cash_buffer_usd'] = 10.
        self.compare(inputs)

    def test_three_through_eight_ticker_control_domains_exact(self):
        randomizer = random.Random(44193)
        for count in range(3, 9):
            names = [f'T{index}' for index in range(count)]
            for budget in (1, 17, 100000):
                inputs = fixture()
                inputs.update(
                    prices={name: randomizer.uniform(5., 100.) for name in names},
                    target_weights={name: 1. / count for name in names},
                    current_shares={name: randomizer.randrange(3) for name in names},
                    current_cash=300.,
                    risk_chain_by_ticker={name: f'chain{index % 3}' for index, name in enumerate(names)},
                    share_domains={name: [2, 0, 1] for name in names},
                    max_evaluations=budget,
                )
                with self.subTest(count=count, budget=budget):
                    self.compare(inputs)

    def test_full_simulation_overlap_and_candidate_globals_unchanged(self):
        inputs = simulation_fixture()
        schedule = inputs.pop('schedule')
        inputs.pop('selection_policy')
        inputs.update(decision_dates=[schedule[0][0], inputs['execution_calendar'][2]],
                      incumbent_weights=schedule[0][1], corporate_actions=[])
        before = dict(candidate.__dict__)
        old, new = old_simulate(**inputs), new_simulate(**inputs)
        self.assertEqual(new.pop('schema'), 'ndx_incumbent_execution_control_research_v2')
        old.pop('schema')
        source = new.pop('source_hashes')
        old.pop('source_hashes')
        self.assertEqual(new, old)
        self.assertTrue(any(p.endswith('ndx_exact_pareto_frontier_research.py') for p in source))
        for name, value in before.items():
            self.assertIs(candidate.__dict__[name], value)

    def test_loaded_source_drift_rejected(self):
        inputs = simulation_fixture()
        schedule = inputs.pop('schedule')
        inputs.pop('selection_policy')
        inputs.update(decision_dates=[schedule[0][0]], incumbent_weights=schedule[0][1], corporate_actions=[])
        # _RUN holds its own bound function globals; replacing its source hasher
        # exercises the loaded-source barrier before any execution work.
        with patch.dict(wrapper._RUN.__globals__, {'_hashes': lambda: {}}):
            with self.assertRaisesRegex(ValueError, 'since import'):
                new_simulate(**inputs)


if __name__ == '__main__':
    unittest.main()
