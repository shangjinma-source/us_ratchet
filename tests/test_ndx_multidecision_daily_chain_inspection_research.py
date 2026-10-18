"""Independent chain checker: all positions, numeric bases, and tail attacks."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import test_ndx_multidecision_daily_chain_projection_research as fixtures
from backtest import ndx_multidecision_daily_chain_inspection_research as checker
from backtest import ndx_saved_chain_weight_aggregation_research as aggregation


class Tests(unittest.TestCase):
    def test_all_positions_and_independent_decimal_sum(self):
        args = fixtures.fixture()
        day = args['supplement_document']['supplement']['original_raw_bundles_preserved']['control'][1]['document']['result']['daily'][-1]
        day.update(shares={'SID': 1, 'OTHER': 1}, risk={'actual_weights': {'SID': .1, 'OTHER': .8999999999999998}},
                   risk_chains={'SID': 'CHAIN', 'OTHER': 'CHAIN'},
                   risk_chain_observation_dates={'SID': '2026-01-01', 'OTHER': day['session']})
        result = fixtures.m.build_chain_projection(**args, aggregate_saved_weights=aggregation.aggregate_saved_weights)
        before = deepcopy(args)
        with patch.object(fixtures.m, 'build_chain_projection', side_effect=AssertionError('Producer forbidden')), \
             patch.object(aggregation, 'aggregate_saved_weights', side_effect=AssertionError('Aggregation producer forbidden')):
            detail = checker.inspect_chain_projection(projection=result, **args)
        self.assertEqual(detail['day_count'], 2880)
        self.assertEqual(detail['numeric_day_count'], 2772)
        self.assertEqual(detail['undefined_day_count'], 108)
        self.assertEqual(args, before)
        self.assertEqual(result['paths'][17]['rows'][-1]['chain_weights']['CHAIN'],
                         {'numerator': '4999999999999999', 'denominator': '5000000000000000'})

    def test_tail_table_locator_basis_and_authority_attacks(self):
        args = fixtures.fixture()
        original = fixtures.m.build_chain_projection(**args, aggregate_saved_weights=aggregation.aggregate_saved_weights)
        mutations = [
            lambda p: p['paths'][31]['rows'][-1]['chain_weights']['CHAIN'].update(numerator='0'),
            lambda p: p['paths'][8]['rows'][-1].update(basis='ORIGINAL_SAVED_CONTROL_CONTINUOUS_CHAIN_WEIGHTS'),
            lambda p: p['paths'][16]['rows'][-1].update(basis='DERIVED_SUM_OF_SAVED_WHOLE_SID_WEIGHTS_NO_RENORMALIZATION'),
            lambda p: p['paths'][9]['rows'][0].update(chain_weights={}),
            lambda p: p['paths'][9]['rows'][-1]['source_locator'].update(json_pointer='/result/daily/0'),
            lambda p: p.update(normalization_performed=True),
            lambda p: p['references']['diagnostics'].update(sha256='d' * 64),
            lambda p: p['paths'][0].update(rows=[]),
            lambda p: p['counts_by_role_track']['candidate_WHOLE_LOT'].update(numeric=393),
        ]
        for table in range(4):
            mutations.append(lambda p, i=table: p['tables'][i]['rows'].pop())
        for index, mutate in enumerate(mutations):
            with self.subTest(attack=index):
                attacked = deepcopy(original);mutate(attacked)
                with self.assertRaises(ValueError): checker.inspect_chain_projection(projection=attacked, **args)

    def test_missing_held_weights_not_converted_to_cash(self):
        args = fixtures.fixture()
        result = fixtures.m.build_chain_projection(**args, aggregate_saved_weights=aggregation.aggregate_saved_weights)
        args['supplement_document']['supplement']['original_raw_bundles_preserved']['candidate'][9]['document']['result']['daily'][22]['risk'].pop('actual_weights')
        with self.assertRaises((KeyError, ValueError)):
            checker.inspect_chain_projection(projection=result, **args)

    def test_zero_quantity_slot_is_empty_but_positive_risk_is_rejected(self):
        args = fixtures.fixture()
        day = args['supplement_document']['supplement']['original_raw_bundles_preserved']['candidate'][9]['document']['result']['daily'][0]
        day['shares'] = {'SID': 0}
        result = fixtures.m.build_chain_projection(**args, aggregate_saved_weights=aggregation.aggregate_saved_weights)
        self.assertEqual(checker.inspect_chain_projection(projection=result, **args)['undefined_day_count'], 108)
        day['risk']['actual_weights'] = {'SID': .2}
        day['risk_chains'] = {'SID': 'CHAIN'}
        day['risk_chain_observation_dates'] = {'SID': day['session']}
        with self.assertRaises(ValueError):
            checker.inspect_chain_projection(projection=result, **args)


if __name__ == '__main__': unittest.main()
