import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import test_ndx_historical_cross_k_bounded_refit_20260923 as owner
from scripts import ndx_historical_cross_k_bounded_refit_20260923 as m


class HistoricalBoundedReview(unittest.TestCase):
    def fixture(self):
        helper=owner.Tests();self.addCleanup(helper.doCleanups)
        return helper.setup_runner()

    def test_resigned_finalization_and_remote_orphan_refuse_before_any_fit(self):
        folder,snapshot,task,engine=self.fixture()
        saved=m.run(folder=folder,max_new=1)['index_reference']
        index=json.loads(Path(saved['path']).read_bytes())
        self.assertNotIn('fit_performed',index)
        self.assertIs(index['contains_new_historical_fit_results'],True)
        for name in ('raw.json','result.json'):
            self.assertIs(json.loads((folder/task['task_id']/name).read_bytes())['fit_performed'],True)
        changed=copy.deepcopy(index);changed['finalized_after_full_source_verification']=1
        forged=folder/'index_forged.json';forged.write_bytes(m.pack(changed))
        with self.assertRaises(ValueError):m.run(folder=folder,max_new=0,index_path=str(forged),index_sha256=m.sha(forged))
        remote=folder/'other_task';remote.mkdir();(remote/'started.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'Unindexed'):m.run(folder=folder,max_new=1,index_path=saved['path'],index_sha256=saved['sha256'])
        self.assertEqual(engine.call_count,1)

    def test_fitter_selected_mutation_keeps_raw_but_refuses_completion(self):
        folder,snapshot,task,engine=self.fixture()
        def mutate(**kwargs):kwargs['selected']['s']['issuer_id']='wrong';return {'raw':'saved'}
        engine.side_effect=mutate
        with self.assertRaisesRegex(ValueError,'mutated'):m.run(folder=folder,max_new=1)
        self.assertTrue((folder/task['task_id']/'raw.json').exists())
        self.assertFalse((folder/task['task_id']/'result.json').exists())
        with self.assertRaises(ValueError):m.run(folder=folder,max_new=1)
        self.assertEqual(engine.call_count,1)

    def test_source_drift_after_fit_prevents_result_and_final_index(self):
        folder,snapshot,task,engine=self.fixture()
        _,tasks,frame=m.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            code=Path(tmp)/'numerical.py';code.write_text('original')
            snapshot['sources']={str(code):m.sha(code)}
            def mutate(**kwargs):code.write_text('changed');return {'raw':'preserved'}
            engine.side_effect=mutate
            with patch.object(m,'prepare',return_value=(m.pack(snapshot),tasks,frame)):
                with self.assertRaisesRegex(ValueError,'source changed'):m.run(folder=folder,max_new=1)
            self.assertTrue((folder/task['task_id']/'raw.json').exists())
            self.assertFalse((folder/task['task_id']/'result.json').exists())
            self.assertEqual(list(folder.glob('index_*.json')),[])

    def test_latest_date_cannot_be_resigned_into_historical_pending(self):
        target=json.loads(Path(m.producer.TARGET['path']).read_bytes())
        historical={k:v for k,v in target['task'].items() if k!='task_id'}
        reference=dict(task=historical,task_id=target['job_id'],result_reused=False,status='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED',completed_external_reference=m.producer.TARGET)
        latest=copy.deepcopy(historical);latest['cutoff']='2026-09-17'
        pending=dict(task=latest,task_id=m.producer.digest(latest),result_reused=False,status='PENDING_HISTORICAL_FIT',completed_external_reference=None)
        plan=dict(schema='HISTORICAL_FOURTEEN_CROSS_K_TASK_PLAN_V1',cutoff='2026-03-18',tasks=[reference,pending],canonical_task_count=2,completed_external_reference_count=1,pending_historical_fit_count=1,**dict.fromkeys(m.producer.FALSE,False))
        with self.assertRaises(ValueError):m.select_pending(plan)


if __name__=='__main__':unittest.main()
