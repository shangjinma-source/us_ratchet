from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_dated_fixed_task_preparation_20261003 as m
from backtest import ndx_dated_fixed_task_preparation_research as core
from test_ndx_dated_fixed_task_preparation_research import fixture as pure_fixture


def fixture():
    a=pure_fixture();refs={k:dict(path=k+'.json',sha256='a'*64) for k in m.BOUND}
    refs.update(training=a['training_reference'],training_readback=a['training_readback_reference'],prior_preparation=a['prior_preparation_reference'],original_plan=a['original_plan_reference'])
    flags=dict(fit_performed=False,point_in_time_verified=False,execution_authorized=False,legal_training_input_admitted=False)
    typed=dict(schema='DATED_CONDITIONAL_TRAINING_PANEL_DOCUMENT_V1',panel=a['training_panel'],source_hashes={},**flags)
    pub=dict(status='PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED',panel_reference=refs['training'],source_hashes={},**flags)
    audit=dict(schema=m.AUDIT_SCHEMA,status='PASS',panel_sha256=refs['training']['sha256'],publication_sha256=refs['training_publication']['sha256'])
    prior=a['prior_preparation'];prior['source_hashes']={}
    oldpub=dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1',status='PREPARED_NOT_ATTEMPTED',preparation_reference=refs['prior_preparation'],source_hashes={})
    oldaudit=dict(status='PASS',preparation_sha256=refs['prior_preparation']['sha256'],publication_sha256=refs['prior_publication']['sha256'])
    return dict(training=typed,training_publication=pub,training_readback=audit,prior_preparation=prior,prior_publication=oldpub,prior_audit=oldaudit,original_plan=dict(plan=a['original_lazy_plan'])),refs


class WrapperTests(unittest.TestCase):
    def test_pending_anchor_no_files(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'):
            self.assertEqual(m.run()['status'],'NOT_EXECUTED')
            pending=deepcopy(m.BOUND);pending['training_readback']=(pending['training_readback'][0],None)
            with patch.object(m,'BOUND',pending):
                with self.assertRaises(ValueError):m.run(execute=True)
            self.assertFalse(m.OUTPUT.exists())

    def test_explicit_original_and_new_publication_bindings(self):
        docs,refs=fixture();args=m.project_inputs(docs,refs)
        self.assertEqual(args['training_panel'],docs['training']['panel'])
        for role,key in [('training_readback','panel_sha256'),('prior_audit','preparation_sha256')]:
            bad=deepcopy(docs);bad[role][key]='b'*64
            with self.assertRaises(ValueError):m.project_inputs(bad,refs)

    def test_runtime_drift_after_raw_output_and_no_retry(self):
        docs,refs=fixture();result=dict(schema=core.SCHEMA,materialized_task_count=1632,new_fit_count=0);result['content_sha256']=core.digest(result)
        with tempfile.TemporaryDirectory() as temp,patch.object(m,'OUTPUT',Path(temp)/'new'),patch.object(m,'load_inputs',return_value=(docs,refs,{},m.runtime(),core)),patch.object(m,'project_inputs',return_value={}),patch.object(core,'prepare_dated_tasks',return_value=result),patch.object(m,'guard',side_effect=[None,None,ValueError('runtime changed')]):
            with self.assertRaises(ValueError):m.run(execute=True)
            self.assertTrue((m.OUTPUT/'preparation.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
            with self.assertRaises(ValueError):m.run(execute=True)

if __name__=='__main__':unittest.main()
