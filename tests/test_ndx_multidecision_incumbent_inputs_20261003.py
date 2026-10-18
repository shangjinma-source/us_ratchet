import unittest,tempfile
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
from test_ndx_multidecision_incumbent_inputs_research import fixture
from scripts import ndx_multidecision_incumbent_inputs_20261003 as w


def physical(root):
 a=fixture();bound={}
 def put(p,v,raw=False):
  p.parent.mkdir(parents=True,exist_ok=True);b=v if raw else w.enc(v);p.write_bytes(b);return w.reference(p,w.sha(b))
 for i,row in enumerate(a['original_eight_evidence']['document']['rows']):
  for role in ('raw_reference','receipt_reference'):
   rr=put(root/f'underlying/{i}-{role}',b'original raw bytes',True);row['channel'][role]=rr;row['complete_benchmark_metadata'][role]=rr
  ch=row['channel'];ch['receipt_preserved'].update(raw_path=ch['raw_reference']['path'],raw_sha256=ch['raw_reference']['sha256'])
 for prefix,key,filename in [('candidate','candidate_evidence','inputs.json'),('original','original_eight_evidence','channels.json')]:
  e=a[key];home=root/prefix;reader=put(root/(prefix+'_reader.py'),b'# read-only source',True)
  e['document']['source_hashes']={};e['publication']['source_hashes']={};ir=put(home/filename,e['document']);e['publication']['inputs_reference' if prefix=='candidate' else 'channels_reference']=ir;pr=put(home/'publication.json',e['publication']);put(home/'started.json',{'observed_start':True})
  au=e['readback'];au['reader_sha256']=reader['sha256']
  if prefix=='candidate':au.update(inputs_reference=ir,publication_reference=pr)
  else:au.update(channels_sha256=ir['sha256'],publication_sha256=pr['sha256'])
  ar=put(root/(prefix+'_audit.json'),au)
  for role,r in dict(inputs=ir,publication=pr,readback=ar,reader=reader).items():bound[prefix+'_'+role]=(r['path'],r['sha256'])
 return bound

class Tests(unittest.TestCase):
 def test_pending_pre_io(self):
  b=deepcopy(w.BOUND);b['candidate_inputs']=(b['candidate_inputs'][0],None)
  with patch.object(w,'BOUND',b),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):w.load_inputs()
 def test_full_physical_inputs_no_accounts_and_exact_namespace(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root)
   with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'published'):
    rr=w.run(execute=True);d=w.decode(Path(rr['path']).read_bytes());self.assertEqual(d['inputs']['track_count'],16);self.assertFalse(d['account_simulation_performed']);self.assertEqual(len(d['inputs']['original_candidate_provenance']),101)
    with self.assertRaisesRegex(ValueError,'no retry'):w.run(execute=True)
 def test_postpublication_parent_inventory_drift(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);bound=physical(root);original=w.save
   def save(name,value,emergency=False):
    r=original(name,value,emergency)
    if name=='publication.json':(root/'original'/'unknown').write_bytes(b'bad')
    return r
   with patch.object(w,'BOUND',bound),patch.object(w,'OUTPUT',root/'output'),patch.object(w,'save',side_effect=save):
    with self.assertRaisesRegex(ValueError,'inventory drift'):w.run(execute=True)
    self.assertTrue((w.OUTPUT/'failure.json').exists());self.assertTrue((w.OUTPUT/'inputs.json').exists())
 def test_source_conflict_and_corruption(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'source';p.write_bytes(b'one');r=w.reference(p,w.sha(b'one'))
   with self.assertRaisesRegex(ValueError,'conflict'):w.load(r,{str(p):'f'*64},False)
   p.write_bytes(b'two')
   with self.assertRaisesRegex(ValueError,'mismatch'):w.load(r,{},False)

if __name__=='__main__':unittest.main()
