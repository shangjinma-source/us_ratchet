"""Independent gap transition attacks; all sources synthetic, no IO runtime."""
from copy import deepcopy
from hashlib import sha256
import unittest
from backtest import ndx_gap_history_independent_reconstruction_research_v1 as module
from backtest import ndx_prospective_gap_history_research_v5 as producer
from backtest import ndx_accounted_source_prefix_independent_reconstruction_research_v1 as prefix
from test_ndx_gap_history_independent_reconstruction_research_v1 import reconstruct
from test_ndx_prospective_history_parent_view_research_v5 import fixture,wrap,next_arguments
from test_ndx_prospective_gap_history_research_v5 import arguments,reference


class IndependentGapTransitionAttacks(unittest.TestCase):
    def test_repeat_v5_and_no_expired_keep_full_suffix_actuals_and_both_baseline_roles(self):
        first_args,_=fixture();first=reconstruct(first_args);parent=wrap(first,'independent_first')
        args=next_arguments(parent,first_args,('2026-10-14',),('2026-10-12',),'2026-10-13T20:02:00+00:00','independent_second')
        before=deepcopy(args);second=reconstruct(args)
        self.assertEqual(second,producer.extend_gap_history(**args));self.assertEqual(args,before)
        self.assertEqual((second['typed_row_count'],second['observation_count'],second['gap_count']),(72,2,10))
        self.assertEqual(second['observations'],first['observations']);self.assertEqual(second['baseline_references'],first['baseline_references'])
        self.assertEqual(second['known_typed_rows_preserved'],first['known_typed_rows'])
        last_args=next_arguments(wrap(second,'independent_second'),args,(),(),'2026-10-13T20:03:00+00:00','independent_last')
        last=reconstruct(last_args);self.assertEqual(last,producer.extend_gap_history(**last_args))
        self.assertEqual(last['known_typed_rows'],second['known_typed_rows']);self.assertEqual(last['status'],'NO_EXPIRED_SESSION_TO_APPEND')
        self.assertEqual([x['session']for x in last['pending_source_sessions']],['2026-10-13'])
        self.assertEqual([x['session']for x in last['excluded_not_completed_source_sessions']],['2026-10-14'])

    def test_prior_pending_unfinished_withdrawal_or_clock_regression_rejected(self):
        old_args,_=fixture();parent=wrap(reconstruct(old_args),'old')
        for mode in ('pending','unfinished','clock'):
            args=next_arguments(parent,old_args,(),(),'2026-10-12T20:03:00+00:00','new_'+mode)
            if mode=='clock':args['capture_started_at']='2026-10-12T19:00:00+00:00';args['capture_completed_at']='2026-10-12T19:00:01+00:00'
            else:
                day='2026-10-12'if mode=='pending'else'2026-10-13'
                for ticker in ('QQQ','SPY'):
                    args['source_bytes'][ticker]=args['source_bytes'][ticker].replace((day+',10,12,8,10,100\n').encode(),b'')
                    args['source_references'][ticker]=reference('synthetic/withdrawn/'+ticker,args['source_bytes'][ticker])
            with self.subTest(mode=mode),self.assertRaises(ValueError):reconstruct(args)

    def test_weekend_dst_deadline_crossing_remains_pending_until_entire_interval_expired(self):
        before=arguments(dates=('2026-10-09','2026-10-30'),start='2026-11-02T14:29:59+00:00',end='2026-11-02T14:30:01+00:00',expired=('2026-10-09',))
        result=reconstruct(before);self.assertEqual(result,producer.extend_gap_history(**before))
        self.assertEqual(result['new_missed_observation_count'],1)
        item=result['pending_source_sessions'][0];self.assertEqual(item['session'],'2026-10-30')
        self.assertEqual(item['conservative_close_utc'],'2026-10-30T20:00:00+00:00')
        self.assertEqual(item['conservative_next_weekday_open_utc'],'2026-11-02T14:30:00+00:00')
        exact=arguments(dates=('2026-10-09','2026-10-30'),start='2026-11-02T14:30:00+00:00',end='2026-11-02T14:30:00+00:00',expired=('2026-10-09','2026-10-30'))
        self.assertEqual(reconstruct(exact)['new_missed_observation_count'],2)
        self.assertEqual(reconstruct(exact)['observation_count'],2)

    def test_identical_cells_cannot_rewrite_accounted_raw_newline_prefix(self):
        args=arguments()
        for ticker in ('QQQ','SPY'):
            args['source_bytes'][ticker]=args['source_bytes'][ticker].replace(b'\n',b'\r\n')
            args['source_references'][ticker]=reference('synthetic/reformatted/'+ticker,args['source_bytes'][ticker])
        with self.assertRaisesRegex(ValueError,'raw byte prefix'):reconstruct(args)

    def test_full_evidence_artifact_lf_digest_is_distinct_from_summary_list_digests(self):
        args=arguments();result=reconstruct(args)
        for ticker in ('QQQ','SPY'):
            _,evidence=prefix.reconstruct_accounted_prefix(source_bytes=args['source_bytes'][ticker],source_reference=args['source_references'][ticker],
                accounted_sessions=[row['session']for row in result['known_typed_rows']],scope_start=result['known_typed_rows'][0]['session'])
            self.assertEqual(result['accounted_prefix_evidence'][ticker]['excluded_before_scope_rows_sha256'],sha256(module.encode(evidence['excluded_before_scope_rows'])).hexdigest())
            changed=deepcopy(args);changed['prefix_evidence_references'][ticker]['sha256']=sha256(module.encode(evidence)).hexdigest()
            with self.assertRaisesRegex(ValueError,'artifact SHA'):reconstruct(changed)

    def test_reusing_prior_capture_identity_cannot_duplicate_gap_pointers(self):
        first_args,_=fixture();first=reconstruct(first_args);parent=wrap(first,'old')
        args=next_arguments(parent,first_args,('2026-10-14',),('2026-10-12',),'2026-10-13T20:02:00+00:00','new')
        args['capture_references']=deepcopy(first['capture_references'])
        with self.assertRaisesRegex(ValueError,'Duplicate historical evidence pointer'):reconstruct(args)


if __name__=='__main__':unittest.main()
