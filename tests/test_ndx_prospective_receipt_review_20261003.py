"""Independent receipt preparation counterexamples, no actual observation."""
from copy import deepcopy
import unittest
import test_ndx_prospective_observation_receipt_research as owner
m=owner.m


class Review(unittest.TestCase):
    def test_historical_ohlc_issue_is_preserved_but_required_issue_rejected(self):
        a=owner.fixture()
        for role in ('sources','baseline_sources'):
            for ticker in ('QQQ','SPY'):
                item=a['capture'][role][ticker]
                header,rest=item['bytes'].split(b'\n',1)
                item['bytes']=header+b'\n2015-03-30,205.74,208,206.96,207,100\n'+rest
                item['reference']['sha256']=m.sha(item['bytes'])
        r=m.prepare_observation_payload(**a)
        self.assertEqual(r['source_row_locations']['SPY']['original_data_row_index'],2)
        self.assertEqual(r['full_original_sources_preserved']['SPY']['sources']['rows'][0]['Open'],'205.74')
        item=a['capture']['sources']['SPY'];item['bytes']=item['bytes'].replace(b'2026-10-02,10,11,9,10,100',b'2026-10-02,8,11,9,10,100');item['reference']['sha256']=m.sha(item['bytes'])
        with self.assertRaises(ValueError):m.prepare_observation_payload(**a)

    def test_inventory_exact_source_and_partial_blocks_next_observation(self):
        for kind in ('missing','wrongpayload','partial'):
            a=owner.fixture();a['known_typed_rows'][0].update(kind='PROSPECTIVE_OBSERVED_SESSION',seal_status='UNKNOWN')
            attempt=dict(observation_id='b'*64,status='PERSISTED_AND_INDEPENDENTLY_READ_BACK',session='2026-10-01',payload_reference=owner.ref('old'),receipt_reference=owner.ref('receipt'),independent_readback_reference=owner.ref('independent'))
            if kind=='wrongpayload':attempt['payload_reference']=owner.ref('another')
            elif kind=='partial':attempt['status']='PAYLOAD_WITHOUT_RECEIPT'
            a['parent_attempt_inventory']=[] if kind=='missing' else [attempt]
            with self.assertRaises(ValueError):m.prepare_observation_payload(**a)

    def test_late_writer_keeps_identity_and_month_while_clock_cannot_backdate(self):
        a=owner.fixture();before=deepcopy(a);timely=m.prepare_observation_payload(**a)
        self.assertEqual(a,before)
        a['writer_started_at_utc']=a['writer_completed_at_utc']='2026-10-05T13:30:00+00:00'
        late=m.prepare_observation_payload(**a)
        self.assertEqual(late['observation_id'],timely['observation_id'])
        self.assertEqual(late['timing_classification'],'LATE_OBSERVATION')
        self.assertTrue(late['month_first_actual_observation'])
        self.assertTrue(all(late[k] is False for k in m.FLAGS))
        a['writer_started_at_utc']='2026-10-02T19:59:59+00:00'
        with self.assertRaises(ValueError):m.prepare_observation_payload(**a)

    def test_hidden_date_drop_or_conflicting_sha_rejected(self):
        for kind in ('drop','conflict','tz'):
            a=owner.fixture()
            if kind=='drop':a['capture']['sources']['QQQ']=owner.csv_item('QQQ',['2026-10-02'])
            elif kind=='conflict':a['parent_readback_reference']=dict(a['parent_reference'],sha256='b'*64)
            else:a['capture']['tzif']['bytes']+=b'changed'
            with self.assertRaises(ValueError):m.prepare_observation_payload(**a)


if __name__=='__main__':unittest.main()
