import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_multidecision_path_comparison_source_adapter_20261003 import physical
from scripts import ndx_multidecision_path_comparison_20261003 as p

ADAPTER_SHA='3e9690118f50248dbf939f613cc7cf0fc5dabbb7ee2db5a4d3be79b33285d32b'

def configured(root):
    return patch.multiple(p,BOUND=physical(root/'sources'),OUTPUT=root/'output',ADAPTER=(p.ADAPTER[0],ADAPTER_SHA))


class Tests(unittest.TestCase):
    def test_pending_before_read_or_directory(self):
        with patch.object(p,'BOUND',{**p.BOUND,'candidate_inputs':(p.BOUND['candidate_inputs'][0],None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('read')),patch.object(Path,'exists',side_effect=AssertionError('exists')):
            with self.assertRaisesRegex(ValueError,'pending'):p.run(execute=True)
    def test_complete_physical_adapter_private_comparison_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td,configured(Path(td)):
            r=p.run(execute=True);d=json.loads(Path(r['path']).read_bytes());self.assertEqual(len(d['comparison']['rows']),16);self.assertEqual(d['comparison']['counts']['control_metrics'],16);self.assertEqual(len(d['input_references']),20)
            self.assertEqual({q.name for q in p.OUTPUT.iterdir()},{'started.json','raw_result.json','comparison.json','publication.json'})
            self.assertFalse(d['formal_comparison_passed']);self.assertIn('PRIVATE_INSTANCE',d['adapter_configuration_source'])
            with self.assertRaisesRegex(ValueError,'no retry'):p.run(execute=True)
    def test_return_then_source_drift_preserves_raw(self):
        original=p.private_core
        with tempfile.TemporaryDirectory() as td,configured(Path(td)):
            def private(sources):
                core=original(sources);call=core.compare_multidecision_paths
                def changed(**kw):
                    result=call(**kw);Path(p.BOUND['candidate_reader'][0]).write_bytes(b'changed after return');return result
                core.compare_multidecision_paths=changed;return core
            with patch.object(p,'private_core',side_effect=private),self.assertRaisesRegex(ValueError,'drift'):p.run(execute=True)
            raw=json.loads((p.OUTPUT/'raw_result.json').read_bytes());self.assertTrue(raw['returned']);self.assertEqual(raw['result']['track_count'],16);self.assertTrue((p.OUTPUT/'failure.json').exists());self.assertFalse((p.OUTPUT/'publication.json').exists())
    def test_none_exception_and_unserializable_returns_preserved_not_published(self):
        original=p.private_core
        for mode in ('none','exception','badrepr'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td,configured(Path(td)):
                class Bad:
                    def __repr__(self):raise RuntimeError('bad repr')
                def private(sources):
                    core=original(sources)
                    def call(**kwargs):
                        if mode=='exception':raise RuntimeError('original exception')
                        return Bad() if mode=='badrepr' else None
                    core.compare_multidecision_paths=call;return core
                with patch.object(p,'private_core',side_effect=private),self.assertRaises(ValueError):p.run(execute=True)
                raw=json.loads((p.OUTPUT/'raw_result.json').read_bytes());self.assertEqual(raw['returned'],mode!='exception');self.assertIsNone(raw['result']);self.assertFalse((p.OUTPUT/'publication.json').exists())
                if mode=='badrepr':self.assertFalse(raw['original_return_is_json']);self.assertEqual(raw['repr_error']['message'],'bad repr')
    def test_resource_after_return_cannot_discard_raw(self):
        from types import SimpleNamespace
        original=p.private_core;returned=[False]
        with tempfile.TemporaryDirectory() as td,configured(Path(td)):
            def private(sources):
                core=original(sources);call=core.compare_multidecision_paths
                def wrapped(**kwargs):
                    r=call(**kwargs);returned[0]=True;return r
                core.compare_multidecision_paths=wrapped;return core
            with patch.object(p,'private_core',side_effect=private),patch.object(p.shutil,'disk_usage',side_effect=lambda _:SimpleNamespace(free=0 if returned[0] else 10*1024**3)),self.assertRaisesRegex(ValueError,'reserve'):p.run(execute=True)
            raw=json.loads((p.OUTPUT/'raw_result.json').read_bytes());self.assertTrue(raw['returned']);self.assertEqual(raw['result']['track_count'],16);self.assertTrue((p.OUTPUT/'failure.json').exists())
    def test_final_output_and_parent_inventory_drift(self):
        original=p.save
        for mode in ('output','parent'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as td,configured(Path(td)):
                def save(name,value,**kwargs):
                    r=original(name,value,**kwargs)
                    if name=='publication.json':
                        if mode=='output':(p.OUTPUT/'raw_result.json').write_bytes(b'changed')
                        else:(Path(p.BOUND['candidate_execution'][0]).parent/'unexpected.txt').write_bytes(b'new')
                    return r
                with patch.object(p,'save',side_effect=save),self.assertRaises(ValueError):p.run(execute=True)
                self.assertTrue((p.OUTPUT/'failure.json').exists())
                with self.assertRaisesRegex(ValueError,'no retry'):p.run(execute=True)

if __name__=='__main__':unittest.main()
