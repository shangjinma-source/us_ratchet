import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.news_desk_v1 import create_router


class NewsDeskTests(unittest.TestCase):
    def test_refresh_rejects_cross_origin_and_custom_input(self):
        with TemporaryDirectory() as directory, patch('api.news_desk_v1.NewsRefreshService') as factory:
            factory.return_value.start.return_value = (202, {'status': 'RUNNING'})
            app = FastAPI()
            app.include_router(create_router(directory))
            client = TestClient(app)
            self.assertEqual(client.post('/api/news/refresh', json={}, headers={'origin': 'https://external.invalid'}).status_code, 403)
            self.assertEqual(client.post('/api/news/refresh', json={'model':'other'}).status_code, 400)
            self.assertEqual(client.post('/api/news/refresh', content='{}').status_code, 415)
            self.assertEqual(client.post('/api/news/refresh', json={}, headers={'origin': 'http://testserver'}).status_code, 202)
            factory.return_value.start.assert_called_once()

    def test_read_only_empty_saved_and_invalid(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = FastAPI()
            app.include_router(create_router(root))
            client = TestClient(app)
            self.assertEqual(client.get('/api/news/latest').json()['status'], 'empty')
            self.assertEqual(list(root.iterdir()), [])
            path = root / 'data/cache/news/latest.json'
            path.parent.mkdir(parents=True)
            payload = dict(schema_version='news-desk-v1', status='ready', events=[])
            path.write_text(json.dumps(payload))
            self.assertEqual(client.get('/api/news/latest').json(), payload)
            self.assertEqual(client.post('/api/news/latest').status_code, 405)
            path.write_text('{broken')
            self.assertEqual(client.get('/api/news/latest').status_code, 503)
            path.write_bytes(b' ' * (2 * 1024 * 1024 + 1))
            self.assertEqual(client.get('/api/news/latest').status_code, 503)


if __name__ == '__main__':
    unittest.main()
