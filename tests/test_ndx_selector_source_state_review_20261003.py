from copy import deepcopy
import unittest
from backtest import ndx_full_ndx_multidecision_selector_research as selector
from test_ndx_full_ndx_multidecision_selector_research import fixture


class Review(unittest.TestCase):
    def test_source_block_is_distinct_from_absent_scores_and_preserves_two_modes(self):
        registration,records=fixture()
        blocked=registration['coordinates'][0]
        blocked.update(source_status='SOURCE_BLOCKED',source_blockers=[dict(reason_code='TARGET_MISSING',evidence_reference=deepcopy(registration['scope_reference']))])
        original=deepcopy(registration)
        result=selector.select_full_ndx_lanes(registration=registration,records=records[3:])
        self.assertEqual(registration,original)
        self.assertEqual(result['rows'][0]['unreceived_job_ids'],blocked['expected_job_ids'])
        self.assertEqual(result['rows'][0]['received_task_count'],0)
        self.assertEqual(result['rows'][0]['source_blocked_task_count'],3)
        self.assertTrue(all(c['status']=='SOURCE_BLOCKED' and c['selected'] is None for c in result['rows'][0]['choices']))
        self.assertTrue(all(c['selected'] is not None for c in result['rows'][1]['choices']))
        for supplied in (records[:1]+records[3:], records):
            out=selector.select_full_ndx_lanes(registration=registration,records=supplied)
            self.assertTrue(all(c['status']=='INPUT_INVALID' for c in out['rows'][0]['choices']))
        blocked.update(source_status='READY_FOR_SCORING',source_blockers=[])
        out=selector.select_full_ndx_lanes(registration=registration,records=records[3:])
        self.assertTrue(all(c['status']=='INPUT_INVALID' for c in out['rows'][0]['choices']))
        blocked['source_blockers']=[dict(reason_code='STALE_BLOCKER',evidence_reference=registration['scope_reference'])]
        with self.assertRaises(ValueError):selector.select_full_ndx_lanes(registration=registration,records=records)


if __name__=='__main__':unittest.main()
