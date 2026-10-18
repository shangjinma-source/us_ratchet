"""Independent tiny alignment oracle; no actual NAV or official FX rows."""
from copy import deepcopy
from decimal import Context,Inexact,localcontext
from fractions import Fraction
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nav_fx_fixture',ROOT/'tests/test_ndx_nav_usd_observation_alignment_research.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);m=f.m

class Review(unittest.TestCase):
 def test_independent_linear_oracle_all_modes_with_missing_dates(self):
  a=f.fixture();a['session_dates']=['2026-03-19','2026-03-20','2026-03-21','2026-03-23','2026-03-24','2026-03-25','2026-03-26']
  out=m.align_nav_usd_observations(**a)
  for row in out['rows']:
   day=row['session'];nav=[r for r in a['nav_rows'] if r['date']<=day];same=[r for r in a['fx_rows'] if r['date']==day and r['status']=='REPORTED_RATE'];back=[r for r in a['fx_rows'] if r['date']<=day and r['status']=='REPORTED_RATE']
   for mode,values in zip(m.MODES,(same,back)):
    expected=None if not nav or not values else Fraction(nav[-1]['nav_cny_decimal'])/Fraction(values[-1]['rate_decimal'])
    actual=row['conversions'][mode]['nav_usd_exact'];self.assertEqual(None if actual is None else Fraction(actual),expected)
   self.assertFalse(row['nav_date_fx_used_for_conversion'])
  self.assertEqual(out['mode_missing_counts'][m.MODES[0]],4);self.assertEqual(out['mode_missing_counts'][m.MODES[1]],1)

 def test_all_nd_no_future_substitution_and_preserved_receipt_extras(self):
  a=f.fixture();a['session_dates']=['2026-03-20','2026-03-23','2026-03-24']
  for row in a['fx_rows'][:3]:row.update(status='NOT_AVAILABLE_ND',rate_decimal=None,rate_literal='ND')
  a['fx_context']['actual_receipt']={'received':'2026-10-02','late':True};before=deepcopy(a);out=m.align_nav_usd_observations(**a)
  self.assertEqual(a,before);self.assertEqual(out['fx_context_preserved'],a['fx_context']);self.assertEqual(len(out['rows'][-1]['session_fx']['skipped_nd_rows']),3)
  for row in out['rows']:
   self.assertIsNone(row['session_fx']['backward_valid'])
   self.assertTrue(all(x['nav_usd_exact'] is None for x in row['conversions'].values()))
  self.assertEqual(out['fx_rows_preserved'],a['fx_rows'])

 def test_nonterminating_ratio_context_and_no_return_authority(self):
  a=f.fixture();a['nav_rows'][0]['nav_cny_decimal']='1.0000000000000000000000001';a['fx_rows'][0].update(rate_literal='3',rate_decimal='3')
  normal=m.align_nav_usd_observations(**a);ctx=Context(prec=1);ctx.traps[Inexact]=True
  with localcontext(ctx):out=m.align_nav_usd_observations(**a)
  self.assertEqual(out,normal);self.assertEqual(Fraction(out['rows'][0]['conversions'][m.MODES[0]]['nav_usd_exact']),Fraction(a['nav_rows'][0]['nav_cny_decimal'])/3)
  self.assertTrue(all(out[k] is False for k in m.FLAGS));self.assertEqual(out['modes'],list(m.MODES))

 def test_units_known_availability_false_boolean_and_hash_conflicts(self):
  for mutate in (lambda a:a['fx_context'].update(historical_available_at_verified=0),lambda a:a['fx_context'].update(rate_direction='USD_PER_CNY'),lambda a:a['nav_rows'][0].update(available_at='2026-03-20T12:00:00Z'),lambda a:a['fx_reference'].update(path='nav.csv',sha256='b'*64),lambda a:a['fx_rows'][0].update(rate_literal='7.01'),lambda a:a['fx_context'].update(limitations=[])):
   a=f.fixture();mutate(a)
   with self.assertRaises(ValueError):m.align_nav_usd_observations(**a)

if __name__=='__main__':unittest.main()
