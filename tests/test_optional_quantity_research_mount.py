"""Synthetic, filesystem-isolated deployment boundary checks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.optional_quantity_research_mount import (
    LOCAL_DEPLOYMENT_PATHS,
    legacy_quantity_research_configured,
    unconfigured_quantity_research_router,
)


class OptionalResearchMountTests(unittest.TestCase):
    def test_absent_deployment_disables_reads_and_writes_without_creating_storage(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            self.assertFalse(legacy_quantity_research_configured(root=root, environment={}))
            app = FastAPI()
            app.include_router(unconfigured_quantity_research_router())
            with TestClient(app) as client:
                for path in ("", "/snapshot", "/bars", "/intraday", "/difference",
                             "/automatic_simulation", "/paper_v2/account",
                             "/paper_v2/accept", "/paper_v2/monthly/research/generate"):
                    for method in ("get", "post"):
                        response = getattr(client, method)("/api/current_portfolio_research"+path)
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.json()["status"], "UNCONFIGURED")
                        self.assertTrue(response.json()["execution_blocked"])
                        self.assertFalse(response.json()["orders_created"])
            self.assertEqual(list(root.iterdir()), [])

    def test_any_partial_deployment_requires_strict_original_construction(self):
        for name in LOCAL_DEPLOYMENT_PATHS:
            with self.subTest(name=name), TemporaryDirectory() as folder:
                root = Path(folder)
                (root/name).mkdir(parents=True)
                self.assertTrue(legacy_quantity_research_configured(root=root, environment={}))

    def test_explicit_environment_never_silently_disables_research(self):
        with TemporaryDirectory() as folder:
            for key in ("QUANTITY_V2_MONTHLY_CONFIG_PATH", "QUANTITY_V2_MONTHLY_CONFIG_SHA256",
                        "QUANTITY_V2_EXECUTION_REVIEW_MODE"):
                self.assertTrue(legacy_quantity_research_configured(root=folder, environment={key: ""}))
            self.assertFalse(legacy_quantity_research_configured(root=folder, environment={"UNRELATED": "value"}))


if __name__ == "__main__":
    unittest.main()
