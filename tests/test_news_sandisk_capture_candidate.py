import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'data'


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parser = load('sndk_parser', 'news_sandisk_parser.py')
with patch.dict(sys.modules, {'data.news_sandisk_parser': parser}):
    capture = load('sndk_capture', 'news_sandisk_capture.py')


class Response:
    def __init__(self, raw, status=200):
        self.raw, self.status_code = raw, status
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_content(self, size): yield self.raw


class CaptureTests(unittest.TestCase):
    def test_three_request_cap_failure_receipts_and_no_retry(self):
        date = capture.datetime.now(capture.timezone.utc).isoformat()
        rows = [dict(url=f'https://www.sandisk.com/company/newsroom/press-releases/2026/{i}',
                     documentType=['Press Release'], documentTypeDate=date, title=['Headline']) for i in range(5)]
        responses = [Response(json.dumps(dict(docs=rows)).encode()), Response(b'bot page'), Response(b'failure', 503)]
        calls = []
        def get(url, **kwargs):
            calls.append((url, kwargs))
            return responses[len(calls)-1]
        with tempfile.TemporaryDirectory() as directory:
            result = capture.capture(directory, session=types.SimpleNamespace(get=get))
            self.assertEqual(result['request_count'], 3)
            self.assertEqual(len(result['receipts']), 3)
            self.assertEqual(len(result['errors']), 2)
            self.assertEqual(result['events'], [])
            self.assertEqual(len(list((Path(directory)/'raw').glob('*.raw'))), 3)
        self.assertTrue(all(not kwargs['allow_redirects'] for _, kwargs in calls))

    def test_foreign_list_url_rejected_without_fetch(self):
        row = dict(url='https://evil.example/press-releases/a', documentType=['Press Release'])
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            return Response(json.dumps(dict(docs=[row])).encode())
        with tempfile.TemporaryDirectory() as directory:
            result = capture.capture(directory, session=types.SimpleNamespace(get=get))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['errors'][0]['message'], 'SANDISK_LIST_IDENTITY')


if __name__ == '__main__': unittest.main()
