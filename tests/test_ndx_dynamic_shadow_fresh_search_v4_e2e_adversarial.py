"""Independent post-controller archive drift check using the real local chain."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import fixture_fresh_search_v4_e2e as fixture
from scripts import ndx_dynamic_shadow_fresh_search_v4 as acceptance


class ArchiveDriftAfterSearchTests(unittest.TestCase):
    def test_real_completed_search_does_not_accept_changed_archive(self):
        with TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory).resolve()
            path, watched = fixture.prepare(root)
            calls = []
            fixture.bindings(stack, root, calls)
            real_controller = acceptance.execute_budgeted

            def execute_then_corrupt(snapshot_path):
                result = real_controller(snapshot_path)
                self.assertTrue(result["final_role_seal_verified"])
                snapshot = json.loads(snapshot_path.read_bytes())
                archive_path = Path(snapshot["membership_evidence"]["candidate_v3_source_archive"]["path"])
                archive = json.loads(archive_path.read_bytes())
                member = archive_path.parent / archive["source_descriptors"][0]["archive_filename"]
                member.write_bytes(b"changed after actual controller completion")
                return result

            # This wrapper executes the real controller first; it only injects
            # an external source change after completion, not a fabricated result.
            stack.enter_context(patch.object(acceptance, "execute_budgeted", side_effect=execute_then_corrupt))
            with self.assertRaisesRegex(ValueError, "source archive bytes changed"):
                acceptance.execute(path)
            self.assertEqual(len(calls), 8)
            self.assertTrue((root / acceptance.SEARCH / "final" / "2026-10-01" / "manifest.json").is_file())
            self.assertFalse((root / acceptance.ACCEPTANCE / "2026-10-01" / "receipt.json").exists())
            for source, digest in watched.items():
                self.assertEqual(acceptance.digest(source), digest)
