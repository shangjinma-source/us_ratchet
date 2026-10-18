import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from test_ndx_persisted_fresh_snapshot_sources_research import fixture, encoded, resign
from backtest import ndx_persisted_fresh_snapshot_sources_research as m

class Review(unittest.TestCase):
 def test_receipt_swap_stale_bytes_and_full_scope(self):
  a=fixture(); original=deepcopy(a)
  with patch.object(Path,'read_bytes',side_effect=AssertionError('no filesystem')):
   out=m.inspect_source_bundle(**a)
  self.assertEqual(a,original)
  self.assertEqual(len(out['role_order']),16)
  self.assertNotIn('execution_input',out)
  self.assertTrue(all(out[k] is False for k in m.FLAGS))
  self.assertIn('calendar',{x['role'] for x in out['blockers']})
  a['role_bindings']['nominal_prices']['receipt_reference']=a['role_bindings']['target_nav']['receipt_reference']
  with self.assertRaises(ValueError):m.inspect_source_bundle(**a)
  a=fixture();a['artifacts'][0]['raw_bytes']=a['artifacts'][0]['raw_bytes'].replace(b',123',b',124')
  with self.assertRaises(ValueError):m.inspect_source_bundle(**a)

 def test_self_resigned_scope_and_date_attacks(self):
  for field,value in [('rows_after_decision_date_included',0),('schema_version',True),('decision_date','2026-10-03')]:
   a=fixture(); resign(a,a['role_bindings']['nominal_prices']['receipt_reference'],lambda d:d.update({field:value}))
   with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_source_bundle(**a)
  for raw in (b'Date,Close\n2026-10-02,1\n2026-10-01,2\n',b'Date,Close\n20261001,1\n'):
   with self.assertRaises(ValueError):m.csv_rows(raw,True)

 def test_csv_lexical_integrity(self):
  self.assertEqual(m.csv_rows(b'ticker,name\nMRVL,"Marvell, Inc."\n')[1][0]['name'],'Marvell, Inc.')
  for raw in (b'ticker,name\nMRVL,"unterminated\n',b'ticker,name\nMRVL,"quoted"junk\n'):
   with self.subTest(raw=raw),self.assertRaises((ValueError,m.csv.Error)):
    m.csv_rows(raw)

if __name__=='__main__':unittest.main()
