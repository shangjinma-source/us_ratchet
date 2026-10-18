"""Independent synthetic boundary checks; no saved source projection or publication."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_gap_candidate_calendar_research as pf
import test_ndx_gap_candidate_calendar_adapter_20261003 as wf

p = pf.m
w = wf.m


class Review(unittest.TestCase):
    def test_whole_capture_interval_and_deadline_are_strict(self):
        for start, end, seal in [
            ('2026-10-02T19:59:59+00:00', '2026-10-02T20:00:01+00:00', '2026-10-02T20:00:02+00:00'),
            ('2026-10-02T20:00:00+00:00', '2026-10-05T13:30:00+00:00', '2026-10-05T13:30:00+00:00'),
        ]:
            a = pf.fixture()
            a['new_observation_evidence'][0].update(capture_started_at_utc=start, capture_completed_at_utc=end)
            a['clock_evidence']['seal_evaluation_at_utc'] = seal
            r = p.prepare_candidate_calendar_evidence(**a)
            self.assertIsNone(r['selected_row'])
            self.assertEqual(len(r['complete_typed_rows']), 2)
            self.assertTrue(r['monthly_coordinate'])
            self.assertTrue(all(r[k] is False for k in p.FLAGS))

    def test_source_prefix_revision_conflict_and_tzif(self):
        for mutation in ('drop', 'conflict', 'tzif'):
            a = pf.fixture()
            if mutation == 'drop':
                a['source_references']['complete_source_session_dates']['SPY'].pop(0)
            elif mutation == 'conflict':
                a['source_references']['references'].append(dict(path='capture', sha256='b'*64))
            else:
                a['clock_evidence']['tzif_bytes'] += b'changed'
            with self.assertRaises(ValueError):
                p.prepare_candidate_calendar_evidence(**a)
        a = pf.fixture()
        a['source_references']['revisions'] = [{'session': '2026-10-01', 'old': '1', 'new': '2'}]
        r = p.prepare_candidate_calendar_evidence(**a)
        self.assertIn('SOURCE_REVISION_REQUIRES_ADJUDICATION', r['reasons'])
        self.assertIsNone(r['selected_row'])

    def test_current_capture_candidate_never_becomes_observation(self):
        docs, refs, artifacts = wf.fixture()
        docs['capture']['plan']['capture_plan']['timeliness_candidate'] = {'session': '2026-10-02', 'timely': True}
        before = deepcopy(docs)
        args = w.project_inputs(docs, refs, artifacts)
        result = p.prepare_candidate_calendar_evidence(**args)
        self.assertEqual(docs, before)
        self.assertEqual(args['new_observation_evidence'], [])
        self.assertIsNone(args['decision_session'])
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertEqual(sum(r['kind']=='MISSED_OBSERVATION' for r in result['complete_typed_rows']), 5)
        self.assertEqual(sum(r['seal_status']=='UNKNOWN' for r in result['complete_typed_rows']), 60)

    def test_projection_original_indices_receipts_and_permissions(self):
        for mutation in ('index', 'include', 'ledger_receipt', 'authority', 'frontier'):
            docs, refs, artifacts = wf.fixture()
            docs = deepcopy(docs)
            ev = docs['capture']['plan']['csv_scope_evidence']['source']['QQQ']
            if mutation == 'index': ev['original_rows'][0]['original_data_row_index'] = False
            elif mutation == 'include': ev['included_original_row_indexes'][0] = False
            elif mutation == 'ledger_receipt': docs['ledger_publication']['artifacts']['ledger']['sha256'] = 'b'*64
            elif mutation == 'authority': docs['capture_publication']['candidate_seal_allowed'] = 0
            else: docs['frontier']['known_accounted_rows'].pop()
            with self.assertRaises(ValueError):
                w.project_inputs(docs, refs, artifacts)

    def test_failed_namespace_blocks_before_loading(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, 'OUTPUT', Path(tmp)), patch.object(w, 'load_inputs') as load:
            (Path(tmp)/'failure.json').write_text('{}')
            with self.assertRaises(ValueError): w.run(execute=True)
            load.assert_not_called()


if __name__ == '__main__': unittest.main()
