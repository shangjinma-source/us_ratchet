"""Temporary-file source-bound tests, no actual observations or candidate sealing."""
import copy,csv,hashlib,io,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_first_persisted_candidate_calendar_20261003 as w
from test_ndx_first_persisted_candidate_calendar_research import fixture,m

def file_fixture(root):
 original=fixture();g=original['genesis'];g['readback']['source_hashes'].pop(g['readback_reference']['path'],None);original['history']['document']['genesis_preserved']=copy.deepcopy(g);o=original['observation'];o['audit']['source_hashes'].pop(o['audit_reference']['path'],None);original['history']['document']['observations'][0]['original_source_hash_claims']['audit']=copy.deepcopy(o['audit']['source_hashes']);mapping={};identities={};sources=root/'sources';sources.mkdir()
 def collect(v):
  if type(v)is dict:
   if 'path'in v and 'sha256'in v:mapping.setdefault(v['path'],None)
   for k,x in v.items():
    if type(x)is str and len(x)==64 and all(c in '0123456789abcdef'for c in x)and k not in ('sha256','observation_id','reader_sha256'):mapping.setdefault(k,None)
    collect(x)
  elif type(v)is list:
   for x in v:collect(x)
 collect(original)
 payload=original['observation']['payload'];blob_by_path={payload['tzif_reference']['path']:original['tzif_bytes']}
 for ticker in ('QQQ','SPY'):
  for role in ('sources','baseline_sources'):
   item=payload['full_original_sources_preserved'][ticker][role];f=io.StringIO(newline='');writer=csv.DictWriter(f,fieldnames=['Date','Open','High','Low','Close','Volume'],lineterminator='\n');writer.writeheader();writer.writerows(item['rows']);blob_by_path[item['reference']['path']]=f.getvalue().encode()
 for i,path in enumerate(mapping):
  p=sources/f'atom-{i}';p.write_bytes(blob_by_path.get(path,path.encode()));mapping[path]=dict(path=str(p),sha256=w.sha(p.read_bytes()))
 for ticker in ('QQQ','SPY'):
  old_snapshot=original['capture']['document']['captured_artifacts'][ticker]['path'];snapshot_path=sources/(ticker+'.csv');snapshot_path.write_bytes(blob_by_path[old_snapshot]);mapping[old_snapshot]=dict(path=str(snapshot_path),sha256=w.sha(snapshot_path.read_bytes()))
  old_live=original['capture']['document']['input_references']['current_'+ticker]['path'];live=root/'data/cache'/f'{ticker}.csv';live.parent.mkdir(parents=True,exist_ok=True);live.write_bytes(b'REFRESHED LIVE CONTENT MUST NEVER BE READ');mapping[old_live]=dict(path=str(live),sha256=mapping[old_snapshot]['sha256'])
 def rewrite(v):
  if type(v)is list:return [rewrite(x)for x in v]
  if type(v)is dict:
   if 'path'in v and 'sha256'in v and v['path']in mapping:return dict(v,**mapping[v['path']])
   return {mapping[k]['path']if k in mapping and type(x)is str else k:mapping[k]['sha256']if k in mapping and type(x)is str else rewrite(x)for k,x in v.items()}
  return identities.get(v,v)if type(v)is str else v
 def save_document(original_reference,document,label):
  p=sources/(label+'.json');p.write_bytes(w.enc(document));mapping[original_reference['path']]=dict(path=str(p),sha256=w.sha(p.read_bytes()));return document
 for old_entry in original['history']['document']['observations'][:-1]:identities[old_entry['observation_id']]=m.digest(rewrite(old_entry['observation_identity']))
 g=original['genesis']
 identities[g['reader_reference']['sha256']]=mapping[g['reader_reference']['path']]['sha256']
 save_document(g['reference'],rewrite(g['document']),'genesis');save_document(g['publication_reference'],rewrite(g['publication']),'genesis-publication');save_document(g['readback_reference'],rewrite(g['readback']),'genesis-audit')
 c=original['capture'];save_document(c['reference'],rewrite(c['document']),'capture');save_document(c['publication_reference'],rewrite(c['publication']),'capture-publication');save_document(c['readback_reference'],dict(rewrite(c['readback']),reader_sha256=mapping[c['reader_reference']['path']]['sha256']),'capture-audit')
 o=original['observation'];p=rewrite(o['payload']);identities[p['observation_id']]=m.digest(p['observation_identity']);p['observation_id']=identities[p['observation_id']];save_document(o['payload_reference'],p,'observation');save_document(o['receipt_reference'],rewrite(o['receipt']),'receipt');save_document(o['audit_reference'],dict(rewrite(o['audit']),reader_sha256=mapping[o['reader_reference']['path']]['sha256']),'observation-audit')
 h=original['history'];hd=rewrite(h['document'])
 for e in hd['observations']:identities[e['observation_id']]=m.digest(e['observation_identity'])
 hd=rewrite(hd);save_document(h['reference'],hd,'history');save_document(h['publication_reference'],rewrite(h['publication']),'history-publication');save_document(h['readback_reference'],dict(rewrite(h['readback']),reader_sha256=mapping[h['reader_reference']['path']]['sha256']),'history-audit')
 bindings=dict(ROOT=root,OUTPUT=root/'output',GENESIS_BOUND={k:(mapping[g[k]['path']]['path'],mapping[g[k]['path']]['sha256'])for k in w.ENVELOPE_ROLES},HISTORY_BOUND={k:(mapping[h[k]['path']]['path'],mapping[h[k]['path']]['sha256'])for k in w.ENVELOPE_ROLES},CAPTURE_BOUND={k:(mapping[c[k]['path']]['path'],mapping[c[k]['path']]['sha256'])for k in w.ENVELOPE_ROLES},OBSERVATION_BOUND={k:(mapping[o[k]['path']]['path'],mapping[o[k]['path']]['sha256'])for k in w.OBSERVATION_ROLES})
 return bindings

class Tests(unittest.TestCase):
 def test_physical_bridge_path_and_audit_attacks(self):
  for mode in ('path','hash','third','audit'):
   with tempfile.TemporaryDirectory()as td:
    bindings=file_fixture(Path(td))
    with ExitStack()as stack:
     for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
     docs,refs,s,core,tz,core_ref=w.load_inputs();c=docs['capture'];doc=c['document']
     if mode=='path':doc['captured_artifacts']['QQQ']['path']=str(Path(td)/'elsewhere/QQQ.csv')
     elif mode=='hash':doc['input_references']['current_QQQ']['sha256']='a'*64
     elif mode=='third':
      for d in (doc['source_hashes'],c['publication']['source_hashes'],c['readback']['capture_original_source_hashes_preserved']):d[str(Path(td)/'data/cache/DIA.csv')]='a'*64
     else:del c['readback']['source_hashes'][doc['captured_artifacts']['QQQ']['path']]
     with self.assertRaises(ValueError):w.validate_snapshot_bridge(c,{})
 def test_original_live_claim_is_unsupported_not_silently_removed(self):
  with tempfile.TemporaryDirectory()as td:
   bindings=file_fixture(Path(td));path,_=bindings['GENESIS_BOUND']['reference'];p=Path(path)
   doc=json.loads(p.read_bytes());live=str(bindings['ROOT']/'data/cache/QQQ.csv');doc['source_hashes'][live]='a'*64
   raw=w.enc(doc);p.write_bytes(raw);bindings['GENESIS_BOUND']['reference']=(path,w.sha(raw))
   with ExitStack()as stack:
    for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
    with self.assertRaisesRegex(ValueError,'UNSUPPORTED_LIVE_CACHE_SOURCE_CLAIM'):w.run(execute=True)
   self.assertFalse(bindings['OUTPUT'].exists());self.assertEqual(json.loads(p.read_bytes())['source_hashes'][live],'a'*64)
 def test_full_sourcebound_temporary_publication_and_late_clock(self):
  for clock in ('2026-10-02T20:02:00+00:00','2026-10-06T20:02:00+00:00'):
   with tempfile.TemporaryDirectory()as td:
    bindings=file_fixture(Path(td))
    with ExitStack()as stack:
     for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
     stack.enter_context(patch.object(w,'now',return_value=clock));original_read=Path.read_bytes
     def guarded_read(path):
      if path.parent==Path(td)/'data/cache':raise AssertionError('Live cache must never be opened')
      return original_read(path)
     stack.enter_context(patch.object(Path,'read_bytes',guarded_read));out=w.run(execute=True);doc=json.loads(Path(out['result_reference']['path']).read_bytes());self.assertEqual(doc['evidence']['calendar_prerequisites_conditionally_satisfied'],clock.startswith('2026-10-02'));self.assertFalse(doc['candidate_seal_allowed']);self.assertEqual(len(list(bindings['OUTPUT'].iterdir())),3)
     with self.assertRaisesRegex(ValueError,'Create-only'):w.run(execute=True)
 def test_source_drift_after_result_retains_failure_no_retry(self):
  with tempfile.TemporaryDirectory()as td:
   bindings=file_fixture(Path(td));original_save=w.save;target=Path(bindings['HISTORY_BOUND']['reference'][0])
   def save(path,value,**kwargs):
    out=original_save(path,value,**kwargs)
    if path.name=='result.json':target.write_bytes(target.read_bytes()+b' ')
    return out
   with ExitStack()as stack:
    for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
    stack.enter_context(patch.object(w,'save',side_effect=save));stack.enter_context(patch.object(w,'now',return_value='2026-10-02T20:02:00+00:00'))
    with self.assertRaisesRegex(ValueError,'Source drift'):w.run(execute=True)
    self.assertTrue((bindings['OUTPUT']/'failure.json').exists());self.assertTrue((bindings['OUTPUT']/'result.json').exists())
    with self.assertRaises(ValueError):w.run(execute=True)
 def test_pending_before_io_and_resource_failure_marker_exemption(self):
  with patch.object(w,'HISTORY_BOUND',dict.fromkeys(w.ENVELOPE_ROLES)),patch.object(Path,'read_bytes',side_effect=AssertionError('No pending IO')):
   with self.assertRaisesRegex(ValueError,'Pending'):w.run(execute=True)
  with tempfile.TemporaryDirectory()as td,patch.object(w,'resource_gate',side_effect=ValueError('resource')):
   p=Path(td)/'failure.json';w.save(p,dict(status='FAILED'),failure=True);self.assertTrue(p.exists())
   with self.assertRaises(ValueError):w.save(Path(td)/'result.json',{})
 def test_source_conflict_live_claim_and_corrupt_anchor_fail_before_output(self):
  with self.assertRaises(ValueError):w.merge({'x':'a'*64},dict(path='x',sha256='b'*64))
  with self.assertRaises(ValueError):w.no_live({str(w.ROOT/'data/cache/QQQ.csv'):'a'*64})
  with tempfile.TemporaryDirectory()as td:
   bindings=file_fixture(Path(td));path,digest=bindings['CAPTURE_BOUND']['reference'];Path(path).write_bytes(b'{}')
   with ExitStack()as stack:
    for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
    with self.assertRaisesRegex(ValueError,'SHA'):w.run(execute=True)
    self.assertFalse(bindings['OUTPUT'].exists())

if __name__=='__main__':unittest.main()
