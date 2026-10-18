"""Network receipt review with fake transport only; never network or real namespace."""
import json
import tempfile
import types
from decimal import localcontext, Inexact
from pathlib import Path
import unittest
from unittest.mock import patch
from scripts import ndx_forward_network_day_receipt_20261003 as m
from backtest import ndx_sina_saved_day_response_research as core
from test_ndx_sina_saved_day_response_research import fixture, raw


class Response:
    code = 200
    headers = {}
    def __init__(self, chunks, badclose=False):
        self.chunks = iter(chunks)
        self.badclose = badclose
    def geturl(self): return 'https://saved.example/'
    def read(self, count): return next(self.chunks)
    def close(self):
        if self.badclose: raise OSError('synthetic close failure')


class NetworkReview(unittest.TestCase):
    def test_eof_over_budget_is_not_complete(self):
        response = Response([b''])
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'build_opener', return_value=types.SimpleNamespace(open=lambda *a, **k: response)), patch.object(m.time, 'monotonic', side_effect=[0, 0, 91]):
            saved = m.receive('QQQ', Path(temp)/'raw.bin')
        self.assertIs(saved['response_complete'], False)
        self.assertIsNotNone(saved['transport_error'])

    def test_close_error_keeps_durable_received_bytes_and_receipt(self):
        response = Response([b'original bytes', b''], badclose=True)
        with tempfile.TemporaryDirectory() as temp, patch.object(m, 'build_opener', return_value=types.SimpleNamespace(open=lambda *a, **k: response)), patch.object(m.time, 'monotonic', return_value=0), patch.object(m.os, 'fsync', wraps=m.os.fsync) as sync:
            path = Path(temp)/'raw.bin'
            saved = m.receive('QQQ', path)
            self.assertEqual(path.read_bytes(), b'original bytes')
            self.assertEqual(saved['raw_reference']['sha256'], m.sha(b'original bytes'))
            self.assertIsNotNone(saved['completed_at_utc'])
            self.assertIsNotNone(saved['transport_error'])
            self.assertGreaterEqual(sync.call_count, 1)

    def test_both_receipts_exist_before_any_parse_and_failure_blocks_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)/'new'
            def receive(ticker, path):
                r = m.write(path, b'not valid JSONP')
                return dict(raw_reference=r, transport_error=None, response_complete=True, http_status=200, request_url='same', final_url='same', response_headers={})
            def inspect(**kwargs):
                self.assertTrue(all((out/(ticker+suffix)).is_file() for ticker in ('QQQ','SPY') for suffix in ('.response.bin','.receipt.json')))
                raise ValueError('synthetic parser rejects unknown envelope')
            with patch.object(m, 'OUTPUT', out), patch.object(m, 'load', return_value=({}, dict(QQQ=b'x', SPY=b'x'), {}, types.SimpleNamespace(inspect_response=inspect))), patch.object(m, 'receive', side_effect=receive):
                with self.assertRaises(ValueError): m.run(execute=True)
                self.assertTrue((out/'failure.json').is_file())
                with self.assertRaises(ValueError): m.run(execute=True)

    def test_exact_long_numeric_and_boolean_volume_no_imputation(self):
        _, baseline, rows = fixture()
        token = '100.123456789012345678901234567890123456789'
        rows[-1]['o'] = token
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            result = core.inspect_response(raw_bytes=raw(rows), ticker='QQQ', baseline_csv_bytes=baseline)
        self.assertEqual(result['target_row']['normalized']['Open'], token)
        self.assertEqual(result['target_row']['original_row']['o'], token)
        self.assertTrue(all(result[k] is False for k in core.FLAGS))
        rows[-1]['v'] = True
        with self.assertRaises(ValueError): core.inspect_response(raw_bytes=raw(rows), ticker='QQQ', baseline_csv_bytes=baseline)


if __name__ == '__main__': unittest.main()
