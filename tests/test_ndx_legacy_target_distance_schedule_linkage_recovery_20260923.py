"""Synthetic six-target receipts; no actual schedule publication or optimizer."""
from contextlib import contextmanager,ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_legacy_target_distance_schedule_linkage_recovery_20260923 as m


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        folder=Path(tmp);reader=folder/'reader.py';reader.write_text('synthetic-reader')
        sha=hashlib.sha256(reader.read_bytes()).hexdigest()
        for key,value in dict(FOLDER=folder,READER=reader,READER_SHA=sha,LOADED={}).items():stack.enter_context(patch.object(m,key,value))
        calendar=m.publish(folder/'calendar.json',{'execution':{'daily':[{'session':d} for d in sorted(set(m.DATES+m.CUTOFFS))]}})
        plan=m.publish(folder/'plan.json',{'schema':'LEGACY_TARGET_DISTANCE_SIX_PERIOD_STRATEGIC_TARGET_PLAN_V1','calendar':calendar,'selected_job_ids':['j'+str(i) for i in range(6)],'materialization_modes':list(m.MODES),'weight_specs':list(m.SPECS)})
        stack.enter_context(patch.object(m,'PLAN',plan))
        full=m.publish(folder/'full.json',{'synthetic':True});diff=m.publish(folder/'diff.json',{'synthetic':True})
        refs=[];details=[];previous=None;previous_raw=None
        for i,day in enumerate(m.DATES):
            indices=list(range(6)) if i==4 else list(range(3,7)) if i==5 else list(range(4))
            targets={f'S{j}':dict(ticker=f'T{j}',issuer_id=f'I{j}',target_weight=1./len(indices)) for j in indices}
            chains={sid:'R'+sid[1:] for sid in set(targets)|set(previous or {})}
            directory=folder/day;directory.mkdir()
            provenance=dict(origin='HARD_COMPLETE_TRAINING_RECORD',complete_date_reference=full,independent_full_diff_reference=diff,
                original_task={'job_id':'j'+str(i)},old_queue_candidate_present=False)
            binding=dict(lane_previous_target_weights=deepcopy(previous),fit_actual_previous_target_weights=deepcopy(previous or {}),
                lane_risk_chains_by_security=chains,fit_uses_lane_previous_target=True,original_fit_reference=None,
                original_fit_audit_reference=None,imported_no_anchor_fit=False,candidate_provenance=provenance)
            operation=m.counts(i)
            planned={key:value for key,value in operation.items() if key not in ('materialization_mode','optimizer_called_by_equal_branch')}
            started=m.publish(directory/'started.json',dict(schema='LEGACY_TARGET_DISTANCE_TARGET_SINGLE_ATTEMPT_V1',
                plan_reference=plan,execution_date=day,cutoff=m.CUTOFFS[i],job_id='j'+str(i),weight_spec=m.SPECS[i],
                previous_target_reference=previous_raw,previous_target_weights=previous,numerical_and_lane_binding=binding,
                materialization_mode=m.MODES[i],optimizer_called_by_equal_branch=operation['optimizer_called_by_equal_branch'],planned_operation_counts=planned))
            raw=m.publish(directory/'raw.json',dict(schema='LEGACY_TARGET_DISTANCE_TARGET_RAW_RESULT_V1',status='FIT_RETURNED',plan_reference=plan,
                execution_date=day,started_reference=started,fitted={'targets':targets,'previous_target_weights':binding['fit_actual_previous_target_weights'],'weight_spec':m.SPECS[i]},
                previous_target_weights=previous,previous_target_reference=previous_raw,**operation,numerical_and_lane_binding=binding))
            final=m.publish(directory/'finalization.json',dict(schema='LEGACY_TARGET_DISTANCE_TARGET_STEP_FINALIZATION_V1',plan_reference=plan,
                execution_date=day,status='TARGET_FIVE_RISKS_PASSED',detail=None,raw_reference=raw,**operation,
                fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False))
            refs.append(final);details.append(dict(finalization_reference=final,execution_date=day,cutoff=m.CUTOFFS[i],job_id='j'+str(i),
                raw_reference=raw,started_reference=started,targets=targets,numerical_and_lane_binding=binding,
                lane_risk_chains_by_security=chains,operation_counts=operation))
            previous={sid:t['target_weight'] for sid,t in targets.items()};previous_raw=raw
        audit=dict(schema='LEGACY_TARGET_DISTANCE_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1',status='PASSED',plan_reference=plan,
            completed_prefix_count=6,details=details,finalization_references=refs,wrapper_call_attempt_count=6,deterministic_generation_request_count=3,numerical_fit_request_count=3,import_count=0,
            source_hashes={str(reader):sha,plan['path']:plan['sha256'],full['path']:full['sha256'],diff['path']:diff['sha256']},
            **dict.fromkeys(('optimizer_called','owner_validator_called','account_engine_called','point_in_time_verified','promotion_allowed','next_step_execution_authorized'),False))
        yield folder,audit


class ScheduleRecoveryTests(unittest.TestCase):
    def test_missing_schedule_published_once_and_existing_exact_reused(self):
        with fixture() as (folder,audit):
            ref=m.publish(folder/'audit.json',audit)
            first=m.run(ref['path'],ref['sha256']);self.assertTrue(first['schedule_created'])
            raw=(folder/'schedule.json').read_bytes()
            self.assertEqual([len(row['targets']) for row in m.loads(raw)['schedule']],[4,4,4,4,6,4])
            second=m.run(ref['path'],ref['sha256']);self.assertFalse(second['schedule_created'])
            self.assertEqual(raw,(folder/'schedule.json').read_bytes())
            self.assertEqual(first['linkage_reference'],second['linkage_reference'])

    def test_wrong_mode_counts_and_candidate_source_closure_rejected(self):
        for attack in ('mode','numerical','import','bool','provenance','source'):
            with fixture() as (folder,audit):
                detail=audit['details'][4]
                if attack=='mode':detail['operation_counts']['materialization_mode']='NEW_ANCHORED_FIT'
                if attack=='numerical':detail['operation_counts']['numerical_fit_request_count']=1
                if attack=='import':detail['operation_counts']['import_count']=1
                if attack=='bool':detail['operation_counts']['wrapper_call_attempt_count']=True
                if attack=='provenance':detail['numerical_and_lane_binding']['candidate_provenance']['old_queue_candidate_present']=True
                if attack=='source':del audit['source_hashes'][detail['numerical_and_lane_binding']['candidate_provenance']['complete_date_reference']['path']]
                ref=m.publish(folder/'audit.json',audit)
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.run(ref['path'],ref['sha256'])
                self.assertFalse((folder/'schedule.json').exists())

    def test_existing_wrong_schedule_never_overwritten(self):
        with fixture() as (folder,audit):
            ref=m.publish(folder/'audit.json',audit);m.publish(folder/'schedule.json',{'wrong':True})
            before=(folder/'schedule.json').read_bytes()
            with self.assertRaises(ValueError):m.run(ref['path'],ref['sha256'])
            self.assertEqual(before,(folder/'schedule.json').read_bytes())
            self.assertFalse((folder/'schedule_independent_linkage.json').exists())

    def test_incomplete_or_risk_denominator_attack_rejected(self):
        for attack in ('prefix','bool','risk','order'):
            with fixture() as (folder,audit):
                if attack=='prefix':audit['completed_prefix_count']=5
                if attack=='bool':audit['wrapper_call_attempt_count']=True
                if attack=='risk':audit['details'][0]['lane_risk_chains_by_security']={'S0':'R0'}
                if attack=='order':audit['finalization_references'].reverse()
                ref=m.publish(folder/'audit.json',audit)
                with self.subTest(attack=attack),self.assertRaises(ValueError):m.run(ref['path'],ref['sha256'])
                self.assertFalse((folder/'schedule.json').exists())

    def test_orphan_and_source_drift_after_schedule_cannot_pass(self):
        with fixture() as (folder,audit):
            ref=m.publish(folder/'audit.json',audit);(folder/m.DATES[0]/'orphan').write_text('x')
            with self.assertRaises(ValueError):m.run(ref['path'],ref['sha256'])
        with fixture() as (folder,audit):
            ref=m.publish(folder/'audit.json',audit)
            with patch.object(m.os,'fsync',side_effect=lambda _:m.READER.write_text('changed')):
                with self.assertRaises(ValueError):m.run(ref['path'],ref['sha256'])
            self.assertTrue((folder/'schedule.json').exists())
            self.assertFalse((folder/'schedule_independent_linkage.json').exists())


if __name__=='__main__':unittest.main()
