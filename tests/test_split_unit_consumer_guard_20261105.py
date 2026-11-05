from hashlib import sha256
from unittest.mock import patch
import unittest
from core.strategy_account_ledger import canonical
from docs.candidates import strategy_account_split_unit_review as consumer
from docs.candidates.split_three_clock_review_20261105 import review_recorded_splits
from docs.candidates.split_unit_consumer_guard_20261105 import review_interval
from test_split_unit_review_v1 import split_case
from data.strategy_recorded_split_review_v1 import review_recorded_splits as legacy_matcher


class ConsumerBoundary(unittest.TestCase):
    def test_content_only_cannot_be_promoted_by_guarded_consumer(self):
        arguments,action=split_case()
        matcher_args={key:arguments[key] for key in ('state','securities','action_package','now')}
        self.assertEqual(review_recorded_splits(**matcher_args),legacy_matcher(**matcher_args))
        proof=dict(schema='SPLIT_THREE_CLOCK_CONTENT_V1',action_id=action['action_id'],
                   recorded_action_sha256=sha256(canonical(action)).hexdigest(),
                   distribution_at=action['effective_at'],quote_unit_effective_at=action['effective_at'],
                   broker_tradable_at=action['broker_confirmed_at'],
                   source_references=[next(iter(arguments['action_package']['source_hashes']))])
        def content(**kwargs):return review_recorded_splits(timing_reviews=[proof],**kwargs)
        # Demonstrate the existing consumer DOES promote the marked-only result.
        with patch.object(consumer,'review_recorded_splits',side_effect=content):
            unsafe=consumer.review_interval(**arguments)
        self.assertEqual(unsafe['status'],'CONDITIONAL_CURRENT_UNITS_REVIEWED')
        self.assertTrue(unsafe['recorded_split_review']['execution_blocked'])
        with self.assertRaisesRegex(ValueError,'CONTENT_ONLY_NOT_CURRENT_UNIT_ADMISSION'):
            review_interval(split_reviewer=content,**arguments)
        self.assertEqual(review_interval(**arguments),consumer.review_interval(**arguments))


if __name__=='__main__':unittest.main()
