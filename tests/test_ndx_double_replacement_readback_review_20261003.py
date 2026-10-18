import json,tempfile,unittest
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from test_ndx_double_replacement_preparation_independent_readback_20261003 import prepared
from scripts import ndx_double_replacement_preparation_independent_readback_20261003 as m

class Tests(unittest.TestCase):
 def test_asymmetric_triangle_and_boundary_independent_enumeration(self):
  for A in range(1,8):
   for B in range(1,9):
    for C in range(-1,31):
     a,b,c=Fraction(A,3),Fraction(B,7),Fraction(C,5)
     expected=sum(1 for x in range(1,max(1,int(c/a)+1)) for y in range(1,max(1,int(c/b)+1)) if a*x+b*y<=c)
     self.assertEqual(m.independent_joint_count(a,b,c),expected)
  n=10**60+17
  self.assertEqual(m.independent_joint_count(Fraction(2),Fraction(3),Fraction(6*n)),3*n*n-2*n)

 def test_re_signed_entire_publisher_chain_wrong_joint_count_reaches_arithmetic(self):
  with tempfile.TemporaryDirectory() as tmp,prepared(Path(tmp)) as (refs,_):
   def write(path,obj):
    raw=m.encode(obj);path.write_bytes(raw);return dict(path=str(path),sha256=m.hashlib.sha256(raw).hexdigest())
   out=m.decode((m.PARENT/'preparation.json').read_bytes());body=out['preparation']['document']
   body['cases'][0]['pairs'][0]['financial_integer_count']+=1
   out['preparation']['content_sha256']=m.digest(body)
   raw=m.decode((m.PARENT/'raw_preparation.json').read_bytes());raw['result']=deepcopy(out['preparation'])
   rawref=write(m.PARENT/'raw_preparation.json',raw);out['raw_preparation_reference']=rawref
   outref=write(m.PARENT/'preparation.json',out)
   pub=m.decode((m.PARENT/'publication.json').read_bytes());pub.update(preparation_reference=outref,raw_preparation_reference=rawref)
   pubref=write(m.PARENT/'publication.json',pub)
   with patch.multiple(m,PREPARATION_SHA=outref['sha256'],PUBLICATION_SHA=pubref['sha256']),self.assertRaisesRegex(ValueError,'Independent full rational'):
    m.readback(execute=True)
   self.assertTrue((m.OUTPUT/'started.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
   self.assertFalse((m.OUTPUT/'independent_readback.json').exists())

 def test_final_parent_addition_and_bool_claim_preserve_failure(self):
  with tempfile.TemporaryDirectory() as tmp,prepared(Path(tmp)) as (refs,_):
   original=m.save
   def changed(name,value):
    result=original(name,value)
    if name=='independent_readback.json':(m.PARENT/'late-extra').write_bytes(b'x')
    return result
   with patch.object(m,'save',side_effect=changed),self.assertRaisesRegex(ValueError,'namespace'):m.readback(execute=True)
   self.assertTrue((m.OUTPUT/'failure.json').exists())
   with self.assertRaisesRegex(ValueError,'retry'):m.readback(execute=True)
  with tempfile.TemporaryDirectory() as tmp,prepared(Path(tmp)) as (refs,_):
   docs={k:m.decode(Path(refs[k]['path']).read_bytes())for k in ('policy','inputs','input_publication','inventory','inventory_publication','scenarios')}
   saved=m.decode((m.PARENT/'preparation.json').read_bytes())['preparation']
   for field in ('budget_helper_source_bytes_authenticated','source_bytes_authenticated'):
    bad=deepcopy(saved);bad['document'][field]=0;bad['content_sha256']=m.digest(bad['document'])
    with self.assertRaises(ValueError):m.inspect_domain(documents=docs,references=refs,saved_preparation=bad)

if __name__=='__main__':unittest.main()
