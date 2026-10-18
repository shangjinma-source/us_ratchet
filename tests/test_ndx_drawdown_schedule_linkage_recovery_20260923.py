"""Synthetic six-target receipts; no actual schedule publication or optimizer."""
from contextlib import contextmanager,ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_schedule_linkage_recovery_20260923 as m


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as tmp,ExitStack() as stack:
        folder=Path(tmp);reader=folder/'reader.py';reader.write_text('synthetic-reader')
        sha=hashlib.sha256(reader.read_bytes()).hexdigest()
        for key,value in dict(FOLDER=folder,READER=reader,READER_SHA=sha,LOADED={}).items():stack.enter_context(patch.object(m,key,value))
        calendar=m.publish(folder/'calendar.json',{'execution':{'daily':[{'session':d} for d in sorted(set(m.DATES+m.CUTOFFS))]}})
        plan=m.publish(folder/'plan.json',{'calendar':calendar,'selected_job_ids':['j'+str(i) for i in range(6)]})
        stack.enter_context(patch.object(m,'PLAN',plan))
        targets={f'S{i}':dict(ticker=f'T{i}',issuer_id=f'I{i}',target_weight=.25) for i in range(4)}
        chains={f'S{i}':f'R{i}' for i in range(4)}
        refs=[];details=[];previous=None;previous_raw=None
        for i,day in enumerate(m.DATES):
            directory=folder/day;directory.mkdir()
            binding=dict(lane_previous_target_weights=deepcopy(previous),fit_actual_previous_target_weights={} if i in (0,5) else deepcopy(previous),lane_risk_chains_by_security=chains)
            started=m.publish(directory/'started.json',{'numerical_and_lane_binding':binding})
            raw=m.publish(directory/'raw.json',dict(schema='DRAWDOWN_TARGET_RAW_RESULT_V1',status='FIT_RETURNED',plan_reference=plan,
                execution_date=day,started_reference=started,fitted={'targets':targets,'previous_target_weights':binding['fit_actual_previous_target_weights']},
                previous_target_weights=previous,previous_target_reference=previous_raw,new_fit_attempt_count=0 if i in (0,5) else 1,numerical_and_lane_binding=binding))
            final=m.publish(directory/'finalization.json',dict(schema='DRAWDOWN_TARGET_STEP_FINALIZATION_V1',plan_reference=plan,
                execution_date=day,status='TARGET_FIVE_RISKS_PASSED',detail=None,raw_reference=raw,
                fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False))
            refs.append(final);details.append(dict(finalization_reference=final,execution_date=day,cutoff=m.CUTOFFS[i],job_id='j'+str(i),
                raw_reference=raw,started_reference=started,targets=targets,numerical_and_lane_binding=binding,
                lane_risk_chains_by_security=chains,new_fit_attempt_count=0 if i in (0,5) else 1))
            previous={sid:t['target_weight'] for sid,t in targets.items()};previous_raw=raw
        audit=dict(schema='DRAWDOWN_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1',status='PASSED',plan_reference=plan,
            completed_prefix_count=6,details=details,finalization_references=refs,first_import_count=1,last_no_anchor_import_count=1,new_fit_observed_count=4,
            source_hashes={str(reader):sha,plan['path']:plan['sha256']},
            **dict.fromkeys(('optimizer_called','owner_validator_called','account_engine_called','point_in_time_verified','promotion_allowed','next_step_execution_authorized'),False))
        yield folder,audit


class ScheduleRecoveryTests(unittest.TestCase):
    def test_missing_schedule_published_once_and_existing_exact_reused(self):
        with fixture() as (folder,audit):
            ref=m.publish(folder/'audit.json',audit)
            first=m.run(ref['path'],ref['sha256']);self.assertTrue(first['schedule_created'])
            raw=(folder/'schedule.json').read_bytes()
            second=m.run(ref['path'],ref['sha256']);self.assertFalse(second['schedule_created'])
            self.assertEqual(raw,(folder/'schedule.json').read_bytes())
            self.assertEqual(first['linkage_reference'],second['linkage_reference'])

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
                if attack=='bool':audit['first_import_count']=True
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
