import json
import tempfile
import unittest
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from data.strategy_advice_followup_plan_v2 import resolve_policy_binding, plan_journal_page
from data.strategy_advice_followup_plan_v1 import plan_journal_page as original_plan
import test_strategy_advice_followup_plan_v1 as fixture

class PolicyBindingTests(unittest.TestCase):
    def case(self,root):
        release=dict(policy_id='MONTHLY_CAP50_EXIT20',authorized=True,authorized_at='2026-10-23T14:00:00+00:00',monthly_cap='1/2',exit_ratio='4/5',sma20_overlay=False)
        raw=json.dumps(release).encode();(root/'release.json').write_bytes(raw)
        ref=dict(path='release.json',sha256=sha256(raw).hexdigest())
        event=dict(generated_at='2026-10-23T15:00:00+00:00',response=dict(policy_id='MONTHLY_CAP50_EXIT20'),
            policy_references=dict(base=dict(base=dict(base=dict(policy_id='OLD'),cap_exit_release=ref),supplement={}),risk_history={}))
        return event,ref

    def test_nested_actual_version_and_no_event_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);event,ref=self.case(root);before=deepcopy(event)
            self.assertEqual(resolve_policy_binding(event,root=root),('MONTHLY_CAP50_EXIT20',ref['sha256']))
            self.assertEqual(event,before)

    def test_changed_release_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);event,_=self.case(root);(root/'release.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'RELEASE_CHANGED'):resolve_policy_binding(event,root=root)

    def test_policy_conflict_future_and_path_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);event,ref=self.case(root)
            conflict=deepcopy(event);conflict['policy_references']['cap_exit_release']=ref
            with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):resolve_policy_binding(conflict,root=root)
            future=deepcopy(event);future['generated_at']='2026-10-22T15:00:00+00:00'
            with self.assertRaisesRegex(ValueError,'AUTHORIZED_AFTER'):resolve_policy_binding(future,root=root)
            ref['path']='../release.json'
            with self.assertRaisesRegex(ValueError,'RELEASE_PATH'):resolve_policy_binding(event,root=root)

    def test_missing_cap_never_uses_old_release(self):
        event=dict(response=dict(policy_id='MONTHLY_CAP50_EXIT20'),policy_references=dict(policy_id='OLD',evidence_references=dict(trusted_release_sha256='a'*64)))
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):resolve_policy_binding(event)

    def test_legacy_page_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            _,journal,clock,_,raw,_=fixture.FollowupPlanTests().setup_case(folder)
            args=dict(journal=journal,account_id='account',calendar_bytes=raw,calendar_sha256=sha256(raw).hexdigest(),now=clock[0])
            self.assertEqual(plan_journal_page(**args),original_plan(**args))
