"""Native saved-frontier bridge tests using independently signed toy inputs.

The fixtures never call a selector, candidate generator, execution kernel or the
original continuous32 validator (which would regenerate candidate proposals).
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import math
import unittest

from core.saved_monthly_frontier_proposal import build_frontier_proposal


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                            ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def sign(target):
    selected = target['payload']['decision']['payload']
    selected['input_id'] = digest(selected['input_binding'])
    target['payload']['decision']['decision_id'] = digest(selected)
    target['target_id'] = digest(target['payload'])
    return target


def saved_record(quantities, arguments):
    capital = F(arguments['entered_cash'])
    notional = sum((quantity * F(arguments['prices'][sid])
                    for sid, quantity in quantities.items()), F(0))
    fees = notional * F(arguments['fee_bps']) / 10000
    residual = capital - notional - fees
    # Direct cash-plus-investments equation, independent of the bridge's affine
    # numerator implementation. All twelve scenarios are intentionally equal.
    growth = [(residual + sum((quantity * F(arguments['prices'][sid]) * F(scenario[sid])
                              for sid, quantity in quantities.items()), F(0))) / capital
              for scenario in arguments['training_scenarios']]
    return dict(quantities=deepcopy(quantities), actual_k=len(quantities),
                notional=str(notional), fees=str(fees), residual_cash=str(residual),
                training_mean_net_log_wealth=sum(math.log(float(value)) for value in growth) / len(growth),
                training_gross_growth_product=str(math.prod(growth)),
                actual_weights={sid: str(quantity * F(arguments['prices'][sid]) / capital)
                                for sid, quantity in quantities.items()},
                cash_fraction=str(residual / capital), issuer_unique=True,
                budget_conservation_exact=True, exact_product_comparison=True,
                large_exact_product_serialization_omitted=False)


def native_fixture(*, fee='1', tie=False, held=False, zero_cap=False, month='2026-10'):
    valuation_date = month + '-20'
    prices = {'A': '15000' if zero_cap else '100', 'B': '100', 'C': '50'}
    relatives = {'A': '2', 'B': '2' if tie else '9/5', 'C': '9/10'}
    arguments = dict(prices=prices,
        metadata={sid: dict(ticker=sid, issuer_id='issuer-' + sid) for sid in prices},
        entered_cash='20000', fee_bps=fee, minimum_cash_buffer='0',
        training_scenarios=[deepcopy(relatives) for _ in range(12)],
        scenario_dates=[f'2025-{number:02d}-01' for number in range(1, 13)],
        decision_date=valuation_date, max_objective_evaluations=8192, fixed_seed='native-toy')
    selected = saved_record({'A': 1 if zero_cap else 199}, arguments)
    frontier = {'0': saved_record({}, arguments), '1': selected}
    if not zero_cap:
        frontier['2'] = saved_record({'A': 50, 'B': 50} if tie else {'A': 99, 'B': 99}, arguments)
    source_hashes = {'synthetic-prices.json': 'a' * 64,
                     'synthetic-training.json': 'b' * 64, 'synthetic-units.json': 'c' * 64}
    marks = {sid: dict(security_id=sid, ticker=sid, currency='USD', price=price,
        price_basis='UNADJUSTED_USD', observed_at=valuation_date + 'T20:00:00+00:00',
        captured_at=valuation_date + 'T20:00:01+00:00', checked_at=valuation_date + 'T20:00:02+00:00',
        valuation_max_age_seconds=120, source_references=['synthetic-prices.json'],
        source_hashes={'synthetic-prices.json': source_hashes['synthetic-prices.json']})
        for sid, price in prices.items()}
    binding = dict(schema='STRATEGY_ACCOUNT_CONTINUOUS32_INPUT_V1', account_id='synthetic-account',
        account_revision='synthetic-revision', holdings_revision='synthetic-holdings',
        continuous_iterations=32, selector_profile='REAL_ACCOUNT_CONTINUOUS32_V1',
        selection_method='FAIR_K_V2_PLUS_CONTINUOUS32_EXPERIMENT_V1',
        strategy_equity='20000', strategy_shares={'C': 3} if held else {},
        holding_market_values={'C': '150'} if held else {},
        total_uninvested_cash='19850' if held else '20000', marks=marks,
        documents=dict(marks='synthetic-prices.json', training_manifest='synthetic-training.json',
                       unit_review='synthetic-units.json'), source_hashes=source_hashes,
        training_cutoff_date='2026-10-14', valuation_date=valuation_date,
        valuation_at=valuation_date + 'T20:00:02+00:00', current_price_basis='UNADJUSTED_USD',
        search_arguments=arguments, historical_search_arguments=deepcopy(arguments),
        original_input_id='d' * 64,
        execution_context=dict(available_cash='19850' if held else '20000',
            cash_confirmation_revision='synthetic-cash', pending_orders=[], reserved_cash='0',
            reserved_shares={}, sell_proceeds_available=True))
    result = dict(method_version=binding['selection_method'], status='BUDGET_STOPPED',
        objective='TRAINING_PRICE_SCENARIO_MEAN_NET_LOG_WEALTH',
        fee_scope='INITIAL_BUY_ONLY_NO_TERMINAL_LIQUIDATION',
        decision_date=arguments['decision_date'], scenario_dates=deepcopy(arguments['scenario_dates']),
        max_objective_evaluations=8192, entered_cash='20000', fee_bps=fee,
        minimum_cash_buffer='0', selected=selected, best_by_k=frontier)
    decision = dict(status='TARGET_READY', core_calls=1, orders_created=False,
        account_mutated=False, execution_blocked=True, limitations=[],
        payload=dict(schema='REAL_STRATEGY_CONTINUOUS32_TARGET_DECISION_V1', input_binding=binding,
                     search_result=result, target_quantities=deepcopy(selected['quantities'])))
    target = dict(payload=dict(schema='REAL_STRATEGY_MONTHLY_TARGET_V1',
        account_id='synthetic-account', created_at=valuation_date + 'T20:00:03+00:00',
        decision=decision, previous_target_id=None, target_month=month,
        request=dict(event_id='synthetic-' + month, reason='INITIAL',
                     expected_revision='synthetic-revision', previous_target_id=None),
        runtime_pins=deepcopy(source_hashes), target_quantities=deepcopy(selected['quantities'])))
    return sign(target)


class SavedMonthlyFrontierProposalTests(unittest.TestCase):
    def test_held_security_outside_selection_domain_remains_required_without_invented_issuer(self):
        original = native_fixture()
        binding = original['payload']['decision']['payload']['input_binding']
        held_mark = deepcopy(binding['marks']['C'])
        held_mark.update(security_id='D', ticker='OLD-D', price='50')
        binding['marks']['D'] = held_mark
        binding['strategy_shares'] = {'D': 3}
        binding['holding_market_values'] = {'D': '150'}
        binding['total_uninvested_cash'] = '19850'
        binding['execution_context']['available_cash'] = '19850'
        original = sign(original)
        snapshot = deepcopy(original)
        self.assertNotIn('D', binding['search_arguments']['prices'])
        self.assertNotIn('D', binding['search_arguments']['metadata'])
        self.assertTrue(all('D' not in scenario for scenario in binding['search_arguments']['training_scenarios']))
        output = build_frontier_proposal(target=original)
        payload = output['payload']
        self.assertEqual(payload['proposed_target_quantities'], {'A': 99, 'B': 99})
        self.assertEqual(payload['proposed_security_ids'], ['A', 'B'])
        self.assertEqual(payload['required_security_ids'], ['A', 'B', 'D'])
        old = {item['security_id']: item for item in payload['required_securities']}['D']
        self.assertEqual(old['ticker'], 'OLD-D')
        self.assertIsNone(old['issuer_id'])
        self.assertEqual(old['identity_status'], 'HELD_ONLY_ISSUER_UNAVAILABLE_REQUIRES_ADMISSION')
        self.assertEqual((old['original_held_quantity'], old['proposed_quantity']), (3, 0))
        self.assertEqual(old['mark'], held_mark)
        self.assertEqual(original, snapshot)
        self.assertFalse(output['production_admitted'])
        self.assertFalse(output['orders_created'])
        self.assertFalse(output['account_mutated'])
        # Still fail closed when the old holding loses its genuine bound mark.
        broken = deepcopy(original)
        broken['payload']['decision']['payload']['input_binding']['marks'].pop('D')
        with self.assertRaises(ValueError):
            build_frontier_proposal(target=sign(broken))

    def test_new_york_valuation_day_accepts_utc_next_day_and_rejects_resigned_date_shift(self):
        original = native_fixture()
        selected = original['payload']['decision']['payload']
        selected['input_binding']['valuation_at'] = '2026-10-21T01:00:00+00:00'
        original = sign(original)
        # UTC October 21 at 01:00 is still October 20 in New York.
        proposal = build_frontier_proposal(target=original)
        self.assertEqual(proposal['payload']['target_month'], '2026-10')
        self.assertEqual(proposal['payload']['proposed_target_quantities'], {'A': 99, 'B': 99})
        changed = deepcopy(original)
        selected = changed['payload']['decision']['payload']
        selected['input_binding']['valuation_date'] = '2026-11-20'
        selected['input_binding']['search_arguments']['decision_date'] = '2026-11-20'
        selected['search_result']['decision_date'] = '2026-11-20'
        changed['payload']['target_month'] = '2026-11'
        # Recomputing all three content IDs cannot turn the old timestamp into
        # a later monthly observation, even when all date labels agree.
        with self.assertRaises(ValueError):
            build_frontier_proposal(target=sign(changed))

    def test_strict_change_new_security_and_original_holdings_have_full_identity(self):
        original = native_fixture(held=True)
        output = build_frontier_proposal(target=original)
        payload = output['payload']
        self.assertEqual(payload['base_capped_target_quantities'], {'A': 100})
        self.assertEqual(payload['proposed_target_quantities'], {'A': 99, 'B': 99})
        self.assertTrue(payload['proof']['strict_improvement'])
        self.assertEqual(payload['proof']['unique_capped_baskets'], 3)
        self.assertEqual(payload['proof']['source_cardinality'], 2)
        self.assertEqual(payload['required_security_ids'], ['A', 'B', 'C'])
        proposed = {item['security_id']: item for item in payload['proposed_securities']}
        self.assertEqual(set(proposed), {'A', 'B'})
        self.assertEqual(proposed['B']['quantity'], 99)
        self.assertEqual(proposed['B']['issuer_id'], 'issuer-B')
        self.assertEqual(proposed['B']['mark'], original['payload']['decision']['payload']['input_binding']['marks']['B'])
        held = {item['security_id']: item for item in payload['required_securities']}['C']
        self.assertEqual((held['original_held_quantity'], held['proposed_quantity']), (3, 0))
        for name, growth in [('base', F(29999, 20000)), ('selected', F(1890901, 1000000))]:
            product = growth ** 12
            expected = sha256(f'{product.numerator:x}/{product.denominator:x}'.encode()).hexdigest()
            self.assertEqual(payload['proof'][name + '_product_sha256'], expected)

    def test_tie_retains_original_and_zero_cap_keys_are_preserved(self):
        tied = build_frontier_proposal(target=native_fixture(tie=True))['payload']
        self.assertFalse(tied['proof']['strict_improvement'])
        self.assertEqual(tied['proposed_target_quantities'], {'A': 100})
        zero = build_frontier_proposal(target=native_fixture(zero_cap=True))['payload']
        self.assertFalse(zero['proof']['strict_improvement'])
        self.assertEqual(zero['proposed_target_quantities'], {'A': 0})
        self.assertEqual(zero['proposed_security_ids'], [])

    def test_zero_and_one_basis_point_inputs_are_preserved_and_bound(self):
        products = []
        for fee in ('0', '1'):
            with self.subTest(fee=fee):
                original = native_fixture(fee=fee)
                output = build_frontier_proposal(target=original)
                self.assertEqual(output['payload']['fee_bps'], fee)
                products.append(output['payload']['proof']['selected_product_sha256'])
                original['payload']['decision']['payload']['search_result']['fee_bps'] = '999'
                with self.assertRaisesRegex(ValueError, 'RESULT_FINANCIAL_BINDING'):
                    build_frontier_proposal(target=sign(original))
        self.assertNotEqual(*products)

    def test_each_native_identity_and_resigned_false_financial_claim_are_rejected(self):
        for level in ('target', 'decision', 'input'):
            original = native_fixture()
            if level == 'target':
                original['target_id'] = '0' * 64
            elif level == 'decision':
                original['payload']['decision']['decision_id'] = '0' * 64
                original['target_id'] = digest(original['payload'])
            else:
                original['payload']['decision']['payload']['input_id'] = '0' * 64
                original['payload']['decision']['decision_id'] = digest(original['payload']['decision']['payload'])
                original['target_id'] = digest(original['payload'])
            with self.subTest(level=level), self.assertRaisesRegex(ValueError, 'ORIGINAL_NATIVE_ID_CHANGED'):
                build_frontier_proposal(target=original)
        mutations = [
            lambda binding, result: binding.update(total_uninvested_cash='19999'),
            lambda binding, result: result['best_by_k']['2'].update(fees='0'),
            lambda binding, result: binding['search_arguments']['prices'].update(B='101'),
            lambda binding, result: binding.update(continuous_iterations=31),
            lambda binding, result: result['best_by_k']['2'].update(training_gross_growth_product='2'),
        ]
        for index, mutate in enumerate(mutations):
            original = native_fixture()
            selected = original['payload']['decision']['payload']
            mutate(selected['input_binding'], selected['search_result'])
            with self.subTest(index=index), self.assertRaises(ValueError):
                build_frontier_proposal(target=sign(original))

    def test_missing_new_security_and_disconnected_source_or_future_training_rejected(self):
        mutations = [
            lambda binding: binding['marks'].pop('B'),
            lambda binding: binding['search_arguments']['metadata'].pop('B'),
            lambda binding: binding['marks']['B']['source_hashes'].update({'synthetic-prices.json': 'f' * 64}),
            lambda binding: binding['marks']['B'].update(currency='HKD'),
            lambda binding: binding['marks']['B'].update(price_basis='SPLIT_ADJUSTED_USD'),
            lambda binding: binding['marks']['B'].update(observed_at='2026-10-21T20:00:00+00:00'),
            lambda binding: binding.update(valuation_at='2026-10-20T20:00:02'),
            lambda binding: binding['search_arguments']['training_scenarios'][0].pop('B'),
            lambda binding: binding.update(training_cutoff_date='2026-10-21'),
            lambda binding: binding['documents'].update(unit_review='unbound.json'),
        ]
        for index, mutate in enumerate(mutations):
            original = native_fixture()
            mutate(original['payload']['decision']['payload']['input_binding'])
            with self.subTest(index=index), self.assertRaises(ValueError):
                build_frontier_proposal(target=sign(original))

    def test_deterministic_separate_identity_no_mutation_and_no_runtime_admission(self):
        original = native_fixture()
        snapshot = deepcopy(original)
        first = build_frontier_proposal(target=original)
        second = build_frontier_proposal(target=original)
        self.assertEqual(original, snapshot)
        self.assertEqual(first, second)
        self.assertEqual(first['proposal_id'], digest(first['payload']))
        self.assertNotEqual(first['proposal_id'], original['target_id'])
        self.assertEqual(first['payload']['original_target'], original)
        self.assertEqual(first['payload']['source_target_id'], original['target_id'])
        self.assertEqual(first['status'], 'READ_ONLY_FRONTIER_PROPOSAL')
        for field in ('source_bytes_verified', 'production_admitted', 'orders_created', 'account_mutated'):
            self.assertIs(first[field], False)
        self.assertEqual((first['new_searches'], first['new_candidate_generation']), (0, 0))
        first['payload']['original_target']['payload']['target_quantities']['A'] = 0
        first['payload']['proposed_securities'][0]['mark']['price'] = '0'
        self.assertEqual(original, snapshot)
        next_month = build_frontier_proposal(target=native_fixture(month='2026-11'))
        self.assertNotEqual(next_month['proposal_id'], second['proposal_id'])
        self.assertEqual(second['payload']['target_month'], '2026-10')
        self.assertEqual(next_month['payload']['target_month'], '2026-11')
        relabelled = deepcopy(original)
        relabelled['payload']['target_month'] = '2026-11'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_TARGET_MONTH_BINDING'):
            build_frontier_proposal(target=sign(relabelled))


if __name__ == '__main__':
    unittest.main()
