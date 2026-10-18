from copy import deepcopy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_dated_account_input_research as pure
from scripts import ndx_dated_account_inputs_20261003 as core
from test_ndx_dated_account_input_research import fixture,REF


def documents():
    a=fixture();rows=[];events=[{} for _ in range(13)]
    for sid,c in a['candidate_channels_by_security'].items():
        coordinate=dict(security_id=sid,**a['task']['numerical_identity']['selected'][sid]);policy=c['event_policies'][0];i=2 if c['ticker']=='BKNG' else 12
        e=dict(ticker=c['ticker'],first_adjusted_trading_date=policy['session'],new_shares=policy['numerator'],old_shares=1,raw_path=f'{c["ticker"]}.bin',raw_sha256='d'*64,source_url='https://saved.example/notice',specific_simple_share_split_event_supported=True,corporate_action_completeness_verified=False,point_in_time_verified=False)
        events[i]=e
        c['bridge_row_preserved']=dict(event_policy_bridge=dict(events=[dict(session=policy['session'],status='SPECIFIC_POLICY_MATCH',specific_event_reference=dict(event_index=i,parent=core.ref('registry'),original_raw_reference=dict(path=e['raw_path'],sha256=e['raw_sha256'])))]))
        rows.append(dict(coordinate=coordinate,channel=c))
    for i in range(75):rows.append(dict(coordinate={'security_id':f'security:extra:{i}'},channel={}))
    controlrows=[dict(original_control_security=r,channel=a['incumbent_channels_by_security'][r['security_id']]) for r in a['incumbent_securities']]
    docs=dict(channels=dict(rows=rows,original_provenance_and_missing=[{}]*101,preserved_evidence_sidecars={str(i):{} for i in range(7)}),control=dict(rows=controlrows,original_control_preserved={'securities':a['incumbent_securities']}),registry={'events':events})
    return a,docs

class Tests(unittest.TestCase):
    def test_real_saved_parent_schema_metadata_only(self):
        # Read sealed JSON metadata only; no load_common/project/raw audit/task.
        docs={}
        for role in ('preparation','channels','channels_publication','channels_audit','control','control_publication','control_audit'):
            r=core.ref(role);blob=Path(r['path']).read_bytes()
            self.assertEqual(core.sha(blob),r['sha256']);docs[role]=core.loads(blob)
        core.validate_parents(docs)
        self.assertNotIn('legal_training_input_admitted',docs['control_audit'])
        docs['control_audit']['benchmark_qualified']=True
        with self.assertRaises(ValueError):core.validate_parents(docs)

    def test_projection_preserves_events_labels_and_normalization_evidence(self):
        a,docs=documents();result=core.project(pure,a['task'],dict(REF,json_pointer='/task'),a['fit_result'],REF,docs)
        self.assertEqual(result['inputs']['candidate']['corporate_actions'][0]['security_id'],'security:1:BKNG')
        self.assertEqual(result['split_source_facts_preserved']['security:2:KLAC'][0]['registry_row'],docs['registry']['events'][12])
        self.assertEqual(result['inputs']['candidate_engine_normalization_evidence']['effective_weights'],{s:.5 for s in a['task']['numerical_identity']['selected']})
        self.assertFalse(result['account_executed']);self.assertEqual(len(result['original_provenance_and_missing']),101)

    def test_wrong_registry_byte_reference_is_rejected(self):
        a,docs=documents();docs['registry']['events'][2]['raw_sha256']='e'*64
        with self.assertRaises(ValueError):core.project(pure,a['task'],REF,a['fit_result'],REF,docs)

    def test_guard_rejects_loaded_source_conflict_and_execute_false(self):
        with self.assertRaises(ValueError):core.guard({str(core.CORE):'0'*64})
        with patch.object(core,'load_common') as load:
            with self.assertRaises(ValueError):core.run('a'*64,REF,execute=False)
            load.assert_not_called()

    def test_publication_drift_leaves_failure_and_forbids_retry(self):
        a,docs=documents();tid=a['task']['numerical_task_id'];taskref=dict(core.ref('preparation'),json_pointer='/materialized/combinations/0/tasks/0')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);attempts=root/'attempts';folder=attempts/tid;folder.mkdir(parents=True)
            started=core.save(folder/'started.json',dict(schema='DATED_SINGLE_TASK_STARTED_V1',task=a['task'],task_reference=taskref))
            raw=core.save(folder/'raw.json',dict(schema='DATED_SINGLE_TASK_RAW_V1',started_reference=started,status='FIT_RETURNED',returned_fit_count=1,error=None,numerical_task_id=tid,fitted=a['fit_result']))
            post=core.save(folder/'postcheck.json',dict(schema='DATED_SINGLE_TASK_POSTCHECK_V1',started_reference=started,raw_reference=raw,error=None,numerical_task_id=tid,status='ORIGINAL_RISKS_PASSED_PENDING_INDEPENDENT_READBACK'))
            report=core.save(folder/'independent_readback.json',dict(schema='DATED_SINGLE_TASK_INDEPENDENT_READBACK_V1',status='PASSED',numerical_task_id=tid,attempt_outcome='RISK_PASSED',task_reference=taskref,source_hashes={core.ref('fit_reader')['path']:core.ref('fit_reader')['sha256']},started_reference=started,raw_reference=raw,postcheck_reference=post))
            common={'ordered_task_ids':[tid]};core._CACHE[id(common)]=(common,docs,{tid:(a['task'],taskref)},{},pure)
            out=root/'out';counter=[0]
            def guard(sources):
                counter[0]+=1
                if counter[0]==5:raise ValueError('source drift after receipt')
            with patch.object(core,'OUTPUT',out),patch.object(core,'ATTEMPTS',attempts),patch.object(core,'guard',side_effect=guard):
                with self.assertRaises(ValueError):core.run(tid,report,execute=True,common=common)
                self.assertTrue((out/tid/'failure.json').exists());self.assertTrue((out/tid/'inputs.json').exists());self.assertTrue((out/tid/'publication.json').exists())
                with self.assertRaises(ValueError):core.run(tid,report,execute=True,common=common)
            core._CACHE.pop(id(common))

if __name__=='__main__':unittest.main()
