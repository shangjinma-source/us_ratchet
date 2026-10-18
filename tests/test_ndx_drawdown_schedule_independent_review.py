from copy import deepcopy
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_schedule_linkage_recovery_20260923 as m


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(m.encoded(value))
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def fixture(folder):
    calendar=sorted(set(m.CUTOFFS+m.DATES))
    calref=save(folder/'calendar.json',{'execution':{'daily':[{'session':d} for d in calendar]}})
    planref=save(folder/'plan.json',{'calendar':calref,'selected_job_ids':['job'+str(i) for i in range(6)]})
    details=[];refs=[];previous=None;previous_raw=None
    for i,day in enumerate(m.DATES):
        directory=folder/day;targets={'sid':{'target_weight':1}}
        binding=dict(lane_previous_target_weights=previous,fit_actual_previous_target_weights={} if i in (0,5) else previous,
                     lane_risk_chains_by_security={'sid':'risk'})
        started=save(directory/'started.json',{'numerical_and_lane_binding':binding})
        raw=save(directory/'raw.json',dict(schema='DRAWDOWN_TARGET_RAW_RESULT_V1',status='FIT_RETURNED',plan_reference=planref,
            execution_date=day,fitted={'targets':targets,'previous_target_weights':binding['fit_actual_previous_target_weights']},
            previous_target_weights=previous,previous_target_reference=previous_raw,started_reference=started,
            new_fit_attempt_count=0 if i in (0,5) else 1,numerical_and_lane_binding=binding))
        final=save(directory/'finalization.json',dict(schema='DRAWDOWN_TARGET_STEP_FINALIZATION_V1',plan_reference=planref,
            execution_date=day,status='TARGET_FIVE_RISKS_PASSED',detail=None,raw_reference=raw,
            fallback_performed=False,whole_lot_execution_performed=False,promotion_allowed=False))
        details.append(dict(finalization_reference=final,raw_reference=raw,started_reference=started,execution_date=day,
            cutoff=m.CUTOFFS[i],job_id='job'+str(i),targets=targets,new_fit_attempt_count=0 if i in (0,5) else 1,
            numerical_and_lane_binding=binding,lane_risk_chains_by_security={'sid':'risk'}))
        refs.append(final);previous={'sid':1};previous_raw=raw
    audit=dict(schema='DRAWDOWN_COMPLETE_PREFIX_INDEPENDENT_READBACK_V1',status='PASSED',plan_reference=planref,
        completed_prefix_count=6,details=details,finalization_references=refs,first_import_count=1,last_no_anchor_import_count=1,
        new_fit_observed_count=4,source_hashes={str(m.READER):m.READER_SHA,planref['path']:planref['sha256']},
        optimizer_called=False,owner_validator_called=False,account_engine_called=False,point_in_time_verified=False,
        promotion_allowed=False,next_step_execution_authorized=False)
    return planref,audit


class IndependentReview(unittest.TestCase):
    def test_complete_recovery_idempotent_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);plan,audit=fixture(folder);ref=save(folder/'audit.json',audit)
            with patch.object(m,'FOLDER',folder),patch.object(m,'PLAN',plan):
                first=m.run(ref['path'],ref['sha256']);second=m.run(ref['path'],ref['sha256'])
                self.assertTrue(first['schedule_created']);self.assertFalse(second['schedule_created'])
                self.assertEqual(first['schedule_reference'],second['schedule_reference'])
                schedule=folder/'schedule.json';schedule.write_text('{}')
                with self.assertRaisesRegex(ValueError,'never overwrite'):m.run(ref['path'],ref['sha256'])
                self.assertEqual(schedule.read_text(),'{}')

    def test_incomplete_prefix_or_mixed_last_prior_rejected(self):
        for mode in ('five','last_prior','risk_missing'):
            with tempfile.TemporaryDirectory() as root:
                folder=Path(root);plan,audit=fixture(folder)
                if mode=='five':audit['completed_prefix_count']=5
                elif mode=='last_prior':audit['details'][-1]['numerical_and_lane_binding']['fit_actual_previous_target_weights']={'sid':1}
                else:audit['details'][1]['lane_risk_chains_by_security']={}
                ref=save(folder/'audit.json',audit)
                with patch.object(m,'FOLDER',folder),patch.object(m,'PLAN',plan):
                    with self.assertRaises(ValueError):m.reconstruct(ref)
                    self.assertFalse((folder/'schedule.json').exists())

    def test_orphan_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);plan,audit=fixture(folder);ref=save(folder/'audit.json',audit)
            (folder/m.DATES[3]/'unknown.json').write_text('{}')
            with patch.object(m,'FOLDER',folder),patch.object(m,'PLAN',plan):
                with self.assertRaisesRegex(ValueError,'orphan'):m.reconstruct(ref)

    def test_source_mutation_during_publish_cannot_succeed(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);plan,audit=fixture(folder);ref=save(folder/'audit.json',audit)
            with patch.object(m,'FOLDER',folder),patch.object(m,'PLAN',plan), \
                    patch.object(m.os,'fsync',side_effect=lambda _:Path(plan['path']).write_text('{}')):
                with self.assertRaisesRegex(ValueError,'Source drift'):m.run(ref['path'],ref['sha256'])


if __name__=='__main__':unittest.main()

