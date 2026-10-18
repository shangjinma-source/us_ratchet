from copy import deepcopy
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from scripts import ndx_multidecision_nav_reference_metrics_independent_readback_20261003 as r
from scripts import ndx_multidecision_nav_reference_metrics_20261003 as producer
from test_ndx_multidecision_nav_reference_metrics_20261003 import physical as parents

def physical(root,missing=False):
 bound=parents(root,missing);parent=root/'published'
 # Only fixture construction uses the producer; the reader's oracle is independent.
 with patch.object(producer,'ROOT',root),patch.object(producer,'BOUND',bound),patch.object(producer,'OUTPUT',parent),patch.object(producer,'resource'):
  mr=producer.run(execute=True)
 return dict(ROOT=root,BOUND=bound,PARENT=parent,OUTPUT=root/'readback',METRICS_SHA=mr['sha256'],PUBLICATION_SHA=r.hashfile(parent/'publication.json'))

class Tests(unittest.TestCase):
 def test_future_bindings_no_io(self):
  with patch.object(r,'METRICS_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
   with self.assertRaisesRegex(ValueError,'pending'):r.load_inputs()
 def test_complete_physical_chain_and_missing_mode(self):
  for missing in (False,True):
   with self.subTest(missing=missing),tempfile.TemporaryDirectory() as td:
    settings=physical(Path(td),missing)
    with patch.multiple(r,**settings),patch.object(producer,'run',side_effect=AssertionError('no producer')):
     rr=r.readback(execute=True)
     with self.assertRaisesRegex(ValueError,'Create only'):r.readback(execute=True)
    report=r.decode(Path(rr['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertEqual(report['inspection']['interval_count'],119);self.assertEqual(report['inspection']['missing_by_mode'][r.MODES[0]],int(missing));self.assertFalse(report['alignment_conversion_reaudited']);self.assertFalse(report['account_executed'])
 def test_resigned_calendar_metrics_and_original_rows_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   settings=physical(Path(td))
   with patch.multiple(r,**settings):c=r.load_inputs()
   for mode in ('calendar','metric','originalrow','flag'):
    d=deepcopy(c['docs']);saved=deepcopy(c['document']['metrics'])
    if mode=='calendar':
     obj=d['account_inputs']['inputs'];obj['rows'][2]['tracks'][1]['stateful_input']['calendar'].pop(3);obj['content_sha256']=r.digest({k:v for k,v in obj.items() if k!='content_sha256'})
    elif mode=='metric':saved['modes'][r.MODES[1]]['metrics']['maximum_drawdown']['numerator']='0'
    elif mode=='originalrow':saved['modes'][r.MODES[0]]['observations'][5]['original_alignment_row']['nav_date_fx_used_for_conversion']=True
    else:saved['source_bytes_authenticated']=0
    with self.subTest(mode=mode),self.assertRaises(ValueError):r.inspect_reference(d,c['refs'],saved)
 def test_postreport_directory_drift_retained_and_no_retry(self):
  with tempfile.TemporaryDirectory() as td:
   settings=physical(Path(td));save=r.save
   def write(name,obj):
    rr=save(name,obj)
    if name=='independent_readback.json':(settings['PARENT']/'alien').write_bytes(b'bad')
    return rr
   with patch.multiple(r,**settings),patch.object(r,'save',side_effect=write):
    with self.assertRaisesRegex(ValueError,'inventory'):r.readback(execute=True)
    with self.assertRaisesRegex(ValueError,'Create only'):r.readback(execute=True)
   self.assertTrue((settings['OUTPUT']/'failure.json').exists());self.assertTrue((settings['OUTPUT']/'independent_readback.json').exists())

if __name__=='__main__':unittest.main()
