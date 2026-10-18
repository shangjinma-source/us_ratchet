import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_cash_neighbor_combined_independent_readback_20261008 as subject
from test_ndx_cash_neighbor_recovery_partition_research import fixture

class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue,cls.ids,cls.partition,cls.sidecar=fixture()
        cls.domain=subject.expected_domain(cls.queue,cls.ids,cls.partition,cls.sidecar)
    def test_full_independent_domain_matches_all_45_original_segments(self):
        self.assertEqual(self.domain['recovery_task_count'],42301)
        self.assertEqual(self.domain['segments'][0]['original_task_start'],163)
        self.assertEqual(self.domain['segments'][-1]['original_global_stop'],301657)
    def test_same_count_old_id_swap_is_not_full_coverage(self):
        partition=deepcopy(self.partition);groups=partition['task_ids_by_saved_status']
        groups['UNDISPATCHED'][0],groups['INFEASIBLE'][0]=groups['INFEASIBLE'][0],groups['UNDISPATCHED'][0]
        with self.assertRaises(ValueError):subject.expected_domain(self.queue,self.ids,partition,self.sidecar)
    def result(self):
        groups={k:[] for k in ('FEASIBLE','INFEASIBLE','EVALUATION_EXCEPTION','VALIDATION_FAILURE','RAW_SAVED_POSTCHECK_MISSING','UNRESOLVED_DISPATCH','UNDISPATCHED')}
        groups['INFEASIBLE']=[i for segment in self.domain['segments'] for i in segment['task_ids']]
        return dict(schema='CASH_NEIGHBOR_RECOVERY_REQUEST_V1',status='COMPLETE_PENDING_INDEPENDENT_READBACK',registration_reference={'path':'registered','sha256':'a'*64},stopped=None,remaining_segment_descriptors=[],full_recovery_task_count=42301,completed_segment_references=[subject.ref(subject.RECOVERY/f'segment-{i:04d}/completion.json','b'*64) for i in range(45)],partition=dict(task_ids_by_status=groups,counts={k:len(v) for k,v in groups.items()},old_task_dispatch_count=0),old_tasks_reevaluated=False,continuous_source_monitoring_claimed=False,**subject.FLAGS)
    def test_full_recovery_requires_all_terminal_no_alias_or_segment_swap(self):
        result=self.result();subject.validate_recovery_result(result,result['registration_reference'],self.domain['segments'])
        for attack in ('missing','swap','unknown','bool'):
            candidate=deepcopy(result)
            if attack=='missing':candidate['completed_segment_references'].pop()
            elif attack=='swap':candidate['completed_segment_references'][0],candidate['completed_segment_references'][1]=candidate['completed_segment_references'][1],candidate['completed_segment_references'][0]
            elif attack=='unknown':candidate['partition']['task_ids_by_status']['UNRESOLVED_DISPATCH']=['x']
            else:candidate['partition']['old_task_dispatch_count']=False
            with self.subTest(attack=attack),self.assertRaises(ValueError):subject.validate_recovery_result(candidate,result['registration_reference'],self.domain['segments'])
    def test_merge_conflict_and_ordered_logical_shard(self):
        with self.assertRaises(ValueError):subject.merge_bindings({str(subject.SOURCE):'a'*64},{str(subject.SOURCE):'b'*64})
        with self.assertRaises(ValueError):subject.consume_block([dict(task_id='b',outcome='INFEASIBLE'),dict(task_id='a',outcome='INFEASIBLE')],['a','b'],dict(INFEASIBLE=0))
    def test_pending_registration_and_pure_fail_before_file_read(self):
        with patch.object(subject,'REGISTRATION_SHA',None),patch.object(Path,'read_bytes') as read:
            with self.assertRaises(ValueError):subject.run(registration_reference=subject.ref(subject.SOURCE,'a'*64),execute=True)
            read.assert_not_called()
    def test_bounded_load_checks_ram_before_open_and_authenticates_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source';path.write_bytes(b'bound bytes');reference=subject.ref(path,subject.sha(b'bound bytes'))
            with patch.object(Path,'open',side_effect=AssertionError('Must not read')):
                with self.assertRaises(ValueError):subject.load_bytes(reference,maximum_bytes=100,available=0)
            self.assertEqual(subject.load_bytes(reference,maximum_bytes=100,available=10*1024**3),b'bound bytes')
            with self.assertRaises(ValueError):subject.load_bytes(reference,maximum_bytes=1,available=10*1024**3)

if __name__=='__main__':unittest.main()
