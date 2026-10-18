"""Temporary-file source-bound tests, no actual observations or candidate sealing."""
import copy,csv,hashlib,io,json,tempfile,unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_persisted_candidate_calendar_20261003 as w
from test_ndx_persisted_candidate_calendar_research import fixture,m

def file_fixture(root):
 original=fixture();mapping={};identities={};sources=root/'sources';sources.mkdir()
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
 def rewrite(v):
  if type(v)is list:return [rewrite(x)for x in v]
  if type(v)is dict:
   if 'path'in v and 'sha256'in v and v['path']in mapping:return dict(v,**mapping[v['path']])
   return {mapping[k]['path']if k in mapping and type(x)is str else k:mapping[k]['sha256']if k in mapping and type(x)is str else rewrite(x)for k,x in v.items()}
  return identities.get(v,v)if type(v)is str else v
 def save_document(original_reference,document,label):
  p=sources/(label+'.json');p.write_bytes(w.enc(document));mapping[original_reference['path']]=dict(path=str(p),sha256=w.sha(p.read_bytes()));return document
 for old_entry in original['history']['document']['observations'][:-1]:identities[old_entry['observation_id']]=m.digest(rewrite(old_entry['observation_identity']))
 c=original['capture'];save_document(c['reference'],rewrite(c['document']),'capture');save_document(c['publication_reference'],rewrite(c['publication']),'capture-publication');save_document(c['readback_reference'],dict(rewrite(c['readback']),reader_sha256=mapping[c['reader_reference']['path']]['sha256']),'capture-audit')
 o=original['observation'];p=rewrite(o['payload']);identities[p['observation_id']]=m.digest(p['observation_identity']);p['observation_id']=identities[p['observation_id']];save_document(o['payload_reference'],p,'observation');save_document(o['receipt_reference'],rewrite(o['receipt']),'receipt');save_document(o['audit_reference'],dict(rewrite(o['audit']),reader_sha256=mapping[o['reader_reference']['path']]['sha256']),'observation-audit')
 h=original['history'];hd=rewrite(h['document'])
 for e in hd['observations']:identities[e['observation_id']]=m.digest(e['observation_identity'])
 hd=rewrite(hd);save_document(h['reference'],hd,'history');save_document(h['publication_reference'],rewrite(h['publication']),'history-publication');save_document(h['readback_reference'],dict(rewrite(h['readback']),reader_sha256=mapping[h['reader_reference']['path']]['sha256']),'history-audit')
 bindings=dict(OUTPUT=root/'output',HISTORY_BOUND={k:(mapping[h[k]['path']]['path'],mapping[h[k]['path']]['sha256'])for k in w.ENVELOPE_ROLES},CAPTURE_BOUND={k:(mapping[c[k]['path']]['path'],mapping[c[k]['path']]['sha256'])for k in w.ENVELOPE_ROLES},OBSERVATION_BOUND={k:(mapping[o[k]['path']]['path'],mapping[o[k]['path']]['sha256'])for k in w.OBSERVATION_ROLES})
 return bindings

class Tests(unittest.TestCase):
 def test_full_sourcebound_temporary_publication_and_late_clock(self):
  for clock in ('2026-11-02T21:02:00+00:00','2026-11-04T21:02:00+00:00'):
   with tempfile.TemporaryDirectory()as td:
    bindings=file_fixture(Path(td))
    with ExitStack()as stack:
     for k,v in bindings.items():stack.enter_context(patch.object(w,k,v))
     stack.enter_context(patch.object(w,'now',return_value=clock));out=w.run(execute=True);doc=json.loads(Path(out['result_reference']['path']).read_bytes());self.assertEqual(doc['evidence']['calendar_prerequisites_conditionally_satisfied'],clock.startswith('2026-11-02'));self.assertFalse(doc['candidate_seal_allowed']);self.assertEqual(len(list(bindings['OUTPUT'].iterdir())),3)
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
    stack.enter_context(patch.object(w,'save',side_effect=save));stack.enter_context(patch.object(w,'now',return_value='2026-11-02T21:02:00+00:00'))
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
