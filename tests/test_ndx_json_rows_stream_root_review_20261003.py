import hashlib
import io
import json
import unittest

from backtest.ndx_research_json_rows_stream import JsonRowsStream, RowsStreamError


class RootReview(unittest.TestCase):
    def test_original_byte_locations_and_detached_summary(self):
        document = {'before': ['汉字', {'escaped': '\\"{},[]'}],
                    'rows': [False, None, {'名称': 'é𐀀', 'nested': [0, -4, 0.25]}, []],
                    'after': {'completed': True}}
        raw = (' \n' + json.dumps(document, ensure_ascii=False, indent=2) + '\r\n').encode()
        for block_size in (1, 7, 65536):
            reader = JsonRowsStream(io.BytesIO(raw), block_size=block_size)
            rows = list(reader)
            self.assertEqual([row['value'] for row in rows], document['rows'])
            for index, row in enumerate(rows):
                original = raw[row['byte_start']:row['byte_stop']]
                self.assertEqual(row['row_index'], index)
                self.assertEqual(json.loads(original), row['value'])
                self.assertEqual(hashlib.sha256(original).hexdigest(), row['sha256'])
            summary = reader.summary
            self.assertEqual(summary['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(summary['byte_count'], len(raw))
            summary['metadata']['after']['completed'] = False
            self.assertTrue(reader.summary['metadata']['after']['completed'])

    def test_bad_tail_cannot_release_complete_summary(self):
        for raw in (b'{"rows":[1,]}', b'{"rows":[1],}',
                    b'{"rows":[1],"r\\u006fws":[]}',
                    b'{"rows":[1],"tail":{"x":0,"\\u0078":1}}',
                    b'{"rows":[1],"tail":1e9999}',
                    b'{"rows":[1]}null'):
            reader = JsonRowsStream(io.BytesIO(raw), block_size=3)
            self.assertEqual(next(reader)['value'], 1)
            with self.subTest(raw=raw), self.assertRaises(RowsStreamError):
                list(reader)
            with self.assertRaises(RowsStreamError):
                _ = reader.summary

    def test_stream_failure_never_becomes_successful_prefix(self):
        class BrokenStream:
            def __init__(self):
                self.calls = 0

            def read(self, size):
                self.calls += 1
                if self.calls == 1:
                    return b'{"rows":[1'
                if self.calls == 2:
                    return b','
                raise OSError('Original input became unavailable')

        reader = JsonRowsStream(BrokenStream(), block_size=16)
        self.assertEqual(next(reader)['value'], 1)
        with self.assertRaises(OSError):
            list(reader)
        with self.assertRaises(RowsStreamError):
            _ = reader.summary


if __name__ == '__main__':
    unittest.main()
