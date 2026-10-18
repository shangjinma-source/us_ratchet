import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
from scripts import ndx_dated_economic_batch_20261003 as m


class Tests(unittest.TestCase):
    def test_dynamic_stage_sources_never_enter_base_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);publication=root/'publication.json';publication.write_text('{}')
            base={'base':'a'*64};guarded=[];calls=[]
            modules={k:SimpleNamespace(load_common=lambda:object()) for k in m.PINS if k!='summary_reader'}
            modules['input_readback'].run=lambda *refs:dict(path='audited',sha256='c'*64)
            checked=dict(summary={'rows':[]},initial={'rows':[]},order=[],sources=base)
            def read(ref,sources):
                sources[ref['path']]=ref['sha256'];calls.append(ref['path']);return {'status':'PASS'}
            def queue(ids,**kw):
                for i in range(3):
                    kw['validate_stage']('a'*64,'inputs',dict(path='new'+str(i),sha256='b'*64),{})
                    kw['stage_functions']['input_readback']('a'*64,{'inputs':dict(path=str(root/'inputs.json'),sha256='b'*64)})
                    kw['verify_sources']()
                return 'synthetic-only'
            with patch.object(m,'preflight',return_value=checked),patch.object(m,'load_module',side_effect=lambda k,s:modules[k]),patch.object(m,'guard',side_effect=lambda s:guarded.append(dict(s))),patch.object(m,'read',side_effect=read),patch.object(m,'execute_queue',side_effect=queue):
                self.assertEqual(m.run(execute=True),'synthetic-only')
            self.assertEqual(base,{'base':'a'*64});self.assertEqual(len(calls),6)
            self.assertEqual(sum(g==base for g in guarded),4)
            self.assertTrue(all(len(g)==1 for g in guarded))

    def execute(self,root,**kwargs):
        return m.execute_queue(['a'*64,'b'*64],initial_rows=[],output=root/'batch',**kwargs)

    def test_predispatch_guard_failure_retains_current_unattempted(self):
        with tempfile.TemporaryDirectory() as tmp:
            callback=Mock(return_value=dict(path='saved',sha256='a'*64));guard=Mock(side_effect=[None,ValueError('before first dispatch')])
            ref=self.execute(Path(tmp),stage_functions=dict.fromkeys(m.STAGES,callback),verify_sources=guard)
            d=json.loads(Path(ref['path']).read_bytes());callback.assert_not_called()
            self.assertEqual(d['undispatched_task_ids'],['a'*64,'b'*64]);self.assertEqual(d['unresolved_task_ids'],[])
            self.assertFalse(d['failure']['stage_may_have_written_evidence'])

    def test_resource_probe_exception_is_recorded_without_dispatch(self):
        for probe in (Mock(side_effect=OSError('volume unavailable')),lambda:True):
            with tempfile.TemporaryDirectory() as tmp:
                callback=Mock();ref=self.execute(Path(tmp),stage_functions=dict.fromkeys(m.STAGES,callback),verify_sources=lambda:None,resource_check=probe)
                d=json.loads(Path(ref['path']).read_bytes());callback.assert_not_called()
                self.assertEqual(d['undispatched_task_ids'],['a'*64,'b'*64]);self.assertEqual(d['unresolved_task_ids'],[])
                self.assertTrue((Path(tmp)/'batch'/'failure.json').exists())

    def test_partial_stage_preserved_and_threshold_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            count=[0]
            def guard():
                count[0]+=1
                if count[0]==3:raise ValueError('after first callback')
            callback=Mock(return_value=dict(path='saved',sha256='a'*64))
            ref=self.execute(Path(tmp),stage_functions=dict.fromkeys(m.STAGES,callback),verify_sources=guard,resource_check=lambda:m.MIN_FREE_BYTES)
            d=json.loads(Path(ref['path']).read_bytes());callback.assert_called_once()
            self.assertEqual(d['unresolved_task_ids'],['a'*64]);self.assertEqual(d['undispatched_task_ids'],['b'*64])
            self.assertEqual(d['failure']['completed_stage_references']['inputs'],dict(path='saved',sha256='a'*64))

if __name__=='__main__':unittest.main()
