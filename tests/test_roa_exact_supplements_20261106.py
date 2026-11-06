import unittest
from copy import deepcopy
from docs.candidates.roa_exact_supplements_20261106 import admit
class ExactSupplementTests(unittest.TestCase):
    def test_only_exact_event_and_missing_stream_preserved(self):
        observed={'security_id':'A','date':'2021-02-05','source':'raw','source_sha256':'a'*64,'kind':'dividends','provider_event':{'amount':.205,'date':123}}
        row={'observed_provider_events':[deepcopy(observed)]};event={'security_id':'A','ex_date':'2021-02-05'}
        gate={'unmapped_events':[observed],'missing_action_streams':[],'admitted':False}
        self.assertTrue(admit(gate,[(row,event)])['admitted'])
        for key,value in [('security_id','B'),('date','2021-02-06'),('source','other'),('source_sha256','b'*64)]:
            bad=deepcopy(gate);bad['unmapped_events'][0][key]=value
            self.assertFalse(admit(bad,[(row,event)])['admitted'])
        bad=deepcopy(gate);bad['unmapped_events'][0]['provider_event']['amount']=.21
        self.assertFalse(admit(bad,[(row,event)])['admitted'])
        bad=deepcopy(gate);bad['missing_action_streams']=['A']
        self.assertFalse(admit(bad,[(row,event)])['admitted'])
        self.assertEqual(gate['unmapped_events'],[observed])
        bad=deepcopy(gate);del bad['unmapped_events'][0]['source_sha256']
        self.assertFalse(admit(bad,[(row,event)])['admitted'])
if __name__=='__main__':unittest.main()
