from copy import deepcopy
import unittest
from backtest import ndx_observation_gap_frontier_research as m
from test_ndx_observation_gap_frontier_research import fixture

class FrontierIndependentReview(unittest.TestCase):
    def test_future_dates_are_only_unaccounted_no_authority(self):
        a=fixture(); a['common_source_session_dates']=['2026-09-22']+a['common_source_session_dates']+['2026-10-02','2026-11-02']
        original=deepcopy(a); r=m.prepare_observation_frontier(**a)
        self.assertEqual(a,original)
        self.assertEqual(r['unaccounted_source_dates'],['2026-10-02','2026-11-02'])
        self.assertEqual(r['last_observed_session'],'2026-09-24');self.assertEqual(r['last_accounted_session'],'2026-10-01')
        self.assertEqual(r['excluded_source_dates_before_parent_start'],['2026-09-22'])
        self.assertEqual([v['kind'] for v in r['known_accounted_rows']],['SEALED_PARENT_OBSERVED_SESSION']*2+['MISSED_OBSERVATION']*5)
        for key in m.FALSE_FIELDS:self.assertIs(r[key],False)
        for key in m.INCREMENTS:self.assertIs(type(r[key]),int);self.assertEqual(r[key],0)
        self.assertEqual(r['month_first_semantics'],'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE')

    def test_full_prefix_not_tail_or_intersection_and_date_types(self):
        for kind in ('old_missing','gap_missing','reverse','weekend','date_object','extra_middle'):
            a=fixture()
            if kind=='old_missing':a['common_source_session_dates'].pop(0)
            elif kind=='gap_missing':a['common_source_session_dates'].pop(3)
            elif kind=='reverse':a['common_source_session_dates'].reverse()
            elif kind=='weekend':a['common_source_session_dates'].append('2026-10-03')
            elif kind=='date_object':
                from datetime import date
                a['common_source_session_dates'][-1]=date(2026,10,1)
            else:
                a['parent_session_dates'].pop(0);a['gap_ledger']['parent_binding']['session_count']=1
                a['common_source_session_dates'].insert(3,'2026-09-26')
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare_observation_frontier(**a)

    def test_event_sequence_and_permission_types_cannot_be_projected(self):
        for mutate in (
            lambda a:a['gap_ledger']['events'][-1].update(event_sequence=8.0),
            lambda a:a['gap_ledger']['events'][-1].update(fresh_observation=0),
            lambda a:a['gap_ledger'].update(cohort_increment=False),
            lambda a:a['gap_ledger']['events'][-1].update(session='2026-09-24'),
            lambda a:a['gap_ledger'].update(old_last_observed_session_unchanged='2026-10-01')):
            a=fixture();mutate(a)
            with self.assertRaises(ValueError):m.prepare_observation_frontier(**a)

if __name__=='__main__':unittest.main()
