import json
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.current_research_intraday_initial_retarget import BASE, create_router
import test_current_research_intraday_initial_retarget_service as fixtures


class InitialRetargetRouteTests(unittest.TestCase):
    def client(self, service):
        app = FastAPI()
        app.include_router(create_router(service=service))
        return TestClient(app)

    def test_context_binding_comes_from_verified_account_and_preview(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            original = service.store.path.read_bytes()
            with self.client(service) as client:
                response = client.get(BASE + '/context', params={'account_id': before['account_id']})
                self.assertEqual(response.status_code, 200, response.text)
                context = response.json()
                self.assertEqual(context['status'], 'RETARGET_CONTEXT')
                binding = context['binding']
                self.assertEqual(binding['revision'], before['revision'])
                self.assertEqual(binding['cash'], before['cash'])
                self.assertEqual(binding['original_acceptance_id'], before['acceptance_id'])
                self.assertEqual({p['security_id']: p['quantity'] for p in binding['positions']},
                                 {sid: q for sid, q in before['shares'].items() if q > 0})
                self.assertEqual({p['security_id'] for p in binding['securities']},
                                 set(current[0]['sizing_inputs']['execution_references']))
                self.assertEqual(context['preview']['expected_revision'], binding['revision'])
                self.assertEqual(service.store.path.read_bytes(), original)
                for field in ('source_hashes', 'execution_evidence', 'genesis'):
                    self.assertNotIn(field, response.text)
                duplicate = client.get(BASE + '/context?account_id=one&account_id=two')
                self.assertEqual(duplicate.status_code, 400)
                injected = client.get(BASE + '/context', params={'account_id': before['account_id'], 'cash': '999999'})
                self.assertEqual(injected.status_code, 400)
                self.assertEqual(client.request('GET', BASE + '/context', params={'account_id': before['account_id']},
                                                json={'selection': {}}).status_code, 400)

    def test_context_missing_account_never_creates_database(self):
        from pathlib import Path
        from data.current_research_intraday_initial_retarget_service import IntradayInitialRetargetService
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / 'absent'
            service = IntradayInitialRetargetService(directory=directory)
            with self.client(service) as client:
                response = client.get(BASE + '/context', params={'account_id': 'uncreated'})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['mutation_outcome'], 'NOT_A_MUTATION')
            self.assertFalse(directory.exists())

    def test_context_restores_accepted_account_without_new_quote(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            preview = service.preview(before['account_id'], before['revision'])
            accepted = service.accept(before['account_id'], preview['proposal']['proposal_id'], 'restore-account', before['revision'])
            service.evidence_provider = lambda **_: self.fail('restore must not select or fetch sources')
            service.clock = lambda: self.fail('stored account restoration needs no new quote time')
            with self.client(service) as client:
                response = client.get(BASE + '/context', params={'account_id': before['account_id']})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['status'], 'MULTIORDER_CONTEXT')
                self.assertEqual(response.json()['account'], accepted['account'])

    def test_preview_accept_and_exact_retry_preserve_account(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            with self.client(service) as client:
                request = dict(account_id=before['account_id'], expected_revision=before['revision'])
                response = client.post(BASE + '/preview', json=request)
                self.assertEqual(response.status_code, 200, response.text)
                proposal = response.json()['proposal']
                body = dict(request, proposal_id=proposal['proposal_id'], operation_id='http-retarget')
                response = client.post(BASE + '/accept', json=body)
                self.assertEqual(response.status_code, 200, response.text)
                accepted = response.json()
                self.assertEqual(accepted['account']['cash'], before['cash'])
                self.assertEqual(accepted['mutation_outcome'], 'APPLIED_OR_IDEMPOTENT')
                service.proposals.clear()
                service.evidence_provider = lambda **_: self.fail('retry provider')
                service.acceptance_guard = lambda **_: self.fail('retry guard')
                service.clock = lambda: self.fail('retry clock')
                self.assertEqual(client.post(BASE + '/accept', json=body).json(), accepted)
                for hidden in ('execution_evidence', 'source_hashes', 'causal_inputs', 'genesis'):
                    self.assertNotIn(hidden, response.text)

    def test_request_evidence_and_duplicate_json_rejected_without_write(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            original = service.store.path.read_bytes()
            request = dict(account_id=before['account_id'], expected_revision=before['revision'])
            with self.client(service) as client:
                for change in ({'cash': '1'}, {'selection': {}}, {'source_hashes': {}},
                               {'now': clock[0].isoformat()}, {'account_id': True}, {'expected_revision': 1}):
                    self.assertEqual(client.post(BASE + '/preview', json=dict(request, **change)).status_code, 400)
                duplicate = json.dumps(request)[:-1] + ',"account_id":"other"}'
                self.assertEqual(client.post(BASE + '/preview', content=duplicate,
                                            headers={'content-type': 'application/json'}).status_code, 400)
                self.assertEqual(client.post(BASE + '/preview?cash=1', json=request).status_code, 400)
                malformed = client.post(BASE + '/accept', json=dict(request, proposal_id='bad', operation_id='bad'))
                self.assertEqual(malformed.json()['mutation_outcome'], 'NOT_APPLIED')
                self.assertFalse(malformed.json()['retry_same_request'])
            self.assertEqual(service.store.path.read_bytes(), original)

    def test_response_failure_after_commit_requires_identical_retry(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            request = dict(account_id=before['account_id'], expected_revision=before['revision'])
            with self.client(service) as client:
                proposal = client.post(BASE + '/preview', json=request).json()['proposal']
                body = dict(request, proposal_id=proposal['proposal_id'], operation_id='response-lost')
                with patch('data.current_research_intraday_initial_retarget_service.compact_multiorder_account',
                           side_effect=ValueError('RESPONSE_UNAVAILABLE')):
                    response = client.post(BASE + '/accept', json=body)
                self.assertEqual(response.json()['mutation_outcome'], 'UNKNOWN_RETRY_SAME_REQUEST')
                self.assertTrue(response.json()['retry_same_request'])
                committed = service.store.read(before['account_id'])
                self.assertNotEqual(committed['revision'], before['revision'])
                clock[0] += timedelta(days=1)
                service.proposals.clear()
                service.evidence_provider = lambda **_: self.fail('retry source')
                response = client.post(BASE + '/accept', json=body)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['account']['revision'], committed['revision'])
                self.assertEqual(service.store.read(before['account_id']), committed)

    def test_expired_quote_cannot_be_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            service, before, clock, current = fixtures.InitialRetargetServiceTests().fixture(root)
            request = dict(account_id=before['account_id'], expected_revision=before['revision'])
            with self.client(service) as client:
                proposal = client.post(BASE + '/preview', json=request).json()['proposal']
                clock[0] += timedelta(seconds=121)
                response = client.post(BASE + '/accept', json=dict(
                    request, proposal_id=proposal['proposal_id'], operation_id='expired'))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['mutation_outcome'], 'NOT_APPLIED')
                self.assertFalse(response.json()['retry_same_request'])
                self.assertEqual(service.store.read(before['account_id']), before)


if __name__ == '__main__':
    unittest.main()
