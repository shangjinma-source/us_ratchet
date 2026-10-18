"""Independent source-consumption and authority attacks; synthetic files only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_first_persisted_candidate_calendar_independent_readback_20261003 import staged,patched,m


class Tests(unittest.TestCase):
 def test_loaded_bytes_are_the_hashed_bytes(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'source.json';good=b'{"bound":true}';bad=b'{"bound":false}';p.write_bytes(good)
   original=Path.read_bytes;reads=[]
   def alternating(path):
    if path==p:
     reads.append(path)
     return good if len(reads)==1 else bad
    return original(path)
   with patch.object(Path,'read_bytes',alternating):
    try:actual=m.load(dict(path=str(p),sha256=m.sha(good)),{})
    except ValueError:return
    self.assertEqual(actual,good,'Never return bytes different from the bytes whose SHA was checked')

 def test_resigned_permission_and_bridge_claims_rejected(self):
  for mode in ('false_zero','original_claim','permanent_live'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td:
    settings=staged(Path(td));folder=settings['PARENT'];r=json.loads((folder/'result.json').read_bytes());p=json.loads((folder/'publication.json').read_bytes())
    if mode=='false_zero':r['evidence']['future_independent_oos']=0
    elif mode=='original_claim':
     r['original_source_claims_preserved']={};p['original_source_claims_preserved']={}
    else:
     live=str(Path(td)/'data/cache/DIA.csv')
     r['source_hashes'][live]='a'*64;p['source_hashes'][live]='a'*64
    raw=m.enc(r);(folder/'result.json').write_bytes(raw);settings['RESULT_SHA']=m.sha(raw);p['result_reference']['sha256']=settings['RESULT_SHA']
    raw=m.enc(p);(folder/'publication.json').write_bytes(raw);settings['PUBLICATION_SHA']=m.sha(raw)
    with patched(settings):
     with self.assertRaises(ValueError):m.readback(execute=True)
     self.assertTrue((settings['OUTPUT']/'failure.json').exists())

 def test_snapshot_after_write_drift_and_pre_read_live_rejection(self):
  for path in ('C:/elsewhere/data/cache/DIA.csv','E:/Git/us_ratchet/data/cache/QQQ.csv'):
   read=Path.read_bytes
   def sentinel(p):
    if m.is_live(p):raise AssertionError('Forbidden live read')
    return read(p)
   with patch.object(Path,'read_bytes',sentinel),self.assertRaises(ValueError):m.load(dict(path=path,sha256='a'*64),{})
  with tempfile.TemporaryDirectory() as td:
   settings=staged(Path(td));original=m.guard;snapshot=Path(td)/'sources/QQQ.csv'
   def drift(sources):
    if (settings['OUTPUT']/'independent_readback.json').exists():snapshot.write_bytes(b'changed after report write')
    return original(sources)
   with patched(settings),patch.object(m,'guard',side_effect=drift):
    with self.assertRaisesRegex(ValueError,'Source drift'):m.readback(execute=True)
    self.assertTrue((settings['OUTPUT']/'failure.json').exists())
    with self.assertRaises(ValueError):m.readback(execute=True)


if __name__=='__main__':unittest.main()
