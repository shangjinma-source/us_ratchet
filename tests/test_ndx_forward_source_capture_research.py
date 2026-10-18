import struct
import unittest
from backtest import ndx_forward_source_capture_research as module


def tzif():
    header=b'TZif2'+b'\0'*15+struct.pack('>6i',0,0,0,0,1,4)
    block=struct.pack('>iBB',-18000,0,0)+b'EST\0'
    return header+block+header+block+b'\nEST5EDT,M3.2.0,M11.1.0\n'


def csv_bytes(days, close='10'):
    return ('Date,Open,High,Low,Close,Volume\n'+''.join(f'{day},10,12,8,{close},100\n' for day in days)).encode()


def fixture(parent='2026-09-24', new=('2026-09-25',), start='2026-09-25T20:01:00+00:00', end=None):
    frontier={'schema':'OBSERVATION_GAP_FRONTIER_RESEARCH_V1',
        'known_accounted_rows':[{'session':parent,'kind':'SEALED_PARENT_OBSERVED_SESSION'}],
        'last_accounted_session':parent,'last_observed_session':parent,
        'parent_observed_session_count':1,'accounted_gap_count':0,
        'month_first_semantics':'UNRESOLVED_AFTER_GAP_NOT_AUTO_ELIGIBLE',
        **{key:False for key in ('fresh_observation','decision_eligible','candidate_seal_allowed',
                                'cohort_registration_allowed','point_in_time_verified','oos_recovery_completed')}}
    return dict(frontier=frontier,source_csv_bytes={key:csv_bytes([parent]+list(new)) for key in ('QQQ','SPY')},
        baseline_csv_bytes={key:csv_bytes([parent]) for key in ('QQQ','SPY')},tzif_bytes=tzif(),
        capture_started_at_utc=start,observed_at_utc=end or start)


class CaptureTests(unittest.TestCase):
    def test_weekend_dst_and_exact_deadline(self):
        value=module.plan_forward_source_capture(**fixture())
        self.assertEqual(value['timeliness_candidate']['conservative_next_weekday_open_utc'],'2026-09-28T13:30:00+00:00')
        args=fixture(start='2026-09-28T13:29:00+00:00',end='2026-09-28T13:30:00+00:00')
        self.assertIsNone(module.plan_forward_source_capture(**args)['timeliness_candidate'])
        value=module.plan_forward_source_capture(**fixture('2026-03-05',('2026-03-06',),'2026-03-06T21:01:00+00:00'))
        self.assertEqual(value['timeliness_candidate']['conservative_close_utc'],'2026-03-06T21:00:00+00:00')
        self.assertEqual(value['timeliness_candidate']['conservative_next_weekday_open_utc'],'2026-03-09T13:30:00+00:00')

    def test_cross_close_excluded_and_multiple_pending(self):
        args=fixture(start='2026-09-25T19:59:00+00:00',end='2026-09-25T20:01:00+00:00')
        value=module.plan_forward_source_capture(**args)
        self.assertEqual(value['excluded_unfinished_source_dates'],['2026-09-25'])
        self.assertIsNone(value['timeliness_candidate'])
        value=module.plan_forward_source_capture(**fixture(new=('2026-09-25','2026-09-28'),start='2026-09-28T20:01:00+00:00'))
        self.assertEqual(value['classifications'][0]['classification'],'MISSED_EARLIER_COMPLETED_SOURCE_SESSION')
        self.assertEqual(value['timeliness_candidate']['session'],'2026-09-28')
        self.assertFalse(value['fresh_observation'])

    def test_revision_and_no_new(self):
        args=fixture(new=())
        args['source_csv_bytes']['QQQ']=csv_bytes(['2026-09-24'],close='11')
        value=module.plan_forward_source_capture(**args)
        self.assertEqual(value['status'],'NO_NEW_SOURCE_SESSION')
        self.assertEqual(len(value['revisions']),1)
        self.assertEqual(value['revisions'][0]['baseline_evidence']['normalized_ohlcv']['Close'],'10')

    def test_bad_price_dates_prefix_and_clock(self):
        for replacement in (b'NaN',b'0',b'13'):
            args=fixture(); args['source_csv_bytes']['QQQ']=args['source_csv_bytes']['QQQ'].replace(b',10,100',b','+replacement+b',100')
            with self.assertRaises(ValueError): module.plan_forward_source_capture(**args)
        args=fixture(); args['source_csv_bytes']['QQQ']=csv_bytes(['2026-09-25'])
        with self.assertRaises(ValueError): module.plan_forward_source_capture(**args)

    def test_decimal_encoding_is_not_revision(self):
        args=fixture(new=())
        args['source_csv_bytes']['QQQ']=args['source_csv_bytes']['QQQ'].replace(b',10,12,8,10,100',b',10.00,12.0,8.00,1E1,1E2')
        self.assertEqual(module.plan_forward_source_capture(**args)['revisions'],[])

    def test_each_prefix_exact_and_unmatched_suffix_blocks_candidate(self):
        for role in ('source_csv_bytes','baseline_csv_bytes'):
            args=fixture('2026-09-23',(),start='2026-09-28T20:01:00+00:00')
            args['frontier']['known_accounted_rows'].append({'session':'2026-09-28','kind':'SEALED_PARENT_OBSERVED_SESSION'})
            args['frontier'].update(last_accounted_session='2026-09-28',last_observed_session='2026-09-28',parent_observed_session_count=2)
            for field in ('source_csv_bytes','baseline_csv_bytes'):
                args[field]={ticker:csv_bytes(['2026-09-23','2026-09-28']) for ticker in ('QQQ','SPY')}
            args[role]['QQQ']=csv_bytes(['2026-09-23','2026-09-24','2026-09-28'])
            with self.assertRaisesRegex(ValueError,'exact accounted prefix'):
                module.plan_forward_source_capture(**args)
        args=fixture(); args['source_csv_bytes']['QQQ']=csv_bytes(['2026-09-24','2026-09-25','2026-09-28'])
        value=module.plan_forward_source_capture(**args)
        self.assertIsNone(value['timeliness_candidate'])
        self.assertEqual(value['unmatched_new_source_dates_by_ticker']['QQQ'],['2026-09-28'])
        args=fixture(); args['baseline_csv_bytes']['QQQ']=csv_bytes(['2026-09-23'])
        with self.assertRaises(ValueError): module.plan_forward_source_capture(**args)
        args=fixture(); args['observed_at_utc']='2026-09-25T20:00:00+00:00'
        with self.assertRaises(ValueError): module.plan_forward_source_capture(**args)


if __name__=='__main__': unittest.main()
