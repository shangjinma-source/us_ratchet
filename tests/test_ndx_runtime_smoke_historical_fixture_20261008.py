"""Historical synthetic smoke adversaries, never current runtime/task evidence.

The SHA-bound original test and production module remain byte-for-byte intact.
Only their datetime fixtures are scoped to 2026-09-10 for these inherited cases.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch
import unittest


_original_path = Path(__file__).with_name('test_ndx_dynamic_shadow_runtime_v4_smoke.py')
_expected_sha = 'b7e44b4d19a62629a52cc9c0ca844e27fe243cdfbd5956fa9154fb6e712deda7'
if hashlib.sha256(_original_path.read_bytes()).hexdigest() != _expected_sha:
    raise ValueError('Historical smoke test source changed')
_spec = importlib.util.spec_from_file_location('_historical_smoke_fixture', _original_path)
_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


class HistoricalDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)
        return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)


class HistoricalRuntimeSmokeTests(_original.RuntimeV4SmokeTests):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.object(_original, 'datetime', HistoricalDatetime))
        self.enterContext(patch.object(_original.smoke, 'datetime', HistoricalDatetime))


if __name__ == '__main__':
    unittest.main()
