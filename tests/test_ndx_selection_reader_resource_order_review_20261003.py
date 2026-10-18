from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts import ndx_registered_scoring_selection_independent_readback_20261003 as m

class StopAfterLoad(Exception):pass

def setup(root):
 parent=root/'parent';parent.mkdir();refs={}
 def add(name,doc):
  p=parent/(name+'.json');b=m.enc(doc);p.write_bytes(b);refs[name]=m.ref(p,m.sha(b))
 add('started',{'raw_score_record_bytes':400})
 add('raw_inputs',{'result':{'large':'x'*1000}});add('raw_selection',{'result':{'large':'y'*1500}})
 add('index',{});add('publication',{k+'_reference':refs[k]for k in ('started','raw_inputs','raw_selection')})
 return parent,refs

class Tests(unittest.TestCase):
 def test_raw_files_never_open_before_complete_metadata_and_combined_gate(self):
  with TemporaryDirectory()as tmp:
   root=Path(tmp);parent,refs=setup(root);opened=[];real_open=Path.open;scorebytes=400;rawbytes=sum(Path(refs[k]['path']).stat().st_size for k in ('raw_inputs','raw_selection'))
   # Enough for B's score-only gate, one byte short for C's added raw objects.
   memory=5*1024**3+32*(scorebytes+rawbytes)-1
   def reader(path,*args,**kwargs):
    if path.name in ('raw_inputs.json','raw_selection.json'):opened.append(path.name);raise AssertionError('Large raw read before budget gate')
    return real_open(path,*args,**kwargs)
   def metadata():
    m.resource_gate(score_bytes=scorebytes)
    return {},{}, {},[(None,None)]*306,scorebytes
   with patch.multiple(m,PARENT=parent,OUTPUT=root/'out',INDEX_SHA=refs['index']['sha256'],PUBLICATION_SHA=refs['publication']['sha256'],PRODUCER_SHA='a'*64,BOUND={'pending_fixture':(str(root/'p'),'a'*64)}),patch.object(m,'load_metadata',side_effect=metadata)as loader,patch.object(m,'source_sets'),patch.object(m,'available_memory',return_value=memory),patch.object(m.shutil,'disk_usage',return_value=type('D',(),{'free':10**12})()),patch.object(Path,'open',reader):
    with self.assertRaisesRegex(ValueError,'saved outputs'):m.readback(execute=True)
   self.assertEqual(loader.call_count,1);self.assertEqual(opened,[]);self.assertFalse((root/'out').exists())

 def test_size_authenticated_reads_occur_only_after_both_gates(self):
  with TemporaryDirectory()as tmp:
   root=Path(tmp);parent,refs=setup(root);events=[];real_open=Path.open
   def reader(path,*args,**kwargs):
    if path.name in ('raw_inputs.json','raw_selection.json'):events.append('open:'+path.name)
    return real_open(path,*args,**kwargs)
   def metadata():
    events.append('all306metadata');return {},{},{},[(None,None)]*306,400
   def gate(**kw):events.append(('resource',kw))
   with patch.multiple(m,PARENT=parent,OUTPUT=root/'out',INDEX_SHA=refs['index']['sha256'],PUBLICATION_SHA=refs['publication']['sha256'],PRODUCER_SHA='a'*64,BOUND={'fixture':(str(root/'p'),'a'*64)}),patch.object(m,'load_metadata',side_effect=metadata),patch.object(m,'source_sets'),patch.object(m,'resource_gate',side_effect=gate),patch.object(m,'inspect_output_envelopes',side_effect=StopAfterLoad),patch.object(Path,'open',reader):
    with self.assertRaises(StopAfterLoad):m.readback(execute=True)
   self.assertEqual(events[0],'all306metadata');self.assertEqual(events[1][0],'resource')
   self.assertEqual(events[1][1],dict(score_bytes=400,preserved_output_bytes=sum(Path(refs[k]['path']).stat().st_size for k in ('raw_inputs','raw_selection'))))
   self.assertEqual(events[2:],['open:raw_inputs.json','open:raw_selection.json'])

 def test_conservative_threshold_and_exact_types(self):
  with TemporaryDirectory()as tmp,patch.object(m,'OUTPUT',Path(tmp)/'absent'/'out'),patch.object(m.shutil,'disk_usage',return_value=type('D',(),{'free':10**12})()):
   needed=5*1024**3+32*(100+200)
   with patch.object(m,'available_memory',return_value=needed):m.resource_gate(score_bytes=100,preserved_output_bytes=200)
   with patch.object(m,'available_memory',return_value=needed-1),self.assertRaises(ValueError):m.resource_gate(score_bytes=100,preserved_output_bytes=200)
   for invalid in (True,-1,1.0):
    with self.subTest(invalid=invalid),self.assertRaises(ValueError):m.resource_gate(preserved_output_bytes=invalid)

if __name__=='__main__':unittest.main()
