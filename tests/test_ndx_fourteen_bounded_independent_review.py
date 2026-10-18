"""Independent bounded-run counterexamples; synthetic inputs only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_fourteen_incremental_bounded_refit_20260919 import fixture
from scripts import ndx_fourteen_incremental_bounded_refit_20260919 as m


class IndependentBoundedReview(unittest.TestCase):
    def test_fitter_cannot_mutate_selected_then_return_original_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); snapshot,tasks,panel,result=fixture(root)
            def altered(**kwargs):
                sid=next(iter(kwargs['selected']))
                kwargs['selected'][sid]['risk_chain']='fabricated'
                return result
            with patch.object(m,'prepare',return_value=(snapshot,tasks,panel)), patch.object(m,'full',return_value={}), patch.object(m.original.archive,'load_contract',return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',side_effect=altered):
                with self.assertRaises(ValueError):
                    m.run_bounded('x','y',root/'tasks',max_new=1)
                self.assertEqual(list((root/'tasks').glob('index_*.json')),[])

    def test_marker_changed_or_deleted_during_fit_prevents_publication(self):
        for remove in (False,True):
            with self.subTest(remove=remove),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);snapshot,tasks,panel,result=fixture(root)
                def altered(**kwargs):
                    marker=next((root/'tasks').glob('*.started.json'))
                    marker.unlink() if remove else marker.write_text('{}')
                    return result
                with patch.object(m,'prepare',return_value=(snapshot,tasks,panel)), patch.object(m,'full',return_value={}), patch.object(m.original.archive,'load_contract',return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',side_effect=altered) as fit:
                    with self.assertRaises((ValueError,FileNotFoundError)):
                        m.run_bounded('x','y',root/'tasks',max_new=1)
                    with self.assertRaises(ValueError):
                        m.run_bounded('x','y',root/'tasks',max_new=1)
                    self.assertEqual(fit.call_count,1)
                    self.assertEqual(list((root/'tasks').glob('index_*.json')),[])

    def test_equal_label_cannot_hide_unequal_targets_with_passing_risks(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); snapshot,tasks,panel,result=fixture(root)
            task=m.unpack(tasks[0]); task.pop('task_id')
            task['weight_spec']='equal_weight'
            task['task_id']=m.original.digest(task)
            result['weight_spec']='equal_weight'
            sids=sorted(result['targets'])
            result['targets'][sids[0]]['target_weight']=.26
            result['targets'][sids[1]]['target_weight']=.24
            # A relaxed-but-valid risk vector must still obey its explicit equal spec.
            m.original.check_result(result,task,panel)
            with patch.object(m,'prepare',return_value=(snapshot,(m.pack(task),),panel)), patch.object(m,'full',return_value={}), patch.object(m.original.archive,'load_contract',return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',return_value=result):
                with self.assertRaises(ValueError):
                    m.run_bounded('x','y',root/'tasks',max_new=1)
                self.assertEqual(list((root/'tasks').glob('index_*.json')),[])

    def test_all_old_references_are_excluded_from_fit_queue(self):
        rows = []
        old_ids = set()
        for i in range(31828):
            task = {'synthetic_input': i}
            identifier = m.original.digest(task)
            old = i < 764
            if old:
                old_ids.add(identifier)
            rows.append(dict(task=task, task_id=identifier, result_reused=False,
                             input_equivalent_to_old_task=old,
                             completed_old_result_verified=old,
                             completed_old_result_reference={'path': 'old', 'sha256': 'a'*64} if old else None,
                             old_equivalent_task_id=identifier if old else None,
                             status='OLD_INPUT_EQUIVALENT_RESULT_REFERENCE_VERIFIED_NOT_IMPORTED' if old else 'PENDING_OLD_OR_NEW'))
        value = dict(schema='SOURCE_BOUND_FOURTEEN_INCREMENTAL_PLAN_V1',
                     delta=dict(tasks=rows, old_canonical_count=764, new_canonical_count=31828,
                                input_equivalent_old_count=764, new_input_count=31064,
                                completed_old_reference_count=764),
                     **dict.fromkeys(('result_import_performed', 'fit_performed', 'automatic_refit_authorized', 'point_in_time_verified', 'promotion_allowed'), False))
        pending, references = m.select_new_tasks(value)
        self.assertEqual(len(pending), 31064)
        self.assertEqual(len(references), 764)
        self.assertFalse(old_ids & {m.unpack(t)['task_id'] for t in pending})
        rows[0]['input_equivalent_to_old_task'] = False
        with self.assertRaises(ValueError):
            m.select_new_tasks(value)

    def test_resigned_result_boolean_zero_rejected_on_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot, tasks, panel, result = fixture(root)
            with patch.object(m, 'prepare', return_value=(snapshot,tasks,panel)), patch.object(m, 'full', return_value={}), patch.object(m.original.archive, 'load_contract', return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original.fitter, 'refit_dynamic_cutoff_weights', return_value=result) as fit:
                first = m.run_bounded('x', 'y', root/'tasks', max_new=1)
                index = json.loads(Path(first['index_reference']['path']).read_bytes())
                target = Path(index['entries'][0]['path'])
                value = json.loads(target.read_bytes())
                value['old_results_imported'] = False
                target.write_bytes(m.pack(value))
                index['entries'][0]['sha256'] = m.sha(target)
                resign = root/'resigned_index.json'
                resign.write_bytes(m.pack(index))
                with self.assertRaises(ValueError):
                    m.run_bounded('x','y',root/'tasks',max_new=0,index_path=resign,index_sha256=m.sha(resign))
                self.assertEqual(fit.call_count, 1)

    def test_resigned_index_finalization_type_and_deleted_task_source_rejected(self):
        for defect in ('finalized_bool','deleted_source'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);snapshot,tasks,panel,result=fixture(root)
                with patch.object(m,'prepare',return_value=(snapshot,tasks,panel)), patch.object(m,'full',return_value={}), patch.object(m.original.archive,'load_contract',return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',return_value=result) as fit:
                    first=m.run_bounded('x','y',root/'tasks',max_new=1)
                    index=json.loads(Path(first['index_reference']['path']).read_bytes())
                    if defect=='finalized_bool':
                        index['finalized_after_full_source_verification']=1
                    else:
                        target=Path(index['entries'][0]['path']); value=json.loads(target.read_bytes())
                        value['historical_expected_source_hashes'].pop(str(root/'input.txt'))
                        # Correctly re-sign both the altered task and its external index.
                        target.write_bytes(m.pack(value));index['entries'][0]['sha256']=m.sha(target)
                    ref=root/'resigned_index.json';ref.write_bytes(m.pack(index))
                    with self.assertRaises(ValueError):
                        m.run_bounded('x','y',root/'tasks',max_new=0,index_path=ref,index_sha256=m.sha(ref))
                    self.assertEqual(fit.call_count,1)

    def test_remote_orphan_and_exclusive_marker_race_refuse_before_fit(self):
        for mode in ('remote_orphan', 'marker_race'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); snapshot,tasks,panel,result=fixture(root)
                folder=root/'tasks';folder.mkdir()
                original_publish=m.original.exclusive_publish
                def publish(path,value):
                    if str(path).endswith('.started.json'):
                        Path(path).write_text('{}')
                    return original_publish(path,value)
                if mode=='remote_orphan':
                    (folder/('f'*64+'.json.started.json')).write_text('{}')
                with patch.object(m,'prepare',return_value=(snapshot,tasks,panel)), patch.object(m,'full',return_value={}), patch.object(m.original.archive,'load_contract',return_value=dict(authority_source_hashes={},rows={})), patch.object(m.original,'exclusive_publish',side_effect=publish if mode=='marker_race' else original_publish), patch.object(m.original.fitter,'refit_dynamic_cutoff_weights',return_value=result) as fit:
                    with self.assertRaises((ValueError,FileExistsError)):
                        m.run_bounded('x','y',folder,max_new=1)
                    self.assertEqual(fit.call_count,0)


if __name__ == '__main__':
    unittest.main()
