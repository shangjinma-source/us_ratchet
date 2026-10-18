import gzip,hashlib,io,json,unittest
from copy import deepcopy
from backtest import ndx_double_replacement_compressed_raw_inspection_research as m


def fixture(value=None,raw=None):
    raw=m.canonical(value)if raw is None else raw
    target=io.BytesIO()
    with gzip.GzipFile(filename='',mode='wb',fileobj=target,compresslevel=6,mtime=0)as stream:stream.write(raw)
    compressed=target.getvalue()
    meta=dict(schema='DOUBLE_REPLACEMENT_CANONICAL_GZIP_V1',encoding=deepcopy(m.ENCODING),compressed_sha256=hashlib.sha256(compressed).hexdigest(),compressed_byte_count=len(compressed),uncompressed_sha256=hashlib.sha256(raw).hexdigest(),uncompressed_byte_count=len(raw))
    return compressed,meta

def inspect(compressed,metadata,**kwargs):return m.inspect_gzip_raw(compressed_bytes=compressed,metadata=metadata,max_compressed_bytes=2000000,max_uncompressed_bytes=2000000,**kwargs)

class Tests(unittest.TestCase):
    def test_all_json_return_types_and_cross_chunk_utf8_escapes(self):
        values=[None,True,False,0,-3,1.5,-0.0,'中文\\"',[0,False,None],{'中文':{'x':[1,2]},'long':'x'*140000}]
        for value in values:
            compressed,meta=fixture(value)
            class Tiny(io.BytesIO):
                def read(self,size=-1):return super().read(min(size,3))
            result=m.read_gzip_raw(Tiny(compressed),metadata=meta,max_compressed_bytes=2000000,max_uncompressed_bytes=2000000)
            self.assertEqual(m.canonical(result['value']),m.canonical(value))
            self.assertEqual(result['inspection']['status'],'PASS_BYTES_ONLY')
            self.assertIs(result['inspection']['economic_schema_checked'],False)
        self.assertEqual(inspect(*fixture(None))['inspection']['json_top_level_type'],'null')

    def test_second_member_garbage_truncation_crc_and_header(self):
        compressed,meta=fixture({'x':1})
        for kind in ('second','garbage','truncated','crc','header'):
            bad=compressed+compressed if kind=='second'else compressed+b'garbage'if kind=='garbage'else compressed[:-3]if kind=='truncated'else bytearray(compressed)
            if kind=='crc':bad[-8]^=1;bad=bytes(bad)
            if kind=='header':bad[4]=1;bad=bytes(bad)
            claimed=deepcopy(meta);claimed['compressed_byte_count']=len(bad);claimed['compressed_sha256']=hashlib.sha256(bad).hexdigest()
            with self.subTest(kind=kind),self.assertRaises(ValueError):inspect(bad,claimed)

    def test_duplicate_nonfinite_canonical_and_syntax_rejection(self):
        for raw in (b'{"a":1,"a":2}',b'{"outer":{"a":1,"a":2}}',b'NaN',b'Infinity',b'1e999',b'{ "a":1}',b'{"b":2,"a":1}',b'1.00',b'-0',b'{} {}',b'"unterminated',b'\xef\xbb\xbf{}'):
            with self.subTest(raw=raw),self.assertRaises(ValueError):inspect(*fixture(raw=raw))

    def test_hash_lengths_typed_metadata_and_inflation_engineering_gate(self):
        compressed,meta=fixture('x'*1000000)
        bad=deepcopy(meta);bad['uncompressed_byte_count']=20
        with self.assertRaisesRegex(ValueError,'Inflation'):inspect(compressed,bad)
        for key,value in (('compressed_byte_count',True),('uncompressed_byte_count',False),('uncompressed_sha256','0'*64),('extra',1)):
            bad=deepcopy(meta);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):inspect(compressed,bad)
        bad=deepcopy(meta);bad['encoding']['mtime']=False
        with self.assertRaises(ValueError):inspect(compressed,bad)
        class NoRead:
            def read(self,size):raise AssertionError('Limit checked before reading')
        with self.assertRaises(ValueError):m.read_gzip_raw(NoRead(),metadata=meta,max_compressed_bytes=1,max_uncompressed_bytes=2000000)
        with self.assertRaises(ValueError):m.read_gzip_raw(NoRead(),metadata=meta,max_compressed_bytes=True,max_uncompressed_bytes=2000000)
        with self.assertRaisesRegex(ValueError,'nesting'):inspect(*fixture([[[0]]]),max_json_depth=2)
        self.assertEqual(inspect(*fixture('[[[{'),max_json_depth=1)['value'],'[[[{')

if __name__=='__main__':unittest.main()
