import json
import sys
import unittest
from fractions import Fraction as F
from backtest.research_exact_fraction_json import dumps, loads, ENCODING, TAG


class ExactFractionJsonTests(unittest.TestCase):
    def test_beyond_decimal_limit_roundtrip_without_global_change(self):
        limit = sys.get_int_max_str_digits()
        value = F(10**5000 + 7, 10**5001 + 19)
        encoded = dumps({'value': value})
        self.assertEqual(json.loads(encoded)['encoding'], ENCODING)
        self.assertEqual(loads(encoded), {'value': value})
        self.assertEqual(sys.get_int_max_str_digits(), limit)
        self.assertIn('0x', encoded)

    def test_nested_sign_zero_and_strict_version(self):
        value = {'rows': [F(-7, 13), {'zero': F(0), 'integer_fraction': F(3), 'large_negative': F(-(10**5000+1), 17)}], 'plain': [None, True, 3, 'text']}
        self.assertEqual(loads(dumps(value)), value)
        with self.assertRaises(ValueError):loads('{"encoding":"wrong","payload":0}')
        with self.assertRaises(ValueError):dumps({TAG: 'collision'})
        invalid = {'encoding': ENCODING, 'payload': {TAG: {'numerator':'-0x1','denominator':'-0x3'}}}
        with self.assertRaises(ValueError):loads(json.dumps(invalid))


if __name__=='__main__':unittest.main()
