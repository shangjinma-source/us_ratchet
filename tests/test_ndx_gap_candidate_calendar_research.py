from copy import deepcopy
from pathlib import Path
import unittest
from backtest import ndx_gap_candidate_calendar_research as m

def ref(name,pointer=None):
    r={'path':name,'sha256':'a'*64}
    if pointer:r['json_pointer']=pointer
    return r

def fixture(session='2026-10-02'):
    tz=Path(__file__).resolve().parents[1]/'data/cache/research/forward_source_capture_scoped_20261002_v1/New_York.tzif'
    blob=tz.read_bytes()
    prior='2026-10-01' if session=='2026-10-02' else '2026-10-29'
    known=[dict(sequence=1,session=prior,kind='MISSED_OBSERVATION',evidence_reference=ref('old','/rows/0'),seal_status='NOT_ATTEMPTED')]
    evidence=dict(evidence_kind='RESEARCH_SUPPLIED_OBSERVATION_NOT_AUTHENTICATED',typed_row=dict(sequence=2,session=session,kind='PROSPECTIVE_OBSERVED_SESSION',evidence_reference=ref('receipt','/rows/0'),seal_status='NOT_ATTEMPTED'),capture_reference=ref('capture'),observation_reference=ref('receipt','/rows/0'),capture_started_at_utc=session+'T20:00:00+00:00',capture_completed_at_utc=session+'T20:00:01+00:00',source_rows={t:dict(Date=session,Open='1',High='1',Low='1',Close='1',Volume='1') for t in ('QQQ','SPY')})
    return dict(policy_id=m.POLICY,known_typed_rows=known,new_observation_evidence=[evidence],decision_session=session,capture_reference=ref('capture'),clock_evidence=dict(tzif_bytes=blob,tzif_reference=dict(path=str(tz),sha256=m.sha(blob)),seal_evaluation_at_utc=session+'T20:00:02+00:00'),source_references=dict(coverage_reference=ref('coverage'),references=[],complete_source_session_dates={t:[prior,session] for t in ('QQQ','SPY')},revisions=[]))

class Tests(unittest.TestCase):
    def test_gap_does_not_consume_month_but_does_not_grant_authority(self):
        args=fixture();before=deepcopy(args);r=m.prepare_candidate_calendar_evidence(**args)
        self.assertTrue(r['monthly_coordinate']);self.assertEqual(r['status'],'CONDITIONAL_RESEARCH_PREREQUISITES_ONLY')
        self.assertTrue(all(r[k] is False for k in m.FLAGS));self.assertEqual(args,before)
    def test_failed_or_unknown_first_still_consumes_month(self):
        for status in ('FAILED','UNKNOWN','SEALED'):
            a=fixture();old=a['new_observation_evidence'][0]['typed_row'];old['seal_status']=status;a['known_typed_rows'].append(old)
            ev=deepcopy(a['new_observation_evidence'][0]);ev['typed_row'].update(sequence=3,session='2026-10-05',seal_status='NOT_ATTEMPTED',evidence_reference=ref('next','/rows/0'));ev['observation_reference']=ref('next','/rows/0')
            for r in ev['source_rows'].values():r['Date']='2026-10-05'
            ev['capture_started_at_utc']='2026-10-05T20:00:00+00:00';ev['capture_completed_at_utc']='2026-10-05T20:00:01+00:00'
            a.update(new_observation_evidence=[ev],decision_session='2026-10-05');a['clock_evidence']['seal_evaluation_at_utc']='2026-10-05T20:00:02+00:00'
            for ds in a['source_references']['complete_source_session_dates'].values():ds.append('2026-10-05')
            r=m.prepare_candidate_calendar_evidence(**a);self.assertIn('NOT_FIRST_ACTUAL_OBSERVATION_OF_MONTH',r['reasons']);self.assertIsNone(r['selected_row']);self.assertEqual(r['months'][0]['first_observed_session'],'2026-10-02')
    def test_late_capture_does_not_delete_observation_and_dst(self):
        a=fixture('2026-10-30');r=m.prepare_candidate_calendar_evidence(**a);self.assertEqual(r['timing_status']['conservative_next_weekday_open_utc'],'2026-11-02T14:30:00+00:00')
        a['new_observation_evidence'][0]['capture_completed_at_utc']='2026-11-02T14:30:00+00:00';a['clock_evidence']['seal_evaluation_at_utc']='2026-11-02T14:30:00+00:00'
        r=m.prepare_candidate_calendar_evidence(**a);self.assertTrue(r['monthly_coordinate']);self.assertIsNone(r['selected_row']);self.assertIn('CAPTURE_INTERVAL_OUTSIDE_CONSERVATIVE_WINDOW',r['reasons'])
    def test_complete_sources_and_exact_types(self):
        a=fixture();a['source_references']['complete_source_session_dates']['QQQ'].append('2026-10-05');r=m.prepare_candidate_calendar_evidence(**a);self.assertIn('SOURCE_SUFFIX_ASYMMETRY',r['reasons'])
        for mutation in ('bool','naive','duplicate'):
            a=fixture()
            if mutation=='bool':a['known_typed_rows'][0]['sequence']=True
            elif mutation=='naive':a['clock_evidence']['seal_evaluation_at_utc']='2026-10-02T20:00:02'
            else:a['new_observation_evidence'][0]['observation_reference']=a['known_typed_rows'][0]['evidence_reference'];a['new_observation_evidence'][0]['typed_row']['evidence_reference']=a['known_typed_rows'][0]['evidence_reference']
            with self.assertRaises(ValueError):m.prepare_candidate_calendar_evidence(**a)
    def test_no_receipt_no_selection(self):
        a=fixture();a.update(new_observation_evidence=[],decision_session=None)
        for t in ('QQQ','SPY'):a['source_references']['complete_source_session_dates'][t]=['2026-10-01']
        r=m.prepare_candidate_calendar_evidence(**a);self.assertEqual(r['status'],'BLOCKED');self.assertIn('NO_NEW_OBSERVATION_EVIDENCE',r['reasons']);self.assertIsNone(r['selected_row'])

if __name__=='__main__':unittest.main()
