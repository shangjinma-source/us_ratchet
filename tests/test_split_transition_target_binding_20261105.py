"""An old split transformation must never supply quantities for a new target."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest

import test_split_three_clock_daily_20261105 as fixture
from docs.candidates.split_three_clock_daily_evidence_20261105 import verify_transition_ancestry

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_original_target_accepts_but_replacement_bindings_are_rejected(self):
        with TemporaryDirectory(dir=ROOT / 'tmp') as directory:
            case, accounts, arguments = fixture.Tests().case(directory, 'AS_TRADED')
            with closing(sqlite3.connect(arguments['risk_path'])) as connection:
                preparation = json.loads(connection.execute(
                    'SELECT payload FROM split_preparation').fetchone()[0])
            values = dict(state=accounts.read(), transition=preparation['transition'],
                          risk_before=preparation['original_risk_state'],
                          target=case['target'], proposal_id=case['proposal']['proposal_id'])
            self.assertIsNotNone(verify_transition_ancestry(**values))
            before = deepcopy(values)
            for changed in ('target', 'proposal'):
                with self.subTest(changed=changed):
                    replacement = deepcopy(values)
                    if changed == 'target':
                        replacement['target']['target_id'] = 'new-month-target'
                    else:
                        replacement['proposal_id'] = 'new-month-proposal'
                    with self.assertRaisesRegex(ValueError, 'SPLIT_TRANSITION_TARGET_REQUIRES_NEW_MONTHLY_PATH'):
                        verify_transition_ancestry(**replacement)
            self.assertEqual(values, before)


if __name__ == '__main__':
    unittest.main()
