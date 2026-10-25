from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
from data.strategy_profiled_runtime import build_runtime
from data.strategy_unified_server_preparation_v7 import bind_publication_guard, PUBLICATION_SOURCES
from api.strategy_unified_reviewed_domain_composition_v6 import SOURCES
import test_unified_reviewed_domain_http_v6 as fixture


class UnifiedPublicationGuardTests(unittest.TestCase):
    def setup_case(self, folder):
        helper = fixture.ReviewedDomainHTTPTests()
        c = helper.runtime_case(fixture.base_fixture.ProfiledPacketTests().setup_case, folder)
        root = Path(folder)
        def save(name, value):
            raw = canonical(value)
            (root/name).write_bytes(raw)
            return sha256(raw).hexdigest()
        config_hash = save("guard-runtime.json", c.configuration)
        archive_hash = save("guard-archive.json", dict(schema="PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1",
            entries=[dict(configuration_path="guard-runtime.json", configuration_sha256=config_hash)]))
        snapshot = dict(revision=0, registry_path="unused.json", registry_sha256="0"*64,
                        archive_path="guard-archive.json", archive_sha256=archive_hash)
        def builder(**kwargs):
            runtime = build_runtime(**kwargs)
            runtime.execution_provider.__self__.market = c.provider.market
            runtime.execution_provider.__self__.actions = c.provider.actions
            return runtime
        monthly = ProfiledRollingMonthlyRuntimeRouter(root=root, initial_snapshot=snapshot,
            snapshot_provider=lambda: snapshot, clock=lambda: c.clock[0],
            runtime_builder=builder, identity_configuration=c.configuration)
        pins = {}
        for name in SOURCES | PUBLICATION_SOURCES:
            raw = (fixture.ROOT/name).read_bytes()
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        gate = BoundedSourceGateV1(root=root, source_pins=pins)
        calendar = dict(path="calendar.json", sha256=sha256((root/"calendar.json").read_bytes()).hexdigest())
        prepared = bind_publication_guard(prepared=dict(monthly=monthly, validate_code=gate),
                                          root=root, calendar=calendar)
        return c, monthly, prepared

    def test_actual_runtime_publication_uses_guard_and_repeat_after_close_is_readonly(self):
        with TemporaryDirectory() as folder:
            c, monthly, prepared = self.setup_case(folder)
            runtime, _ = monthly._for_target(monthly.current())
            self.assertIs(runtime.targets, prepared["publication_guard"])
            before_account = monthly.accounts.path.read_bytes()
            request = dict(event_id="guarded-real-selection", reason="EXPLICIT_RECONFIGURE",
                expected_revision=monthly.accounts.read()["revision"],
                previous_target_id=monthly.current()["target_id"])
            result = runtime.generate(**request)
            self.assertEqual(monthly.current(), result)
            target_bytes = monthly.targets.path.read_bytes()
            c.clock[0] = datetime.fromisoformat("2026-11-02T21:01:00+00:00")
            with patch.object(type(runtime.selection), "select",
                              side_effect=AssertionError("retry must not select")):
                self.assertEqual(runtime.generate(**request), result)
            self.assertEqual(monthly.targets.path.read_bytes(), target_bytes)
            self.assertEqual(monthly.accounts.path.read_bytes(), before_account)

    def test_actual_selector_finishing_after_close_cannot_publish(self):
        with TemporaryDirectory() as folder:
            c, monthly, prepared = self.setup_case(folder)
            runtime, _ = monthly._for_target(monthly.current())
            before = monthly.targets.path.read_bytes()
            account_before = monthly.accounts.path.read_bytes()
            real_select = runtime.selection.select
            def cross_close():
                result = real_select()
                self.assertEqual(result["status"], "READY")
                c.clock[0] = datetime.fromisoformat("2026-11-02T21:00:00+00:00")
                return result
            with patch.object(runtime.selection, "select", side_effect=cross_close):
                with self.assertRaisesRegex(ValueError, "PUBLICATION_OUTSIDE_SESSION"):
                    runtime.generate(event_id="late-real-selection", reason="EXPLICIT_RECONFIGURE",
                        expected_revision=monthly.accounts.read()["revision"],
                        previous_target_id=monthly.current()["target_id"])
            self.assertEqual(monthly.targets.path.read_bytes(), before)
            self.assertEqual(monthly.accounts.path.read_bytes(), account_before)

    def test_rebinding_after_runtime_cached_is_rejected(self):
        with TemporaryDirectory() as folder:
            c, monthly, prepared = self.setup_case(folder)
            monthly._for_target(monthly.current())
            with self.assertRaisesRegex(ValueError, "REQUIRES_COLD_RUNTIME"):
                bind_publication_guard(prepared=prepared, root=folder,
                                       calendar=prepared["publication_calendar"])


if __name__ == "__main__":
    unittest.main()
