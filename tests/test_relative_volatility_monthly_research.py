from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction as F
import unittest
from backtest.relative_volatility_monthly_research import scale_selection


def exact(value):
    return F(int(value['numerator_hex'], 16), int(value['denominator_hex'], 16))


class RelativeSizingTests(unittest.TestCase):
    def fixture(self, high_recent=False):
        dates = [(date(2024, 1, 1) + timedelta(days=i)).isoformat() for i in range(253)]
        values = [F(100)]
        for i in range(252):
            values.append(values[-1] * (F(11, 10) if i % 2 else F(9, 10))
                          if high_recent and i >= 230 else values[-1])
        gross = [str(values[i + 21] / values[i]) for i in range(0, 252, 21)]
        arguments = dict(decision_date=dates[-1], prices={'S': str(values[-1])},
                         training_scenarios=[{'S': value} for value in gross])
        selected = dict(target_quantities={'S': 100},
                        raw_selection=dict(binding=dict(search_arguments=arguments)),
                        rerank_decision_id='old-id', rerank_binding={'old': True})
        window = dict(decision_date=dates[-1], training_dates=dates,
                      candidates=[dict(security_id='S', decision_cost=str(values[-1]),
                                       training_close=[str(value) for value in values])])
        return selected, window

    def test_flat_unchanged_and_input_immutable(self):
        selected, window = self.fixture()
        selected.update(rerank_audit={'selected_residual_cash': '123'},
                        base_capped_target_quantities={'S': 100}, frontier_reranked_after_cap=True)
        original = deepcopy(selected)
        result = scale_selection(selected, window)
        self.assertEqual(result['target_quantities'], {'S': 100})
        self.assertEqual(selected, original)
        self.assertNotIn('rerank_decision_id', result)
        self.assertNotIn('rerank_audit', result)
        self.assertNotIn('base_capped_target_quantities', result)
        self.assertEqual(result['v27_selection'], original)

    def test_high_recent_variance_scales_exact_integer(self):
        selected, window = self.fixture(True)
        result = scale_selection(selected, window)
        multiplier = exact(result['relative_risk']['multiplier'])
        self.assertTrue(0 < multiplier < 1)
        self.assertEqual(result['target_quantities']['S'], int(100 * multiplier))

    def test_wrong_date_or_history_is_rejected(self):
        selected, window = self.fixture()
        window['decision_date'] = '2030-01-01'
        with self.assertRaises(ValueError):
            scale_selection(selected, window)
        selected, window = self.fixture()
        window['candidates'][0]['training_close'].pop()
        with self.assertRaises(ValueError):
            scale_selection(selected, window)

    def test_two_asset_covariance_is_included_before_variance(self):
        for correlation in (1, -1):
            with self.subTest(correlation=correlation):
                selected, window = self.fixture()
                arguments = selected['raw_selection']['binding']['search_arguments']
                returns = [F(0)] * 230 + [F(1 if i % 2 else -1, 10) for i in range(22)]
                window['candidates'] = []
                selected['target_quantities'] = {'A': 10, 'B': 10}
                arguments['prices'] = {'A': '100', 'B': '100'}
                arguments['training_scenarios'] = [{} for _ in range(12)]
                for sid, sign in [('A', 1), ('B', correlation)]:
                    values = [F(100)]
                    for change in returns:
                        values.append(values[-1] * (1 + sign * change))
                    window['candidates'].append(dict(security_id=sid, decision_cost='100',
                        training_close=list(map(str, values))))
                    for j in range(12):
                        arguments['training_scenarios'][j][sid] = str(values[(j+1)*21] / values[j*21])
                risk = scale_selection(selected, window)['relative_risk']
                if correlation == -1:
                    self.assertEqual(exact(risk['short_variance']), 0)
                    self.assertEqual(exact(risk['long_variance']), 0)
                    self.assertEqual(exact(risk['multiplier']), 1)
                else:
                    sample = returns[-21:]
                    mean = sum(sample) / 21
                    self.assertEqual(exact(risk['short_variance']), sum((r-mean)**2 for r in sample) / 20)
                    self.assertLess(exact(risk['multiplier']), 1)

    def test_training_coordinate_scale_preserves_risk_but_changes_binding(self):
        selected, window = self.fixture(True)
        before = scale_selection(selected, window)
        scaled = deepcopy(window)
        scaled['candidates'][0]['training_close'] = [str(F(v)*7) for v in scaled['candidates'][0]['training_close']]
        after = scale_selection(selected, scaled)
        self.assertEqual(before['relative_risk'], after['relative_risk'])
        self.assertEqual(before['target_quantities'], after['target_quantities'])
        self.assertNotEqual(before['relative_decision_id'], after['relative_decision_id'])

    def test_cash_and_floor_to_zero_are_distinct(self):
        selected, window = self.fixture(True)
        selected['target_quantities'] = {'S': 1}
        floor = scale_selection(selected, window)
        self.assertEqual(floor['target_quantities'], {'S': 0})
        self.assertFalse(floor['relative_risk']['empty_basket'])
        selected['target_quantities'] = {}
        cash = scale_selection(selected, window)
        self.assertEqual(cash['target_quantities'], {})
        self.assertTrue(cash['relative_risk']['empty_basket'])
        self.assertTrue(cash['relative_risk']['all_targets_zero'])
        self.assertEqual(exact(cash['relative_risk']['multiplier']), 1)

    def test_large_exact_variance_serializes_without_decimal_integer_limit(self):
        import json
        selected, window = self.fixture()
        values = [10**80 + i*i + i + 1 for i in range(253)]
        window['candidates'][0]['training_close'] = list(map(str, values))
        arguments = selected['raw_selection']['binding']['search_arguments']
        arguments['training_scenarios'] = [{'S': str(F(values[i+21], values[i]))}
                                           for i in range(0, 252, 21)]
        result = scale_selection(selected, window)
        restored = json.loads(json.dumps(result))
        variance = exact(restored['relative_risk']['long_variance'])
        self.assertGreater(variance.denominator.bit_length(), 15000)
        multiplier = exact(restored['relative_risk']['multiplier'])
        self.assertEqual(restored['target_quantities']['S'], (100*multiplier).numerator // (100*multiplier).denominator)

    def test_monthly_provider_freezes_scaled_target_split_and_exit_remain_latched(self):
        from backtest.continuous_guided_cost_monthly_provider import build_cost_monthly_quantity_provider
        from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
        selected, window = self.fixture(True)
        day = date.fromisoformat(window['decision_date'])
        days = [(day + timedelta(days=i)).isoformat() for i in range(6)]
        selected['investable_equity'] = '100000'
        scaled = scale_selection(selected, window)
        quantity = scaled['target_quantities']['S']
        self.assertGreater(quantity, 0)
        calls = []
        def decide(**arguments):
            calls.append(arguments['decision_date'])
            return deepcopy(scaled)
        action = dict(date=days[2], security_id='S', type='split', old_shares=1,
                      new_shares=2, source_references=['synthetic-split'])
        prices = dict(zip(days, ['100', '120', '60', '48', '70', '70']))
        provider = build_cost_monthly_quantity_provider(session_dates=days,
            monthly_inputs=[dict(decision_date=days[0], search_arguments={'fee_bps': '1'},
                valuation_quotes=[dict(security_id='S', price='100')], source_hashes={})],
            close_prices={'S': prices}, actions=[action], decide=decide)
        risk = MonthlyExitCoreResearchAdapter([action])
        outputs = []
        for i, current in enumerate(days[:-1]):
            result = provider(decision_date=current, active_date=days[i+1],
                              state=dict(asof=current, cash='100000', shares={}))
            self.assertEqual(result['status'], 'READY', result)
            self.assertEqual(result['target_shares'], {'S': quantity * (2 if i >= 2 else 1)})
            target, diagnostic = risk.apply(day=current, month=days[0],
                target=result['target_shares'], closes={'S': prices[current]},
                adjustments=result['target_adjustments'])
            outputs.append(target['S'])
            if i == 2:
                self.assertEqual(F(diagnostic['state']['peaks']['S']), 60)
        self.assertEqual(calls, [days[0]])
        self.assertEqual(outputs, [quantity, quantity, 2*quantity, 0, 0])


if __name__ == '__main__':
    unittest.main()
