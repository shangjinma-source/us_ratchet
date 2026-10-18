from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_dated_account_input_research as pure
from scripts import ndx_dated_account_execution_20261003 as core
from test_ndx_dated_account_input_research import fixture,REF


def state(track='candidate',blocked=False):
    a=fixture()
    for i in (3,4):
        sid=f'security:{i}:T{i}';a['task']['numerical_identity']['selected'][sid]=dict(ticker=f'T{i}',issuer_id=f'issuer:{i}',risk_chain=f'chain{i}')
        c=deepcopy(next(iter(a['incumbent_channels_by_security'].values())));c['ticker']=f'T{i}';a['candidate_channels_by_security'][sid]=c
        a['channel_references'][sid]=dict(REF,json_pointer=f'/extra/{i}');a['split_evidence_by_security'][sid]=[]
        a['fit_result']['targets'][sid]=dict(ticker=f'T{i}',issuer_id=f'issuer:{i}',target_weight=.25)
    for r in a['fit_result']['targets'].values():r['target_weight']=.25
    if blocked:
        targets=list(a['fit_result']['targets'].values());targets[0]['target_weight']=0;targets[1]['target_weight']=.5
    a['task']['numerical_identity']['holding_count']=4;a['task']['numerical_task_id']=pure.digest(a['task']['numerical_identity'])
    for c in list(a['candidate_channels_by_security'].values())+list(a['incumbent_channels_by_security'].values()):
        for r in c['quote_rows']:
            value=pure.Fraction(100)
            for e in c['event_policies']:
                if r['session']>=e['session']:value/=e['numerator']
            r['nominal_open_exact']=r['nominal_close_exact']=str(value)
    inputs=pure.assemble_dated_account_inputs(**a)
    return dict(track=track,numerical_task_id=a['task']['numerical_task_id'],account=inputs[track],calendar=inputs['calendar'],common_incumbent_identity='e'*64,blocked_nonpositive=blocked,source_hashes={},runtime=core.runtime())

class Tests(unittest.TestCase):
    def invoke(self,s,root):
        r=dict(path=str(root/s['numerical_task_id']/'inputs.json'),sha256='a'*64)
        with patch.object(core,'prepare',return_value=s),patch.object(core,'OUTPUT',root/'outputs'):
            return core.run(s['track'],r,REF,execute=True)

    def test_saved_actual_audited_input_prepare_only(self):
        # No account execution and no producer/auditor calls. Actual readback pin
        # must arrive from root before this integration test is eligible to run.
        if core.INPUT_READER_SHA is None:self.skipTest('Await root sealed input reader/reference pins')
        initial=core.loads((core.ROOT/'research_contracts/dated_initial_completed_tasks_20261003_v1.json').read_bytes())
        tid=initial['rows'][0]['numerical_task_id'];folder=core.INPUT_ROOT/tid
        audit_path=folder/'independent_readback.json'
        if not audit_path.is_file():self.skipTest('Root has not published actual input readback')
        # Publication bytes and external audit bytes are supplied by the root's
        # saved immutable documents; this test performs read-only prepare only.
        audit=core.loads(audit_path.read_bytes())
        self.assertEqual(audit['reader_sha256'],core.INPUT_READER_SHA)
        reference=dict(path=str(audit_path),sha256='396b45c1eec5a3fa0f2441744d409c0642eb21d2f6719da33725360707e114a3')
        self.assertEqual(core.sha(audit_path.read_bytes()),reference['sha256'])
        for track in ('candidate','incumbent'):
            prepared=core.prepare(track,audit['inputs_reference'],reference)
            self.assertEqual(prepared['numerical_task_id'],tid)
            self.assertEqual(len(prepared['calendar']),127)

    def test_actual_frozen_both_tracks_splits_and_unique_incumbent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);s=state();ref=self.invoke(s,root);post=core.loads(Path(ref['path']).read_bytes());self.assertEqual(post['status'],'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING')
            raw=core.loads(Path(post['raw_reference']['path']).read_bytes())['account'];self.assertTrue(raw['trades'])
            for sid,n in [('security:1:BKNG',25),('security:2:KLAC',10)]:self.assertEqual(raw['daily'][-1]['shares'][sid],raw['daily'][1]['shares'][sid]*n)
            self.assertAlmostEqual(raw['daily'][1]['total_value_usd'],raw['daily'][-1]['total_value_usd'])
            c=state('incumbent');result=self.invoke(c,root);self.assertEqual(core.loads(Path(result['path']).read_bytes())['status'],'ACCOUNT_SAVED_PENDING_INDEPENDENT_ACCOUNTING')
            c['numerical_task_id']='f'*64
            with self.assertRaises(ValueError):self.invoke(c,root)

    def test_zero_weight_not_executed_and_retry_blocked(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(core,'execute_engine') as engine:
            root=Path(temporary);s=state(blocked=True);ref=self.invoke(s,root);post=core.loads(Path(ref['path']).read_bytes())
            self.assertEqual(post['status'],'NOT_EXECUTED_NONPOSITIVE_TARGET');engine.assert_not_called()
            raw=core.loads(Path(post['raw_reference']['path']).read_bytes());self.assertEqual(raw['engine_call_attempt_count'],0)
            with self.assertRaises(ValueError):self.invoke(s,root)

    def test_returned_raw_survives_postguard_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            count=[0]
            def guard(s):
                count[0]+=1
                if count[0]>=2:raise ValueError('source drift')
            with patch.object(core,'guard',side_effect=guard):ref=self.invoke(state(),Path(temporary))
            post=core.loads(Path(ref['path']).read_bytes());self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            raw=core.loads(Path(post['raw_reference']['path']).read_bytes());self.assertIsNotNone(raw['account']);self.assertEqual(raw['returned_account_count'],1)

    def test_none_return_is_preserved_but_not_accepted(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(core,'execute_engine',return_value=None):
            reference=self.invoke(state(),Path(temporary))
            post=core.loads(Path(reference['path']).read_bytes())
            self.assertEqual(post['status'],'VALIDATION_FAILURE_RECORDED')
            raw=core.loads(Path(post['raw_reference']['path']).read_bytes())
            self.assertIsNone(raw['account']);self.assertEqual(raw['returned_account_count'],0)

    def test_pending_audit_and_execute_bool_are_closed(self):
        with patch.object(core,'INPUT_READER_SHA',None):
            with self.assertRaises(ValueError):core.prepare('candidate',REF,REF)
        with self.assertRaises(ValueError):core.run('candidate',REF,REF,execute=1)
        with tempfile.TemporaryDirectory() as temporary,patch.object(core,'execute_engine',side_effect=ValueError('engine raised before return')):
            ref=self.invoke(state(),Path(temporary));post=core.loads(Path(ref['path']).read_bytes());self.assertEqual(post['status'],'ACCOUNT_EXCEPTION_NO_RETURNED_RESULT')

if __name__=='__main__':unittest.main()
