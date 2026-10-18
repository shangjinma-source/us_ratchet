from copy import deepcopy
import unittest
from scripts import ndx_cash_neighbor_recovery_worker_20261008 as subject


class IndependentRecoveryWorkerReview(unittest.TestCase):
    def fixture(self):
        segments=[dict(task_ids=[key*64]) for key in ('a','b')]
        reports=[dict(segment=segment,status='COMPLETE_PENDING_INDEPENDENT_READBACK',
            inspection=dict(terminal_rows=[dict(task_id=segment['task_ids'][0],status='INFEASIBLE')],
                active=None,undispatched_task_ids=[],complete=True)) for segment in segments]
        return dict(segments=segments),reports

    def test_technical_terminal_at_segment_end_stops_later_segment(self):
        for status in ('EVALUATION_EXCEPTION','VALIDATION_FAILURE'):
            domain,reports=self.fixture()
            reports[0]['inspection']['terminal_rows'][0]['status']=status
            reports[0]['status']='STOPPED_NO_AUTOMATIC_RETRY'
            with self.subTest(status=status),self.assertRaises(ValueError):
                subject.request_partition(domain,reports)

    def test_same_count_ids_swapped_across_segments_rejected(self):
        domain,reports=self.fixture()
        reports[0]['inspection']['terminal_rows'][0]['task_id']='b'*64
        reports[1]['inspection']['terminal_rows'][0]['task_id']='a'*64
        with self.assertRaises(ValueError):
            subject.request_partition(domain,reports)

    def test_positive_complete_partition_and_terminal_last_failure(self):
        domain,reports=self.fixture()
        value=subject.request_partition(domain,reports)
        self.assertEqual(value['counts']['INFEASIBLE'],2)
        reports[-1]['inspection']['terminal_rows'][0]['status']='VALIDATION_FAILURE'
        reports[-1]['status']='STOPPED_NO_AUTOMATIC_RETRY'
        value=subject.request_partition(domain,reports)
        self.assertEqual(value['counts']['VALIDATION_FAILURE'],1)


if __name__=='__main__':unittest.main()
