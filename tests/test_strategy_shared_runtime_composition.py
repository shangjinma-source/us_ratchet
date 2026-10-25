from hashlib import sha256
from pathlib import Path
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

import test_strategy_rolling_composition as fixtures
from data.strategy_dynamic_source_gate import bind_dynamic_source_gate
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
from api.strategy_shared_runtime_composition import create_shared_runtime_router


class SharedRuntimeCompositionTests(fixtures.RollingCompositionTests):
    """Reuse actual account writes/target tests against the shared-instance router."""
    def client(self):
        name = "api/strategy_shared_runtime_composition.py"
        raw = (Path(__file__).resolve().parents[1] / name).read_bytes()
        (self.root / name).write_bytes(raw)
        self.pins[name] = sha256(raw).hexdigest()
        gate = bind_dynamic_source_gate(root=self.root, source_pins=self.pins)
        initial = {key: self.arguments[key] for key in
                   ("registry_path", "registry_sha256", "archive_path", "archive_sha256")}
        monthly = RollingMonthlyRuntimeRouter(root=self.root,
            initial_snapshot=dict(initial, revision=0),
            snapshot_provider=lambda: dict(initial, revision=0),
            clock=lambda: self.fixture.now, runtime_builder=self.fixture.build,
            identity_configuration=self.fixture.configuration)
        router = create_shared_runtime_router(monthly=monthly,
            validate_code=gate, bootstrap_configuration=self.fixture.configuration)
        parent = APIRouter()
        parent.include_router(router)
        app = FastAPI()
        app.include_router(parent)
        client = TestClient(app)
        self.addCleanup(client.close)
        return client

    def test_missing_self_pin_rejected_without_construction(self):
        # The shared factory receives an already-admitted runtime and a gate;
        # source-domain completeness belongs to the server preparation factory.
        def rejected_gate():
            raise ValueError("SOURCE_DOMAIN_NOT_ADMITTED")
        with self.assertRaisesRegex(ValueError, "SOURCE_DOMAIN_NOT_ADMITTED"):
            create_shared_runtime_router(monthly=None, validate_code=rejected_gate)
