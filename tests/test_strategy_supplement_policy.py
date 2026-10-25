"""Real policy verifier with isolated source fixtures; no live authorization."""
from copy import deepcopy
from hashlib import sha256
from tempfile import TemporaryDirectory
import json
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_monthly_supplement_capture import review_supplement_policy
import test_strategy_daily_domain_policy_review_v1 as fixture


class SupplementPolicyTests(unittest.TestCase):
    def case(self, folder):
        context, root, arguments = fixture.DomainPolicyReviewTests().setup(folder)
        decision = None
        for sid, packet in arguments['packets'].items():
            receipt = json.loads(packet['receipt_bytes'])
            inputs = json.loads(packet['files'][receipt['normalized_inputs_path']])
            decision = inputs['base_target']['monthly_decision_date']
            name = 'monthly-full-'+sid+'.json'
            packet['files'][name] = canonical(inputs)
            receipt['monthly_history_inputs_path'] = name
            receipt['source_sha256'][name] = sha256(packet['files'][name]).hexdigest()
            packet['receipt_bytes'] = canonical(receipt)
            packet['trusted_receipt_sha256'] = sha256(packet['receipt_bytes']).hexdigest()
        return context, arguments, decision

    def test_policy_review_keeps_complete_domain_monthly_references(self):
        with TemporaryDirectory() as folder:
            context, arguments, decision = self.case(folder)
            before = context.store.path.read_bytes()
            result = review_supplement_policy(decision_date=decision, **arguments)
            self.assertEqual(result['status'], 'DOMAIN_POLICY_REVIEW_READY_NOT_PUBLISHED')
            self.assertEqual(set(result['receipt']['monthly_history_inputs']), {'A', 'B'})
            self.assertEqual(result['receipt_sha256'], sha256(canonical(result['receipt'])).hexdigest())
            self.assertFalse(result['published'])
            self.assertFalse(result['policy_approved'])
            self.assertEqual(before, context.store.path.read_bytes())

    def test_changed_monthly_price_is_rejected_after_policy_review(self):
        with TemporaryDirectory() as folder:
            context, arguments, decision = self.case(folder)
            packet = arguments['packets']['A']
            receipt = json.loads(packet['receipt_bytes'])
            name = receipt['monthly_history_inputs_path']
            inputs = json.loads(packet['files'][name])
            inputs['histories']['A']['closes'][-1]['close'] = '999'
            packet['files'][name] = canonical(inputs)
            receipt['source_sha256'][name] = sha256(packet['files'][name]).hexdigest()
            packet['receipt_bytes'] = canonical(receipt)
            packet['trusted_receipt_sha256'] = sha256(packet['receipt_bytes']).hexdigest()
            before = context.store.path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'SUPPLEMENT_MONTHLY_PRICE_CHANGED'):
                review_supplement_policy(decision_date=decision, **arguments)
            self.assertEqual(before, context.store.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
