from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from scripts import ndx_dated_first_economic_comparison_20261003 as core


def saved_metadata():
    docs={}
    for role in core.BOUND:
        if role.endswith('_reader'):continue
        ref=core.ref(role);blob=Path(ref['path']).read_bytes()
        if core.sha(blob)!=ref['sha256']:raise ValueError('Metadata fixture source drift')
        docs[role]=core.loads(blob)
    for row in docs['account_audit']['rows']:
        role=row['track'];docs[role+'_postcheck']=core.loads(Path(row['postcheck_reference']['path']).read_bytes());docs[role+'_started']=core.loads(Path(docs[role+'_account']['started_reference']['path']).read_bytes())
    return docs

class Tests(unittest.TestCase):
    def test_real_saved_parent_metadata_projection_not_comparison(self):
        # Metadata/schema linkage only; no core metrics function/engine/audit run.
        docs=saved_metadata();args=core.project_inputs(docs)
        self.assertEqual(args['candidate_account']['schema'],'ndx_dynamic_frozen_execution_research_v2')
        self.assertEqual(len(args['candidate_account']['daily']),127)
        self.assertEqual(set(args['source_references']),{'candidate_account','incumbent_account','continuous','nav_metrics'})
        docs['account_audit']['rows'][0]['input_reference']['sha256']='0'*64
        with self.assertRaises(ValueError):core.project_inputs(docs)

    def test_different_publication_or_reader_rejected(self):
        docs=saved_metadata();docs['continuous_audit']['reader_sha256']='f'*64
        with self.assertRaises(ValueError):core.project_inputs(docs)
        docs=saved_metadata();docs['nav_publication']['status']='PUBLISHED_SOMETHING_UNRELATED'
        with self.assertRaises(ValueError):core.project_inputs(docs)

    def test_receipt_drift_failure_is_not_retryable(self):
        result=dict(schema='DATED_SAME_WINDOW_ECONOMIC_DIAGNOSTIC_V1',status='SINGLE_PATH_DIAGNOSTIC_ONLY',formal_comparison_passed=False,winner_selected=False)
        fake=SimpleNamespace(compare_dated_paths=lambda **kw:result)
        docs={k:{} for k in ('account_audit','continuous_audit','nav_audit')}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'new';n=[0]
            def guard(s):
                n[0]+=1
                if n[0]==3:raise ValueError('postreceipt source drift')
            with patch.object(core,'OUTPUT',out),patch.object(core,'load_inputs',return_value=(docs,{},fake)),patch.object(core,'project_inputs',return_value={}),patch.object(core,'guard',side_effect=guard):
                with self.assertRaises(ValueError):core.run(execute=True)
                self.assertTrue((out/'comparison.json').exists());self.assertTrue((out/'publication.json').exists());self.assertTrue((out/'failure.json').exists())
                with self.assertRaises(ValueError):core.run(execute=True)

    def test_no_execute_and_source_conflict(self):
        with patch.object(core,'load_inputs') as load:
            with self.assertRaises(ValueError):core.run()
            with self.assertRaises(ValueError):core.run(execute=1)
            load.assert_not_called()
        with self.assertRaises(ValueError):core.guard({str(core.CORE):'0'*64})

if __name__=='__main__':unittest.main()
