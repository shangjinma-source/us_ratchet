from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_delta_selected_input_research import fixture
from backtest import ndx_selected_delta_drift_snapshot_research as core
from scripts import ndx_selected_delta_drift_snapshot_runner_research as runner


def save(path,value):
    path.write_bytes(core.selected.encoding._json_bytes(value));return core.drift.file_sha(path)


class SelectedSnapshotTests(unittest.TestCase):
    def setup_fixture(self,folder,stack):
        all_sources={};rows=[];parameters=[]
        for i,anchored in enumerate((True,False)):
            directory=folder/str(i);directory.mkdir();params,cells=fixture(directory,anchored)
            parameters.append(params);core.merge(all_sources,params['arguments']['source_hashes'])
            rows.append(dict(new_job_id=str(i),task=params['arguments']['task'],runtime=params['arguments']['runtime'],
                context_path=str(params['context_path']),context_sha256=params['context_sha256'],
                checkpoint_path=str(params['checkpoint_path']),checkpoint_sha256=params['checkpoint_sha256']))
        stack.enter_context(patch.object(core.selected,'CORRECTIONS',cells))
        stack.enter_context(patch.object(core.selected,'correction_sources',return_value={}))
        contract=dict(authority_source_hashes={},exceptions={})
        stack.enter_context(patch.object(core.drift,'load_contract',return_value=contract))
        core.merge(all_sources,core.sources())
        observations={r['context_path']:dict(context_sha256=r['context_sha256'],gaps=core.selected.provenance.validate_historical_evidence(
            core.read(r['context_path'],r['context_sha256']),all_sources)) for r in rows}
        parent=dict(dates=[dict(tasks=rows)],source_hashes=all_sources,errors=[dict(ticker=t,session=d,old=a,new=b) for t,d,a,b in cells],
            historical_context_gap_observations=observations,probe=dict(date='synthetic',task=rows[0]))
        parent_path=folder/'parent.json';parent_sha=save(parent_path,parent)
        stack.enter_context(patch.object(core.drift,'SELECTED_PLAN',parent_path))
        stack.enter_context(patch.object(core.drift,'SELECTED_PLAN_SHA',parent_sha))
        all_sources=dict(all_sources);all_sources[str(parent_path)]=parent_sha
        parameters[0]['arguments']['source_hashes']=all_sources
        first=core.selected.evaluate_selected_delta(**parameters[0])
        probe=dict(selected=parent['probe'],plan_path=str(parent_path),plan_sha256=parent_sha,result=first)
        probe_path=folder/'probe.json';probe_sha=save(probe_path,probe)
        manifest=dict(schema='ndx_selected_delta_exact_gap_manifest_v1',parent_plan_path=str(parent_path),parent_plan_sha256=parent_sha,
            tasks=rows,corrections=parent['errors'],planned=2,context_count=2,historical_expected_source_hashes=all_sources,
            completed_probe=dict(path=str(probe_path),sha256=probe_sha,new_job_id='0'))
        manifest_path=folder/'manifest.json';manifest_sha=save(manifest_path,manifest)
        return manifest_path,manifest_sha,manifest,parameters,probe_path,probe_sha

    def test_max0_import_max1_new_exact_and_external_resume_without_new_fit(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,_,_=self.setup_fixture(folder,stack)
            stack.enter_context(patch.object(runner,'load_manifest',return_value=manifest))
            with patch.object(core.selected.trace,'evaluate_with_window_trace',wraps=core.selected.trace.evaluate_with_window_trace) as traced:
                first=runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=0)
                self.assertEqual(traced.call_count,0)
                second=runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=1,resume_index=first['path'],resume_index_sha256=first['sha256'])
                self.assertEqual(traced.call_count,1)
                third=runner.run(manifest_path=path,manifest_sha256=sha,output=folder/'out',max_new_tasks=0,resume_index=second['path'],resume_index_sha256=second['sha256'])
                self.assertEqual(traced.call_count,1);self.assertEqual(third['completed'],2)
            output=core.read(folder/'out/1.json',core.drift.file_sha(folder/'out/1.json'))
            expected=core.selected.trace.full.evaluate_joint_weight_task_v3(params[1]['arguments']['task'],**params[1]['corrected_inputs'])
            self.assertEqual(output['result']['result'],expected)
            self.assertFalse(output['historical_full_source_closure_verified'])

    def test_resigned_economics_and_unindexed_task_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,probe,probe_sha=self.setup_fixture(folder,stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            value=core.import_probe(snapshot,probe,probe_sha);core.finish(snapshot)
            value['result']['result']['return_p50']+=.1
            target=folder/'bad.json';bad_sha=save(target,value)
            reopened=core.begin(manifest_path=path,manifest_sha256=sha)
            with self.assertRaisesRegex(ValueError,'twenty metrics'):core.restore(reopened,target,bad_sha)
            stack.enter_context(patch.object(runner,'load_manifest',return_value=manifest))
            output=folder/'out';output.mkdir();(output/'0.json').write_text('{}')
            with patch.object(core.selected.trace,'evaluate_with_window_trace') as traced:
                with self.assertRaisesRegex(ValueError,'Unindexed'):runner.run(manifest_path=path,manifest_sha256=sha,output=output,max_new_tasks=1)
                traced.assert_not_called()

    def test_captured_inputs_actual_runtime_or_unallowed_source_drift_reject(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,_,_=self.setup_fixture(folder,stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha);s=core.STATES[snapshot]
            item=s['contexts'][manifest['tasks'][0]['context_path']];item['inputs']['returns'].iloc[0,0]+=.2
            with self.assertRaisesRegex(ValueError,'typed input'):core.evaluate(snapshot,'0')
            with self.assertRaisesRegex(ValueError,'typed input'):core.finish(snapshot)
            with self.assertRaisesRegex(ValueError,'closed'):core.evaluate(snapshot,'0')
            reopened=core.begin(manifest_path=path,manifest_sha256=sha)
            with patch.object(core.selected,'current_runtime',return_value={}):
                with self.assertRaisesRegex(ValueError,'runtime'):core.evaluate(reopened,'1')
            (folder/'0/fixture.txt').write_text('changed')
            with self.assertRaisesRegex(ValueError,'Non-exempt'):core.finish(reopened)

    def test_explicit_budget_rejects_bool_and_bulk(self):
        for budget in (True,-1,2,11254):
            with self.assertRaisesRegex(ValueError,'max0/max1'):
                runner.run(manifest_path='none',manifest_sha256='none',output='none',max_new_tasks=budget)

    def test_resigned_nan_infinity_or_boolean_scalar_rejected(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,probe,probe_sha=self.setup_fixture(folder,stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            original=core.import_probe(snapshot,probe,probe_sha);core.finish(snapshot)
            reopened=core.begin(manifest_path=path,manifest_sha256=sha)
            for location in ('metric','window'):
                for invalid in (float('nan'),float('inf'),False):
                    value=deepcopy(original)
                    if location=='metric':value['result']['result']['return_p50']=invalid
                    else:value['result']['new_windows'][0]['candidate_return']=invalid
                    target=folder/'resigned.json';target.write_text(json.dumps(value),encoding='utf8')
                    with self.assertRaises(ValueError):core.restore(reopened,target,core.drift.file_sha(target))

    def test_unindexed_remote_queue_task_blocks_before_import_or_fit(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,probe,probe_sha=self.setup_fixture(folder,stack)
            stack.enter_context(patch.object(runner,'load_manifest',return_value=manifest))
            output=folder/'out';output.mkdir();(output/'1.json').write_text('{}')
            with (patch.object(core,'evaluate') as calculate,patch.object(core,'import_probe') as imported):
                with self.assertRaisesRegex(ValueError,'anywhere in output'):
                    runner.run(manifest_path=path,manifest_sha256=sha,output=output,max_new_tasks=1)
                calculate.assert_not_called();imported.assert_not_called()

    def test_restore_cannot_upgrade_disclosure_or_redirect_first_probe(self):
        with tempfile.TemporaryDirectory() as directory,ExitStack() as stack:
            folder=Path(directory);path,sha,manifest,params,probe,probe_sha=self.setup_fixture(folder,stack)
            snapshot=core.begin(manifest_path=path,manifest_sha256=sha)
            original=core.import_probe(snapshot,probe,probe_sha);core.finish(snapshot)
            duplicate=folder/'same_probe_elsewhere.json';duplicate.write_bytes(probe.read_bytes())
            for defect in ('flag','scope','path','sha'):
                reopened=core.begin(manifest_path=path,manifest_sha256=sha);value=deepcopy(original)
                if defect=='flag':value['non20_risk_projection_fields_independently_recomputed']=True
                elif defect=='scope':value['saved_result_revalidation_scope']='ALL_FIELDS_VERIFIED'
                elif defect=='path':value['imported_probe_path']=str(duplicate)
                else:value['imported_probe_sha256']='0'*64
                target=folder/(defect+'.json');changed_sha=save(target,value)
                with self.assertRaises(ValueError):core.restore(reopened,target,changed_sha)
            reopened=core.begin(manifest_path=path,manifest_sha256=sha)
            with self.assertRaisesRegex(ValueError,'exact manifest'):core.import_probe(reopened,duplicate,probe_sha)


if __name__=='__main__':unittest.main()
