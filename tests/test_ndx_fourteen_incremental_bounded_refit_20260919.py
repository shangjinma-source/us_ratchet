import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_latest_conditional_all_k_refit_20260919 import panel,PARAMETERS
from test_ndx_latest_all_k_independent_review_20260919 import diagnostic
from scripts import ndx_fourteen_incremental_bounded_refit_20260919 as m


def fixture(root):
    p=panel(4);task=m.original.enumerate_plan(p,PARAMETERS,50000)['canonical_tasks'][0]
    source=root/'input.txt';source.write_text('original')
    sources={str(source):m.sha(source)}
    snapshot=dict(reference=dict(path=str(root/'plan.json'),sha256='a'*64),sources=sources,numerical={},old_references=[])
    result=diagnostic(task,p);result['source_hashes']={}
    return m.pack(snapshot),(m.pack(task),),p,result


class BoundedTests(unittest.TestCase):
    def test_unsealed_and_invalid_budget_fail_before_fit(self):
        for budget in (True,-1,101):
            with self.assertRaises(ValueError):m.run_bounded('x','y','z',max_new=budget)
        with self.assertRaises(ValueError):m.prepare('x','y')

    def test_fit_once_external_finalized_resume_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);snapshot,tasks,p,result=fixture(root);contract=dict(authority_source_hashes={},rows={})
            with patch.object(m,'prepare',return_value=(snapshot,tasks,p)),patch.object(m,'full',return_value={}),patch.object(m.original.archive,'load_contract',return_value=contract),patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',return_value=result) as fit:
                first=m.run_bounded('x','y',root/'tasks',max_new=1)
                self.assertEqual(first['new_fits_this_invocation'],1);self.assertEqual(fit.call_count,1)
                second=m.run_bounded('x','y',root/'tasks',max_new=0,index_path=first['index_reference']['path'],index_sha256=first['index_reference']['sha256'])
                self.assertEqual(second['new_fits_this_invocation'],0);self.assertEqual(fit.call_count,1)
                self.assertEqual(second['old_results_imported'],0)
                progress=next((root/'tasks').glob('progress_*.json'))
                with self.assertRaises(ValueError):m.run_bounded('x','y',root/'tasks',max_new=0,index_path=progress,index_sha256=m.sha(progress))

    def test_orphan_and_keyboard_interrupt_never_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);snapshot,tasks,p,result=fixture(root);contract=dict(authority_source_hashes={},rows={})
            with patch.object(m,'prepare',return_value=(snapshot,tasks,p)),patch.object(m,'full',return_value={}),patch.object(m.original.archive,'load_contract',return_value=contract),patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',side_effect=KeyboardInterrupt) as fit:
                with self.assertRaises(KeyboardInterrupt):m.run_bounded('x','y',root/'tasks',max_new=1)
                with self.assertRaises(ValueError):m.run_bounded('x','y',root/'tasks',max_new=1)
                self.assertEqual(fit.call_count,1)
                self.assertEqual(len(list((root/'tasks').glob('*.started.json'))),1)
                self.assertEqual(len(list((root/'tasks').glob('index_*.json'))),0)

    def test_ram_and_unknown_source_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot,tasks,p,_=fixture(Path(directory));expected=m.original.digest(m.original.panel_io.typed_encode(p));sources=m.unpack(snapshot)['sources']
            m.small_verify(snapshot,tasks[0],p,expected,sources)
            with self.assertRaises(ValueError):m.small_verify(snapshot,tasks[0],p,expected,dict(sources,unknown='f'*64))
            p['returns'].iloc[0,0]=.01
            with self.assertRaises(ValueError):m.small_verify(snapshot,tasks[0],p,expected,sources)

    def test_end_source_drift_never_finalizes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);snapshot,tasks,p,result=fixture(root);contract=dict(authority_source_hashes={},rows={})
            def verify(sources):
                for path,h in sources.items():
                    if m.sha(path)!=h:raise ValueError('drift')
                return {}
            def fitting(**kwargs):
                (root/'input.txt').write_text('changed');return result
            with patch.object(m,'prepare',return_value=(snapshot,tasks,p)),patch.object(m,'full',side_effect=verify),patch.object(m.original.archive,'load_contract',return_value=contract),patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',side_effect=fitting):
                with self.assertRaises(ValueError):m.run_bounded('x','y',root/'tasks',max_new=1)
                self.assertEqual(len(list((root/'tasks').glob('index_*.json'))),0)


if __name__=='__main__':unittest.main()
