"""Independent synthetic counterexamples; no saved source projection."""
from copy import deepcopy
from decimal import localcontext, Inexact
from fractions import Fraction
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
purefixture=load('history_benchmark_fixture','tests/test_ndx_long_window_benchmark_requirements_research.py')
wrapperfixture=load('history_benchmark_wrapper_fixture','tests/test_ndx_bulk_long_window_benchmark_requirements_20261003.py')
c=purefixture.core;w=wrapperfixture.m

class Review(unittest.TestCase):
 def test_all_nav_rows_independent_backward_oracle_and_boundaries(self):
  a=purefixture.fixture();days=a['reference_calendar']['dates'];nav=a['nav_metadata']['rows']
  a['nav_metadata']['rows']=[r for i,r in enumerate(nav) if i>=3 and i%7==0]
  for i,r in enumerate(a['nav_metadata']['rows']):r['row_index']=i
  out=c.prepare_benchmark_requirements(**a)
  for day,row in zip(days,out['nav_date_mappings']):
   eligible=[r for r in a['nav_metadata']['rows'] if r['date']<=day];expected=eligible[-1] if eligible else None
   self.assertEqual(row['nav_date'],None if expected is None else expected['date'])
   self.assertIsNone(row['available_at']);self.assertIs(row['publication_time_known'],False)
   if expected:self.assertEqual(row['mapped_row_reference']['row_index'],expected['row_index'])
  self.assertEqual(out['training_return_end_dates'],days[1:127]);self.assertEqual(out['evaluation_return_end_dates'],days[127:253])
  self.assertEqual(out['training_freeze_close_date'],days[126]);self.assertEqual(out['evaluation_initial_close_date'],days[126])

 def test_removed_freeze_rows_do_not_shorten_calendar_or_extend_identity(self):
  a=purefixture.fixture();days=a['reference_calendar']['dates']
  for t in c.TICKERS:
   a['stock_metadata'][t]['observation_rows']=[r for i,r in enumerate(a['stock_metadata'][t]['observation_rows']) if i not in (125,126,127)]
  out=c.prepare_benchmark_requirements(**a)
  for row in out['stock_requirements']:
   self.assertEqual(row['missing_observation_dates'],days[125:128]);self.assertEqual(len(row['requirements']),253)
   self.assertTrue(row['identity_and_risk_window_extension_not_automatic'])
   self.assertTrue(all(row[k] is False for k in c.FLAGS))

 def test_literal_weights_context_and_full_sources_unchanged(self):
  a=purefixture.fixture();a['original_control']['securities'][0]['target_weight']='0.123456789123456789123456789';before=deepcopy(a)
  with localcontext() as ctx:
   ctx.prec=2;ctx.traps[Inexact]=True;out=c.prepare_benchmark_requirements(**a)
  self.assertEqual(a,before);self.assertEqual(Fraction(out['original_target_weight_sum_exact']),sum(Fraction(str(r['target_weight'])) for r in a['original_control']['securities']))
  self.assertEqual(out['original_control_preserved'],a['original_control']);self.assertFalse(out['weights_normalized'])
  for mutate in (lambda x:x['fx_metadata'].update(bound=True),lambda x:x['nav_metadata'].update(publication_time_known=0),lambda x:x['stock_metadata']['TSM']['identity_evidence'].append(dict(path='calendar',sha256='b'*64))):
   b=deepcopy(a);mutate(b)
   with self.assertRaises(ValueError):c.prepare_benchmark_requirements(**b)

 def test_wrapper_receipt_sidecar_nav_cross_reference_attacks(self):
  docs,refs=wrapperfixture.fixture()
  for mutate in (lambda x:x['asml_publication']['identity_reference'].update(sha256='f'*64),lambda x:x['nav_snapshot']['immutable_copies']['nav.csv'].update(path='wrong'),lambda x:x['receipt_GOOG'].update(request_url='https://example/chart/GOOGL'),lambda x:x['wiring']['rows'][0]['coordinate'].update(issuer_id='other')):
   d=deepcopy(docs);mutate(d)
   with self.assertRaises(ValueError):w.project_inputs(d,refs)
  d=deepcopy(docs);next(r for r in d['readback']['rows'] if r['ticker']=='AAPL')['observation']['rows'][0]['missing_fields']=['close']
  a=w.project_inputs(d,refs);self.assertEqual(len(a['reference_calendar']['dates']),253)
  self.assertEqual(a['stock_metadata']['TSM']['complete_identity_sidecar'],docs['tsm']);self.assertEqual(a['stock_metadata']['ASML']['returned_events'],{'dividends':{'unchanged':1}})
  self.assertFalse(a['original_control']['new_execution_contract_frozen']);self.assertFalse(a['fx_metadata']['bound'])

 def test_wrapper_source_drift_and_orphan_fail_closed(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'source.py';p.write_bytes(b'new')
   with patch.object(w,'SOURCE',p),patch.object(w,'LOADED_SHA',w.sha(b'old')):
    with self.assertRaises(ValueError):w.guard({})
   out=Path(tmp)/'out';out.mkdir();(out/'failure.json').write_text('{}')
   with patch.object(w,'OUTPUT',out),patch.object(w,'load_inputs') as call:
    with self.assertRaises(ValueError):w.run()
    call.assert_not_called()

if __name__=='__main__':unittest.main()
