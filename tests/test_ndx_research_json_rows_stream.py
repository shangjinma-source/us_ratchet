import hashlib
import io
import json
import unittest
from backtest.ndx_research_json_rows_stream import JsonRowsStream,RowsStreamError

class ShortReads(io.BytesIO):
    def read(self,n=-1):return super().read(min(n,2))

class Tests(unittest.TestCase):
    def test_utf8_escaped_boundaries_spans_false_and_metadata(self):
        rows=[{'中文':'引号"和反斜线\\以及😀','nested':[False,{'a':'}][{'}]},False,None,0,[],{'尾':'末'}]
        raw=(' \n{"before":{"值":false},"rows": [ '+',\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+' ], "after":[1,"中文"]}\r\n').encode()
        for size in (1,2,3,7,64):
            iterator=JsonRowsStream(io.BytesIO(raw),block_size=size);got=list(iterator)
            self.assertEqual([r['value'] for r in got],rows)
            for i,r in enumerate(got):
                b=raw[r['byte_start']:r['byte_stop']];self.assertEqual(hashlib.sha256(b).hexdigest(),r['sha256']);self.assertEqual(json.loads(b),rows[i]);self.assertEqual(r['row_index'],i)
            self.assertEqual(iterator.summary,dict(metadata={'before':{'值':False},'after':[1,'中文']},row_count=6,byte_count=len(raw),sha256=hashlib.sha256(raw).hexdigest(),complete_document_consumed=True))
    def test_summary_only_verified_exhaustion_and_short_reads(self):
        raw=b'{"rows":[false],"end":true}'
        it=JsonRowsStream(ShortReads(raw),block_size=8)
        with self.assertRaises(RowsStreamError):_ = it.summary
        self.assertIs(next(it)['value'],False)
        with self.assertRaises(RowsStreamError):_ = it.summary
        with self.assertRaises(StopIteration):next(it)
        self.assertEqual(it.summary['metadata'],{'end':True})
        copy=it.summary;copy['metadata']['end']=False;self.assertTrue(it.summary['metadata']['end'])
    def test_duplicate_nested_keys_nonfinite_and_trailing_documents(self):
        examples=[b'{"rows":[],"rows":[]}',b'{"a":1,"a":2,"rows":[]}',b'{"rows":[{"x":1,"x":2}]}',b'{"rows":[],"meta":{"nested":{"x":1,"x":2}}}',b'{"rows":[NaN]}',b'{"rows":[Infinity]}',b'{"rows":[1e9999]}',b'{"rows":[]}{}',b'{"rows":[]}garbage',b'{"rows":{},"x":1}',b'{}',b'{"rows":[1,]}',b'{"rows":[],}',b'{"rows":["\xff"]}']
        for raw in examples:
            with self.subTest(raw=raw):
                it=JsonRowsStream(io.BytesIO(raw),block_size=1)
                with self.assertRaises((RowsStreamError,ValueError)):list(it)
                with self.assertRaises(RowsStreamError):_ = it.summary
    def test_every_truncated_prefix_rejected_without_summary(self):
        raw=b'{"meta":{"a":[1,2]},"rows":[{"a":"escaped\\\"quote"},false],"end":3}'
        for stop in range(len(raw)):
            with self.subTest(stop=stop):
                it=JsonRowsStream(io.BytesIO(raw[:stop]),block_size=3)
                with self.assertRaises(RowsStreamError):list(it)
                with self.assertRaises(RowsStreamError):_ = it.summary
        self.assertEqual(len(list(JsonRowsStream(io.BytesIO(raw)))),2)
    def test_resource_failures_empty_rows_and_binary_contract(self):
        for kwargs,raw in [({'max_row_bytes':3},b'{"rows":[1234]}'),({'max_metadata_bytes':8},b'{"abc":"12345","rows":[]}'),({'max_metadata_bytes':6},b'{"rows":[],"abcdef":0}')]:
            with self.subTest(kwargs=kwargs),self.assertRaises(RowsStreamError):list(JsonRowsStream(io.BytesIO(raw),**kwargs))
        it=JsonRowsStream(io.BytesIO(b'{"rows":[]}'));self.assertEqual(list(it),[]);self.assertEqual(it.summary['row_count'],0)
        with self.assertRaises(RowsStreamError):list(JsonRowsStream(io.StringIO('{"rows":[]}')))
        with self.assertRaises(RowsStreamError):JsonRowsStream(io.BytesIO(),block_size=True)
    def test_rows_are_released_and_order_unmodified(self):
        it=JsonRowsStream(io.BytesIO(b'{"rows":[{"x":1},{"x":2}]}'),block_size=1)
        first=next(it);first['value']['x']=999
        self.assertEqual(next(it)['value'],{'x':2})
        with self.assertRaises(StopIteration):next(it)
        self.assertNotIn('rows',it.summary['metadata'])

if __name__=='__main__':unittest.main()
