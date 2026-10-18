import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_historical_cross_k_prefix_independent_audit_20260923 as m


def fixture():
    load=lambda p:json.loads(Path(p).read_bytes())
    document=load(m.plan_reader.INPUT['path']);target=load(m.plan_reader.TARGET['path'])
    frame=m.plan_reader.first_window(document);numerical=target['result']['source_hashes']
    row=m.plan_reader.expected_task(target['task']['selected'],'equal_weight',m.scalar.PARAMS,frame,numerical)
    folder=Path('data/cache/research/test_only_historical_prefix').resolve();sid=row['task_id']
    entry=dict(task_id=sid,**{k+'_reference':dict(path=str(folder/sid/(k+'.json' if k!='result' else 'result.json')),sha256=h*64) for k,h in (('started','a'),('raw','b'),('result','c'))})
    base={str(Path('test_source.py').resolve()):'d'*64};partition=dict(live_verified_source_hashes=dict(base))
    task=dict(row['task'],task_id=sid);local=dict(base);local[entry['started_reference']['path']]=entry['started_reference']['sha256']
    marker=dict(schema='HISTORICAL_CROSS_K_ATTEMPT_V1',plan_reference=m.PLAN,task_id=sid,attempt_count=1,runtime=m.runtime())
    result=copy.deepcopy(target['result'])
    raw=dict(schema='HISTORICAL_CROSS_K_RAW_FIT_V1',plan_reference=m.PLAN,task=task,result=result,started_reference=entry['started_reference'],runtime=m.runtime(),historical_expected_source_hashes=copy.deepcopy(local),fit_performed=True,**dict.fromkeys(m.FALSE,False))
    local[entry['raw_reference']['path']]=entry['raw_reference']['sha256'];finalpart=copy.deepcopy(partition);finalpart['live_verified_source_hashes'].update(local)
    saved=dict(schema='HISTORICAL_CROSS_K_CHECKPOINT_V1',plan_reference=m.PLAN,task=task,result=result,started_reference=entry['started_reference'],raw_reference=entry['raw_reference'],independent_matrix_and_risk_checks={'risk_pass':True},status='FITTED_FIVE_RISKS_PASSED',historical_expected_source_hashes=local,archive_resolution=finalpart,fit_performed=True,**dict.fromkeys(m.FALSE,False))
    documents=dict(started=marker,raw=raw,result=saved)
    return row,documents,entry,frame,numerical,base,partition


class PrefixReadbackTests(unittest.TestCase):
    def test_marker_raw_checkpoint_full_scope_with_numerical_reader_spy(self):
        args=fixture()
        # Isolate receipt/schema gates; numerical oracle correctness has its own real tests.
        with patch.object(m.shape,'result_schema'),patch.object(m.scalar,'inspect_result',return_value={'risk_pass':True}) as scalar:
            self.assertTrue(m.inspect_task(*args)['risk_pass']);scalar.assert_called_once()
            self.assertEqual(len(scalar.call_args.args[2]['returns']['data']),126)
        for defect in ('markerbool','rawsource','rawfit','futurecutoff','resultscope','savedresult'):
            changed=list(copy.deepcopy(args));documents=changed[1]
            if defect=='markerbool':documents['started']['attempt_count']=True
            elif defect=='rawsource':documents['raw']['historical_expected_source_hashes']={}
            elif defect=='rawfit':documents['raw']['fit_performed']=False
            elif defect=='futurecutoff':documents['raw']['task']['cutoff']='2026-09-17'
            elif defect=='resultscope':documents['result']['promotion_allowed']=True
            else:
                documents['result']['result']=copy.deepcopy(documents['result']['result'])
                documents['result']['result']['cutoff']='2026-09-17'
            with self.subTest(defect=defect),patch.object(m.shape,'result_schema'),patch.object(m.scalar,'inspect_result',return_value={'risk_pass':True}),self.assertRaises(ValueError):m.inspect_task(*changed)

    def test_external_historical_result_cannot_be_newly_fitted(self):
        args=list(fixture());args[0]['task_id']=m.plan_reader.target_reader.JOB
        with self.assertRaisesRegex(ValueError,'sole historical'):m.inspect_task(*args)

    def test_index_finalization_denominator_and_source_omission(self):
        row,_,entry,_,_,base,_=fixture();sources=dict(base)
        for k in ('started_reference','raw_reference','result_reference'):sources[entry[k]['path']]=entry[k]['sha256']
        folder=str(Path(entry['started_reference']['path']).parent.parent)
        index=dict(schema='HISTORICAL_CROSS_K_FINALIZED_PREFIX_V1',plan_reference=m.PLAN,independent_plan_audit_reference=m.AUDIT,folder=folder,
            canonical_task_count=31828,external_completed_reference_count=1,external_completed_reference=m.plan_reader.TARGET,pending_task_count=31827,completed_new_count=1,remaining_new_count=31826,
            entries=[entry],status='PARTIAL',finalized_after_full_source_verification=True,contains_new_historical_fit_results=True,historical_expected_source_hashes=sources,archive_resolution={},**dict.fromkeys(m.FALSE,False))
        self.assertEqual(m.validate_index(index,[row],base),{})
        for defect in ('boolcount','final','fitflag','external','source','extra'):
            value=copy.deepcopy(index)
            if defect=='boolcount':value['completed_new_count']=True
            elif defect=='final':value['finalized_after_full_source_verification']=1
            elif defect=='fitflag':value['contains_new_historical_fit_results']=False
            elif defect=='external':value['external_completed_reference']['sha256']='0'*64
            elif defect=='source':value['historical_expected_source_hashes'].pop(entry['raw_reference']['path'])
            else:value['historical_expected_source_hashes'][str(Path(folder)/'unknown.json')]='0'*64
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.validate_index(value,[row],base)

    def test_caller_must_confirm_finished_run_and_hard_runner(self):
        with self.assertRaisesRegex(ValueError,'explicitly'):m.build('missing','0'*64)
        with patch.object(m,'RUNNER_SHA',None),self.assertRaisesRegex(ValueError,'Await'):m.build('missing','0'*64,completed_prefix_confirmed=True)


if __name__=='__main__':unittest.main()
