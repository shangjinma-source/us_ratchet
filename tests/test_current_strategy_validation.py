import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fastapi.responses import JSONResponse
from data import current_strategy_validation as service


class StrategyValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.pins = dict(service.PINS)
        for name in self.pins:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((service.ROOT / name).read_bytes())
        self.patch_root = patch.object(service, 'ROOT', self.root)
        self.patch_pins = patch.object(service, 'PINS', self.pins)
        self.patch_root.start(); self.patch_pins.start()

    def tearDown(self):
        self.patch_pins.stop(); self.patch_root.stop(); self.directory.cleanup()

    def test_saved_evidence_is_displayed_without_calculation(self):
        response = service.read_current_strategy_validation()
        self.assertEqual(response['period'], dict(start='2024-07-31', end='2025-07-30', calendar_days=364))
        self.assertEqual(len(response['modes']), 4)
        self.assertTrue(response['research_only']); self.assertTrue(response['execution_blocked'])
        self.assertFalse(response['independent_oos'])
        self.assertEqual(response['calculation_calls'], 0)
        self.assertEqual(response['modes'][0]['mode'], 'ACTUAL_EQUITY_FRESH_QUANTITY_MONTHLY')
        self.assertAlmostEqual(response['modes'][0]['annualized_return'], .19623359066754142)
        self.assertLess(response['modes'][0]['total_return'], response['modes'][3]['total_return'])
        self.assertGreater(response['modes'][0]['max_drawdown'], response['modes'][3]['max_drawdown'])
        latest = response['latest_period']
        self.assertEqual(latest['period']['start'], '2025-07-31')
        self.assertEqual(latest['successful_books'], 2)
        self.assertEqual(latest['total_attempts'], 3)
        self.assertIn('23.89', latest['conclusion'])
        self.assertIn('0.14', latest['conclusion'])
        self.assertFalse(latest['current_candidate_performance'])

    def test_latest_failure_count_mismatch_rejected_with_matching_fixture_hash(self):
        path = self.root / service.NEXT_READBACK
        review = json.loads(path.read_bytes())
        review['total_book_attempts'] = 2
        path.write_text(json.dumps(review), encoding='utf-8')
        self.pins[service.NEXT_READBACK] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(service.StrategyValidationSourceError):
            service.read_current_strategy_validation()

    def test_source_changed_after_success_never_returns_cached_numbers(self):
        service.read_current_strategy_validation()
        path = self.root / service.BASE / 'result.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(service.StrategyValidationSourceError):
            service.read_current_strategy_validation()
        path.unlink()
        with self.assertRaises(service.StrategyValidationSourceError):
            service.read_current_strategy_validation()

    def test_readback_semantic_mismatch_rejected_even_with_fixture_pin(self):
        path = self.root / service.READBACK
        review = json.loads(path.read_bytes())
        review['modes'][0]['return_fraction'] = '99'
        path.write_text(json.dumps(review), encoding='utf-8')
        self.pins[service.READBACK] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(service.StrategyValidationSourceError):
            service.read_current_strategy_validation()

    def test_actual_evidence_change_and_semantic_mismatch_fail_closed(self):
        path=self.root/service.ACTUAL_READBACK
        review=json.loads(path.read_bytes());review['terminal_equity_exact']='1'
        path.write_text(json.dumps(review),encoding='utf-8')
        with self.assertRaises(service.StrategyValidationSourceError):service.read_current_strategy_validation()
        self.pins[service.ACTUAL_READBACK]=hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaises(service.StrategyValidationSourceError):service.read_current_strategy_validation()

    def test_actual_route_success_and_source_failure(self):
        # Execute the real route body without starting API services or loading account state.
        server = Path(__file__).resolve().parents[1] / 'api/server.py'
        tree = ast.parse(server.read_text(encoding='utf-8-sig'))
        route = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'api_current_strategy_validation')
        self.assertIn('/api/current_strategy_validation', ast.unparse(route.decorator_list[0]))
        route.decorator_list = []
        namespace = dict(JSONResponse=JSONResponse, StrategyValidationSourceError=service.StrategyValidationSourceError,
                         read_current_strategy_validation=service.read_current_strategy_validation)
        exec(compile(ast.Module(body=[route], type_ignores=[]), str(server), 'exec'), namespace)
        self.assertEqual(namespace[route.name]()['status'], 'AVAILABLE')
        (self.root / service.READBACK).unlink()
        response = namespace[route.name]()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('modes', json.loads(response.body))


if __name__ == '__main__':
    unittest.main()
