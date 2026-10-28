import sys,importlib.util,unittest,json,subprocess,base64,inspect,os
from unittest.mock import patch
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from hashlib import sha256
from copy import deepcopy
sys.path.insert(0,str(Path('.').resolve()))
STAGE=Path(os.environ.get('NEWS_FOLLOWUP_STAGE_DIRECTORY','.'))
for name in ['strategy_followup_historical_reader_v1','strategy_followup_frontier_source_v1']:
 spec=importlib.util.spec_from_file_location('data.'+name,(STAGE/'data')/(name+'.py'));module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
h=sys.modules['data.strategy_followup_historical_reader_v1'];r=module
class Checks(unittest.TestCase):
 def sealed(self,x):return dict(x,review_id=sha256(r.canonical(x)).hexdigest())
 def test_exact_and_explicit_schema(self):
  old=self.sealed({'a':1});current=self.sealed({'a':1,'future_notice_scope':{'S':{'reviewed':True}}})
  self.assertEqual(r.compare_source_review(old,current,r.LEGACY_SOURCE_REVIEW)['added_future_notice_scope'],current['future_notice_scope'])
  self.assertEqual(r.compare_source_review(current,current,'unknown')['mode'],'EXACT_CURRENT_INDEPENDENT_REVIEW')
 def test_no_broad_compatibility(self):
  old=self.sealed({'a':1});current=self.sealed({'a':1,'future_notice_scope':{}})
  for original,new,pin in [(old,current,'unknown'),(dict(old,review_id='0'*64),current,r.LEGACY_SOURCE_REVIEW),(old,self.sealed({'a':2,'future_notice_scope':{}}),r.LEGACY_SOURCE_REVIEW),(old,self.sealed({'a':1,'future_notice_scope':{},'x':1}),r.LEGACY_SOURCE_REVIEW),(self.sealed({'a':1,'future_notice_scope':{'old':1}}),current,r.LEGACY_SOURCE_REVIEW)]:
   with self.assertRaises(ValueError):r.compare_source_review(original,new,pin)
 def test_archived_code_wins_live_mutation(self):
  with TemporaryDirectory() as d:
   root=Path(d);p=root/h.ENTRY;p.parent.mkdir(parents=True);p.write_text('raise RuntimeError("LIVE")')
   self.assertEqual(h.code_closure(root,{h.ENTRY:b'x=1'},{}),{h.ENTRY:b'x=1'})
 def test_missing_dependency_no_live_fallback(self):
  with TemporaryDirectory() as d:
   root=Path(d);p=root/'core/unpinned.py';p.parent.mkdir();p.write_text('x=1')
   with self.assertRaisesRegex(ValueError,'DEPENDENCY_UNPINNED'):h.code_closure(root,{h.ENTRY:b'import core.unpinned'}, {})
 def test_pinned_dependency_tamper_rejected(self):
  with TemporaryDirectory() as d:
   root=Path(d);p=root/'core/a.py';p.parent.mkdir();p.write_text('x=2')
   with self.assertRaisesRegex(ValueError,'BYTES_UNAVAILABLE'):h.code_closure(root,{h.ENTRY:b'import core.a'},{'core/a.py':sha256(b'x=1').hexdigest()})
 def test_paths_reject_escape(self):
  with TemporaryDirectory() as d:
   for name in ['../outside',str(Path(d).resolve()/'absolute')]:
    with self.assertRaisesRegex(ValueError,'PATH_ESCAPE'):h.safe_path(Path(d),name)
 def test_worker_guards_and_original_time(self):
  self.assertIn("datetime.fromisoformat(request.pop('now'))",h.WORKER)
  self.assertIn('clock=lambda:now',h.WORKER)
  self.assertIn('HISTORICAL_WRITE_FORBIDDEN',h.WORKER);self.assertIn('HISTORICAL_NETWORK_OR_PROCESS_FORBIDDEN',h.WORKER)
 def test_scoped_schema_requires_actual_old_scope_and_double_pin(self):
  scope={'S':{'ignored_future_items':[{'id':'original'}]}}
  old=self.sealed({'a':1,'future_notice_scope':scope});current=self.sealed({'a':1,'future_notice_scope':{'S':{'new':'checked'}}})
  self.assertIn('REPRODUCED',r.compare_source_review(old,current,r.SCOPED_SOURCE_REVIEW,r.SCOPED_LEAF,scope)['mode'])
  for source,leaf,observed,original in [('unknown',r.SCOPED_LEAF,scope,old),(r.SCOPED_SOURCE_REVIEW,'unknown',scope,old),(r.SCOPED_SOURCE_REVIEW,r.SCOPED_LEAF,{},old),(r.SCOPED_SOURCE_REVIEW,r.SCOPED_LEAF,scope,self.sealed({'a':1,'future_notice_scope':{'S':{'tampered':True}}}))]:
   with self.assertRaises(ValueError):r.compare_source_review(original,current,source,leaf,observed)
 def test_independent_adapters_match_existing_checks(self):
  import data.saved_frontier_capture_review_v1 as packets
  import data.saved_frontier_source_reader_v1 as reader
  expected=inspect.getsource(packets.review_supplement_packets).replace('def review_supplement_packets(*,','def _review_packets(*, first_window,').replace('    from data.saved_frontier_first_window_v1 import review_first_window','    review_first_window=first_window')
  self.assertEqual(inspect.getsource(h._review_packets).strip(),expected.strip())
  expected=inspect.getsource(reader.read_frontier_capture).replace('def read_frontier_capture(*,','def _read_capture(*, packet_reviewer,').replace('review_supplement_packets(root=root','packet_reviewer(root=root')
  self.assertEqual(inspect.getsource(h._read_capture).strip(),expected.strip())
 def test_archived_configuration_byte_tamper_before_worker(self):
  with TemporaryDirectory() as d,patch.object(h,'historical_pins',return_value=({},{})),patch.object(h.subprocess,'run',side_effect=AssertionError('must not run')) as run:
   with self.assertRaisesRegex(ValueError,'ARCHIVED_CODE_CHANGED'):
    h.read_historical_frontier_capture(root=d,preparation_reference={},archived_files={h.ENTRY:b'changed'},prepared={'configurations':{'S':{'source_pins':[{'path':h.ENTRY,'sha256':sha256(b'original').hexdigest()}]}}},capture={},state={},target={},proposal={},risk_state=None,now=datetime.now(timezone.utc))
   run.assert_not_called()
 def test_archive_collection_survives_original_sources_removed(self):
  spec=importlib.util.spec_from_file_location('archive_candidate',(STAGE/'scripts/archive_saved_daily_followups_v4.py'));archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
  with TemporaryDirectory() as d:
   root=Path(d);(root/'core').mkdir();original=b'old-code';supplement=b'pinned-dependency';prep=b'{}'
   source=root/'core/dependency.py';source.write_bytes(supplement);manifest=root/'prep.json';manifest.write_bytes(prep)
   pins={'core/old.py':sha256(original).hexdigest(),'core/dependency.py':sha256(supplement).hexdigest()}
   checked={'historical_provenance':{'materialized_sha256':pins,'preparation_chain':{'prep.json':sha256(prep).hexdigest()}}}
   bundle=archive.collect_historical_sources(root=root,checked=checked,original_sources={'core/old.py':original})
   saved=root/'archive';saved.mkdir()
   for name,body in bundle.items():p=saved/name;p.parent.mkdir(exist_ok=True);p.write_bytes(body)
   source.unlink();manifest.unlink()
   for name,digest in pins.items():self.assertEqual(sha256((saved/'historical-materialized'/(digest+'.bin')).read_bytes()).hexdigest(),digest)
   self.assertEqual((saved/'historical-preparations'/(sha256(prep).hexdigest()+'.json')).read_bytes(),prep)
   source.write_bytes(b'tampered');manifest.write_bytes(prep)
   with self.assertRaisesRegex(AssertionError,'COPY_CHANGED'):archive.collect_historical_sources(root=root,checked=checked,original_sources={'core/old.py':original})
 def test_real_worker_clock_and_network_write_guards(self):
  for mode in ('clock','network','write'):
   with self.subTest(mode=mode),TemporaryDirectory() as d:
    folder=Path(d);root=folder/'root';(root/'data').mkdir(parents=True)
    body="def review_first_window(*,root,clock,**kwargs):\n"
    if mode=='network':body+=" import socket; socket.socket()\n"
    if mode=='write':body+=" (root/'forbidden').write_text('x')\n"
    body+=" return {'receipt':{'clock':clock().isoformat()},'files':{}}\n"
    (root/h.ENTRY).write_text(body)
    worker=folder/'worker.py';worker.write_text(h.WORKER)
    request=folder/'request.json';request.write_text(json.dumps({'configuration_bytes':'','capture_files':{},'now':'2026-10-26T17:23:13+00:00'}))
    result=subprocess.run([sys.executable,'-I','-B',str(worker),str(root),str(request)],capture_output=True,text=True,timeout=10)
    if mode=='clock':self.assertEqual(json.loads(result.stdout)['receipt']['clock'],'2026-10-26T17:23:13+00:00')
    else:self.assertNotEqual(result.returncode,0);self.assertIn('FORBIDDEN',result.stderr)
    self.assertFalse((root/'forbidden').exists())
if __name__=='__main__':unittest.main()
