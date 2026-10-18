"""Public projection from actual bounded review bytes; no network or real accounts."""
import json
import unittest
from copy import deepcopy
from types import SimpleNamespace
import test_current_quantity_v2_bounded_unit_review as fixtures
from data.current_quantity_v2_continuation_service import QuantityV2ContinuationSourceBridge


class PublicReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):fixtures.BoundedTests.setUpClass()
    @classmethod
    def tearDownClass(cls):fixtures.BoundedTests.tearDownClass()

    def test_validated_bounded_projection_has_no_raw_evidence(self):
        case=fixtures.BoundedTests()
        state,source,clock,calls,rss=case.setup_bounded()
        captured=source.capture(state)
        bridge=QuantityV2ContinuationSourceBridge(
            store=SimpleNamespace(read=lambda account_id:deepcopy(state)),
            resolver=source.resolve,clock=lambda:clock[0])
        result=bridge.preview(account_id=captured['account_id'],expected_revision=state['ledger']['revision'])
        review=result['unit_review']
        self.assertEqual(review['policy'],'BOUNDED_PUBLIC_KNOWN_ACTIONS_V1')
        self.assertIs(review['coverage_complete'],False)
        self.assertIs(review['source_authenticated'],False)
        self.assertIs(review['limited_name_coverage'],True)
        self.assertEqual(len(rss),1)
        self.assertEqual(len(calls),2)
        text=json.dumps(result)
        for key in ('bounded_evidence','files_base64','rss_raw_path','causal_inputs'):
            self.assertNotIn(key,text)

if __name__=='__main__':unittest.main()
