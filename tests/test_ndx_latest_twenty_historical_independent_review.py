"""Independent input mapping boundaries; never build, fit, or publish."""
import copy
import unittest
import test_ndx_latest_twenty_historical_inputs_20260919 as owner_fixture
from scripts import ndx_latest_twenty_historical_inputs_20260919 as m


class TwentyInputsIndependentReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner_fixture.HistoricalInputTests.setUpClass()
        cls.fixture=owner_fixture.HistoricalInputTests

    def test_specific_ratio_boolean_cannot_authenticate_share_units(self):
        f=self.fixture;bad=copy.deepcopy(f.witness);bad[0]['denominator']=True
        with self.assertRaises(ValueError):m.inspect_channel('NFLX',f.rows,f.raw,f.calendar,bad)

    def test_nav_noncanonical_date_and_backward_calendar_rejected(self):
        for raw,calendar in [(b'Date,Close\n2026-09-017,1\n',['2026-09-17']),
                             (b'Date,Close\n2026-09-10,1\n2026-09-17,2\n',['2026-09-17','2026-09-10'])]:
            with self.assertRaises(ValueError):m.map_nav(raw,calendar)

    def test_future_nav_is_not_used_before_its_observation_date(self):
        value=m.map_nav(b'Date,Close\n2026-03-18,1\n2026-03-20,1000\n',['2026-03-18','2026-03-19'])
        self.assertEqual([r['nav'] for r in value['rows']],['1','1'])
        self.assertFalse(value['future_nav_observation_used'])
        self.assertFalse(value['publication_time_verified'])
        self.assertFalse(value['legal_comparison_ready'])

    def test_utc_receipt_uses_new_york_day_not_utc_date(self):
        calendar=['2026-09-17']
        with self.assertRaises(ValueError):m.verify_receipt('2026-09-18T03:00:00+00:00',calendar)
        with self.assertRaises(ValueError):m.verify_receipt('2026-09-18T12:00:00+08:00',calendar)
        with self.assertRaises(ValueError):m.verify_receipt('2026-09-18T12:00:00',calendar)
        self.assertEqual(m.verify_receipt('2026-09-18T05:00:00+00:00',calendar),'2026-09-18')


if __name__=='__main__':unittest.main()
