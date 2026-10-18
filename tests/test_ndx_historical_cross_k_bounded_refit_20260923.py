import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_historical_cross_k_bounded_refit_20260923 as m


class Tests(unittest.TestCase):
    def setup_runner(self,effect=None):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=Path(tmp.name)
        selected={'s':dict(ticker='A',issuer_id='i',risk_chain='r')}
        task=dict(selected=selected,holding_count=1,weight_spec='equal_weight',cutoff='2026-03-18',parameters=m.scalar.PARAMS,previous_target_weights=None)
        task['task_id']=m.producer.digest(task)
        frame=pd.DataFrame({'A':[.01]},index=pd.DatetimeIndex(['2026-03-18']))
        snapshot=dict(plan_reference={'path':'plan','sha256':'a'*64},independent_plan_audit_reference={},sources={},numerical={},runtime=m.runtime(),base_partition={'live_verified_source_hashes':{}},canonical_task_count=2,pending_planned=1,external_reference=m.producer.TARGET,coordinates=selected)
        for name,value in [('prepare',(m.pack(snapshot),(m.pack(task),),frame)),('full',{}),('validate_result',{'risk_pass':True})]:
            p=patch.object(m,name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch.object(m.fitter,'refit_dynamic_cutoff_weights',return_value={'raw':'result'},side_effect=effect);engine=p.start();self.addCleanup(p.stop)
        return folder,snapshot,task,engine

    def test_actual_historical_result_validation_without_refit(self):
        target=json.loads(Path(m.producer.TARGET['path']).read_bytes());inputs=json.loads(Path(m.producer.INPUT['path']).read_bytes())
        panel=m.producer.historical_view(inputs)
        report=m.validate_result(target['result'],target['task'],panel['returns'],target['result']['source_hashes'])
        self.assertTrue(report['risk_pass'])

    def test_budget_failclosed_and_exact_reference_not_queued(self):
        with patch.object(m,'AUDIT_SHA',None):
            with self.assertRaisesRegex(ValueError,'Await'):m.prepare()
        for budget in (True,-1,101):
            with self.assertRaises(ValueError):m.run(folder='unused',max_new=budget)
        target=json.loads(Path(m.producer.TARGET['path']).read_bytes());task={k:v for k,v in target['task'].items() if k!='task_id'}
        row=dict(task=task,task_id=target['job_id'],result_reused=False,status='COMPLETED_HISTORICAL_RESULT_EXTERNAL_REFERENCE_NOT_IMPORTED',completed_external_reference=m.producer.TARGET)
        plan=dict(schema='HISTORICAL_FOURTEEN_CROSS_K_TASK_PLAN_V1',cutoff='2026-03-18',tasks=[row],canonical_task_count=1,completed_external_reference_count=1,pending_historical_fit_count=0,**dict.fromkeys(m.producer.FALSE,False))
        self.assertEqual(m.select_pending(plan),())
        plan['tasks'].append(copy.deepcopy(row))
        with self.assertRaises(ValueError):m.select_pending(plan)

    def test_one_fit_resume_zero_and_raw_preserved(self):
        folder,snapshot,task,engine=self.setup_runner()
        first=m.run(folder=folder,max_new=1)
        self.assertEqual(first['new_fits_this_invocation'],1);self.assertTrue((folder/task['task_id']/'raw.json').exists())
        self.assertIs(json.loads((folder/task['task_id']/'raw.json').read_bytes())['fit_performed'],True)
        self.assertIs(json.loads((folder/task['task_id']/'result.json').read_bytes())['fit_performed'],True)
        index=json.loads(Path(first['index_reference']['path']).read_bytes());self.assertNotIn('fit_performed',index);self.assertIs(index['contains_new_historical_fit_results'],True)
        resumed=m.run(folder=folder,max_new=0,index_path=first['index_reference']['path'],index_sha256=first['index_reference']['sha256'])
        self.assertEqual(resumed['completed_new'],1);self.assertEqual(engine.call_count,1)

    def test_baseexception_failure_or_orphan_cannot_retry(self):
        folder,_,task,engine=self.setup_runner(effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):m.run(folder=folder,max_new=1)
        self.assertTrue((folder/task['task_id']/'failure.json').exists())
        with self.assertRaisesRegex(ValueError,'Unindexed'):m.run(folder=folder,max_new=1)
        self.assertEqual(engine.call_count,1)

    def test_fitter_ram_mutation_is_preserved_raw_but_never_completed(self):
        def mutate(**kwargs):kwargs['returns'].iloc[0,0]=.2;return {'raw':'bad'}
        folder,_,task,engine=self.setup_runner(effect=mutate)
        with self.assertRaisesRegex(ValueError,'mutated'):m.run(folder=folder,max_new=1)
        self.assertTrue((folder/task['task_id']/'raw.json').exists());self.assertFalse((folder/task['task_id']/'result.json').exists())

    def test_marker_mutation_after_engine_still_preserves_raw(self):
        folder,_,task,engine=self.setup_runner()
        def mutate(**kwargs):(folder/task['task_id']/'started.json').write_text('{}');return {'raw':'ledger'}
        engine.side_effect=mutate
        with self.assertRaisesRegex(ValueError,'attempt'):m.run(folder=folder,max_new=1)
        self.assertTrue((folder/task['task_id']/'raw.json').exists());self.assertFalse((folder/task['task_id']/'result.json').exists())


if __name__=='__main__':unittest.main()
