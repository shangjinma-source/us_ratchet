import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_historical_single_window_accounts_20260920 as m


def state(track):
    return dict(track=track,selected=dict(arguments=dict(closes=pd.DataFrame({'A':[1.]},index=pd.DatetimeIndex(['2026-03-18']))),original_schedule=[],columns={},labels={},prices={}),calendar=['2026-03-18'],contract={},effective_schedule=[],normalization_evidence={},independent_target_audit_reference={},historical_expected_source_hashes={},archive_resolution={})


class Tests(unittest.TestCase):
    def exercise(self,track='candidate',effect=None,audit_effect=None):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);base=Path(folder.name)
        prepared=state(track)
        stack=[]
        for target,value in [('BASE',base),('prepare',None),('verify_sources',None),('restore_and_audit',None)]:
            p=patch.object(m,target,value) if value is not None else patch.object(m,target)
            stack.append(p);mock=p.start();self.addCleanup(p.stop)
            if target=='prepare':mock.return_value=prepared
            if target=='verify_sources':mock.return_value={}
            if target=='restore_and_audit':mock.side_effect=audit_effect;mock.return_value=({}, {})
        name='simulate_dynamic_frozen_execution_research' if track=='candidate' else 'simulate_dynamic_frozen_incumbent_control'
        p=patch.object(m.candidate if track=='candidate' else m.control,name,side_effect=effect,return_value={'original':'ledger'})
        engine=p.start();self.addCleanup(p.stop)
        return base,prepared,engine

    def test_prepare_only_and_failclosed_audit(self):
        with patch.object(m,'AUDIT_SHA',None):
            with self.assertRaisesRegex(ValueError,'Await'):m.prepare('candidate')
        base,_,engine=self.exercise()
        self.assertFalse(m.run(track='candidate')['execution_performed']);engine.assert_not_called();self.assertFalse((base/'candidate').exists())

    def test_raw_before_audit_baseexception_and_no_replay(self):
        base,_,engine=self.exercise(audit_effect=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):m.run(track='candidate',execute=True)
        self.assertTrue((base/'candidate/raw_execution.json').exists());self.assertTrue((base/'candidate/failure.json').exists());self.assertFalse((base/'candidate/account.json').exists())
        with self.assertRaises(FileExistsError):m.run(track='candidate',execute=True)
        self.assertEqual(engine.call_count,1)

    def test_control_separate_attempt_and_argument_mutation(self):
        def mutate(**kwargs):kwargs['closes'].iloc[0,0]=2.;return {'raw':'preserved'}
        base,prepared,engine=self.exercise('incumbent',effect=mutate)
        with self.assertRaisesRegex(ValueError,'mutated'):m.run(track='incumbent',execute=True)
        self.assertEqual(prepared['selected']['arguments']['closes'].iloc[0,0],1.)
        self.assertTrue((base/'incumbent/raw_execution.json').exists());self.assertFalse((base/'candidate').exists());self.assertEqual(engine.call_count,1)

    def test_ram_mutation_rejected_with_raw_preserved(self):
        base,prepared,engine=self.exercise()
        def mutate(**kwargs):prepared['effective_schedule'].append({'false':'target'});return {'raw':'ledger'}
        engine.side_effect=mutate
        with self.assertRaisesRegex(ValueError,'RAM'):m.run(track='candidate',execute=True)
        self.assertTrue((base/'candidate/raw_execution.json').exists());self.assertTrue((base/'candidate/failure.json').exists())


if __name__=='__main__':unittest.main()
