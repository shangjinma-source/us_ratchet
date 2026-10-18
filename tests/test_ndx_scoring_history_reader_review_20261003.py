from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile,unittest
from scripts import ndx_multidecision_scoring_history_independent_readback_20261003 as m
from test_ndx_multidecision_scoring_history_independent_readback_20261003 import physical

class Review(unittest.TestCase):
 def test_resealed_source_omission_and_extra_claim_rejected(self):
  for mode in ('omit_raw','omit_core','extra','started'):
   with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp:
    pins,index,pub,docs,refs=physical(Path(tmp));parent=pins['PARENT']
    if mode=='started':
     p=parent/'started.json';d=m.loads(p.read_bytes());d['source_hashes'].pop(str(m.CORE));p.write_bytes(m.encoded(d))
    else:
     if mode=='omit_raw':key=next(iter(docs['history']['requirements']['ticker_observations_preserved'].values()))['raw_reference']['path'];index['source_hashes'].pop(key)
     elif mode=='omit_core':index['source_hashes'].pop(str(m.CORE))
     else:index['source_hashes']['unreviewed']='a'*64
     pub['source_hashes']=deepcopy(index['source_hashes']);b=m.encoded(index);(parent/'index.json').write_bytes(b);pins['INDEX_SHA']=m.sha(b);pub['index_reference']['sha256']=pins['INDEX_SHA'];b=m.encoded(pub);(parent/'publication.json').write_bytes(b);pins['PUBLICATION_SHA']=m.sha(b)
    with patch.multiple(m,**pins):
     with self.assertRaises(ValueError):m.load_inputs()
 def test_inventory_path_swap_authority_and_content_types(self):
  with tempfile.TemporaryDirectory() as tmp:
   pins,index,pub,docs,refs=physical(Path(tmp))
   with patch.multiple(m,**pins):
    self.assertEqual(len(m.inspect_inventory(index,pub,docs,refs)),77)
    for attack in (lambda d:d['rows'][0]['channel_reference'].update(path=str(pins['PARENT']/'channel_001.json')),lambda d:d.update(full_ndx_universe_certified=0),lambda d:d['rows'][0]['original_identity_assumed_window'].update(first='2023-01-01'),lambda d:d['outer_inventory_contract']['preserved_sidecar_references'][m.SIDECARS[0]].update(json_pointer='/foreign')):
     bad=deepcopy(index);attack(bad)
     with self.assertRaises(ValueError):m.inspect_inventory(bad,pub,docs,refs)
    sources=m.load_inputs()[1];(pins['PARENT']/'unexpected').write_bytes(b'')
    with self.assertRaises(ValueError):m.guard(sources,refs)
 def test_consumed_raw_single_read(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'raw';p.write_bytes(b'good');r=m.ref(p,m.sha(b'good'));sources={}
   original=Path.read_bytes;calls=[]
   def read(path):
    calls.append(path);return b'bad' if path==p else original(path)
   with patch.object(Path,'read_bytes',read):
    with self.assertRaises(ValueError):m.take(r,sources)
   self.assertEqual(calls,[p]);self.assertEqual(sources,{})
if __name__=='__main__':unittest.main()
