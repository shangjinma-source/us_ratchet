import base64
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from scripts import ndx_native_navigation_utf8_transport_20261003 as m
from test_ndx_native_hyperlinks_review_20261003 import fixture, archive, unzip


def packet():
    parts, links = fixture()
    source = Path('scripts/ndx_workbook_native_hyperlinks_20261003.py').read_bytes()
    return dict(source=base64.b64encode(source).decode('ascii'), sha=m.NATIVE_SHA256,
                xlsx=base64.b64encode(archive(parts)).decode('ascii'), links=links)


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


class Tests(unittest.TestCase):
    def test_fixed_helper_chinese_bytes_and_unchanged_parts(self):
        p = packet(); before = copy.deepcopy(p)
        result = unzip(m.apply_navigation_request(encode(p)))
        self.assertEqual(p, before)
        self.assertEqual(result['unchanged.bin'], b'\x00original\xff')
        self.assertEqual(result['xl/worksheets/_rels/sheet1.xml.rels'].count(b'navTaskLink'), 1632)

    def test_gbk_text_stream_does_not_affect_binary_wire(self):
        env = dict(os.environ, PYTHONIOENCODING='gbk', PYTHONUTF8='0')
        p = packet()
        legacy = subprocess.run([sys.executable, '-S', '-B', '-c',
            "import sys,json; p=json.load(sys.stdin); print(ascii(p['links'][0]['worksheet']))"],
            input=encode(p), capture_output=True, env=env, check=True)
        self.assertNotEqual(legacy.stdout.decode('ascii').strip(), ascii('全部任务'))
        result = subprocess.run([sys.executable, '-S', '-B', m.__file__],
            input=encode(p), capture_output=True, env=env, check=True)
        self.assertIn('xl/worksheets/_rels/sheet1.xml.rels', unzip(result.stdout))

    def test_transport_and_original_order_gates_remain_strict(self):
        for fault in ('source', 'sha', 'worksheet', 'cell', 'location'):
            p = packet()
            if fault == 'source': p['source'] = base64.b64encode(b'raise Exception()').decode()
            elif fault == 'sha': p['sha'] = '0' * 64
            else: p['links'][0][fault] = {'worksheet': 'other', 'cell': 'H3', 'location': "'任务索引'!A3"}[fault]
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                m.apply_navigation_request(encode(p))
        for blob in (b'\xff', b'{"sha":1,"sha":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError): m.apply_navigation_request(blob)


if __name__ == '__main__':
    unittest.main()
