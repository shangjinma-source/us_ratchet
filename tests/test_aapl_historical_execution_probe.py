import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from scripts.research.probe_aapl_historical_execution_events import inspect

class ProbeTests(unittest.TestCase):
    def sample(self, date='2021-06-01'):
        start=int(datetime.fromisoformat(date+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())
        return dict(s='ok',t=list(range(start,start+390*60,60)),o=[101]*390,h=[102]*390,l=[100.5]*390,c=[101]*390,v=[100]*390)

    def test_does_not_fill_before_order_submission(self):
        d=self.sample();d['o'][0]=100;d['l'][0]=99
        r=inspect(json.dumps(d).encode(),dict(date='2021-06-01',side='BUY'))
        self.assertIsNone(r['arms'][0]['fill'])
        self.assertEqual(r['arms'][1]['fill']['minute'],60)
        self.assertEqual(r['arms'][1]['limit'],101)

    def test_wrong_date_rejected(self):
        with self.assertRaises(ValueError):
            inspect(json.dumps(self.sample()).encode(),dict(date='2021-06-02',side='BUY'))

    def test_missing_minutes_not_padded(self):
        d=self.sample();d['t'].pop()
        with self.assertRaises(ValueError):
            inspect(json.dumps(d).encode(),dict(date='2021-06-01',side='BUY'))

if __name__=='__main__': unittest.main()
