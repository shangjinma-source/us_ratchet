"""All filesystem inputs are synthetic temporary publications; no actual audits."""
import copy,json,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from scripts import ndx_persisted_candidate_calendar_independent_readback_20261003 as m
from test_ndx_persisted_candidate_calendar_20261003 import file_fixture,w

def staged(root,clock='2026-11-02T21:02:00+00:00'):
 bindings=file_fixture(root)
 with ExitStack()as stack:
  for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
  stack.enter_context(patch.object(w,'now',return_value=clock));out=w.run(execute=True)
 return dict(PARENT=bindings['OUTPUT'],OUTPUT=root/'readback',RESULT_SHA=out['result_reference']['sha256'],PUBLICATION_SHA=out['publication_reference']['sha256'],**{k:bindings[k]for k in ('HISTORY_BOUND','CAPTURE_BOUND','OBSERVATION_BOUND')})
def patched(values):
 stack=ExitStack()
 for k,v in values.items():stack.enter_context(patch.object(m,k,v))
 return stack

class Tests(unittest.TestCase):
 def test_full_physical_closure_timely_and_late(self):
  for clock,expected in [('2026-11-02T21:02:00+00:00','CONDITIONAL_CALENDAR_PREREQUISITES_ONLY'),('2026-11-04T21:02:00+00:00','BLOCKED')]:
   with tempfile.TemporaryDirectory()as td:
    settings=staged(Path(td),clock)
    with patched(settings):
     ref=m.readback(execute=True);report=json.loads(Path(ref['path']).read_bytes());self.assertEqual(report['counts']['status'],expected);self.assertEqual(report['counts']['typed_row_count'],67);self.assertFalse(report['candidate_seal_allowed']);self.assertFalse(report['producer_or_core_called'])
     with self.assertRaisesRegex(ValueError,'Create-only'):m.readback(execute=True)
 def test_future_anchors_before_any_io(self):
  with patch.object(m,'RESULT_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):m.readback(execute=True)
 def test_resigned_result_cannot_change_month_or_source_closure(self):
  for change in ('month','sources','count'):
   with tempfile.TemporaryDirectory()as td:
    settings=staged(Path(td));parent=settings['PARENT'];r=json.loads((parent/'result.json').read_bytes());pub=json.loads((parent/'publication.json').read_bytes())
    if change=='month':r['evidence']['monthly_coordinate']=False
    elif change=='sources':r['source_hashes']={}
    else:r['evidence']['selected_existing_row']['sequence']=67.0
    (parent/'result.json').write_bytes(m.enc(r));settings['RESULT_SHA']=m.sha((parent/'result.json').read_bytes());pub['result_reference']['sha256']=settings['RESULT_SHA'];(parent/'publication.json').write_bytes(m.enc(pub));settings['PUBLICATION_SHA']=m.sha((parent/'publication.json').read_bytes())
    with patched(settings):
     with self.assertRaises(ValueError):m.readback(execute=True)
     self.assertTrue((settings['OUTPUT']/'failure.json').exists())
 def test_postwrite_source_failure_preserved(self):
  with tempfile.TemporaryDirectory()as td:
   settings=staged(Path(td));original=m.guard
   def guard(s):
    if (settings['OUTPUT']/'independent_readback.json').exists():(settings['PARENT']/'failure.json').write_text('{}')
    return original(s)
   with patched(settings),patch.object(m,'guard',side_effect=guard):
    with self.assertRaisesRegex(ValueError,'Failed'):m.readback(execute=True)
    self.assertTrue((settings['OUTPUT']/'failure.json').exists());self.assertTrue((settings['OUTPUT']/'independent_readback.json').exists())
 def test_source_association_and_clock_not_self_certified(self):
  with tempfile.TemporaryDirectory()as td:
   settings=staged(Path(td));parent=settings['PARENT'];r=json.loads((parent/'result.json').read_bytes());pub=json.loads((parent/'publication.json').read_bytes());r['evaluation_at_utc']='2026-11-02T20:00:00+00:00';(parent/'result.json').write_bytes(m.enc(r));settings['RESULT_SHA']=m.sha((parent/'result.json').read_bytes());pub['result_reference']['sha256']=settings['RESULT_SHA'];(parent/'publication.json').write_bytes(m.enc(pub));settings['PUBLICATION_SHA']=m.sha((parent/'publication.json').read_bytes())
   with patched(settings):
    with self.assertRaisesRegex(ValueError,'before start'):m.readback(execute=True)
if __name__=='__main__':unittest.main()
