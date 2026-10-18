"""All filesystem inputs are synthetic temporary publications; no actual audits."""
import copy,json,tempfile,unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from scripts import ndx_first_persisted_candidate_calendar_independent_readback_20261003 as m
from test_ndx_first_persisted_candidate_calendar_20261003 import file_fixture,w

def staged(root,clock='2026-10-02T20:02:00+00:00'):
 bindings=file_fixture(root)
 with ExitStack()as stack:
  for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
  stack.enter_context(patch.object(w,'now',return_value=clock));out=w.run(execute=True)
 return dict(ROOT=bindings['ROOT'],PARENT=bindings['OUTPUT'],OUTPUT=root/'readback',RESULT_SHA=out['result_reference']['sha256'],PUBLICATION_SHA=out['publication_reference']['sha256'],**{k:bindings[k]for k in ('GENESIS_BOUND','HISTORY_BOUND','CAPTURE_BOUND','OBSERVATION_BOUND')})
def patched(values):
 stack=ExitStack()
 for k,v in values.items():stack.enter_context(patch.object(m,k,v))
 return stack

class Tests(unittest.TestCase):
 def test_full_physical_closure_timely_and_late(self):
  for clock,expected in [('2026-10-02T20:02:00+00:00','CONDITIONAL_CALENDAR_PREREQUISITES_ONLY'),('2026-10-06T20:02:00+00:00','BLOCKED')]:
   with tempfile.TemporaryDirectory()as td:
    settings=staged(Path(td),clock)
    with patched(settings):
     ref=m.readback(execute=True);report=json.loads(Path(ref['path']).read_bytes());self.assertEqual(report['counts']['status'],expected);self.assertEqual(report['counts']['typed_row_count'],66);self.assertFalse(report['candidate_seal_allowed']);self.assertFalse(report['producer_or_core_called'])
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
    else:r['evidence']['selected_existing_row']['sequence']=66.0
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
   settings=staged(Path(td));parent=settings['PARENT'];r=json.loads((parent/'result.json').read_bytes());pub=json.loads((parent/'publication.json').read_bytes());r['evaluation_at_utc']='2026-10-02T19:00:00+00:00';(parent/'result.json').write_bytes(m.enc(r));settings['RESULT_SHA']=m.sha((parent/'result.json').read_bytes());pub['result_reference']['sha256']=settings['RESULT_SHA'];(parent/'publication.json').write_bytes(m.enc(pub));settings['PUBLICATION_SHA']=m.sha((parent/'publication.json').read_bytes())
   with patched(settings):
    with self.assertRaisesRegex(ValueError,'before start'):m.readback(execute=True)
 def test_live_bytes_never_opened_and_original_claims_preserved(self):
  with tempfile.TemporaryDirectory()as td:
   settings=staged(Path(td));original=Path.read_bytes
   def safe_read(path):
    if path.parent==Path(td)/'data/cache':raise AssertionError('Live bytes opened')
    return original(path)
   with patched(settings),patch.object(Path,'read_bytes',safe_read):
    ref=m.readback(execute=True);report=json.loads(original(Path(ref['path'])));self.assertFalse(any(m.is_live(p)for p in report['source_hashes']))
    result=json.loads(original(settings['PARENT']/'result.json'));self.assertEqual(len(result['snapshot_equivalence_bridge']['rows']),2);self.assertEqual(sum(m.is_live(p)for p in result['original_source_claims_preserved']),2)
 def test_bridge_wrong_root_third_live_and_wrong_role(self):
  with tempfile.TemporaryDirectory()as td:
   settings=staged(Path(td));rr=settings['CAPTURE_BOUND'];capture={k:dict(path=v[0],sha256=v[1])for k,v in rr.items()}
   for role,key in (('reference','document'),('publication_reference','publication'),('readback_reference','readback')):capture[key]=json.loads(Path(rr[role][0]).read_bytes())
   with patched(settings):
    m.bridge(capture)
    for mode in ('root','role','third','missing','hash'):
     c=copy.deepcopy(capture);d=c['document'];audit=c['readback']
     if mode=='root':d['input_references']['current_QQQ']['path']=str(Path(td)/'other/data/cache/QQQ.csv')
     elif mode=='role':d['captured_artifacts']['QQQ']=copy.deepcopy(d['captured_artifacts']['SPY'])
     elif mode=='missing':del audit['source_hashes'][d['captured_artifacts']['QQQ']['path']]
     elif mode=='hash':d['input_references']['current_QQQ']['sha256']='a'*64
     else:
      for table in (d['source_hashes'],c['publication']['source_hashes'],audit['capture_original_source_hashes_preserved']):table[str(Path(td)/'data/cache/DIA.csv')]='a'*64
     with self.subTest(mode=mode),self.assertRaises(ValueError):m.bridge(c)
 def test_late_failed_unknown_observation_keeps_first_month(self):
  with tempfile.TemporaryDirectory()as td:
   settings=staged(Path(td));parent=settings['PARENT'];result=json.loads((parent/'result.json').read_bytes());pub=json.loads((parent/'publication.json').read_bytes());started=json.loads((parent/'started.json').read_bytes());docs={};refs=result['input_references']
   for kind,rr in refs.items():
    env=copy.deepcopy(rr);pairs=(('payload_reference','payload'),('receipt_reference','receipt'),('audit_reference','audit'))if kind=='observation'else(('reference','document'),('publication_reference','publication'),('readback_reference','readback'))
    for role,key in pairs:env[key]=json.loads(Path(rr[role]['path']).read_bytes())
    if kind=='genesis':env['baseline_references']=copy.deepcopy(env['readback']['baseline_references'])
    docs[kind]=env
   tz=Path(docs['capture']['document']['captured_artifacts']['tzif']['path']).read_bytes();resultref=pub['result_reference'];args=dict(docs=docs,tz=tz,result=result,pub=pub,started=started,refs=refs,result_ref=resultref,started_ref=result['started_reference'],base=result['source_hashes'])
   with patched(settings):
    for status in ('FAILED','UNKNOWN'):
     x=copy.deepcopy(args);h=x['docs']['history']['document'];h['known_typed_rows'][-1]['seal_status']=status;e=x['result']['evidence'];e['known_typed_rows_preserved'][-1]['seal_status']=status;e['selected_existing_row']['seal_status']=status;e['original_seal_status']=status;e['reasons']=['PRIOR_SEAL_STATE_DOES_NOT_AUTHORIZE_NEW_ATTEMPT'];e['status']='BLOCKED';e['calendar_prerequisites_conditionally_satisfied']=False
     self.assertTrue(m.inspect(**x)['monthly_coordinate'])
    x=copy.deepcopy(args);o=x['docs']['observation'];h=x['docs']['history']['document'];late='2026-10-05T14:00:00+00:00';o['payload']['writer_completed_at_utc']=late;o['receipt']['publication_check_at_utc']=late
    for obj in (o['payload'],o['receipt']):obj['timing_classification']='LATE_OBSERVATION'
    o['audit']['counts']['timing_classification']='LATE_OBSERVATION';entry=h['observations'][0];entry['timing_classification']='LATE_OBSERVATION';entry['payload_timing_classification']='LATE_OBSERVATION';e=x['result']['evidence'];e['selected_compact_entry']=copy.deepcopy(entry);e['timing'].update(writer_end=late,publication_check=late,seal_evaluation_at_utc=late);x['result']['evaluation_at_utc']=late;e.update(status='BLOCKED',calendar_prerequisites_conditionally_satisfied=False,reasons=['PERSISTED_OBSERVATION_PUBLICATION_CHECK_LATE','SEAL_EVALUATION_OUTSIDE_CONSERVATIVE_WINDOW'])
    out=m.inspect(**x);self.assertTrue(out['monthly_coordinate']);self.assertEqual(out['status'],'BLOCKED')
if __name__=='__main__':unittest.main()
