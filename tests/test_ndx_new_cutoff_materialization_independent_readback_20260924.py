"""Synthetic outer readback tests; never audit actual twenty-security tasks."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_materialization_independent_readback_20260924 as m
spec=importlib.util.spec_from_file_location('manual_materialization_fixture',Path(__file__).with_name('test_ndx_issuer_materialization_independent_readback_research.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)


def outer_fixture():
 args=f.fixture();value=args.pop('value');source_map={'synthetic':'a'*64}
 outer=dict(schema='SOURCE_BOUND_NEW_CUTOFF_BOUNDED_MATERIALIZATION_V1',scope='CONDITIONAL_RESEARCH_TASK_INPUTS_NOT_EXECUTION',materialization=value,input_references={k:m.ref(k) for k in m.BOUND},source_hashes=source_map,selected_slice_reason='FIRST_LEXICOGRAPHIC_COMBINATION_OF_FIRST_NONEXCLUDED_K_FOR_INTERFACE_VALIDATION_NOT_SCORE_SELECTION',external_direct_source_bytes_verified=True,materializer_invocation_count=1,combination_enumeration_performed=True,enumerated_combination_count=1,actual_fitter_invocation_count=0,**dict.fromkeys(m.FALSE,False))
 return args,outer,source_map


class Tests(unittest.TestCase):
 def test_synthetic_outer_single_independent_read(self):
  args,value,sources=outer_fixture()
  with patch.object(m,'project',return_value=args),patch.object(m,'producer_sources',return_value=sources),patch.object(m.reader,'verify_materialized',wraps=m.reader.verify_materialized) as read:
   report,bound=m.verify_document(value,{})
   self.assertEqual(report['task_count'],3);self.assertEqual(bound,sources);self.assertEqual(read.call_count,1)
 def test_outer_extra_authority_source_or_count_rejected(self):
  for key,val in [('fit_performed',True),('actual_fitter_invocation_count',False),('enumerated_combination_count',20),('source_hashes',{})]:
   args,value,sources=outer_fixture();value[key]=val
   with patch.object(m,'project',return_value=args),patch.object(m,'producer_sources',return_value=sources),self.subTest(key=key),self.assertRaises(ValueError):m.verify_document(value,{})
 def test_full_source_metadata_closure_only_no_task_readback(self):
  documents={k:m.codec.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
  closure=m.producer_sources(documents)
  self.assertEqual(len(closure),43)
  self.assertTrue(all(closure[p]==h for p,h in documents['plan']['plan']['fitter_source_hashes'].items()))
  self.assertEqual(closure[str(m.PRODUCER)],m.PRODUCER_SHA)
 def test_guard_pin_namespace_and_pending_failclosed(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audit.json';p.write_text('{}')
   with patch.object(m,'OUTPUT',p),patch.object(m,'build') as b:
    with self.assertRaises(ValueError):m.publish()
    b.assert_not_called()
  with patch.object(m,'CANDIDATE_SHA',None),patch.object(m.Path,'read_bytes',side_effect=AssertionError('read')):
   with self.assertRaises(ValueError):m.build()
  with patch.object(m.Path,'read_bytes',return_value=b'drift'):
   with self.assertRaises(ValueError):m.guard({})
 def test_guard_rejects_source_and_loaded_collision(self):
  key=next(iter(m.LOADED))
  with self.assertRaises(ValueError):m.guard({key:'0'*64})
  codec_key=next(iter(m.codec.LOADED))
  with patch.dict(m.LOADED,{codec_key:'0'*64}):
   with self.assertRaises(ValueError):m.guard({})
 def test_candidate_pin_present_not_actual_audit(self):
  self.assertEqual(m.CANDIDATE_SHA,'ce8b3c7545b8123c63eeabd0db138c11689d4d535643e58bde720b5a955fc9e0')
  self.assertEqual(m.BOUND['plan'][1],'50b3c661325bc4c2c4337cdb3d520413aa51f4dc94a869af9f94fdbd5bb0bceb')

if __name__=='__main__':unittest.main()
