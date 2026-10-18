from __future__ import annotations

import json
import unittest

from scripts.ndx_dynamic_shadow_task_migration_notary import (
    EVIDENCE_ALGORITHMS,
    EVIDENCE_ROOT,
    NEW_TASK,
    NOTARY_LEDGER,
    OLD_TASK,
    _load_evidence,
    _verify_notary_ledger,
    verify_declared_record,
)


class TaskMigrationHistoricalEvidenceTest(unittest.TestCase):
    """Validate the immutable v2 rollback observation at its recorded time."""

    def test_historical_rollback_records_and_chain_remain_verifiable(self):
        verified, payloads = _load_evidence()

        self.assertEqual(set(verified), set(EVIDENCE_ALGORITHMS))
        for name, algorithm in EVIDENCE_ALGORITHMS.items():
            self.assertEqual(
                verify_declared_record(EVIDENCE_ROOT / name, algorithm),
                verified[name],
            )
        self.assertEqual(
            payloads["rollback.json"]["post_cutover_record_sha256"],
            payloads["post_cutover.json"]["record_sha256"],
        )

    def test_historical_notary_does_not_reinterpret_current_task_state(self):
        records = _verify_notary_ledger(NOTARY_LEDGER)

        self.assertGreaterEqual(len(records), 1)
        observation = records[-1]
        self.assertEqual(
            observation["manifest_type"],
            "ndx_dynamic_shadow_task_migration_rollback_notary",
        )
        self.assertTrue(observation["scheduler_rollback_verified"])
        self.assertFalse(observation["runtime_recovery_claimed"])
        self.assertTrue(observation["runtime_calendar_revision_unresolved"])
        self.assertTrue(observation["task_state"][OLD_TASK]["enabled"])
        self.assertFalse(observation["task_state"][NEW_TASK]["enabled"])

        raw_lines = [
            json.loads(line)
            for line in NOTARY_LEDGER.read_text(encoding="utf-8").splitlines()
            if line
        ]
        self.assertEqual(records, raw_lines)


if __name__ == "__main__":
    unittest.main()
