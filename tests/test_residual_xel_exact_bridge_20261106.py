import unittest,json
from copy import deepcopy
from unittest.mock import patch
from pathlib import Path
from docs.candidates import residual_xel_exact_bridge_20261106 as bridge
class ExactXelBridge(unittest.TestCase):
    def setUp(self):
        self.event=json.loads((bridge.ROOT/bridge.REVIEW).read_text())['review_rows'][0]['observed_provider_events'][0]
    def test_exact_mapping_does_not_modify_event_or_gate(self):
        gate={'admitted':False,'unmapped_events':[deepcopy(self.event),{'security_id':'other'}],'missing_action_streams':['other']};before=deepcopy(gate)
        result=bridge.map_event(gate['unmapped_events'][0]);self.assertEqual(result['amount_per_share'],'183/400');self.assertEqual(result['payment_date'],'2021-07-20');self.assertEqual(gate,before)
    def test_payload_identity_date_and_source_are_exact(self):
        for key,value in [('date','2021-06-15'),('security_id','security:xel'),('source_sha256','0'*64),('provider_event',{'amount':.4575,'date':1623677400}),('provider_event',{'amount':.45801,'date':1623677400}),('provider_event',{'amount':.458,'date':1623677401})]:
            event=deepcopy(self.event);event[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):bridge.map_event(event)
    def test_changed_review_or_raw_source_rejected(self):
        original=Path.read_bytes
        for name in (bridge.REVIEW,self.event['source']):
            def altered(path):return original(path)+b' ' if path==bridge.ROOT/name else original(path)
            with self.subTest(name=name),patch.object(Path,'read_bytes',altered),self.assertRaisesRegex(ValueError,'SOURCE_HASH_MISMATCH'):bridge.map_event(self.event)
if __name__=='__main__':unittest.main()
