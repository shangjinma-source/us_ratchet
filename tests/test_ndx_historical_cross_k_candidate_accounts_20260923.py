import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_historical_cross_k_candidate_accounts_20260923 as m


class Tests(unittest.TestCase):
    def setup_state(self,skip=False):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);folder=Path(tmp.name)
        ref={'path':'audit','sha256':'a'*64};row=dict(task_id='job',task={},fit_checkpoint_reference={'path':'fit','sha256':'b'*64},audited_detail={})
        auth=dict(audit_reference=ref,queue=[row],inputs={},numerical={},sources={},runtime=m.prefix.runtime(),partition={})
        prepared=dict(status='NOT_EXECUTED_ORIGINAL_FIVE_RISK_FAILURE' if skip else 'READY_FOR_SOURCE_BOUND_SINGLE_ATTEMPT',failed_original_risk_checks=['MIN_SINGLE_WEIGHT'] if skip else [],normalization_evidence={},
            account=None if skip else dict(calendar=['2026-03-18'],contract={},effective_schedule=[],selected=dict(arguments={'schedule':[]},original_schedule=[],columns={})))
        for name,value in [('authority',auth),('bind_task',prepared),('external_reference',m.EXTERNAL_ACCOUNT),('full',{}),('restore',({},{}))]:
            p=patch.object(m,name,return_value=value);p.start();self.addCleanup(p.stop)
        p=patch.object(m.single.candidate,'simulate_dynamic_frozen_execution_research',return_value={'raw':'ledger'});engine=p.start();self.addCleanup(p.stop)
        return folder,auth,prepared,engine

    def test_one_engine_only_and_strict_external_resume(self):
        folder,auth,prepared,engine=self.setup_state();first=m.run(folder=folder,max_new=1)
        self.assertEqual(first['processed_this_invocation'],1)
        second=m.run(folder=folder,max_new=0,index_path=first['index_reference']['path'],index_sha256=first['index_reference']['sha256'])
        self.assertEqual(second['completed'],1);self.assertEqual(engine.call_count,1)

    def test_risk_failure_is_saved_with_no_raw_or_engine(self):
        folder,_,_,engine=self.setup_state(True);result=m.run(folder=folder,max_new=1)
        engine.assert_not_called();self.assertTrue((folder/'job/result.json').exists());self.assertFalse((folder/'job/raw.json').exists());self.assertEqual(result['completed'],1)

    def test_raw_survives_audit_failure_and_cannot_retry(self):
        folder,_,_,engine=self.setup_state()
        with patch.object(m,'restore',side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):m.run(folder=folder,max_new=1)
        self.assertTrue((folder/'job/raw.json').exists());self.assertTrue((folder/'job/failure.json').exists())
        with self.assertRaisesRegex(ValueError,'Unindexed'):m.run(folder=folder,max_new=1)
        self.assertEqual(engine.call_count,1)

    def test_marker_and_argument_mutation_preserve_raw_but_not_result(self):
        for defect in ('marker','arguments'):
            with self.subTest(defect=defect):
                folder,_,_,engine=self.setup_state()
                def mutate(**kwargs):
                    if defect=='marker':(folder/'job/started.json').write_text('{}')
                    else:kwargs['schedule'].append({'changed':True})
                    return {'raw':'ledger'}
                engine.side_effect=mutate
                with self.assertRaises(ValueError):m.run(folder=folder,max_new=1)
                self.assertTrue((folder/'job/raw.json').exists());self.assertFalse((folder/'job/result.json').exists())

    def test_budget_and_unreviewed_task_cannot_be_processed(self):
        for value in (True,-1,11):
            with self.assertRaises(ValueError):m.run(folder='unused',max_new=value)
        folder,auth,_,engine=self.setup_state();auth['queue']=[]
        result=m.run(folder=folder,max_new=10);self.assertEqual(result['completed'],0);engine.assert_not_called()


if __name__=='__main__':unittest.main()
