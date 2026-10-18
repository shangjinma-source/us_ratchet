"""Pure mixed-suffix continuity, exact provenance and conservative clock attacks."""
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_prospective_gap_history_research_v5 as gap
from backtest import ndx_prospective_history_parent_view_research_v5 as view
from backtest import ndx_accounted_source_prefix_research_v1 as prefix
import test_ndx_prospective_gap_history_research_v5 as author
import test_ndx_prospective_history_parent_view_research_v5 as parents


def repin(args,expired):
    days=[r['session']for r in view.inspect_parent_history_v5(args['parent'])['known_typed_rows']]+list(expired)
    for ticker in ('QQQ','SPY'):
        args['source_references'][ticker]=author.reference(args['source_references'][ticker]['path'],args['source_bytes'][ticker])
        raw,evidence=prefix.derive_accounted_prefix(source_bytes=args['source_bytes'][ticker],source_reference=args['source_references'][ticker],
            accounted_sessions=days,scope_start=days[0])
        args['prefix_references'][ticker]=author.reference(args['prefix_references'][ticker]['path'],raw)
        args['prefix_evidence_references'][ticker]=author.reference(args['prefix_evidence_references'][ticker]['path'],gap.prefix_evidence_bytes(evidence))


class IndependentGapV5Tests(unittest.TestCase):
    def test_prior_captured_suffix_clock_cannot_move_backwards(self):
        args,h=parents.fixture();parent=parents.wrap(h)
        changed=parents.next_arguments(parent,args,(),(),'2026-10-12T19:00:00+00:00','clock-regression')
        with self.assertRaises(ValueError):gap.extend_gap_history(**changed)

    def test_repeat_pending_deleted_or_redated_cannot_silently_disappear(self):
        args,h=parents.fixture();parent=parents.wrap(h)
        changed=parents.next_arguments(parent,args,('2026-10-14',),('2026-10-12',),'2026-10-14T20:02:00+00:00','delete_pending')
        for ticker in ('QQQ','SPY'):
            changed['source_bytes'][ticker]=changed['source_bytes'][ticker].replace(b'2026-10-12,10,12,8,10,100\n',b'')
        repin(changed,('2026-10-13',))
        with self.assertRaises(ValueError):gap.extend_gap_history(**changed)
        first=author.arguments(dates=('2026-10-09','2026-10-12'));first_h=gap.extend_gap_history(**first)
        changed=parents.next_arguments(parents.wrap(first_h,'rename_first'),first,(),('2026-10-12',),
            '2026-10-13T20:02:00+00:00','rename_pending')
        for ticker in ('QQQ','SPY'):changed['source_bytes'][ticker]=changed['source_bytes'][ticker].replace(b'2026-10-12,',b'2026-10-13,')
        repin(changed,())
        with self.assertRaises(ValueError):gap.extend_gap_history(**changed)

    def test_repeat_unfinished_deleted_rejects_even_when_pending_preserved(self):
        args,h=parents.fixture();parent=parents.wrap(h)
        changed=parents.next_arguments(parent,args,('2026-10-14',),('2026-10-12',),'2026-10-13T20:02:00+00:00','delete_unfinished')
        for ticker in ('QQQ','SPY'):changed['source_bytes'][ticker]=changed['source_bytes'][ticker].replace(b'2026-10-13,10,12,8,10,100\n',b'')
        repin(changed,('2026-10-12',))
        with self.assertRaises(ValueError):gap.extend_gap_history(**changed)

    def test_same_unconsumed_dates_can_update_provisional_prices_without_actual_or_month_change(self):
        args,h=parents.fixture();parent=parents.wrap(h)
        changed=parents.next_arguments(parent,args,(),('2026-10-12',),'2026-10-13T20:02:00+00:00','provisional_update')
        for ticker in ('QQQ','SPY'):changed['source_bytes'][ticker]=changed['source_bytes'][ticker].replace(b'2026-10-13,10,12,8,10,100',b'2026-10-13,10,12,8,11,100')
        repin(changed,('2026-10-12',));result=gap.extend_gap_history(**changed)
        normalized=view.inspect_parent_history_v5(parents.wrap(result,'updated'))
        self.assertEqual(normalized['observation_count'],2);self.assertEqual(normalized['first_actual_observed_session_by_month']['2026-10'],'2026-10-02')
        self.assertEqual(normalized['last_observed_session'],'2026-10-08')
        self.assertEqual([x['session']for x in result['pending_source_sessions']],['2026-10-13'])

    def test_prefix_and_full_evidence_hash_independent_and_tzif_or_clock_lie_reject(self):
        for mutate in (
            lambda a:a['prefix_evidence_references']['QQQ'].update(sha256=a['prefix_references']['QQQ']['sha256']),
            lambda a:a['prefix_references']['SPY'].update(sha256=a['source_references']['SPY']['sha256']),
            lambda a:a.update(tzif_bytes=a['tzif_bytes']+b'changed'),
            lambda a:a.update(capture_started_at='2026-10-12T20:02:00+08:00'),
            lambda a:a.update(capture_completed_at='2026-10-12T19:00:00+00:00')):
            a=author.arguments();mutate(a)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):gap.extend_gap_history(**a)

    def test_no_expired_and_all_unfinished_remain_exact_unconsumed_without_io(self):
        a=author.arguments(dates=('2026-10-09',),start='2026-10-09T19:59:59+00:00',end='2026-10-09T20:00:01+00:00',expired=())
        before=deepcopy(a)
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure IO')):h=gap.extend_gap_history(**a)
        self.assertEqual(a,before);self.assertEqual(h['new_missed_observation_count'],0);self.assertEqual(h['new_observation_count'],0)
        self.assertEqual(h['known_typed_rows'],h['known_typed_rows_preserved']);self.assertEqual(h['pending_source_sessions'],[])
        self.assertEqual([x['session']for x in h['excluded_not_completed_source_sessions']],['2026-10-09'])
        self.assertTrue(all(h[k] is False for k in gap.FLAGS));self.assertNotIn('timing_classification_recomputed_from_tzif',h)


if __name__=='__main__':unittest.main()
