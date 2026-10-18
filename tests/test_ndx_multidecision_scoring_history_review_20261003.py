"""Independent 505/13 window and missing-slot oracle; synthetic provider bytes only."""
from copy import deepcopy
import json
import unittest

from test_ndx_multidecision_scoring_history_research import fixture, bind, m


class ScoringHistoryReview(unittest.TestCase):
    def test_all_78_window_positions_from_external_calendar(self):
        a=fixture();before=deepcopy(a);out=m.materialize_scoring_history_channel(**a)
        reference=a['reference_calendar'];union=out['calendar']
        for d in out['decisions']:
            last=reference.index(d['cutoff']);required=reference[last-504:last+1]
            self.assertEqual(d['required_price_dates'],required)
            self.assertEqual(len(d['windows']),13)
            for i,w in enumerate(d['windows']):
                wanted=required[21*i:21*i+253]
                self.assertEqual(union[w['price_index_start']:w['price_index_stop']],wanted)
                training=out['return_rows'][w['training_return_index_start']:w['training_return_index_stop']]
                evaluation=out['return_rows'][w['evaluation_return_index_start']:w['evaluation_return_index_stop']]
                self.assertEqual([r['session'] for r in training],wanted[1:127])
                self.assertEqual([r['session'] for r in evaluation],wanted[127:])
                self.assertEqual(training[0]['previous_session'],wanted[0])
                self.assertTrue(set(r['session'] for r in training).isdisjoint(r['session'] for r in evaluation))
                self.assertLessEqual(evaluation[-1]['session'],d['cutoff'])
            self.assertIs(d['scoring_allowed'],False)
            self.assertIs(d['pooling_only_unblocked_windows_allowed'],False)
        self.assertEqual(a,before)

    def test_missing_raw_date_blocks_both_adjacent_returns_without_dropping_window(self):
        a=fixture();day='2026-03-31';body=json.loads(a['raw_bytes']);channel=body['chart']['result'][0]
        i=a['reference_calendar'].index(day);channel['timestamp'].pop(i)
        for values in channel['indicators']['quote'][0].values():values.pop(i)
        bind(a,body);out=m.materialize_scoring_history_channel(**a);j=out['calendar'].index(day)
        self.assertIsNone(out['quote_rows'][j]['raw_row_index'])
        self.assertIn('MISSING_REQUIRED_PRICE_DATE',out['quote_rows'][j]['reasons'])
        for k in (j-1,j):
            self.assertIsNone(out['return_rows'][k]['split_only_return_exact'])
            self.assertIsNone(out['return_rows'][k]['split_only_return_float'])
        self.assertEqual(len(out['return_rows']),len(out['calendar'])-1)
        for d in out['decisions']:
            for w in d['windows']:
                dates=out['calendar'][w['price_index_start']:w['price_index_stop']]
                self.assertEqual(w['status']=='BLOCKED_WINDOW',day in dates)
            self.assertEqual(len(d['windows']),13)
        self.assertEqual(out['decisions'][0]['status'],'BLOCKED_FULL13_SCORING_SUPPLY')

    def test_future_split_reconstruction_is_retrospective_not_price_information(self):
        a=fixture();out=m.materialize_scoring_history_channel(**a)
        before=next(r for r in out['quote_rows'] if r['session']=='2026-06-11')
        after=next(r for r in out['quote_rows'] if r['session']=='2026-06-12')
        self.assertEqual(before['raw_close'],after['raw_close'])
        self.assertEqual(before['split_factor_exact'],'10');self.assertEqual(after['split_factor_exact'],'1')
        self.assertEqual(next(r for r in out['return_rows'] if r['session']=='2026-06-12')['split_only_return_exact'],'0')
        self.assertIs(out['later_returned_actions_used_only_for_retrospective_unit_assumption'],True)
        self.assertIs(out['decision_time_action_knowledge_verified'],False)
        self.assertIs(out['outer_inventory_completeness_verified'],False)
        self.assertTrue(all(out[k] is False for k in m.FLAGS))

    def test_denominator_contract_and_event_mapping_not_resignable(self):
        for change in [lambda a:a['window_contract'].update(windows_per_decision=12),
                       lambda a:a['outer_inventory_contract'].update(issuer_count=True),
                       lambda a:a['outer_inventory_contract']['preserved_sidecar_references'].pop(next(iter(m.SIDECARS))),
                       lambda a:a['bridge_row']['event_policy_bridge']['events'][0].update(provider_event_key='missing'),
                       lambda a:a['receipt'].update(http_status=True)]:
            a=fixture();change(a)
            with self.assertRaises((ValueError,KeyError)):m.materialize_scoring_history_channel(**a)


if __name__=='__main__':unittest.main()
