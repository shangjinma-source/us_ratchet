"""Independent tiny all-box oracle; no real sources, fit or economic cases."""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from itertools import combinations, product
from pathlib import Path
import builtins
import unittest
from unittest.mock import patch

from backtest import ndx_variable_cardinality_new_cash_problem_research as subject


def case(names=('A', 'B', 'C')):
    return dict(
        evidence_facts=dict(conditional_inventory=[dict(security_id=sid, issuer_id='I' + sid,
            ticker=sid, risk_chain='R' + sid) for sid in names]),
        prior_book=dict(holdings={}, cash='0', currency='USD', as_of='2026-09-30', cash_includes_event=False),
        cash_event=dict(amount='2', currency='USD', decision_date='2026-09-30',
            execution_date='2026-10-01', available_at='2026-09-30T19:00:00Z'),
        price_context=dict(currency='USD', stage='DECISION_KNOWN_PRICES',
            decision_at='2026-09-30T20:00:00Z', session_timezone='UTC', basis='SYNTHETIC_UNADJUSTED_USD',
            prices={sid: dict(price='1', lot_size=1, available_at='2026-09-30T19:00:00Z',
                price_date='2026-09-30', basis='SYNTHETIC_UNADJUSTED_USD') for sid in names}),
        policy=dict(risk_parameters=dict(max_single_weight='1', min_single_weight='0',
            top_weight_cap='1', minimum_effective_n_ratio='0', risk_chain_top1_cap='1'),
            transaction_cost_bps='0', minimum_cash_buffer='0', currency='USD'),
        domain_kind='WHOLE_LOT_QUANTITIES')


def prepare(inputs, synthetic=True):
    if synthetic:
        return subject.prepare_synthetic_new_cash_problem(synthetic_case=inputs)
    return subject.prepare_new_cash_problem(**inputs)


def oracle(inputs):
    """Independent exhaustive synthetic domain, never subject math helpers.

    Produce every box tuple's classification, not just the successful count.
    The oracle never receives subject caps/counts/certificates as inputs.
    """
    facts = inputs['evidence_facts']
    identities = {row['security_id']: row for row in
                  facts['conditional_inventory'] + facts.get('frozen_only_securities', [])}
    buys = sorted(row['security_id'] for row in facts['conditional_inventory']
                  if row['security_id'] not in facts.get('conditional_exclusions', {}))
    old = {sid:Fraction(value) for sid,value in inputs['prior_book']['holdings'].items()}
    marks = {sid: Fraction(row['price']) for sid, row in inputs['price_context']['prices'].items()}
    lots = {sid: row['lot_size'] for sid, row in inputs['price_context']['prices'].items()}
    budget = (Fraction(inputs['prior_book']['cash']) + Fraction(inputs['cash_event']['amount'])
              - Fraction(inputs['policy']['minimum_cash_buffer']))
    fee = 1 + Fraction(inputs['policy']['transaction_cost_bps']) / 10000
    thresholds = {key: Fraction(value) for key, value in inputs['policy']['risk_parameters'].items()}
    tol = Fraction(1, 1000000000)
    if budget < 0:
        return dict(caps=None, records=[], feasible_by_k={})
    caps = {sid: int(budget / (marks[sid] * lots[sid] * fee)) for sid in buys}
    records, feasible_by_k = [], {}
    for quantities in product(*(range(caps[sid] + 1) for sid in buys)):
        increments = dict(zip(buys, quantities))
        cost = sum((marks[sid] * lots[sid] * value * fee for sid, value in increments.items()), Fraction(0))
        final = {sid: old.get(sid, 0) + lots[sid] * increments.get(sid, 0) for sid in identities}
        positive = {sid: count for sid, count in final.items() if count > 0}
        issuer_unique = len({identities[sid]['issuer_id'] for sid in positive}) == len(positive)
        total = sum((marks[sid] * count for sid, count in positive.items()), Fraction(0))
        weights = {sid: marks[sid] * count / total for sid, count in positive.items()} if total else {}
        ordered = sorted(weights.values(), reverse=True)
        chains = {}
        for sid, weight in weights.items():
            chain = identities[sid]['risk_chain']
            chains[chain] = chains.get(chain, Fraction(0)) + weight
        checks = [False] * 5
        if weights:
            checks = [max(weights.values()) <= thresholds['max_single_weight'] + tol,
                min(weights.values()) >= thresholds['min_single_weight'] - tol,
                sum(ordered[:3]) <= thresholds['top_weight_cap'] + tol,
                1 / sum(w * w for w in weights.values()) >= thresholds['minimum_effective_n_ratio'] * len(weights) - tol,
                max(chains.values()) <= thresholds['risk_chain_top1_cap'] + tol]
        passed = bool(weights) and cost <= budget and issuer_unique and all(checks)
        if passed:
            feasible_by_k[len(positive)] = feasible_by_k.get(len(positive), 0) + 1
        records.append(dict(tuple=quantities, cost=cost, final=final, weights=weights,
            issuer_unique=issuer_unique, affordable=cost <= budget, checks=checks, passed=passed))
    return dict(caps=caps, records=records, feasible_by_k=feasible_by_k)


class NewCashProblemTests(unittest.TestCase):
    def assert_oracle_consistent(self, inputs):
        result, expected = prepare(inputs), oracle(inputs)
        self.assertEqual(result['domain_formula']['coordinate_caps_or_null'], expected['caps'])
        if expected['caps'] is None:
            self.assertIsNone(result['bounding_box_count_or_null'])
        else:
            self.assertEqual(int(result['bounding_box_count_or_null']), len(expected['records']))
        by_k = {row['holding_count']: row for row in result['all_k_rows']}
        descriptor = result['domain_formula']
        variable_ids = result['conditional_buy_security_ids']
        described_old = {sid:Fraction(value) for sid,value in result['frozen_prior_book']['quantities'].items()}
        for k in expected['feasible_by_k']:
            self.assertEqual(by_k[k]['status'], 'NOT_PRUNED_NECESSARY_ONLY')
        # Check every certificate against every independently feasible tuple.
        for record in expected['records']:
            described_increments = dict(zip(variable_ids, record['tuple']))
            described_final = {sid: described_old.get(sid,0) + descriptor['lot_sizes'][sid]
                * described_increments.get(sid,0) for sid in descriptor['prices']}
            self.assertEqual(described_final, record['final'])
            described_cost = sum((Fraction(descriptor['prices'][sid]) * descriptor['lot_sizes'][sid]
                * count * Fraction(descriptor['fee_factor']) for sid,count in described_increments.items()), Fraction(0))
            self.assertEqual(described_cost, record['cost'])
            self.assertEqual(described_cost <= Fraction(descriptor['cash_budget_after_buffer']), record['affordable'])
            described_total = sum((Fraction(descriptor['prices'][sid]) * count
                for sid,count in described_final.items()), Fraction(0))
            described_weights = {sid: Fraction(descriptor['prices'][sid]) * count / described_total
                for sid,count in described_final.items() if count > 0} if described_total else {}
            self.assertEqual(described_weights, record['weights'])
            if record['passed']:
                row = by_k[len(record['weights'])]
                self.assertFalse(row['necessary_certificates'])
                self.assertFalse(row['domain_necessary_reasons'])
                for bound in result['domain_formula']['frozen_weight_lower_bounds']:
                    if bound['kind'] == 'SECURITY':
                        actual = record['weights'][bound['identity']]
                    else:
                        identities = {r['security_id']: r for r in inputs['evidence_facts']['conditional_inventory']
                            + inputs['evidence_facts'].get('frozen_only_securities', [])}
                        actual = sum((weight for sid, weight in record['weights'].items()
                            if identities[sid]['risk_chain'] == bound['identity']), Fraction(0))
                    self.assertLessEqual(Fraction(bound['lower_bound']), actual)
        return result, expected

    def test_full_three_issuer_box_and_coupled_budget(self):
        result, expected = self.assert_oracle_consistent(case())
        self.assertEqual(len(expected['records']), 27)
        affordable = {row['tuple'] for row in expected['records'] if row['affordable']}
        self.assertEqual(affordable, {(0,0,0),(0,0,1),(0,0,2),(0,1,0),(0,1,1),
            (0,2,0),(1,0,0),(1,0,1),(1,1,0),(2,0,0)})
        self.assertEqual(expected['feasible_by_k'], {1: 6, 2: 3})
        self.assertEqual(result['domain_formula']['whole_lot_activation_upper_or_null'], 2)
        self.assertIn('WHOLE_LOT_ACTIVATION_BUDGET_UPPER_BOUND', result['all_k_rows'][2]['domain_necessary_reasons'])
        self.assertFalse(result['coverage']['bounding_box_is_feasible_count'])

    def test_frozen_ineligible_old_continuous_vs_whole(self):
        inputs = case()
        inputs['prior_book']['holdings'] = {'A': 1}
        inputs['cash_event']['amount'] = '1'
        inputs['evidence_facts']['conditional_exclusions'] = {'A': 'SYNTHETIC_INELIGIBLE_OLD'}
        for row in inputs['price_context']['prices'].values():
            row['price'] = '2'
        inputs['policy']['risk_parameters'].update(max_single_weight='0.75', min_single_weight='0.1')
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(expected['caps'], {'B': 0, 'C': 0})
        self.assertEqual(expected['feasible_by_k'], {})
        self.assertEqual(result['frozen_prior_book']['quantities'], {'A': '1'})
        self.assertEqual(result['frozen_prior_book']['frozen_ineligible_security_ids'], ['A'])
        inputs['domain_kind'] = 'CONTINUOUS_INCREMENTAL_DOLLARS'
        continuous = prepare(inputs)
        self.assertIsNone(continuous['bounding_box_count_or_null'])
        self.assertIsNone(continuous['domain_formula']['coordinate_caps_or_null'])
        self.assertEqual(continuous['all_k_rows'][1]['status'], 'NOT_PRUNED_NECESSARY_ONLY')
        self.assertEqual(Fraction(continuous['domain_formula']['maximum_incremental_gross_or_null']), 1)
        # Independent continuous witness x_B=1, q_A*p_A=2.
        self.assertLessEqual(Fraction(2,3), Fraction('0.75'))
        self.assertGreaterEqual(Fraction(1,3), Fraction('0.1'))

    def test_original_top3_rejects_three_issuer_positive_domain(self):
        inputs = case()
        inputs['policy']['risk_parameters'].update(max_single_weight='0.45', min_single_weight='0.05',
            top_weight_cap='0.8', minimum_effective_n_ratio='0.7', risk_chain_top1_cap='0.55')
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertFalse(expected['feasible_by_k'])
        for row in result['all_k_rows']:
            self.assertEqual(row['status'], 'NECESSARY_INFEASIBLE')
            self.assertIn('TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_CAP', [c['reason'] for c in row['necessary_certificates']])
        self.assertEqual(result['policy']['risk_parameters']['top_weight_cap'], '4/5')

    def test_fee_buffer_and_frozen_k_lower_bound(self):
        inputs = case()
        inputs['prior_book'].update(holdings={'A': 1}, cash='1')
        inputs['cash_event']['amount'] = '3'
        inputs['policy'].update(transaction_cost_bps='1000', minimum_cash_buffer='1')
        inputs['evidence_facts']['conditional_exclusions'] = {'A': 'FROZEN_NOT_BUYABLE'}
        for sid, price in {'A': '3', 'B': '2', 'C': '1'}.items():
            inputs['price_context']['prices'][sid]['price'] = price
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(expected['caps'], {'B': 1, 'C': 2})
        self.assertEqual({r['tuple'] for r in expected['records'] if r['affordable']}, {(0,0),(0,1),(0,2),(1,0)})
        self.assertEqual(expected['feasible_by_k'], {1: 1, 2: 3})
        self.assertEqual(result['domain_formula']['fee_factor'], '11/10')
        inputs['prior_book']['holdings']['B'] = 1
        result, _ = self.assert_oracle_consistent(inputs)
        self.assertIn('BELOW_FROZEN_POSITIVE_HOLDING_COUNT', result['all_k_rows'][0]['domain_necessary_reasons'])

    def test_independent_all_composition_coefficients_with_share_classes(self):
        inputs = case(('A', 'AA', 'B', 'C'))
        rows = inputs['evidence_facts']['conditional_inventory']
        rows[1]['issuer_id'] = 'IA'
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual([int(r['composition_count']) for r in result['conditional_inventory']['all_k_denominators']], [4,5,2])
        inputs['prior_book']['holdings'] = {'A': 1}
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['domain_formula']['issuer_locked_zero_security_ids'], {'AA': 'A'})
        self.assertEqual([r['frozen_old_conditional_composition_count'] for r in result['all_k_rows']], ['1','2','1'])
        self.assertTrue(any(not r['issuer_unique'] for r in expected['records']))
        # Independently enumerate support sets for the frozen conditional domain.
        valid_supports = []
        for size in range(1,5):
            for chosen in combinations(rows, size):
                ids = {r['security_id'] for r in chosen}
                if 'A' in ids and len({r['issuer_id'] for r in chosen}) == size:
                    valid_supports.append(ids)
        for row in result['all_k_rows']:
            self.assertEqual(int(row['frozen_old_conditional_composition_count']),
                sum(len(ids) == row['holding_count'] for ids in valid_supports))
        inputs['prior_book']['holdings']['AA'] = 1
        conflict = prepare(inputs)
        self.assertEqual(conflict['frozen_prior_book']['issuer_conflicts'], {'IA': ['A','AA']})
        self.assertTrue(all(r['status'] == 'STRUCTURALLY_INFEASIBLE' for r in conflict['all_k_rows']))
        self.assertTrue(all(r['frozen_old_conditional_composition_count'] is None for r in conflict['all_k_rows']))
        self.assertEqual(conflict['frozen_prior_book']['quantities'], {'A': '1', 'AA': '1'})

    def test_old_sid_outside_pool_is_retained_and_never_bought(self):
        inputs = case(('B','C'))
        inputs['evidence_facts']['frozen_only_securities'] = [dict(security_id='A', issuer_id='IA', ticker='A', risk_chain='RA')]
        inputs['prior_book']['holdings'] = {'A': 2}
        inputs['price_context']['prices']['A'] = deepcopy(inputs['price_context']['prices']['B'])
        result, _ = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['conditional_inventory']['security_count'], 2)
        self.assertEqual(len(result['all_k_rows']), 3)
        self.assertEqual(result['frozen_prior_book']['quantities'], {'A': '2'})
        self.assertEqual(result['conditional_buy_security_ids'], ['B','C'])
        self.assertNotIn('A', result['domain_formula']['coordinate_caps_or_null'])

    def test_lots_are_not_shares_and_old_odd_lot_is_frozen(self):
        inputs = case()
        inputs['prior_book']['holdings'] = {'A': 1}
        inputs['cash_event']['amount'] = '5'
        inputs['price_context']['prices']['A']['lot_size'] = 2
        inputs['price_context']['prices']['B'].update(price='2', lot_size=2)
        inputs['price_context']['prices']['C'].update(price='3', lot_size=1)
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(expected['caps'], {'A': 2, 'B': 1, 'C': 1})
        for record in expected['records']:
            self.assertEqual(record['final']['A'] % 2, 1)
        self.assertEqual(result['frozen_prior_book']['quantities']['A'], '1')

    def test_fractional_old_shares_are_frozen_while_new_lots_are_integer(self):
        for quantity in ('0.5', Decimal('0.5')):
            with self.subTest(quantity=quantity):
                inputs = case()
                inputs['prior_book']['holdings'] = {'A':quantity}
                inputs['price_context']['prices']['A']['lot_size'] = 2
                result, expected = self.assert_oracle_consistent(inputs)
                self.assertEqual(result['frozen_prior_book']['quantities'], {'A':'1/2'})
                self.assertEqual(result['frozen_prior_book']['positive_holding_count'],1)
                self.assertEqual(result['domain_formula']['old_stock_value'],'1/2')
                for record in expected['records']:
                    self.assertEqual((record['final']['A'] - Fraction(1,2)) % 2, 0)
                    self.assertGreaterEqual(record['final']['A'],Fraction(1,2))
                self.assertEqual(result['all_k_rows'][0]['frozen_old_conditional_composition_count'],'1')

    def test_fractional_ineligible_old_share_class_locks_issuer_and_conserves_cash(self):
        inputs = case(('A','AA','B'))
        inputs['evidence_facts']['conditional_inventory'][1]['issuer_id'] = 'IA'
        inputs['evidence_facts']['conditional_exclusions'] = {'A':'SYNTHETIC_INELIGIBLE'}
        inputs['prior_book']['holdings'] = {'A':'0.5'}
        inputs['cash_event']['amount'] = '3'
        for row in inputs['price_context']['prices'].values():
            row['price'] = '2'
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['frozen_prior_book']['frozen_ineligible_security_ids'],['A'])
        self.assertEqual(result['domain_formula']['issuer_locked_zero_security_ids'],{'AA':'A'})
        self.assertEqual([r['frozen_old_conditional_composition_count'] for r in result['all_k_rows']],['1','1'])
        for record in expected['records']:
            self.assertEqual(record['final']['A'],Fraction(1,2))
            if record['passed']:
                self.assertEqual(record['final']['AA'],0)
                remaining = Fraction(3) - record['cost']
                final_stock = sum(Fraction(2)*count for count in record['final'].values())
                self.assertEqual(remaining+final_stock,Fraction(4))
        self.assertTrue(any(record['final']['AA']>0 and not record['issuer_unique'] for record in expected['records']))

    def test_fractional_frozen_only_sid_outside_inventory(self):
        inputs = case(('B','C'))
        inputs['evidence_facts']['frozen_only_securities'] = [dict(security_id='A',issuer_id='IA',ticker='A',risk_chain='RA')]
        inputs['prior_book']['holdings'] = {'A':'0.125'}
        inputs['price_context']['prices']['A'] = deepcopy(inputs['price_context']['prices']['B'])
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['frozen_prior_book']['quantities'],{'A':'1/8'})
        self.assertTrue(all(record['final']['A']==Fraction(1,8) for record in expected['records']))

    def test_frozen_security_and_chain_dilution_bounds(self):
        inputs = case()
        inputs['prior_book']['holdings'] = {'A': 2, 'B': 1}
        inputs['cash_event']['amount'] = '1'
        inputs['evidence_facts']['conditional_inventory'][1]['risk_chain'] = 'RA'
        inputs['policy']['risk_parameters'].update(max_single_weight='0.49', risk_chain_top1_cap='0.74')
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertFalse(expected['feasible_by_k'])
        reasons = {c['reason'] for r in result['all_k_rows'] for c in r['necessary_certificates']}
        self.assertIn('FROZEN_SECURITY_CANNOT_DILUTE_BELOW_MAX', reasons)
        self.assertIn('FROZEN_CHAIN_CANNOT_DILUTE_BELOW_CAP', reasons)
        bounds = {(b['kind'],b['identity']):Fraction(b['lower_bound']) for b in result['domain_formula']['frozen_weight_lower_bounds']}
        self.assertEqual(bounds[('SECURITY','A')], Fraction(1,2))
        self.assertEqual(bounds[('RISK_CHAIN','RA')], Fraction(3,4))

    def test_exact_tolerance_boundaries_are_not_strictly_excluded(self):
        for key, value, k, reason in (
            ('max_single_weight','0.499999999',2,'MAX_SINGLE_CAPACITY_BELOW_ONE'),
            ('min_single_weight','0.500000001',2,'MIN_SINGLE_REQUIRED_MASS_ABOVE_ONE'),
            ('top_weight_cap','0.749999999',4,'TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_CAP')):
            with self.subTest(key=key):
                inputs = case(('A','B','C','D'))
                inputs['cash_event']['amount'] = '4'
                inputs['policy']['risk_parameters'][key] = value
                result, _ = self.assert_oracle_consistent(inputs)
                reasons = [c['reason'] for c in result['all_k_rows'][k-1]['necessary_certificates']]
                self.assertNotIn(reason, reasons)
        inputs = case()
        inputs['prior_book']['holdings'] = {'A': 2}
        inputs['policy']['risk_parameters'].update(max_single_weight='0.499999999', risk_chain_top1_cap='0.499999999')
        result = prepare(inputs)
        self.assertFalse(any(c['reason'].startswith('FROZEN_') for row in result['all_k_rows'] for c in row['necessary_certificates']))
        inputs['policy']['risk_parameters'].update(max_single_weight='0.499999998', risk_chain_top1_cap='0.499999998')
        result = prepare(inputs)
        self.assertTrue(any(c['reason'].startswith('FROZEN_') for row in result['all_k_rows'] for c in row['necessary_certificates']))

    def test_extreme_small_matrices_have_no_false_infeasibility_certificates(self):
        checked = 0
        for amount, fee, buffer, prior_a, lot_b, chain_shared in product(
                ('0','2','3'), ('0','500'), ('0','1'), (0,1), (1,2), (False,True)):
            inputs = case()
            inputs['cash_event']['amount'] = amount
            inputs['policy'].update(transaction_cost_bps=fee, minimum_cash_buffer=buffer)
            inputs['policy']['risk_parameters'].update(max_single_weight='0.7', min_single_weight='0.1',
                top_weight_cap='1', minimum_effective_n_ratio='0.7', risk_chain_top1_cap='0.8')
            inputs['prior_book']['holdings'] = {'A': prior_a}
            inputs['price_context']['prices']['B']['lot_size'] = lot_b
            if chain_shared:
                inputs['evidence_facts']['conditional_inventory'][1]['risk_chain'] = 'RA'
            self.assert_oracle_consistent(inputs)
            checked += 1
        self.assertEqual(checked, 96)

    def test_all_missing_sources_report_individually_without_short_circuit(self):
        result = prepare(case(), synthetic=False)
        self.assertEqual({row['requirement_id'] for row in result['source_checks']},
            {'HOST_BINDING','PIT_MEMBERSHIP','IDENTITY_AND_ACTIONS','RISK_AND_LIQUIDITY',
             'CAUSAL_MATRIX','PRIOR_BOOK','CASH_EVENT','PRICE_CONTEXT','POLICY','DUAL_BENCHMARKS'})
        self.assertTrue(all(row['reference_state']=='MISSING' and 'SOURCE_BYTES' in row['missing_fields']
            for row in result['source_checks']))
        self.assertTrue(all(row['cutoff']=='2026-09-30' for row in result['source_checks']))
        self.assertEqual(len(result['source_blockers']), 10)
        self.assertEqual(result['numerical_status'], 'CONDITIONAL_CONTEXT_READY')

    def test_strict_universal_bounds_reject_only_beyond_tolerance(self):
        for key,value,k,reason in (
            ('max_single_weight','0.499999998',2,'MAX_SINGLE_CAPACITY_BELOW_ONE'),
            ('min_single_weight','0.500000002',2,'MIN_SINGLE_REQUIRED_MASS_ABOVE_ONE'),
            ('top_weight_cap','0.749999998',4,'TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_CAP')):
            with self.subTest(key=key):
                inputs = case(('A','B','C','D'))
                inputs['cash_event']['amount'] = '4'
                inputs['policy']['risk_parameters'][key] = value
                result, _ = self.assert_oracle_consistent(inputs)
                certificates = result['all_k_rows'][k-1]['necessary_certificates']
                certificate = next(c for c in certificates if c['reason']==reason)
                left,right = Fraction(certificate['left']),Fraction(certificate['right'])
                self.assertTrue(left < right if certificate['comparison']=='<' else left > right)
                self.assertGreater(Fraction(certificate['strict_gap']),0)

    def test_all_excluded_pool_still_preserves_full_conditional_denominator(self):
        inputs = case()
        inputs['evidence_facts']['conditional_exclusions'] = {sid:'NOT_SOURCE_QUALIFIED' for sid in ('A','B','C')}
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['conditional_inventory']['security_count'],3)
        self.assertEqual(len(result['all_k_rows']),3)
        self.assertEqual(result['conditional_buy_security_ids'],[])
        self.assertEqual(result['bounding_box_count_or_null'],'1')
        self.assertEqual(expected['feasible_by_k'],{})
        self.assertTrue(all('ABOVE_CONDITIONAL_ELIGIBLE_ISSUER_SUPPORT' in row['domain_necessary_reasons']
            for row in result['all_k_rows']))

    def test_all_ten_source_requirements_remain_blocked_with_claimed_authority(self):
        inputs = case()
        facts = inputs['evidence_facts']
        facts.update(qualified=True, authority={'execution_authorized': True},
            source_checks={role: 'PASS' for role, _ in subject.SOURCE_REQUIREMENTS},
            source_hashes={'trap-do-not-read': 'a'*64})
        facts['input_references'] = {role:dict(path='trap-do-not-read/'+role, sha256='a'*64,
            json_pointer='/claims') for role, _ in subject.SOURCE_REQUIREMENTS}
        facts['input_references'].update(INCUMBENT=dict(path='trap-incumbent',sha256='b'*64),
            TARGET_012922=dict(path='trap-target',sha256='c'*64))
        with (patch.object(builtins, 'open', side_effect=AssertionError('No IO')),
              patch.object(Path, 'read_bytes', side_effect=AssertionError('No source reads'))):
            result = prepare(inputs, synthetic=False)
        self.assertEqual(len(result['source_checks']), 10)
        self.assertEqual(len(result['source_blockers']), 10)
        self.assertTrue(all(row['status']=='SOURCE_BLOCKED' and not row['qualification_established'] for row in result['source_checks']))
        self.assertTrue(all(row['reference_state']=='CLAIMED_REFERENCE_UNVERIFIED' for row in result['source_checks']))
        self.assertIsNone(result['qualified_inventory_or_null'])
        self.assertIsNone(result['qualified_all_k_denominators_or_null'])
        self.assertTrue(all(value is False for value in result['authority'].values()))
        self.assertEqual(result['current_account'], None)
        self.assertEqual(result['current_new_money'], None)
        self.assertEqual(result['plan_rows'], [])
        self.assertEqual(result['source_binding_status'], 'UNBOUND')
        self.assertEqual(result['input_scope'], 'CONDITIONAL_UNBOUND')
        self.assertFalse(result['benchmark_context']['comparable_economic_readiness'])
        self.assertEqual(result['coverage']['quantity_tuples_evaluated'], 0)

    def test_observation101_conditional77_and_qualified_null_are_separate(self):
        names = tuple('S'+str(i) for i in range(77))
        inputs = case(names)
        inputs['evidence_facts']['conditional_inventory'][1]['issuer_id'] = 'IS0'
        inputs['evidence_facts']['observed_inventory_reference'] = dict(path='observed101',sha256='a'*64,json_pointer='/101')
        inputs['evidence_facts']['conditional_inventory_reference'] = dict(path='conditional77',sha256='b'*64,json_pointer='/77')
        inputs['cash_event']['amount'] = '0'
        result = prepare(inputs, synthetic=False)
        self.assertEqual(result['conditional_inventory']['security_count'], 77)
        self.assertEqual(result['conditional_inventory']['issuer_count'], 76)
        self.assertEqual(len(result['all_k_rows']), 76)
        self.assertEqual(len(result['conditional_inventory']['all_k_denominators']), 76)
        self.assertIsNone(result['qualified_inventory_or_null'])
        self.assertEqual(result['observed_inventory_reference']['path'], 'observed101')
        self.assertEqual(result['conditional_inventory_reference']['path'], 'conditional77')
        self.assertEqual(result['domain_formula']['coordinate_caps_or_null'], dict.fromkeys(names,0))

    def test_more_than_legacy_pool_guard_is_not_truncated(self):
        inputs = case(tuple('S'+str(i) for i in range(257)))
        inputs['cash_event']['amount'] = '0'
        result = prepare(inputs)
        self.assertEqual(result['conditional_inventory']['security_count'], 257)
        self.assertEqual(len(result['all_k_rows']), 257)
        self.assertEqual(result['all_k_rows'][-1]['holding_count'], 257)

    def test_selected_subset_claim_does_not_reduce_pool(self):
        inputs = case()
        inputs['evidence_facts']['selected_target_security_ids'] = ['A','B']
        result = prepare(inputs)
        self.assertEqual(result['conditional_buy_security_ids'], ['A','B','C'])
        inputs['evidence_facts']['conditional_inventory'] = inputs['evidence_facts']['conditional_inventory'][:2]
        del inputs['price_context']['prices']['C']
        inputs['evidence_facts']['supplied_inventory_security_ids'] = ['A','B','C']
        result = prepare(inputs)
        self.assertEqual(result['numerical_status'], 'CONDITIONAL_CONTEXT_BLOCKED')
        self.assertIn('FULL_POOL_OMISSION_OR_MISMATCH', [row['reason'] for row in result['context_blockers']])
        self.assertIsNone(result['domain_formula']['coordinate_caps_or_null'])

    def test_semantic_context_failures_are_distinct_from_math_infeasibility(self):
        mutations = (
            ('currency', lambda x:x['cash_event'].update(currency='CNY'), 'CURRENCY_MISMATCH_NO_BOUND_FX'),
            ('late cash', lambda x:x['cash_event'].update(available_at='2026-10-01T00:00:00Z'), 'CASH_EVENT_NOT_AVAILABLE_AT_DECISION'),
            ('late price', lambda x:x['price_context']['prices']['A'].update(available_at='2026-10-01T14:00:00Z'), 'PRICE_NOT_AVAILABLE_AT_DECISION'),
            ('future prior', lambda x:x['prior_book'].update(as_of='2026-10-01'), 'FUTURE_PRIOR_BOOK'),
            ('double cash', lambda x:x['prior_book'].update(cash_includes_event=True), 'CASH_EVENT_ALREADY_IN_PRIOR_CASH'),
            ('same execution', lambda x:x['cash_event'].update(execution_date='2026-09-30'), 'EXECUTION_MUST_FOLLOW_DECISION'),
            ('timestamp', lambda x:x['price_context'].update(decision_at='2026-09-29T20:00:00Z'), 'DECISION_TIMESTAMP_DATE_MISMATCH'),
            ('basis', lambda x:x['price_context']['prices']['A'].update(basis='OTHER'), 'PRICE_BASIS_MISMATCH'),
            ('mixed sessions', lambda x:x['price_context']['prices']['A'].update(price_date='2026-09-29'), 'COMMON_PRICE_SESSION_MISMATCH'))
        for name, mutate, reason in mutations:
            with self.subTest(name=name):
                inputs = case()
                mutate(inputs)
                result = prepare(inputs)
                self.assertIn(reason, [row['reason'] for row in result['context_blockers']])
                self.assertTrue(all(row['status']=='CONDITIONAL_CONTEXT_BLOCKED' for row in result['all_k_rows']))
                self.assertIsNone(result['bounding_box_count_or_null'])
                self.assertFalse(result['all_cash_control']['feasible_conditionally'])

    def test_realized_open_is_explicitly_postdecision_not_causal_qualification(self):
        inputs = case()
        inputs['price_context']['stage'] = 'REALIZED_EXECUTION_OPEN'
        for row in inputs['price_context']['prices'].values():
            row.update(price_date='2026-10-01', available_at='2026-10-01T14:00:00Z')
        result = prepare(inputs)
        self.assertEqual(result['numerical_status'], 'CONDITIONAL_CONTEXT_READY')
        self.assertEqual(result['pricing_stage'], 'REALIZED_EXECUTION_OPEN')
        self.assertFalse(result['causal_decision_price_proven'])
        self.assertEqual(result['status'], 'SOURCE_BLOCKED')
        inputs['price_context']['prices']['A']['price_date'] = '2026-09-30'
        result = prepare(inputs)
        self.assertIn('REALIZED_OPEN_SESSION_MISMATCH',[r['reason'] for r in result['context_blockers']])

    def test_declared_session_zone_makes_equivalent_instants_representation_invariant(self):
        inputs = case()
        inputs['prior_book']['as_of'] = '2026-10-08'
        inputs['cash_event'].update(decision_date='2026-10-08',execution_date='2026-10-09',
            available_at='2026-10-08T20:00:00-04:00')
        inputs['price_context'].update(session_timezone='America/New_York',decision_at='2026-10-08T20:30:00-04:00')
        for row in inputs['price_context']['prices'].values():
            row.update(price_date='2026-10-08',available_at='2026-10-08T19:00:00-04:00')
        offset_result = prepare(inputs)
        inputs['cash_event']['available_at'] = '2026-10-09T00:00:00Z'
        inputs['price_context']['decision_at'] = '2026-10-09T00:30:00Z'
        for row in inputs['price_context']['prices'].values():
            row['available_at'] = '2026-10-08T23:00:00Z'
        utc_result = prepare(inputs)
        self.assertEqual(offset_result['numerical_status'],'CONDITIONAL_CONTEXT_READY')
        self.assertEqual(utc_result['numerical_status'],'CONDITIONAL_CONTEXT_READY')
        self.assertEqual(offset_result['problem_id'],utc_result['problem_id'])
        self.assertFalse(utc_result['exchange_session_timezone_verified'])
        self.assertFalse(utc_result['exchange_adjacency_verified'])
        inputs['price_context']['session_timezone'] = 'UTC'
        wrong_declared_zone = prepare(inputs)
        self.assertIn('DECISION_TIMESTAMP_DATE_MISMATCH',[r['reason'] for r in wrong_declared_zone['context_blockers']])

    def test_dst_session_day_consistency_uses_zone_not_utc_or_fixed_decision_offset(self):
        inputs = case()
        inputs['prior_book']['as_of'] = '2026-10-30'
        inputs['cash_event'].update(decision_date='2026-10-30',execution_date='2026-11-02',
            available_at='2026-10-30T19:00:00Z')
        inputs['price_context'].update(session_timezone='America/New_York',decision_at='2026-10-30T20:00:00Z',
            stage='REALIZED_EXECUTION_OPEN')
        # DST ended: Nov2 04:30Z is Nov1 23:30 NY, despite its UTC Nov2 date.
        for row in inputs['price_context']['prices'].values():
            row.update(price_date='2026-11-02',available_at='2026-11-02T04:30:00Z')
        early = prepare(inputs)
        self.assertIn('REALIZED_OPEN_SESSION_MISMATCH',[r['reason'] for r in early['context_blockers']])
        for row in inputs['price_context']['prices'].values():
            row['available_at'] = '2026-11-02T05:30:00Z'
        later = prepare(inputs)
        self.assertEqual(later['numerical_status'],'CONDITIONAL_CONTEXT_READY')
        self.assertFalse(later['realized_open_available_at_verified'])
        self.assertEqual(later['status'],'SOURCE_BLOCKED')

    def test_negative_buffer_budget_zero_capital_and_empty_pool(self):
        inputs = case()
        inputs['policy']['minimum_cash_buffer'] = '3'
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(result['domain_formula']['cash_budget_after_buffer'], '-1')
        self.assertTrue(all('CASH_BUFFER_NOT_MET_BEFORE_BUYS' in row['domain_necessary_reasons'] for row in result['all_k_rows']))
        inputs = case()
        inputs['cash_event']['amount'] = '0'
        for kind in ('CONTINUOUS_INCREMENTAL_DOLLARS','WHOLE_LOT_QUANTITIES'):
            inputs['domain_kind'] = kind
            result = prepare(inputs)
            self.assertTrue(result['all_cash_control']['feasible_conditionally'])
            self.assertTrue(all(row['status']=='NECESSARY_INFEASIBLE' for row in result['all_k_rows']))
        empty = prepare(case(()))
        self.assertEqual(empty['all_k_rows'], [])
        self.assertEqual(empty['bounding_box_count_or_null'], '1')
        self.assertTrue(empty['all_cash_control']['feasible_conditionally'])

    def test_exact_decimal_precision_and_zero_increment_domain(self):
        inputs = case(('A',))
        inputs['cash_event']['amount'] = '0.3000000000000000000000000000000000000001'
        inputs['price_context']['prices']['A']['price'] = '0.1'
        result = prepare(inputs)
        self.assertEqual(result['domain_formula']['coordinate_caps_or_null'], {'A': 3})
        self.assertEqual(Fraction(result['domain_formula']['total_cash_before_buys']),
            Fraction(inputs['cash_event']['amount']))
        inputs['cash_event']['amount'] = '0'
        inputs['prior_book']['holdings'] = {'A': 1}
        result, expected = self.assert_oracle_consistent(inputs)
        self.assertEqual(expected['feasible_by_k'], {1: 1})
        self.assertEqual(result['all_k_rows'][0]['frozen_old_conditional_composition_count'], '1')

    def test_validation_rejects_types_nonfinite_negatives_and_missing_fields(self):
        mutations = (
            lambda x:x['cash_event'].update(amount=True),
            lambda x:x['cash_event'].update(amount=1.2),
            lambda x:x['cash_event'].update(amount=Decimal('NaN')),
            lambda x:x['cash_event'].update(amount=Decimal('Infinity')),
            lambda x:x['cash_event'].update(amount='-1'),
            lambda x:x['cash_event'].update(amount=' 1'),
            lambda x:x['prior_book'].update(holdings={'A': True}),
            lambda x:x['prior_book'].update(holdings={'A': -1}),
            lambda x:x['prior_book'].update(holdings={'A': 0.5}),
            lambda x:x['prior_book'].update(holdings={'A': Decimal('NaN')}),
            lambda x:x['prior_book'].update(holdings={'A': '-0.5'}),
            lambda x:x['prior_book'].update(cash_includes_event=0),
            lambda x:x['price_context']['prices']['A'].update(price='0'),
            lambda x:x['price_context']['prices']['A'].update(lot_size=False),
            lambda x:x['price_context']['prices']['A'].update(lot_size=0),
            lambda x:x['price_context']['prices']['A'].update(available_at='2026-09-30T19:00:00'),
            lambda x:x['price_context']['prices'].pop('C'),
            lambda x:x['cash_event'].update(currency='usd'),
            lambda x:x['price_context'].pop('session_timezone'),
            lambda x:x['price_context'].update(session_timezone='../../trap'),
            lambda x:x['price_context'].update(session_timezone='/trap'),
            lambda x:x['price_context'].update(session_timezone='Not_A_Real_Zone'),
            lambda x:x['policy']['risk_parameters'].update(max_single_weight='1.01'),
            lambda x:x['policy']['risk_parameters'].update(min_single_weight='1',max_single_weight='0.5'),
            lambda x:x['policy']['risk_parameters'].pop('top_weight_cap'),
            lambda x:x['policy'].update(transaction_cost_bps='10001'),
            lambda x:x['policy'].update(minimum_cash_buffer='-1'),
            lambda x:x.update(domain_kind='TARGETS'),
            lambda x:x['evidence_facts'].update(conditional_exclusions={'X':'ABSENT'}),
            lambda x:x['evidence_facts']['conditional_inventory'].append(deepcopy(x['evidence_facts']['conditional_inventory'][0])),
            lambda x:x['prior_book'].update(holdings={'ABSENT':1}),
            lambda x:x['evidence_facts'].update(input_references={'PIT_MEMBERSHIP':{'path':'trap','sha256':'bad'}}))
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                inputs = case()
                mutate(inputs)
                with self.assertRaises(ValueError):
                    prepare(inputs)

    def test_outputs_are_detached_repeatable_and_never_include_a_winner(self):
        inputs = case()
        before = deepcopy(inputs)
        result = prepare(inputs)
        original_id = result['problem_id']
        result['conditional_inventory']['securities'][0]['ticker'] = 'CHANGED'
        result['domain_formula']['prices']['A'] = '999'
        result['authority']['execution_authorized'] = True
        result['all_k_rows'][0]['domain_necessary_reasons'].append('FAKE')
        self.assertEqual(inputs, before)
        again = prepare(inputs)
        self.assertEqual(again['problem_id'], original_id)
        self.assertTrue(all(value is False for value in again['authority'].values()))
        self.assertNotIn('winner', again)
        self.assertNotIn('orders', again)


if __name__ == '__main__':
    unittest.main()
