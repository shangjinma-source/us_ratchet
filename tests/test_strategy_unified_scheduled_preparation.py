from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import data.strategy_unified_server_preparation_v29 as module


class ScheduledPreparationTests(unittest.TestCase):
    def fixture(self, root):
        pins = {}
        repository = Path(__file__).resolve().parents[1]
        for name in module.SOURCES:
            raw = (repository/name).read_bytes()
            target = root/name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            pins[name] = sha256(raw).hexdigest()
        configuration = dict(schema='SCHEDULED_EARNINGS_UNIFIED_PREPARATION_V29',
            base_v28=dict(path='base.json', sha256='a'*64), source_pins=pins)
        raw = json.dumps(configuration).encode(); (root/'config.json').write_bytes(raw)
        return dict(root=root, configuration_path='config.json', configuration_sha256=sha256(raw).hexdigest())

    def test_register_read_without_capture_and_preserve_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); arguments = self.fixture(root); validations = []
            base = dict(router=APIRouter(), validate_code=lambda: validations.append(True), policy='UNCHANGED')
            with patch.object(module, 'build_unified_server_preparation_v28', return_value=base) as builder:
                prepared = module.build_unified_server_preparation_v29(**arguments)
            self.assertEqual(prepared['policy'], 'UNCHANGED'); self.assertEqual(builder.call_count, 1)
            app = FastAPI(); app.include_router(prepared['router'])
            with TestClient(app) as client:
                result = client.get('/api/news/scheduled-earnings')
                self.assertEqual(result.status_code, 200); self.assertEqual(result.json()['status'], 'NO_CAPTURE')
                script = client.get('/static/news_scheduled_earnings.js')
                self.assertEqual(script.content, (root/'web/news_scheduled_earnings.js').read_bytes())
            self.assertFalse((root/'data/cache').exists()); self.assertGreater(len(validations), 1)
            (root/'web/news_scheduled_earnings.js').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'V29_SOURCE_CHANGED'): prepared['validate_code']()

    def test_bad_source_prevents_base_construction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); arguments = self.fixture(root)
            (root/'data/news_scheduled_service_v1.py').write_bytes(b'changed')
            with patch.object(module, 'build_unified_server_preparation_v28') as builder:
                with self.assertRaisesRegex(ValueError, 'V29_SOURCE_CHANGED'):
                    module.build_unified_server_preparation_v29(**arguments)
                builder.assert_not_called()


if __name__ == '__main__': unittest.main()
