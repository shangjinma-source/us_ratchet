"""Independent attacks; synthetic candidate generation is not the numeric oracle."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from test_ndx_multidecision_target_inputs_independent_readback_20261003 import case
from backtest import ndx_multidecision_target_inputs_inspection_research as m
from scripts import ndx_multidecision_target_inputs_independent_readback_20261003 as r


class Review(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.args = case()

    def test_independent_fraction_adjacency_and_missing_neighbors(self):
        a = self.args
        days = a['target']['session_dates']
        for mode in a['target']['modes']:
            independently_expected = []
            for day in days:
                nav = [x for x in a['nav_rows'] if x['date'] <= day][-1]
                choices = [x for x in a['fx_rows'] if
                           (x['date'] == day if mode['mode'].startswith('STRICT')
                            else x['date'] <= day and x['status'] == 'REPORTED_RATE')]
                fx = choices[-1] if choices else None
                independently_expected.append(None if fx is None or fx['rate_decimal'] is None
                                              else Fraction(nav['nav_cny_decimal']) / Fraction(fx['rate_decimal']))
            for i, slot in enumerate(mode['return_slots']):
                left, right = independently_expected[i:i+2]
                expected = None if left is None or right is None else str(right / left - 1)
                self.assertEqual(slot['return_exact'], expected)
            self.assertEqual(len(mode['decisions']), 6)
            self.assertTrue(all(len(x['windows']) == 13 for x in mode['decisions']))
        self.assertEqual(m.inspect_target_inputs(**a)['status'], 'PASS')

    def test_resigned_missing_mode_and_authority_attacks(self):
        def fill_missing(a):
            slot = next(x for x in a['target']['modes'][0]['return_slots'] if x['return_exact'] is None)
            slot.update(return_exact='0', return_float=0., status='CONDITIONAL_NUMERIC_RETURN')
        for mutate in (fill_missing,
                       lambda a: a['target']['modes'].reverse(),
                       lambda a: a['target'].update(point_in_time_verified=0),
                       lambda a: a['alignment']['rows'][0].update(nav_date_fx_used_for_conversion=True),
                       lambda a: a['target']['modes'][1]['decisions'][0]['windows'][0].update(window_index=False)):
            a = deepcopy(self.args); mutate(a)
            for key in ('alignment', 'target'):
                a[key]['content_sha256'] = m.sha(m.enc({k:v for k,v in a[key].items() if k != 'content_sha256'}))
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                m.inspect_target_inputs(**a)

    def test_same_consumed_bytes_and_final_started_drift(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp)/'source'; source.write_bytes(b'original')
            ref = {'path':str(source), 'sha256':m.sha(b'original')}
            with patch.object(Path, 'read_bytes', return_value=b'changed'):
                with self.assertRaises(ValueError): r.take(ref, {})
            out = Path(tmp)/'out'
            calls = []
            def guard(sources):
                calls.append(1)
                if len(calls) == 2: (out/'started.json').write_bytes(b'changed after report')
            with patch.object(r, 'OUTPUT', out), patch.multiple(r, INDEX_SHA='a'*64, PUBLICATION_SHA='b'*64, PRODUCER_SHA='c'*64), patch.object(r, 'load_inputs', return_value=(self.args,{},m,ref,ref,{})), patch.object(r, 'guard', side_effect=guard), patch.object(r, 'parent_namespace'), patch('shutil.disk_usage', return_value=type('Disk',(),{'free':10**12})()):
                with self.assertRaisesRegex(ValueError, 'Final report drift'): r.readback(execute=True)
                self.assertTrue((out/'failure.json').exists())
                self.assertTrue((out/'independent_readback.json').exists())
                with self.assertRaisesRegex(ValueError, 'no retry'): r.readback(execute=True)


if __name__ == '__main__': unittest.main()
