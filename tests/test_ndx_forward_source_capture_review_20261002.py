from copy import deepcopy
from decimal import localcontext,Inexact
import struct,unittest
from backtest import ndx_forward_source_capture_research as m
from test_ndx_forward_source_capture_research import fixture,csv_bytes

class SourceCaptureIndependentReview(unittest.TestCase):
    def test_interval_edges_dst_bytes_and_false_permissions(self):
        for start,end,expected in [('2026-09-25T19:59:59+00:00','2026-09-25T20:01:00+00:00',False),('2026-09-25T20:00:00+00:00','2026-09-28T13:29:59+00:00',True),('2026-09-25T20:00:00+00:00','2026-09-28T13:30:00+00:00',False)]:
            a=fixture(start=start,end=end);r=m.plan_forward_source_capture(**a)
            self.assertEqual(r['timeliness_candidate'] is not None,expected)
            for key in m.FALSE:self.assertIs(r[key],False)
        a=fixture(start='2026-09-25T17:00:00+00:00')
        header=b'TZif'+b'\0'*16+struct.pack('>6i',0,0,0,0,1,4)
        a['tzif_bytes']=header+struct.pack('>iBB',0,0,0)+b'UTC\0'
        r=m.plan_forward_source_capture(**a)
        self.assertEqual(r['timeliness_candidate']['conservative_close_utc'],'2026-09-25T16:00:00+00:00')
        self.assertIn('NOT_INDEPENDENTLY_CERTIFIED',r['timezone_semantics'])

    def test_each_source_accounted_prefix_not_intersection(self):
        for mapping in ('source_csv_bytes','baseline_csv_bytes'):
            a=fixture(parent='2026-09-24',new=('2026-09-28',),start='2026-09-28T20:01:00+00:00')
            f=a['frontier'];f['known_accounted_rows'].append(dict(session='2026-09-28',kind='MISSED_OBSERVATION',counts_as_observed_session=False,decision_eligible=False));f['last_accounted_session']='2026-09-28';f['accounted_gap_count']=1
            a['baseline_csv_bytes']={t:csv_bytes(['2026-09-24','2026-09-28']) for t in ('QQQ','SPY')}
            a[mapping]['QQQ']=csv_bytes(['2026-09-24','2026-09-25','2026-09-28'])
            with self.subTest(mapping=mapping),self.assertRaises(ValueError):m.plan_forward_source_capture(**a)

    def test_revision_preserves_original_and_hostile_context(self):
        a=fixture(new=());a['source_csv_bytes']['QQQ']=csv_bytes(['2026-09-24'],close='11.00000000000000000001');saved=deepcopy(a)
        with localcontext() as c:
            c.prec=2;c.traps[Inexact]=True;r=m.plan_forward_source_capture(**a)
        self.assertEqual(a,saved);self.assertEqual(len(r['revisions']),1)
        self.assertEqual(r['revisions'][0]['current_evidence']['normalized_ohlcv']['Close'],'11.00000000000000000001')
        self.assertEqual(r['revisions'][0]['baseline_evidence']['normalized_ohlcv']['Close'],'10')
        self.assertEqual(r['last_observed_session_unchanged'],'2026-09-24')

    def test_strict_bytes_header_row_and_utc(self):
        for kind in ('duplicate','extra_field','negative_volume','tz_truncated','offset','naive'):
            a=fixture()
            if kind=='duplicate':a['source_csv_bytes']['QQQ']+=b'2026-09-25,10,12,8,10,100\n'
            elif kind=='extra_field':a['source_csv_bytes']['QQQ']=a['source_csv_bytes']['QQQ'].replace(b'10,100\n',b'10,100,extra\n')
            elif kind=='negative_volume':a['source_csv_bytes']['QQQ']=a['source_csv_bytes']['QQQ'].replace(b',100\n',b',-1\n')
            elif kind=='tz_truncated':a['tzif_bytes']=b'TZif'
            elif kind=='offset':a['observed_at_utc']='2026-09-25T22:01:00+02:00'
            else:a['capture_started_at_utc']='2026-09-25T20:01:00'
            with self.subTest(kind=kind),self.assertRaises((ValueError,struct.error)):m.plan_forward_source_capture(**a)

    def test_asymmetric_suffix_and_equivalent_decimal_encoding(self):
        a=fixture();a['source_csv_bytes']['QQQ']=csv_bytes(['2026-09-24','2026-09-25','2026-09-28'])
        r=m.plan_forward_source_capture(**a)
        self.assertEqual(r['unmatched_new_source_dates_by_ticker'],{'QQQ':['2026-09-28'],'SPY':[]})
        self.assertEqual(r['status'],'SOURCE_SUFFIX_ASYMMETRY_REQUIRES_REVIEW');self.assertIsNone(r['timeliness_candidate'])
        a=fixture(new=())
        a['source_csv_bytes']['QQQ']=a['source_csv_bytes']['QQQ'].replace(b',10,',b',1e1,').replace(b',100\n',b',100.000\n')
        with localcontext() as c:
            c.prec=2;c.traps[Inexact]=True;r=m.plan_forward_source_capture(**a)
        self.assertEqual(r['revisions'],[])
        self.assertIn('1e1',r['source_rows']['QQQ']['2026-09-24']['raw_csv_row'].values())

if __name__=='__main__':unittest.main()
