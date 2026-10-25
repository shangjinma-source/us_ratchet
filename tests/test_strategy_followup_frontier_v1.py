from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from data.strategy_advice_followup_plan_v2 import resolve_policy_binding as old_resolve
from data.strategy_advice_followup_plan_v3 import resolve_policy_binding, FRONTIER_POLICY
from data.strategy_followup_close_review_v2 import review_close
from test_strategy_advice_followup_plan_v2 import PolicyBindingTests
from test_strategy_followup_close_review_v1 import CloseReviewTests

class FrontierFollowupTests(unittest.TestCase):
    def test_nested_old_release_cannot_override_frontier_and_old_unchanged(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);event,ref=PolicyBindingTests().case(root)
            self.assertEqual(resolve_policy_binding(event,root=root),old_resolve(event,root=root))
            event['response'].update(policy_id=FRONTIER_POLICY,proposal_id='a'*64)
            release=json.loads((root/'release.json').read_bytes());release['policy_id']=FRONTIER_POLICY
            raw=json.dumps(release).encode();(root/'frontier.json').write_bytes(raw)
            event['policy_references']['frontier_release']=dict(path='frontier.json',sha256=sha256(raw).hexdigest())
            with self.assertRaisesRegex(ValueError,'FOLLOWUP_CAP_POLICY_AMBIGUOUS'):old_resolve(event,root=root)
            self.assertEqual(resolve_policy_binding(event,root=root),(FRONTIER_POLICY,sha256(raw).hexdigest()))
            event['policy_references'].pop('frontier_release')
            with self.assertRaisesRegex(ValueError,'FRONTIER_RELEASE_REQUIRED'):resolve_policy_binding(event,root=root)

    def test_monthly_window_and_sha_reference_close_observation(self):
        args=CloseReviewTests().fixture();args['observation']['policy_id']=FRONTIER_POLICY
        history=args['baseline_inputs']['histories']['sid'];history['closes']=history['closes'][-3:]
        history['source_reference']='sha256:'+sha256(args['baseline_files']['raw']).hexdigest()
        result=review_close(**args)
        self.assertEqual(result['baseline_overlap_sessions'],3)
        self.assertEqual(result['price_change_vs_reference'],'-1/10')
        self.assertFalse(result['actual_fill_inferred'])
        changed=deepcopy(args);changed['baseline_inputs']['histories']['sid']['closes'][0]['close']='1000'
        with self.assertRaisesRegex(ValueError,'NORMALIZATION_DIFFERENCE'):review_close(**changed)

    def test_old_close_unchanged(self):
        from data.strategy_followup_close_review_v1 import review_close as old_close
        args=CloseReviewTests().fixture()
        self.assertEqual(review_close(**args),old_close(**args))
