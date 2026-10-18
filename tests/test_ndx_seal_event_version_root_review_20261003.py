"""Observation adapter version must agree with a seal event's V2 audit."""
import unittest

from backtest import ndx_observation_seal_events_research as subject
from test_ndx_observation_seal_events_review_20261003 import observed_v2


class SealObservationVersion(unittest.TestCase):
    def test_foreign_writer_adapter_is_not_authenticated_by_v2_audit_label(self):
        for role in ('payload', 'receipt'):
            for replacement in (None, 'FOREIGN_WRITER'):
                observation = observed_v2()
                if replacement is None:
                    observation[role].pop('writer_adapter_schema', None)
                else:
                    observation[role]['writer_adapter_schema'] = replacement
                with self.subTest(role=role, replacement=replacement), self.assertRaises(ValueError):
                    subject.observed(observation)


if __name__ == '__main__':
    unittest.main()
