from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import gzip,hashlib,json,tempfile,unittest
from backtest import ndx_double_replacement_compressed_batch_research as m
from backtest import ndx_double_replacement_compressed_raw_inspection_research as independent
from scripts import ndx_double_replacement_compressed_raw_io_20261003 as raw_io


def plan(n=560,size=512):
 return m.build_plan(preparation_reference=dict(path='E:/synthetic/preparation.json',sha256='a'*64),prepared_content_sha256='b'*64,scenario_count=40,pair_count=100,financial_integer_count_before_issuer=n+7,structurally_excluded_integer_count=7,integer_count=n,batch_size=size)
def outcome(p,i,status='inspected_feasible'):
 d=m.descriptor(p,i);return dict(descriptor=d,point_runs=[dict(start=d['start'],stop=d['stop'],status=status)])

class Tests(unittest.TestCase):
 def test_complete_geometry_and_full_partition_without_task_enumeration(self):
  for size,count,tail in ((512,102357,297),(10000,5241,6569)):
   p=plan(52406569,size);self.assertEqual(p['document']['batch_count'],count);self.assertEqual(m.descriptor(p,count-1)['point_count'],tail)
  p=plan();o=m.partition(p,[outcome(p,0)]);self.assertEqual(o['counts']['undispatched'],48);self.assertFalse(o['full_domain_complete'])
  o=m.partition(p,[outcome(p,0),outcome(p,1,'inspected_infeasible')]);self.assertTrue(o['full_domain_complete']);self.assertEqual(sum(o['counts'].values()),560)
 def test_technical_unknown_validation_separate_and_no_skipping(self):
  p=plan();first=outcome(p,0);last=outcome(p,1)
  last['point_runs']=[dict(start=512,stop=513,status='evaluation_exception'),dict(start=513,stop=560,status='supplied_not_evaluated_technical')]
  r=m.partition(p,[first,last]);self.assertEqual(r['counts']['evaluation_exception'],1);self.assertEqual(r['counts']['supplied_not_evaluated_technical'],47);self.assertEqual(r['status'],'TECHNICAL_STOP')
  for status in ('unresolved_dispatch_or_raw','validation_failure_returned'):
   r=m.partition(p,[outcome(p,0,status)]);self.assertEqual(r['counts'][status],512);self.assertEqual(r['counts']['undispatched'],48)
  for attack in ('gap','bool','skip','extra_after_stop','hash'):
   p=plan();rows=[outcome(p,0),outcome(p,1)]
   if attack=='gap':rows[0]['point_runs'][0]['stop']=511
   elif attack=='bool':rows[0]['point_runs'][0]['start']=False
   elif attack=='skip':rows=[rows[1]]
   elif attack=='extra_after_stop':rows[0]['point_runs'][0]['status']='unresolved_dispatch_or_raw'
   else:p['document']['batch_count']=1;p['content_sha256']=m.digest(p['document'])
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.partition(p,rows)
 def test_canonical_gzip_roundtrip_every_json_type_and_independent_decoder(self):
  for value in (None,{'中文':[0,True,None,'a\nb',10**50]},[1,2],False,'literal'):
   packed,metadata=m.encode_canonical_gzip(value,max_compressed_bytes=100000,max_uncompressed_bytes=100000)
   self.assertEqual(gzip.decompress(packed),m.encode(value));self.assertEqual(packed[9],255)
   parsed=independent.inspect_gzip_raw(compressed_bytes=packed,metadata=metadata,max_compressed_bytes=100000,max_uncompressed_bytes=100000)
   self.assertEqual(parsed['value'],value)
   self.assertEqual(m.encode_canonical_gzip(value,max_compressed_bytes=100000,max_uncompressed_bytes=100000),(packed,metadata))
 def test_real_durable_return_receipt_and_no_retry(self):
  with tempfile.TemporaryDirectory()as t:
   value=dict(schema='SYNTHETIC_ORIGINAL_RETURN',rows=[dict(q=1,l1='1/3')]);d=m.descriptor(plan(),0)
   r=raw_io.preserve_return(directory=t,descriptor=d,value=value,max_compressed_bytes=100000,max_uncompressed_bytes=100000)
   receipt=json.loads(Path(r['path']).read_bytes());packed=Path(receipt['raw_reference']['path']).read_bytes()
   parsed=independent.inspect_gzip_raw(compressed_bytes=packed,metadata=receipt['codec_metadata'],max_compressed_bytes=100000,max_uncompressed_bytes=100000)
   self.assertEqual(parsed['value'],value);self.assertFalse(receipt['call_event_authenticated']);self.assertFalse(receipt['resource_sufficiency_proved'])
   with self.assertRaises(ValueError):raw_io.preserve_return(directory=t,descriptor=d,value=value,max_compressed_bytes=100000,max_uncompressed_bytes=100000)
 def test_partial_and_hostile_result_preserved_without_success_receipt(self):
  class Hostile:
   def __repr__(self):raise RuntimeError('repr unavailable')
  for value,limit in (({'long':'x'*100},8),(Hostile(),100000),({'bad':float('nan')},100000)):
   with tempfile.TemporaryDirectory()as t:
    with self.assertRaises((ValueError,TypeError)):raw_io.preserve_return(directory=t,descriptor=m.descriptor(plan(),0),value=value,max_compressed_bytes=100000,max_uncompressed_bytes=limit)
    folder=Path(t);self.assertTrue((folder/'raw_return.json.gz').exists());self.assertFalse((folder/'raw_receipt.json').exists());diagnostic=json.loads((folder/'raw_diagnostic.json').read_bytes());self.assertTrue(diagnostic['returned_value_supplied_by_caller']);self.assertFalse(diagnostic['result_preserved_as_complete_json'])
    if isinstance(value,Hostile):self.assertEqual(diagnostic['representation_error']['type'],'RuntimeError')
    with self.assertRaises(ValueError):raw_io.preserve_return(directory=t,descriptor=m.descriptor(plan(),0),value=None,max_compressed_bytes=100000,max_uncompressed_bytes=100000)

if __name__=='__main__':unittest.main()
