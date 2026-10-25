from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import inspect
import textwrap
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_upgrade_handoff import upgrade_handoff_snapshot_provider
import test_strategy_continuous32_upgrade as original_tests


class HandoffTests(unittest.TestCase):
    def test_real_upgrade_history_remains_readable_after_month(self):
        source = textwrap.dedent(inspect.getsource(
            original_tests.UpgradeTests.test_explicit_upgrade_once_original_history_retained))
        source = source.replace(
            "router._snapshot_provider=checked",
            "router._snapshot_provider=upgrade_handoff_snapshot_provider("
            "root=root,package_path='upgrade.json',package_sha256=digest,"
            "base_provider=lambda:snap,target_provider=router.targets.current,"
            "validate_code=runtime.selection._pins)")
        source += "\n  self.assertEqual(router.current(),result['target'])\n"
        source += "  self.assertEqual(router._for_target(oldtarget)[1],old)\n"
        source += "  with self.assertRaisesRegex(ValueError,'MONTHLY_TARGET_REQUIRED'):router.preview()\n"
        namespace = dict(vars(original_tests),
                         upgrade_handoff_snapshot_provider=upgrade_handoff_snapshot_provider)
        exec(source, namespace)
        namespace["test_explicit_upgrade_once_original_history_retained"](self)

    def test_successor_preserves_overlay_and_registry(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            def put(name, value):
                raw = canonical(value)
                (root/name).write_bytes(raw)
                return dict(path=name, sha256=sha256(raw).hexdigest())
            old_entry = dict(configuration_path="old.json", configuration_sha256="1"*64)
            upgrade = put("upgraded.json", {"fixture": True})
            new_entry = dict(configuration_path=upgrade["path"], configuration_sha256=upgrade["sha256"])
            old_archive = put("old-archive.json", dict(schema="REAL_STRATEGY_RUNTIME_ARCHIVE_V1", entries=[old_entry]))
            overlay = put("overlay.json", dict(schema="PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1", entries=[old_entry, new_entry]))
            registry = put("registry.json", dict(entries=[{"month": "2026-10"}]))
            original = dict(revision=0, archive_path=old_archive["path"], archive_sha256=old_archive["sha256"],
                            registry_path=registry["path"], registry_sha256=registry["sha256"])
            package = put("package.json", dict(schema="CONTINUOUS32_RESEARCH_UPGRADE_V1",
                purpose="EXPLICIT_SAME_MONTH_RESEARCH_VERSION_UPGRADE_NOT_MONTHLY_PUBLICATION",
                base_snapshot=original, upgrade_archive=overlay, upgraded_configuration=upgrade))
            successor_registry = put("new-registry.json", dict(entries=[{"month": "2026-10"}, {"month": "2026-11"}]))
            active = dict(original, revision=1, archive_path=overlay["path"], archive_sha256=overlay["sha256"],
                          registry_path=successor_registry["path"], registry_sha256=successor_registry["sha256"])
            read = upgrade_handoff_snapshot_provider(root=root, package_path=package["path"],
                package_sha256=package["sha256"], base_provider=lambda:deepcopy(active),
                target_provider=lambda:None, validate_code=lambda:None)
            self.assertEqual(read(), active)
            active.update(archive_path=old_archive["path"], archive_sha256=old_archive["sha256"])
            with self.assertRaisesRegex(ValueError, "UPGRADE_SUCCESSOR_ARCHIVE_HISTORY_CHANGED"):
                read()
            active.update(archive_path=overlay["path"], archive_sha256=overlay["sha256"])
            missing = put("missing-registry.json", dict(entries=[]))
            active.update(registry_path=missing["path"], registry_sha256=missing["sha256"])
            with self.assertRaisesRegex(ValueError, "UPGRADE_SUCCESSOR_REGISTRY_HISTORY_CHANGED"):
                read()
