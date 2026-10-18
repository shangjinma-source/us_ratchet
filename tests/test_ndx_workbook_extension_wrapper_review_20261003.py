"""Independent extension publisher review; synthetic streams/temp files only."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_dated_workbook_extension_data_20261003 import streams, m, core, classification, classification_fixture


class ExtensionReview(unittest.TestCase):
 def project(self, values):
  pb,cb,p,c,s,a=values
  return m.stream_display(io.BytesIO(pb),io.BytesIO(cb),p,c,s,a,core,lambda b: {'synthetic':True})
 def test_complete_counts_and_both_calendars_are_not_coerced_or_replaced(self):
  for kind in ('bool_count','wrong_missing','chain_calendar'):
   values=streams();p,c=values[2:4]
   p['planned_task_count']=c['planned_task_count']=1632
   if kind=='bool_count':p['projected_task_count']=c['projected_task_count']=True
   elif kind=='wrong_missing':p['not_supplied_task_count']=c['not_supplied_task_count']=999
   else:c['calendar']=c['calendar'][:-1]
   with self.subTest(kind=kind),self.assertRaises(ValueError):self.project(values)
 def test_shared_role_identity_cannot_be_relabelled_or_zeroed(self):
  values=streams();s=values[4]
  key=next(k for k,v in s.items() if v['identity']['role']=='incumbent_integer')
  s[key]['identity']['role']='candidate_integer'
  with self.assertRaises(ValueError):self.project(values)
  values=streams();aggregates=values[5]
  key=next(iter(aggregates));aggregates[key]['identity']['source_reference']['sha256']='f'*64
  with self.assertRaises(ValueError):self.project(values)
 def test_final_output_tail_change_retained_as_failure_not_success(self):
  pb,cb,p,c,s,a=streams();p['planned_task_count']=c['planned_task_count']=1632
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'p').write_bytes(pb);(root/'c').write_bytes(cb)
   p['task_jsonl_reference']['path']=str(root/'p');c['task_jsonl_reference']['path']=str(root/'c')
   p['source_hashes']={};c['source_hashes']={}
   docs=dict(path_index=p,chain_index=c,path_shared={'shared_paths':s},chain_shared={'aggregates':a},classification={'coverage':classification.summarize_saved_classification(**classification_fixture()),'source_hashes':{}})
   out=root/'out';original_save=m.save
   def save(path,value):
    result=original_save(path,value)
    if path.name=='publication.json':
     with (out/'tasks.jsonl').open('ab') as stream:stream.write(b'{}\n')
    return result
   with patch.object(m,'OUTPUT',out),patch.object(m,'load',return_value=(docs,{}, {},core)),patch.object(m,'save',side_effect=save):
    with self.assertRaises(ValueError):m.run(execute=True)
    self.assertTrue((out/'failure.json').exists())
    self.assertTrue((out/'publication.json').exists())
    with self.assertRaises(ValueError):m.run(execute=True)
 def test_pending_before_read_and_source_collision(self):
  with patch.dict(m.BOUND,{'path_index':('missing',None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('No I/O with missing anchor')):
   with self.assertRaises(ValueError):m.load()
  with self.assertRaises(ValueError):m.merge({'same':'a'*64},'same','b'*64)

if __name__=='__main__':unittest.main()
