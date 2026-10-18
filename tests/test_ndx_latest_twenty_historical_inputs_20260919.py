import copy
import gzip
import json
import unittest
from decimal import Decimal
from scripts import ndx_latest_twenty_historical_inputs_20260919 as m


class HistoricalInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sources={};readiness=m.read(m.REFS['readiness'],sources);cls.calendar=readiness['observed_reference_calendar'][-253:]
        reference=dict(path=str(m.BASE/'current101_conditional_prices_20260919_v1/NFLX.json'),sha256='2ac83d8804236f8922b17edd7a75443511f7011890c50c534f054c1c27a90d78')
        cls.quote=m.read(reference,sources);cls.raw=m.raw_read(dict(path=cls.quote['raw_path'],sha256=cls.quote['raw_sha256']),sources)
        cls.rows=cls.quote['result']['reconstruction']['rows'];cls.witness=cls.quote['result']['matched_specific_events']

    def test_actual_nflx_fit_split_is_supported_and_neutral(self):
        channel,proof=m.inspect_channel('NFLX',self.rows,self.raw,self.calendar,self.witness)
        event,=channel['split_events'];self.assertEqual(event['session'],'2025-11-17')
        self.assertLess(event['session'],self.calendar[127]);self.assertEqual(proof['decimal_open_close_cells'],506)
        by_date={r['session']:r for r in channel['nominal_rows']};i=self.calendar.index(event['session']);a=by_date[self.calendar[i-1]]['close'];b=by_date[event['session']]['close']
        self.assertLess(b/a-1,-.8);self.assertGreater(b*10/a-1,-.5)

    def test_missing_event_support_and_price_corruption_rejected(self):
        with self.assertRaises(ValueError):m.inspect_channel('NFLX',self.rows,self.raw,self.calendar,[])
        bad=copy.deepcopy(self.rows);next(r for r in bad if r['session']==self.calendar[0])['nominal_close']*=10
        with self.assertRaises(ValueError):m.inspect_channel('NFLX',bad,self.raw,self.calendar,self.witness)
        bad=copy.deepcopy(self.witness);bad[0]['specific_event_matched']=1
        with self.assertRaises(ValueError):m.inspect_channel('NFLX',self.rows,self.raw,self.calendar,bad)

    def test_nav_maps_only_past_and_never_certifies_publication(self):
        value=m.map_nav(b'Date,Close\n2026-03-18,1\n2026-03-20,2\n',['2026-03-18','2026-03-19','2026-03-20'])
        self.assertEqual(value['rows'][1]['nav_source_date'],'2026-03-18');self.assertEqual(value['same_date_missing_count'],1)
        self.assertEqual(Decimal(value['returns'][0]['conditional_original_currency_return']),0)
        self.assertFalse(value['publication_time_verified']);self.assertFalse(value['legal_comparison_ready'])
        with self.assertRaises(ValueError):m.map_nav(b'Date,Close\n2026-03-20,2\n',['2026-03-19'])

    def test_source_hash_and_unsealed_kernel_fail_closed(self):
        with self.assertRaises(ValueError):m.raw_read(dict(path=m.REFS['panel']['path'],sha256='0'*64),{})
        if m.PURE_SHA is None:
            with self.assertRaises(ValueError):m.build()


if __name__=='__main__':unittest.main()
