"""Independent polynomial/necessary-bound checks; no real planner invocation."""
from fractions import Fraction
import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_shard_prepare_v4_20260925 as owner

m = owner.m


class Review(unittest.TestCase):
    def test_all_saved_anchors_and_metadata_without_planner(self):
        documents = {}
        for role, (relative, expected) in m.BOUND.items():
            raw = (m.BASE/relative).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected, role)
            documents[role] = m.yaml.safe_load(raw) if role == 'search' else m.reader.loads(raw)
        for path, expected in ((m.V4_READER, m.V4_READER_SHA), (m.V4_PRODUCER, m.V4_PRODUCER_SHA), (Path(m.planning.__file__), m.PLANNING_SHA), (Path(m.reader.__file__), m.READER_SHA), (Path(m.fitter.__file__), m.FITTER_SHA)):
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected)
        sources = m.fitter._sources()
        with patch.object(m.planning, 'prepare_issuer_shards', side_effect=AssertionError('no planner')), patch.object(m.fitter, 'refit_dynamic_cutoff_weights', side_effect=AssertionError('no fit')), patch.object(m.reader, 'build', side_effect=AssertionError('no audit')):
            groups, parameters, decoded = m.inputs_from_documents(documents, sources)
        self.assertEqual(len(groups), 21)
        self.assertEqual(sum(len(sids) for _, sids in groups), 22)
        self.assertEqual(parameters, m.PARAMETERS)
        self.assertEqual(decoded['returns'].shape, (126, 22))

    def test_polynomial_counts_and_minimum_weight_bound(self):
        coefficients = [1]
        for size in [1]*20+[2]:
            following = [0]*(len(coefficients)+1)
            for degree, count in enumerate(coefficients):
                following[degree] += count
                following[degree+1] += size*count
            coefficients = following
        excluded = sum(coefficients[k] for k in (1, 2, 3, 21))
        self.assertEqual(sum(coefficients[1:]), 3145727)
        self.assertEqual(excluded, 1774)
        self.assertEqual(coefficients[21], 2)
        self.assertEqual(sum(coefficients[4:21])*3, 9431859)
        self.assertEqual(sum((n+999)//1000 for n in coefficients[4:21]), 3153)
        self.assertGreater(21*(Fraction(1, 20)-Fraction(1, 10**9)), 1+Fraction(1, 10**9))

    def test_k20_not_excluded_and_k21_not_omitted(self):
        value = owner.synthetic_counts()
        value['cardinalities'][-2]['necessary_bound_certificates'] = ['made-up']
        value['cardinalities'][-1]['necessary_bound_certificates'] = []
        with self.assertRaises(ValueError): m.validate_counts(value)

    def test_loaded_source_conflict_before_disk(self):
        path, digest = next(iter(m.LOADED.items()))
        with patch.object(m, 'V4_READER_SHA', 'a'*64), patch.object(m.Path, 'read_bytes', side_effect=AssertionError('no read')):
            with self.assertRaises(ValueError):
                m.guard({path: '0'*64 if digest != '0'*64 else '1'*64})


if __name__ == '__main__':
    unittest.main()
