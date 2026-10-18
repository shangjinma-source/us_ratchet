"""HTTP boundary tests using stubs only; no real account or input provider."""
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.current_research_paper as module


class SuccessorRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(module.router)
        self.client = TestClient(app)
        self.stub = Mock()
        self.patcher = patch.object(module, 'SUCCESSOR_SERVICE', self.stub)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_preview_and_activate_forward_only_ids_in_order(self):
        response = dict(preview_id='preview', research_only=True, execution_blocked=True)
        self.stub.preview.return_value = response
        result = self.client.post('/api/research_paper/successor/preview', json=dict(account_id='paper', input_id='input', expected_revision='rev'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), response)
        self.stub.preview.assert_called_once_with('paper', 'input', 'rev')
        self.stub.activate.return_value = dict(response, activation_performed=True)
        result = self.client.post('/api/research_paper/successor/activate', json=dict(account_id='paper', preview_id='preview', event_id='event', expected_revision='rev'))
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()['activation_performed'])
        self.stub.activate.assert_called_once_with('paper', 'preview', 'event', 'rev')

    def test_latest_input_is_read_only_ids_and_unavailable(self):
        self.stub.available_input.return_value = dict(input_id='input', research_only=True, execution_blocked=True)
        result = self.client.get('/api/research_paper/successor/input', params=dict(account_id='paper', expected_revision='rev'))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['input_id'], 'input')
        self.stub.available_input.assert_called_once_with('paper', 'rev')
        self.stub.available_input.side_effect = ValueError('无已登记输入：UNAVAILABLE')
        result = self.client.get('/api/research_paper/successor/input', params=dict(account_id='paper', expected_revision='rev'))
        self.assertEqual(result.status_code, 400)
        self.assertIn('无已登记输入', result.json()['message'])

    def test_current_plan_bars_route_only_passes_identity(self):
        with patch.object(module, 'CHART_SERVICE') as charts:
            charts.bars.return_value = dict(status='AVAILABLE', bars=[], research_only=True, execution_blocked=True)
            result = self.client.get('/api/research_paper/bars', params=dict(account_id='paper', expected_plan_id='plan', security_id='sid', interval='week'))
            self.assertEqual(result.status_code, 200)
            charts.bars.assert_called_once_with('paper', 'plan', 'sid', 'week')
            charts.bars.side_effect = ValueError('缺少已绑定日线')
            result = self.client.get('/api/research_paper/bars', params=dict(account_id='paper', expected_plan_id='plan', security_id='sid'))
            self.assertEqual(result.status_code, 400)
            self.assertIn('缺少已绑定日线', result.json()['message'])

    def test_raw_payload_missing_or_nonstring_ids_rejected_before_service(self):
        valid = dict(account_id='paper', input_id='input', expected_revision='rev')
        for body in [dict(valid, plan={}), dict(valid, quotes=[]), dict(valid, source_hashes={}),
                     dict(valid, input_id=True), dict(valid, input_id=' '), {'account_id':'paper'}]:
            with self.subTest(body=body):
                result = self.client.post('/api/research_paper/successor/preview', json=body)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(result.json()['status'], 'UNAVAILABLE')
        self.stub.preview.assert_not_called()
        body = dict(account_id='paper', preview_id='preview', event_id='event', expected_revision='rev', raw_plan={})
        self.assertEqual(self.client.post('/api/research_paper/successor/activate', json=body).status_code, 400)
        self.stub.activate.assert_not_called()

    def test_unavailable_source_and_activation_errors_preserve_guards(self):
        self.stub.preview.side_effect = ValueError('后续决策行情输入尚未配置：UNAVAILABLE')
        self.stub.activate.side_effect = ValueError('STALE_ACCOUNT_REVISION')
        for route, body, message in [
            ('preview', dict(account_id='paper', input_id='input', expected_revision='rev'), '行情输入尚未配置'),
            ('activate', dict(account_id='paper', preview_id='preview', event_id='event', expected_revision='rev'), 'STALE_ACCOUNT_REVISION')]:
            result = self.client.post('/api/research_paper/successor/'+route, json=body)
            self.assertEqual(result.status_code, 400)
            data = result.json()
            self.assertEqual(data['status'], 'UNAVAILABLE')
            self.assertIn(message, data['message'])
            self.assertIs(data['research_only'], True)
            self.assertIs(data['execution_blocked'], True)


if __name__ == '__main__':
    unittest.main()
