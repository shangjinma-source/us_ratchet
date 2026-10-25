import itertools
import random
import unittest
from copy import deepcopy
from fractions import Fraction
from unittest.mock import patch
from backtest import quantity_saved_anchor_coordinate_fixing as module
from test_quantity_saved_anchor_coordinate_fixing import sources, inside
from test_quantity_integer_box_certificate_prototype import fixture, oracle


class IndependentCoordinateFixing(unittest.TestCase):
    def test_seeded_cartesian_coverage_and_strict_improvers(self):
        rng = random.Random(9817)
        for index in range(24):
            args = fixture()
            args['fee_bps'] = rng.choice(['0', '50', '9999'])
            args['minimum_cash_buffer'] = rng.choice(['0', '1', '2'])
            args['training_scenarios'] = [{s: str(Fraction(rng.randint(3, 18), 10)) for s in 'ABC'} for _ in range(3)]
            src, anchor = sources(args)
            feasible = oracle(args, anchor['box'])
            src['incumbent'] = deepcopy(rng.choice(feasible)[1])
            with patch('scipy.optimize.minimize', side_effect=AssertionError('NO SOLVER')):
                certificate = module.build(**src)
                module.verify(certificate, **src)
            self.assertEqual([r['sid'] for r in certificate['rows']], sorted(r['sid'] for r in certificate['rows']))
            self.assertEqual(set(certificate['remaining_box']), set(args['prices']))
            regions = [r['box'] for r in certificate['closed_regions']] + [certificate['remaining_box']]
            box = anchor['box']
            for values in itertools.product(*(range(box[s][0], box[s][1]+1) for s in 'ABC')):
                point = dict(zip('ABC', values))
                self.assertEqual(sum(inside(point, region) for region in regions), 1, index)
            lower = Fraction(certificate['lower_product'])
            for value, point in feasible:
                if value > lower:
                    self.assertTrue(inside(point, certificate['remaining_box']))
                if any(inside(point, r['box']) for r in certificate['closed_regions']):
                    self.assertLessEqual(value, lower)
            self.assertGreaterEqual(Fraction(certificate['upper_product']), max(v for v, _ in feasible))

    def test_empty_slab_and_nonzero_lower_preserved(self):
        args = fixture(); args['fee_bps'] = '0'
        src, _ = sources(args, dict(A=[1, 3], B=[0, 2], C=[0, 2]))
        certificate = module.build(**src)
        empty = [r for r in certificate['rows'] if r['bound']['empty']]
        self.assertTrue(empty)
        for row in empty:
            self.assertFalse(oracle(args, row['tested_tail']))
            self.assertTrue(row['fix_lower'])
        self.assertEqual(certificate['remaining_box']['A'][0], 1)

    def test_order_binding_types_and_forged_scope_rejected(self):
        src, _ = sources()
        certificate = module.build(**src)
        for key, value in [('solver_calls', False), ('fixed_coordinate_count', False),
                           ('rows', list(reversed(certificate['rows']))),
                           ('closed_regions', []), ('scope', 'GLOBAL_OPTIMUM')]:
            changed = deepcopy(certificate); changed[key] = value
            if module.canonical(changed) == module.canonical(certificate):
                continue
            with self.assertRaises(ValueError): module.verify(changed, **src)
        changed = deepcopy(certificate); changed['binding']['incumbent'] = {'A': 1}
        with self.assertRaises(ValueError): module.verify(changed, **src)
        for field in ['expected_anchor_sha256', 'expected_anchor_binding_sha256']:
            with self.assertRaises(ValueError): module.build(**dict(src, **{field: '0'*64}))


if __name__ == '__main__': unittest.main()
