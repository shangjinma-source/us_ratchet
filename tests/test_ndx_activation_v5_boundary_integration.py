"""Real activation verifier/proof processes with an in-memory unpublished seal.

Only the two not-yet-published activation files are virtualized. This does not
prove canonical publication or Scheduled Task cutover, and is deliberately not
inside activation.TEST_SUITES: that would recursively invoke its own verifier.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backtest import ndx_dynamic_shadow_activation_v5 as activation
from scripts import ndx_dynamic_shadow_daily_v4 as daily


ROOT = Path(__file__).resolve().parents[1]


class ActivationBoundaryIntegrationTests(unittest.TestCase):
    def test_real_static_and_runtime_gate_without_publishing_seal(self):
        self.assertNotIn(Path(__file__).name, activation.TEST_SUITES)
        manifest_path = (ROOT / activation.MANIFEST).resolve()
        prefix_path = manifest_path.parent / "calendar_event_prefix.json"
        self.assertFalse(manifest_path.exists(), "run before formal seal publication only")
        protected = [ROOT / name for name in (
            "config/config.yaml", "data/state.json", "data/broker_positions.json")]
        before_protected = {path: path.read_bytes() for path in protected}
        before = activation._evidence(ROOT)
        # Execute actual bound test processes; no mock proof or lineage verifier.
        proofs = activation._runtime_proofs(ROOT)
        self.assertEqual(activation._evidence(ROOT), before)
        prefix = (json.dumps(before["events"], sort_keys=True, indent=2) + "\n").encode()
        payload = {
            "schema_version": 1, "manifest_type": "ndx_dynamic_shadow_activation_v5",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": activation.STATUS,
            "predecessor_static_manifest_sha256": before["predecessor"],
            "runner_contract": before["contract"], "sources": before["sources"],
            "runtime_proofs": proofs, "boundaries": dict(activation.BOUNDARIES),
            "calendar_event_prefix_file_sha256": hashlib.sha256(prefix).hexdigest(),
        }
        payload["manifest_sha256"] = activation._hash(payload)
        virtual = {manifest_path: json.dumps(payload, sort_keys=True).encode(), prefix_path: prefix}
        original_read_bytes, original_read_text = Path.read_bytes, Path.read_text

        def read_bytes(path):
            resolved = path.resolve()
            return virtual[resolved] if resolved in virtual else original_read_bytes(path)

        def read_text(path, *args, **kwargs):
            resolved = path.resolve()
            if resolved in virtual:
                return virtual[resolved].decode(kwargs.get("encoding") or "utf-8")
            return original_read_text(path, *args, **kwargs)

        try:
            with patch.object(Path, "read_bytes", read_bytes), patch.object(Path, "read_text", read_text):
                self.assertEqual(daily._verify_activation(static_only=True), payload)
                # This again executes real proof subprocesses via the real gate.
                self.assertEqual(daily._verify_activation(static_only=False), payload)
                poisoned = json.loads(virtual[manifest_path])
                poisoned["boundaries"]["live_mutation_allowed"] = True
                poisoned.pop("manifest_sha256")
                poisoned["manifest_sha256"] = activation._hash(poisoned)
                virtual[manifest_path] = json.dumps(poisoned).encode()
                with self.assertRaises(activation.ActivationV5Error):
                    daily._verify_activation(static_only=True)
        finally:
            self.assertFalse(manifest_path.exists())
            self.assertEqual(before_protected, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()
