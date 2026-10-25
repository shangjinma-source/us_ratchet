"""Capital/advice chain with real runtime builder and archived target routing.

Market transports and V22 base mounting remain isolated fixtures. No real
account, active deployment configuration or network is used.
"""
from hashlib import sha256
import sqlite3
import json
from contextlib import closing
from unittest.mock import patch
from fastapi.testclient import TestClient

from core.strategy_account_ledger import canonical
from data.strategy_continuous32_runtime import RUNTIME_PATHS
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_profiled_runtime import build_runtime
from data.strategy_profiled_runtime_archive import configuration_for_target
from data.strategy_profiled_rolling_router import ProfiledRollingMonthlyRuntimeRouter
import test_capital_supplement_v23_mount as fixture
import test_daily_ready_independent as ledger_fixture


class ArchivedCapitalAdviceTests(fixture.V23CapitalHTTPTests):
    def test_premarket_wait_does_not_latch_after_open_or_rewrite_source(self):
        original = ledger_fixture.IndependentReadyTests.setup_case
        def setup(instance, *args, **kwargs):
            return original(instance, *args, **dict(kwargs, account_id='real-strategy-account-v1'))
        with patch.object(ledger_fixture.IndependentReadyTests, 'setup_case', setup):
            super().test_premarket_wait_does_not_latch_after_open_or_rewrite_source()

    def verify_advice_http(self, c, risk_reader):
        super().verify_advice_http(c, risk_reader)
        monthly = c.capital_monthly
        target = monthly.current()
        state = c.store.read()
        runtime, configuration = monthly._for_target(target)
        self.assertEqual(configuration_for_target(root=monthly.root,
            archive_path=monthly.archive_path, archive_sha256=monthly.archive_sha256,
            target=target), configuration)
        self.assertEqual(runtime.accounts.read(), state)
        path = monthly.root/monthly.archive_path
        original = path.read_bytes()
        try:
            path.write_bytes(original + b' ')
            response = TestClient(c.capital_application).post('/api/strategy-daily-v3/preview',
                json=dict(expected_revision=state['revision'], target_id=target['target_id']))
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()['new_orders'], [])
            self.assertEqual(response.json()['reference_quotes'], {})
            self.assertEqual(c.store.read(), state)
            self.assertEqual(monthly.current(), target)
        finally:
            path.write_bytes(original)

    def monthly_runtime(self, c, root, original_target):
        runtime_root = c.provider.root
        # Move only this temporary fixture's ledger into the real composition's
        # fixed storage location. Keep the same object for bound reader methods.
        destination = runtime_root/'data/strategy_account/real_strategy.sqlite3'
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.assertFalse(destination.exists())
        before = c.store.read()
        with closing(sqlite3.connect(c.store.path)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        c.store.path = destination
        self.assertEqual(c.store.read(), before)
        identity_body = (root/c.identity_reference['path']).read_bytes()
        identity_document = json.loads(identity_body)
        identity_files = {c.identity_reference['path']:identity_body}
        for path, digest in identity_document['source_hashes'].items():
            body = (root/path).read_bytes()
            self.assertEqual(sha256(body).hexdigest(), digest)
            identity_files[path] = body
        for name, body in identity_files.items():
            path = runtime_root/name
            if path.exists():
                self.assertEqual(path.read_bytes(), body)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
        def put(name, value):
            body = canonical(value)
            path = runtime_root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            return sha256(body).hexdigest()

        pins = {}
        for name in RUNTIME_PATHS:
            body = (fixture.fixture.fixture.ROOT/name).read_bytes()
            path = runtime_root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            pins[name] = sha256(body).hexdigest()
        configuration = dict(schema='REAL_STRATEGY_CONTINUOUS32_RUNTIME_V1', selector_profile=PROFILE_ID,
            target_month='2026-11', training_manifest=c.provider.manifest_path,
            training_sha256=c.provider.manifest_hash, training_closed_at=c.provider.closed,
            identity_manifest=c.identity_reference['path'], identity_sha256=c.identity_reference['sha256'],
            runtime_pins=pins)
        config_hash = put('capital-runtime.json', configuration)
        archive_hash = put('capital-archive.json', dict(schema='PROFILED_STRATEGY_RUNTIME_ARCHIVE_V1',
            entries=[dict(configuration_path='capital-runtime.json', configuration_sha256=config_hash)]))
        snapshot = dict(revision=0, registry_path='unused-monthly-registry.json', registry_sha256='0'*64,
                        archive_path='capital-archive.json', archive_sha256=archive_hash)
        original_provider = c.provider

        def builder(**kwargs):
            runtime = build_runtime(**kwargs)
            provider = runtime.execution_provider.__self__
            # Actual runtime/provider/limits/selector. Only vendor sources are fixtures.
            provider.market = original_provider.market
            provider.actions = original_provider.actions
            provider.output = original_provider.output
            self.assertEqual(runtime.accounts.path.resolve(), c.store.path.resolve())
            return runtime

        initial_runtime = builder(root=runtime_root, configuration=configuration, clock=lambda:c.clock[0])
        target = initial_runtime.generate(event_id='archived-capital-initial', reason='INITIAL',
            expected_revision=c.store.read()['revision'], previous_target_id=None)
        self.assertEqual(configuration_for_target(root=runtime_root, archive_path=snapshot['archive_path'],
            archive_sha256=snapshot['archive_sha256'], target=target), configuration)
        monthly = ProfiledRollingMonthlyRuntimeRouter(root=runtime_root, initial_snapshot=snapshot,
            snapshot_provider=lambda:snapshot, clock=lambda:c.clock[0], runtime_builder=builder)
        runtime, resolved = monthly._for_target(monthly.current())
        self.assertEqual(resolved, configuration)
        self.assertEqual(monthly.accounts.read(), c.store.read())
        # Later shortage injection must affect the actual execution provider too.
        c.provider = runtime.execution_provider.__self__
        return monthly
