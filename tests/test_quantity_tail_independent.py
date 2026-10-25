import itertools
import json
import random
import unittest
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from unittest.mock import patch
from backtest import quantity_saved_anchor_tail_tightening as module
from backtest import quantity_saved_anchor_coordinate_fixing as fixing
from test_quantity_saved_anchor_coordinate_fixing import sources, inside
from test_quantity_integer_box_certificate_prototype import fixture, oracle


class IndependentTailTests(unittest.TestCase):
    def test_random_cartesian_full_partition_and_no_improver_lost(self):
        rng = random.Random(2729)
        for _ in range(24):
            args = fixture(); args['fee_bps'] = rng.choice(['0','50','900'])
            args['minimum_cash_buffer'] = rng.choice(['0','1','2'])
            args['training_scenarios'] = [{s:str(F(rng.randint(4,18),10)) for s in 'ABC'} for _ in range(3)]
            source, _ = sources(args)
            source['incumbent'] = rng.choice(oracle(args))[1]
            parent = fixing.build(**source); raw = json.dumps(parent).encode()
            params = dict(fixing_raw=raw, expected_fixing_sha256=sha256(raw).hexdigest(), fixing_sources=source)
            with patch('scipy.optimize.minimize',side_effect=AssertionError('NO SOLVER')):
                c = module.build(**params); module.verify(c, **params)
            box = c['original_box']; regions = [r['box'] for r in c['closed_regions']]+[c['remaining_box']]
            for values in itertools.product(*(range(box[s][0],box[s][1]+1) for s in 'ABC')):
                point = dict(zip('ABC',values))
                self.assertEqual(sum(inside(point,r) for r in regions),1)
            lower = F(c['lower_product'])
            for value, point in oracle(args, box):
                if value>lower:self.assertTrue(inside(point,c['remaining_box']))
                if any(inside(point,r['box']) for r in c['closed_regions']):self.assertLessEqual(value,lower)
            self.assertEqual([r['sid'] for r in c['rows']],sorted(r['sid'] for r in c['rows']))
            self.assertEqual(set(c['remaining_box']),set(args['prices']))
            self.assertLessEqual(c['conditional_bound_calls'],c['conditional_bound_calls_max'])
            self.assertLessEqual(F(c['upper_product']),F(parent['upper_product']))
            for row in c['rows']:
                previous = None; empty_seen = False
                for test in sorted(row['tests'],key=lambda t:t['threshold']):
                    if test['bound']['empty']:empty_seen=True;continue
                    self.assertFalse(empty_seen)
                    upper=F(test['bound']['upper_product'])
                    if previous is not None:self.assertLessEqual(upper,previous)
                    previous=upper

    def test_rehashed_forged_parent_and_tail_types_fail(self):
        source,_=sources(); parent=fixing.build(**source); raw=json.dumps(parent).encode()
        params=dict(fixing_raw=raw,expected_fixing_sha256=sha256(raw).hexdigest(),fixing_sources=source)
        c=module.build(**params)
        for key,value in [('conditional_bound_calls',False),('objective_value_covered',1),('closed_regions',[]),('binding',{}),('upper_product','0')]:
            bad=deepcopy(c);bad[key]=value
            if module.canonical(bad)==module.canonical(c):continue
            with self.assertRaises(ValueError):module.verify(bad,**params)
        forged=deepcopy(parent);forged['remaining_box']['A'][1]=0
        raw=json.dumps(forged).encode()
        with self.assertRaises(ValueError):module.build(**dict(params,fixing_raw=raw,expected_fixing_sha256=sha256(raw).hexdigest()))


if __name__=='__main__':unittest.main()
