"""Real builders against saved sources; HTTP reads only, never a production mount."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.strategy_server_mount_v6 import mount_strategy_routes, PATH_ENV, SHA_ENV
from data.strategy_account_market_capture import StrategyAccountMarketCapture

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = {
    PATH_ENV: "research_contracts/unified_server_20261020_v4_reviewed_domain/server.json",
    SHA_ENV: "898456955c0dcdba50c9746b6b5f8e17412399637d44ec8d5b2cb903c229aeee",
}


def database_hashes():
    return {p.name: sha256(p.read_bytes()).hexdigest()
            for p in (ROOT/"data/strategy_account").glob("*.sqlite*") if p.is_file()}


class ServerMountTests(unittest.TestCase):
    @patch("api.strategy_server_mount_v6._read_active", new=lambda root: (None, None))
    def test_pinned_v7_dispatch_and_unknown_schema_refused(self):
        app = FastAPI()
        reference = {
            PATH_ENV: "research_contracts/unified_server_20261020_v5_session_guard/server.json",
            SHA_ENV: "9ab3d50a7ae31803d659088428c14a234ca731336bf0c627e409ebd8ef26787b",
        }
        before = database_hashes()
        result = mount_strategy_routes(app=app, root=ROOT, environment=reference)
        self.assertEqual(result["mode"], "UNIFIED_V7")
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/strategy-account/target").status_code, 200)
            self.assertEqual(client.post("/api/strategy-account/target/preview", json={}).status_code, 404)
        self.assertEqual(database_hashes(), before)
        with TemporaryDirectory() as folder:
            raw = b'{"schema":"UNKNOWN"}'
            (Path(folder)/"bad.json").write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "CONFIGURATION_SCHEMA"):
                mount_strategy_routes(app=FastAPI(), root=folder,
                    environment={PATH_ENV: "bad.json", SHA_ENV: sha256(raw).hexdigest()})

    def test_persistent_manifest_without_environment_real_builder_and_conflicts(self):
        import api.strategy_server_mount_v6 as module
        read_active = module._read_active
        before = database_hashes()
        with TemporaryDirectory() as folder:
            isolated = Path(folder)
            path = isolated/module.ACTIVE_MANIFEST
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(schema="STRATEGY_SERVER_ACTIVE_V6",
                configuration_path=REFERENCE[PATH_ENV],
                configuration_sha256=REFERENCE[SHA_ENV])), encoding="utf-8")
            # Only the local startup-manifest root is isolated. Its real bounded
            # reader runs; the actual pinned builder and saved account stay read-only.
            with patch.object(module, "_read_active", side_effect=lambda _: read_active(isolated)):
                app = FastAPI()
                result = mount_strategy_routes(app=app, root=ROOT, environment={})
                self.assertEqual(result["mode"], "UNIFIED_V6")
                with TestClient(app) as client:
                    self.assertEqual(client.get("/api/strategy-account").status_code, 200)
                with self.assertRaisesRegex(ValueError, "ENVIRONMENT_CONFLICT"):
                    mount_strategy_routes(app=FastAPI(), root=ROOT,
                        environment=dict(REFERENCE, **{SHA_ENV: "0"*64}))
                result = mount_strategy_routes(app=FastAPI(), root=ROOT, environment=REFERENCE)
                self.assertEqual(result["mode"], "UNIFIED_V6")
        self.assertEqual(database_hashes(), before)

    def test_corrupt_persistent_manifest_never_falls_back(self):
        import api.strategy_server_mount_v6 as module
        cases = (b"broken", b"{}", b'{"schema":"a","schema":"b"}',
                 b'{"schema":"STRATEGY_SERVER_ACTIVE_V6","configuration_path":"../bad.json","configuration_sha256":"' + b"0"*64 + b'"}',
                 b"x"*4097)
        for raw in cases:
            with self.subTest(raw=raw[:30]), TemporaryDirectory() as folder:
                root = Path(folder)
                path = root/module.ACTIVE_MANIFEST
                path.parent.mkdir(parents=True)
                path.write_bytes(raw)
                app = FastAPI()
                count = len(app.routes)
                with self.assertRaises(ValueError):
                    mount_strategy_routes(app=app, root=root, environment={})
                self.assertEqual(len(app.routes), count)
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/module.ACTIVE_MANIFEST
            path.parent.mkdir(parents=True)
            try:
                path.symlink_to(root/"missing.json")
            except OSError:
                self.skipTest("OS cannot create test symlinks")
            with self.assertRaisesRegex(ValueError, "LINK_REFUSED"):
                module._read_active(root)

    @patch("api.strategy_server_mount_v6._read_active", new=lambda root: (None, None))
    def test_real_legacy_and_opt_in_route_sets_and_readonly_http(self):
        before = database_hashes()
        for environment, expected in (({}, "LEGACY"), (REFERENCE, "UNIFIED_V6")):
            with self.subTest(mode=expected):
                app = FastAPI()
                with patch.object(StrategyAccountMarketCapture, "capture",
                                  side_effect=AssertionError("read-only startup must not quote")):
                    result = mount_strategy_routes(app=app, root=ROOT, environment=environment)
                    self.assertEqual(result["mode"], expected)
                    keys = [(r.path, m) for r in app.routes if hasattr(r, "methods")
                            for m in r.methods]
                    self.assertEqual(len(keys), len(set(keys)))
                    self.assertEqual(("/api/strategy-daily/preview", "POST") in keys,
                                     expected == "LEGACY")
                    self.assertEqual(("/api/strategy-account/target/preview", "POST") in keys,
                                     expected == "LEGACY")
                    self.assertIn(("/api/strategy-account/target/generate", "POST"), keys)
                    self.assertIn(("/api/strategy-daily-v3/preview", "POST"), keys)
                    with TestClient(app) as client:
                        self.assertEqual(client.get("/api/strategy-account").status_code, 200)
                        self.assertEqual(client.get("/api/strategy-account/target").status_code, 200)
                        response = client.post("/api/strategy-capital-v1/status",
                                               json={"event_id": "mount-readonly-not-recorded"})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(response.json()["status"], "NOT_FOUND")
                        if expected == "UNIFIED_V6":
                            from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
                            from data.strategy_account_monthly_router import MonthlyRuntimeRouter
                            with patch.object(StrategyAccountEvidenceProvider, "execution",
                                              side_effect=AssertionError("old advice bypass")), \
                                 patch.object(MonthlyRuntimeRouter, "preview",
                                              side_effect=AssertionError("old monthly preview")):
                                response = client.post("/api/strategy-account/target/preview", json={})
                                self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(database_hashes(), before)

    @patch("api.strategy_server_mount_v6._read_active", new=lambda root: (None, None))
    def test_invalid_explicit_configuration_never_falls_back_or_mounts(self):
        cases = ({PATH_ENV: REFERENCE[PATH_ENV]}, {SHA_ENV: REFERENCE[SHA_ENV]},
                 {PATH_ENV: "", SHA_ENV: REFERENCE[SHA_ENV]},
                 dict(REFERENCE, **{SHA_ENV: "0"*64}),
                 dict(REFERENCE, **{PATH_ENV: "missing-v6-server.json"}))
        for environment in cases:
            with self.subTest(environment=environment):
                app = FastAPI()
                count = len(app.routes)
                with self.assertRaises((ValueError, OSError)):
                    mount_strategy_routes(app=app, root=ROOT, environment=environment)
                self.assertEqual(len(app.routes), count)
        # A wholly new checkout exposes no executable or account-writing service.
        with TemporaryDirectory() as folder:
            result = mount_strategy_routes(app=FastAPI(), root=folder, environment={})
            self.assertEqual(result["mode"], "UNCONFIGURED")

    @patch("api.strategy_server_mount_v6._read_active", new=lambda root: (None, None))
    def test_real_opt_in_rejects_preexisting_strategy_route_before_registration(self):
        app = FastAPI()
        @app.get("/api/strategy-account")
        def existing():
            return {}
        count = len(app.routes)
        with self.assertRaisesRegex(ValueError, "STRATEGY_MOUNT_DUPLICATE_ROUTE"):
            mount_strategy_routes(app=app, root=ROOT, environment=REFERENCE)
        self.assertEqual(len(app.routes), count)


class UnconfiguredMountTests(unittest.TestCase):
    def test_absent_configuration_has_explicit_readonly_http_state(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            app = FastAPI()
            result = mount_strategy_routes(app=app, root=root, environment={})
            self.assertEqual(result["mode"], "UNCONFIGURED")
            with TestClient(app) as client:
                for method, path in (("get", "/api/strategy-account"),
                                     ("get", "/api/strategy-account/target"),
                                     ("post", "/api/strategy-account/initialize"),
                                     ("post", "/api/strategy-account/events"),
                                     ("post", "/api/strategy-daily-v3/preview"),
                                     ("post", "/api/strategy-capital-arrival-v2/arrive")):
                    response = getattr(client, method)(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["status"], "UNCONFIGURED")
                    self.assertIsNone(response.json()["account"])
                    self.assertFalse(response.json()["orders_created"])
                    self.assertFalse(response.json()["account_mutated"])
            self.assertEqual(list(root.iterdir()), [])

    def test_partial_or_corrupt_legacy_configuration_does_not_fall_back(self):
        from api.strategy_server_mount_v6 import LEGACY_CONFIGURATIONS
        for name in LEGACY_CONFIGURATIONS:
            with self.subTest(name=name), TemporaryDirectory() as folder:
                root = Path(folder)
                path = root/name
                path.parent.mkdir(parents=True)
                path.write_text("{}", encoding="utf-8")
                app = FastAPI()
                count = len(app.routes)
                with self.assertRaises((OSError, ValueError)):
                    mount_strategy_routes(app=app, root=root, environment={})
                self.assertEqual(len(app.routes), count)

    def test_missing_explicit_reference_does_not_fall_back(self):
        with TemporaryDirectory() as folder:
            app = FastAPI()
            count = len(app.routes)
            with self.assertRaises((OSError, ValueError)):
                mount_strategy_routes(app=app, root=folder, environment={
                    PATH_ENV: "missing.json", SHA_ENV: "0"*64})
            self.assertEqual(len(app.routes), count)

    def test_corrupt_active_manifest_does_not_fall_back(self):
        from api.strategy_server_mount_v6 import ACTIVE_MANIFEST
        with TemporaryDirectory() as folder:
            root = Path(folder)
            path = root/ACTIVE_MANIFEST
            path.parent.mkdir(parents=True)
            path.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "MANIFEST_FIELDS"):
                mount_strategy_routes(app=FastAPI(), root=root, environment={})


if __name__ == "__main__":
    unittest.main()
