from copy import deepcopy
import unittest

from backtest import ndx_persisted_fresh_snapshot_executor_v2_research as executor
from test_ndx_persisted_fresh_snapshot_executor_v2_research import fixture
from test_ndx_persisted_fresh_snapshot_executor_research import ref


class RootReview(unittest.TestCase):
    def test_later_gap_keeps_pointer_and_registers_bytes(self):
        arguments = fixture(True)
        value = arguments['execution_input']
        evidence = value['calendar']['document']['evidence']
        reference = dict(ref('root-gap'), json_pointer='/rows/a~1b/~0')
        rows = evidence['known_typed_rows_preserved']
        rows.insert(66, dict(sequence=67, session='2026-10-30', kind='MISSED_OBSERVATION',
                             seal_status='NOT_ATTEMPTED', evidence_reference=reference))
        rows[-1]['sequence'] = 68
        evidence['selected_existing_row'] = deepcopy(rows[-1])
        before = deepcopy(value)
        claims = {}
        result = executor.calendar_evidence(value['calendar'], value['observation_references'],
                                           value['observation_id'], executor.utc(arguments['execution_started_at_utc']), claims)
        self.assertEqual(result['known_typed_rows_preserved'][66]['evidence_reference'], reference)
        self.assertEqual(claims[reference['path']], reference['sha256'])
        self.assertEqual(value, before)
        with self.assertRaisesRegex(ValueError, 'Conflicting source'):
            executor.calendar_evidence(value['calendar'], value['observation_references'],
                                       value['observation_id'], executor.utc(arguments['execution_started_at_utc']),
                                       {reference['path']: 'f' * 64})


if __name__ == '__main__':
    unittest.main()
