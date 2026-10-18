import base64,hashlib
from copy import deepcopy
import unittest
from backtest import ndx_forward_source_capture_scoped_research as m
from test_ndx_forward_source_capture_research import fixture,csv_bytes

def args():
    a=fixture()
    for mapping in ('source_csv_bytes','baseline_csv_bytes'):
        for ticker in ('QQQ','SPY'):
            raw=a[mapping][ticker];head,tail=raw.split(b'\n',1)
            a[mapping][ticker]=head+b'\n2015-03-30,205.74,208,206.96,207,100\n'+tail
    return a

class ScopedTests(unittest.TestCase):
    def test_old_anomaly_preserved_not_consumed_full(self):
        a=args();before=deepcopy(a);r=m.plan_scoped_forward_source_capture(**a)
        self.assertEqual(a,before);self.assertEqual(r['scope_start'],'2026-09-24')
        self.assertIsNotNone(r['capture_plan']['timeliness_candidate'])
        for role,key in [('source','source_csv_bytes'),('baseline','baseline_csv_bytes')]:
            for ticker in ('QQQ','SPY'):
                e=r['csv_scope_evidence'][role][ticker]
                self.assertEqual(base64.b64decode(e['original_csv_bytes_base64']),a[key][ticker])
                self.assertEqual(e['excluded_original_row_indexes'],[0]);self.assertEqual(e['included_original_row_indexes'][0],1)
                self.assertEqual(e['excluded_before_scope_ohlc_diagnostics'][0]['violations'],['LOW_EXCEEDS_OPEN'])
                self.assertNotIn('2015-03-30',e['scoped_csv_utf8'])
                self.assertEqual(r['capture_plan'][role+'_sha256'][ticker],e['scoped_sha256'])
                self.assertNotEqual(e['original_sha256'],e['scoped_sha256'])
        self.assertFalse(r['frozen_capture_consumed_full_original_csv']);self.assertFalse(r['decision_eligible'])

    def test_needed_bad_fails_and_no_date_drop(self):
        for kind in ('needed','old_nan','old_date_duplicate','missing_prefix'):
            a=args()
            if kind=='needed':a['source_csv_bytes']['SPY']=a['source_csv_bytes']['SPY'].replace(b'2026-09-25,10,12,8',b'2026-09-25,7,12,8')
            elif kind=='old_nan':a['source_csv_bytes']['SPY']=a['source_csv_bytes']['SPY'].replace(b'205.74',b'NaN')
            elif kind=='old_date_duplicate':a['source_csv_bytes']['SPY']=a['source_csv_bytes']['SPY'].replace(b'2015-03-30',b'2026-09-24')
            else:a['source_csv_bytes']['SPY']=a['source_csv_bytes']['SPY'].replace(b'2026-09-24,10,12,8,10,100\n',b'')
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.plan_scoped_forward_source_capture(**a)

    def test_header_timezone_and_full_hash_not_aliased(self):
        a=args();a['source_csv_bytes']['QQQ']=a['source_csv_bytes']['QQQ'].replace(b'Date,',b'Date,Extra,',1)
        with self.assertRaises(ValueError):m.plan_scoped_forward_source_capture(**a)
        a=args();a['observed_at_utc']='2026-09-25T22:01:00+02:00'
        with self.assertRaises(ValueError):m.plan_scoped_forward_source_capture(**a)
        a=args();r=m.plan_scoped_forward_source_capture(**a)
        for ticker in ('QQQ','SPY'):
            self.assertEqual(r['original_source_sha256'][ticker],hashlib.sha256(a['source_csv_bytes'][ticker]).hexdigest())
            self.assertEqual(r['scoped_source_sha256'][ticker],r['capture_plan']['source_sha256'][ticker])
        self.assertEqual(r['capture_plan']['tzif_sha256'],hashlib.sha256(a['tzif_bytes']).hexdigest())

if __name__=='__main__':unittest.main()
