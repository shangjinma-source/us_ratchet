import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_latest_conditional_channels_20260919 as m

class ChannelRecipeTests(unittest.TestCase):
    def test_exclusive_atomic_attempt_and_orphan(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'A.started.json';m.exclusive_publish(p,{'attempt':1})
            with self.assertRaises(FileExistsError):m.exclusive_publish(p,{'attempt':1})
            with self.assertRaises(ValueError):m.scan_orphans(d,[])
            q=Path(d)/'B.started.json'
            with patch.object(m.os,'link',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):m.exclusive_publish(q,{})
            self.assertFalse(q.exists())
    def test_registry_cannot_invent_event(self):
        raw=json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':'A'},'events':{'splits':{'1655991000':{'date':1655991000,'numerator':5,'denominator':1,'splitRatio':'5:1'}}}}]}}).encode()
        with self.assertRaises(ValueError):m.event_policy('A',raw,{'url':'https://x/?period1=1&period2=2000000000'},[])
    def test_post_action_later_event_refused(self):
        raw=json.dumps({'chart':{'result':[{'events':{'splits':{'1655991000':{'date':1655991000,'numerator':5,'denominator':1}}}}]}}).encode()
        with self.assertRaises(ValueError):m.event_policy('EXC',raw,{},[],{'first_post_action_session':'2022-02-02'})
    def test_blocked_never_calls_kernel(self):
        with patch.object(m.kernel,'build_channel_input',side_effect=AssertionError('numeric call')):
            result=m.calculate({'ticker':'TRI','mode':'BLOCKED'},None,'abc')
        self.assertIsNone(result['result']);self.assertFalse(result['legal_training_input_admitted'])
    def test_budget_boolean_refused(self):
        with self.assertRaises(ValueError):m.execute('unused','unused','unused',max_new=True)

if __name__=='__main__':unittest.main()
