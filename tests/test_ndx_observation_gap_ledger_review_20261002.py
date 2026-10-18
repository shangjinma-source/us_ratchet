from copy import deepcopy
import hashlib,json
import unittest
from backtest import ndx_observation_gap_ledger_research as m
from test_ndx_observation_gap_ledger_research import fixture

class IndependentGapReview(unittest.TestCase):
    def test_hashchain_independent_and_prefix_permissions(self):
        a=fixture(); first=m.append_missed_observations(**a)
        b=fixture('2026-09-28'); b['existing_ledger']=first
        second=m.append_missed_observations(**b)
        self.assertEqual(second['events'][:1],first['events'])
        previous=a['parent_binding']['event_tail_sha256']
        for seq,event in enumerate(second['events'],67):
            self.assertEqual(event['event_sequence'],seq); self.assertEqual(event['previous_event_sha256'],previous)
            unsigned={k:v for k,v in event.items() if k!='event_sha256'}
            expected=hashlib.sha256(json.dumps(unsigned,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
            self.assertEqual(event['event_sha256'],expected); previous=expected
            for key in m.FALSE: self.assertIs(event[key],False)
            self.assertIsNone(event['historical_source_first_observed_at_utc'])
        self.assertEqual(second['terminal_event_sha256'],previous)
        self.assertEqual(second['old_last_observed_session_unchanged'],'2026-09-24')

    def test_type_substitution_in_saved_ledger_rejected(self):
        a=fixture(); original=m.append_missed_observations(**a)
        for level,key,value in [('root','fresh_session_increment',False),('root','fresh_observation',0),('event','decision_eligible',0),('event','event_sequence',67.0)]:
            ledger=deepcopy(original); target=ledger if level=='root' else ledger['events'][0]; target[key]=value
            with self.subTest(level=level,key=key),self.assertRaises(ValueError): m.validate_gap_ledger(ledger=ledger,parent_binding=a['parent_binding'])

    def test_capture_clock_cannot_regress_across_append(self):
        a=fixture(capture='2026-10-02T15:00:00+00:00'); first=m.append_missed_observations(**a)
        b=fixture('2026-09-28',capture='2026-10-02T14:00:00+00:00'); b.update(existing_ledger=first,recorded_at_utc='2026-10-04T00:00:00+00:00')
        with self.assertRaises(ValueError): m.append_missed_observations(**b)

    def test_nonlate_missing_source_date_and_parent_prefix(self):
        for kind in ('timely','future','same_day','source','parent','naive'):
            a=fixture(); row=a['classification_capture']['classification']['pending_classifications'][0]
            if kind=='timely': row['classification']='TIMELINESS_CANDIDATE_NOT_YET_SEALED'
            elif kind=='future': row['conservative_seal_deadline_utc']='2026-10-03T13:30:00+00:00'
            elif kind=='same_day': row['session']='2026-09-24'
            elif kind=='source': a['classification_capture']['pending_source_rows']['SPY']['2026-09-25']['Date']='2026-09-26'
            elif kind=='parent': a['classification_capture']['parent_references']['calendar_events']=dict(path='other',sha256='b'*64)
            else: a['recorded_at_utc']='2026-10-03T00:00:00'
            with self.subTest(kind=kind),self.assertRaises(ValueError): m.append_missed_observations(**a)

if __name__=='__main__': unittest.main()
