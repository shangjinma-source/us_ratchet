import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_single_replacement_path_comparison_20261003 import physical
from test_ndx_single_replacement_path_comparison_independent_readback_20261003 import published
from scripts import ndx_single_replacement_path_comparison_20261003 as p
from scripts import ndx_single_replacement_path_comparison_independent_readback_20261003 as r

class Tests(unittest.TestCase):
 def test_authenticated_extra_reference_row_rejected_before_numeric_compile(self):
  with tempfile.TemporaryDirectory()as tmp,physical(Path(tmp))as registration:
   reg=p.decode(Path(registration['path']).read_bytes());refs=reg['input_references']
   path=Path(refs['reference']['path']);doc=p.decode(path.read_bytes());doc['rows'].append(doc['rows'][-1]);path.write_bytes(p.enc(doc));refs['reference']['sha256']=p.filehash(path)
   pubpath=Path(refs['reference_publication']['path']);pub=p.decode(pubpath.read_bytes());pub['comparison_reference']=refs['reference'];pubpath.write_bytes(p.enc(pub));refs['reference_publication']['sha256']=p.filehash(pubpath)
   Path(registration['path']).write_bytes(p.enc(reg));registration['sha256']=p.filehash(registration['path'])
   bound=dict(p.BOUND)
   for key in ('reference','reference_publication'):bound[key]=(refs[key]['path'],refs[key]['sha256'])
   private=p.private
   def only_io(reference,metrics=None):
    if reference['path'] in (refs['pure']['path'],refs['metrics']['path']):raise AssertionError('Numeric before EOF')
    return private(reference,metrics)
   with patch.object(p,'BOUND',bound),patch.object(p,'private',side_effect=only_io),self.assertRaisesRegex(ValueError,'extra reference'):p.run(registration_reference=registration,execute=True)
   self.assertFalse(p.OUTPUT.exists())

 def test_hostile_nonjson_return_raw_fact_and_no_retry(self):
  with tempfile.TemporaryDirectory()as tmp,physical(Path(tmp))as registration:
   c=p.load_inputs(registration)
   class Returned:
    def __repr__(self):raise KeyboardInterrupt('repr interrupted')
   with patch.object(p,'load_inputs',return_value=c),patch.object(c['pure'],'compare_selected_single_replacement_paths',return_value=Returned()),self.assertRaises(ValueError):p.run(registration_reference=registration,execute=True)
   raw=p.decode((p.OUTPUT/'raw_comparison.json').read_bytes());self.assertIs(raw['returned'],True);self.assertEqual(raw['call_count'],1)
   self.assertIs(raw['result_preserved_as_json'],False);self.assertTrue((p.OUTPUT/'failure.json').exists());self.assertFalse((p.OUTPUT/'publication.json').exists())

 def test_reader_resigned_reference_metric_reject(self):
  with tempfile.TemporaryDirectory()as tmp,published(Path(tmp))as args:
   doc=r.decode((r.PARENT/'comparison.json').read_bytes());raw=r.decode((r.PARENT/'raw_comparison.json').read_bytes());pub=r.decode((r.PARENT/'publication.json').read_bytes())
   doc['comparison']['rows'][0]['metrics']['same_flow_zero_trade_control']['annualized_return_diagnostic_decimal']='9'
   raw['result']=doc['comparison'];b=r.encode(raw);(r.PARENT/'raw_comparison.json').write_bytes(b);doc['raw_reference']['sha256']=r.sha(b)
   b=r.encode(doc);(r.PARENT/'comparison.json').write_bytes(b);pub['comparison_reference']['sha256']=r.sha(b);pub['raw_reference']=doc['raw_reference']
   b=r.encode(pub);(r.PARENT/'publication.json').write_bytes(b);args['comparison_reference']=pub['comparison_reference'];args['publication_reference']['sha256']=r.sha(b)
   with self.assertRaises(ValueError):r.readback(**args)
   failure=r.decode((r.OUTPUT/'failure.json').read_bytes());self.assertIs(failure['arithmetic_inspection_completed'],False)
   self.assertFalse((r.OUTPUT/'independent_readback.json').exists())

if __name__=='__main__':unittest.main()

