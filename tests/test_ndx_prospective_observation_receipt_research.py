from copy import deepcopy
import csv,io
from pathlib import Path
import unittest
from backtest import ndx_prospective_observation_receipt_research as m

def ref(path):return dict(path=path,sha256='a'*64)
def csv_item(path,dates):
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=m.FIELDS,lineterminator='\n');w.writeheader()
    for d in dates:w.writerow(dict(Date=d,Open='10',High='11',Low='9',Close='10',Volume='100'))
    b=stream.getvalue().encode();return dict(bytes=b,reference=dict(path=path,sha256=m.sha(b)))
def fixture(session='2026-10-02'):
    prior='2026-10-01' if session=='2026-10-02' else '2026-10-29'
    tz=(Path(__file__).resolve().parents[1]/'data/cache/research/forward_source_capture_scoped_20261002_v1/New_York.tzif').read_bytes()
    capture=dict(reference=ref('capture'),started_at_utc=session+'T20:00:00+00:00',completed_at_utc=session+'T20:00:01+00:00',sources={t:csv_item(t,[prior,session]) for t in ('QQQ','SPY')},baseline_sources={t:csv_item('base'+t,[prior]) for t in ('QQQ','SPY')},tzif=dict(bytes=tz,reference=dict(path='tz',sha256=m.sha(tz))))
    return dict(parent_reference=ref('parent'),parent_readback_reference=ref('audit'),known_typed_rows=[dict(sequence=1,session=prior,kind='MISSED_OBSERVATION',seal_status='NOT_ATTEMPTED',evidence_reference=dict(ref('old'),json_pointer='/rows/0'))],parent_attempt_inventory=[],capture=capture,session=session,writer_started_at_utc=session+'T20:00:02+00:00',writer_completed_at_utc=session+'T20:00:03+00:00')

class Tests(unittest.TestCase):
    def test_single_observation_gap_and_late_preserves_coordinate(self):
        a=fixture();before=deepcopy(a);r=m.prepare_observation_payload(**a);self.assertTrue(r['month_first_actual_observation']);self.assertEqual(a,before);self.assertTrue(all(r[k] is False for k in m.FLAGS))
        a['writer_completed_at_utc']='2026-10-05T13:30:00+00:00';late=m.prepare_observation_payload(**a);self.assertEqual(late['timing_classification'],'LATE_OBSERVATION');self.assertTrue(late['month_first_actual_observation']);self.assertEqual(late['observation_id'],r['observation_id'])
    def test_clock_and_dst(self):
        a=fixture('2026-10-30');self.assertEqual(m.prepare_observation_payload(**a)['conservative_deadline_utc'],'2026-11-02T14:30:00+00:00')
        for key,value in [('writer_started_at_utc','2026-10-30T19:00:00+00:00'),('writer_started_at_utc','2026-10-30T20:00:02')]:
            b=deepcopy(a);b[key]=value
            with self.assertRaises(ValueError):m.prepare_observation_payload(**b)
        a['capture']['started_at_utc']='2026-10-30T19:59:59+00:00'
        with self.assertRaises(ValueError):m.prepare_observation_payload(**a)
    def test_asymmetry_multi_dates_and_revisions(self):
        for kind in ('asymmetric','multi','revision'):
            a=fixture()
            if kind=='asymmetric':a['capture']['sources']['QQQ']=csv_item('QQQ',['2026-10-01','2026-10-02','2026-10-05'])
            elif kind=='multi':
                for t in ('QQQ','SPY'):a['capture']['sources'][t]=csv_item(t,['2026-10-01','2026-10-02','2026-10-05'])
            else:
                item=a['capture']['sources']['QQQ'];item['bytes']=item['bytes'].replace(b'100',b'101',1);item['reference']['sha256']=m.sha(item['bytes'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):m.prepare_observation_payload(**a)
    def test_incomplete_attempt_and_wrong_hash(self):
        a=fixture();a['parent_attempt_inventory']=[dict(observation_id='b'*64,status='PAYLOAD_WITHOUT_RECEIPT')]
        with self.assertRaises(ValueError):m.prepare_observation_payload(**a)
        a=fixture();a['capture']['sources']['QQQ']['reference']['sha256']='0'*64
        with self.assertRaises(ValueError):m.prepare_observation_payload(**a)
    def test_failed_observation_not_replaced_by_later_month_day(self):
        a=fixture();a['known_typed_rows'][0].update(kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='FAILED')
        a['parent_attempt_inventory']=[dict(observation_id='b'*64,status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',session='2026-10-01',payload_reference=ref('old'),receipt_reference=ref('receipt'),independent_readback_reference=ref('independent'))]
        r=m.prepare_observation_payload(**a);self.assertFalse(r['month_first_actual_observation']);self.assertEqual(r['first_actual_observed_session_of_month'],'2026-10-01')
        a['known_typed_rows'][0]['seal_status']='UNKNOWN';self.assertFalse(m.prepare_observation_payload(**a)['month_first_actual_observation'])

if __name__=='__main__':unittest.main()
