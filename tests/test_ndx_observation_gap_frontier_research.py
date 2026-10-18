import copy
import unittest
from backtest import ndx_observation_gap_frontier_research as module


def fixture():
    parent = ['2026-09-23', '2026-09-24']
    gaps = ['2026-09-25', '2026-09-28', '2026-09-29', '2026-09-30', '2026-10-01']
    ledger = {'schema': module.LEDGER_SCHEMA,
        'parent_binding': {'session_count': 2, 'event_count': 3, 'last_session': parent[-1]},
        'old_last_observed_session_unchanged': parent[-1], 'missed_observation_count': 5,
        'events': [{'schema': 'MISSED_OBSERVATION_EVIDENCE_EVENT_V1', 'event_type': 'MISSED_OBSERVATION',
            'event_sequence': 4+i, 'session': day, 'event_sha256': str(i)*64,
            **{key: False for key in module.FALSE_FIELDS}} for i, day in enumerate(gaps)],
        **{key: 0 for key in module.INCREMENTS}, **{key: False for key in module.FALSE_FIELDS}}
    return dict(parent_session_dates=parent, gap_ledger=ledger, common_source_session_dates=parent+gaps)


class FrontierTests(unittest.TestCase):
    def test_complete_prefix_separates_gap_cursor(self):
        args=fixture(); before=copy.deepcopy(args)
        value=module.prepare_observation_frontier(**args)
        self.assertEqual(args,before)
        self.assertEqual(value['last_observed_session'],'2026-09-24')
        self.assertEqual(value['last_accounted_gap_session'],'2026-10-01')
        self.assertEqual(value['unaccounted_source_dates'],[])
        self.assertEqual(value['month_first_semantics'],'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE')
        self.assertFalse(value['known_accounted_rows'][-1]['decision_eligible'])

    def test_unaccounted_future_is_not_observed_or_month_first(self):
        args=fixture(); args['common_source_session_dates'] += ['2026-10-02','2026-10-05']
        result=module.prepare_observation_frontier(**args)
        self.assertEqual(result['unaccounted_source_dates'],['2026-10-02','2026-10-05'])
        self.assertEqual(len(result['known_accounted_rows']),7)
        self.assertFalse(result['fresh_observation']); self.assertFalse(result['first_observed_session_of_month'])

    def test_missing_duplicate_and_extra_prefix_dates_rejected(self):
        for index in (0,1,2,6):
            args=fixture(); args['common_source_session_dates'].pop(index)
            with self.assertRaises(ValueError): module.prepare_observation_frontier(**args)
        args=fixture(); args['common_source_session_dates'].append('2026-10-01')
        with self.assertRaises(ValueError): module.prepare_observation_frontier(**args)
        args=fixture(); args['common_source_session_dates'].insert(0,'2026-09-22')
        self.assertEqual(module.prepare_observation_frontier(**args)['excluded_source_dates_before_parent_start'],['2026-09-22'])

    def test_strict_counts_permissions_parent_and_event_types(self):
        for mutate in (
            lambda a:a['gap_ledger'].update(observed_session_increment=False),
            lambda a:a['gap_ledger'].update(fresh_observation=0),
            lambda a:a['gap_ledger']['parent_binding'].update(session_count=True),
            lambda a:a['gap_ledger']['parent_binding'].update(last_session='2026-09-25'),
            lambda a:a['gap_ledger']['events'][0].update(event_type='PROSPECTIVE_V2_SESSION_OBSERVED'),
            lambda a:a['gap_ledger']['events'][0].update(decision_eligible=True),
        ):
            args=fixture(); mutate(args)
            with self.assertRaises(ValueError): module.prepare_observation_frontier(**args)


if __name__=='__main__': unittest.main()
