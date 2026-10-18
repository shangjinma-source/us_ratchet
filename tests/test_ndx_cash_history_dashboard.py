import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_cash_history_dashboard as module


def endpoint_namespace():
    tree = ast.parse((module.ROOT / 'api/server.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'api_ndx_marginal_allocation')
    function.decorator_list = []
    from fastapi.responses import JSONResponse
    namespace = {'copy': copy, 'JSONResponse': JSONResponse, 'NdxMarginalDashboardError': ValueError,
                 '_ndx_marginal_dashboard_cache': {}, 'read_cash_history_evidence': module.read_cash_history_evidence}
    # These legacy cash cases explicitly exclude modern source availability.
    def unavailable_modern_source():
        raise ValueError('Modern source outside legacy cash harness scope')
    namespace['load_modern_new_cash_inputs_view'] = unavailable_modern_source
    from backtest.ndx_modern_new_cash_inputs_dashboard_view import FLAGS
    namespace['MODERN_NEW_CASH_INPUT_FLAGS'] = FLAGS
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<isolated actual endpoint>', 'exec'), namespace)
    return namespace


class CashHistoryDashboardTests(unittest.TestCase):
    def test_saved_evidence_complete_and_display_matches_published_report(self):
        value = module.read_cash_history_evidence()
        report = module.BOUND['report'][0].read_text(encoding='utf-8')
        self.assertEqual(40, len(value['rows']))
        self.assertFalse(value['full_transitive_source_closure_reverified'])
        self.assertFalse(value['current_cash_input_consumed'])
        for row in value['rows']:
            self.assertEqual('2023', row['decision_date'][:4])
            for group in ('metrics', 'differences'):
                for metric in row[group]:
                    for display in metric['display'].values():
                        self.assertIn(display, report)

    def test_coordinated_projection_publication_change_does_not_change_host_anchor(self):
        original = Path.read_bytes
        def changed(path):
            raw = original(path)
            if path == module.BOUND['projection'][0]:
                value = json.loads(raw); value['rows'][0]['cash_amount_usd'] = '20000'
                return json.dumps(value).encode()
            if path == module.BOUND['publication'][0]:
                value = json.loads(raw); value['projection_reference']['sha256'] = '0' * 64
                return json.dumps(value).encode()
            return raw
        with patch.object(Path, 'read_bytes', changed):
            with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                module.read_cash_history_evidence()

    def test_failure_namespace_rejected_before_any_evidence_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('started.json', 'projection.json', 'report.md', 'publication.json', 'failure.json'):
                (root / name).write_text('{}')
            with patch.object(module, 'REPORT', root), patch.object(Path, 'read_bytes', side_effect=AssertionError('Unexpected read')):
                with self.assertRaisesRegex(ValueError, 'namespace'):
                    module.read_cash_history_evidence()

    def test_cache_does_not_hide_cash_evidence_failure(self):
        namespace = endpoint_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            namespace['_ndx_marginal_dashboard_paths'] = lambda: (root, root, root/'overlay', root/'gap')
            namespace['read_verified_marginal_dashboard'] = lambda **kwargs: {'available': True}
            namespace['read_cash_history_evidence'] = lambda: {'available': True}
            function = namespace['api_ndx_marginal_allocation']
            self.assertTrue(function()['portfolio_optimization_cash_evidence']['available'])
            def failed():
                raise ValueError('Changed namespace')
            namespace['read_cash_history_evidence'] = failed
            self.assertFalse(function()['portfolio_optimization_cash_evidence']['available'])

    def test_unavailable_old_layer_preserves_cash_result(self):
        namespace = endpoint_namespace()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            namespace['_ndx_marginal_dashboard_paths'] = lambda: (root, root, root/'overlay', root/'gap')
            namespace['read_cash_history_evidence'] = lambda: {'available': True}
            def failed(**kwargs):
                raise ValueError('Old layer unavailable')
            namespace['read_verified_marginal_dashboard'] = failed
            response = namespace['api_ndx_marginal_allocation']()
            self.assertEqual(200, response.status_code)
            self.assertTrue(json.loads(response.body)['portfolio_optimization_cash_evidence']['available'])

    def test_old_manifest_stat_permission_error_preserves_cash_result(self):
        namespace = endpoint_namespace()
        class ForbiddenManifest:
            def __truediv__(self, name):
                return self
            def exists(self):
                return True
            def stat(self):
                raise PermissionError('Old manifest denied')
        path = ForbiddenManifest()
        namespace['_ndx_marginal_dashboard_paths'] = lambda: (path, path, path, path)
        cash_calls = []
        namespace['read_cash_history_evidence'] = lambda: cash_calls.append(True) or {'available': True}
        response = namespace['api_ndx_marginal_allocation']()
        self.assertEqual([True], cash_calls)
        self.assertEqual(200, response.status_code)
        body = json.loads(response.body)
        self.assertTrue(body['portfolio_optimization_cash_evidence']['available'])
        self.assertIn('Old manifest denied', body['reason'])
        self.assertEqual({}, namespace['_ndx_marginal_dashboard_cache'])

    def test_old_path_resolution_error_preserves_cash_result(self):
        namespace = endpoint_namespace()
        def failed_paths():
            raise OSError('Old paths inaccessible')
        namespace['_ndx_marginal_dashboard_paths'] = failed_paths
        namespace['read_cash_history_evidence'] = lambda: {'available': True}
        response = namespace['api_ndx_marginal_allocation']()
        self.assertEqual(200, response.status_code)
        self.assertTrue(json.loads(response.body)['portfolio_optimization_cash_evidence']['available'])
        self.assertEqual({}, namespace['_ndx_marginal_dashboard_cache'])

    def test_both_layers_fail_with_service_unavailable(self):
        namespace = endpoint_namespace()
        def failed_paths():
            raise OSError('Old paths inaccessible')
        def failed_cash():
            raise ValueError('Cash namespace failed')
        namespace['_ndx_marginal_dashboard_paths'] = failed_paths
        namespace['read_cash_history_evidence'] = failed_cash
        response = namespace['api_ndx_marginal_allocation']()
        self.assertEqual(503, response.status_code)
        body = json.loads(response.body)
        self.assertFalse(body['portfolio_optimization_cash_evidence']['available'])
        self.assertIn('Cash namespace failed', body['portfolio_optimization_cash_evidence']['reason'])
        self.assertIn('Old paths inaccessible', body['reason'])
        self.assertEqual({}, namespace['_ndx_marginal_dashboard_cache'])

    def test_namespace_added_during_read_is_rejected(self):
        original = Path.iterdir
        calls = [0]
        def listing(path):
            values = list(original(path))
            if path == module.REPORT:
                calls[0] += 1
                if calls[0] >= 3:
                    values.append(path/'unexpected.txt')
            return iter(values)
        with patch.object(Path, 'iterdir', listing):
            with self.assertRaisesRegex(ValueError, 'inventory changed'):
                module.read_cash_history_evidence()


if __name__ == '__main__':
    unittest.main()
