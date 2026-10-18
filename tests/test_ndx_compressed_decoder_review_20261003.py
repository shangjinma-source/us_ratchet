"""Independent gzip boundary tests using stdlib fixtures, not producer codec."""
import gzip,hashlib,io,json,unittest
from copy import deepcopy
from backtest import ndx_double_replacement_compressed_raw_inspection_research as m

def sample(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
    stream=io.BytesIO()
    with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0,compresslevel=6) as f:f.write(raw)
    packed=stream.getvalue()
    return packed,dict(schema='DOUBLE_REPLACEMENT_CANONICAL_GZIP_V1',encoding=dict(m.ENCODING),compressed_sha256=hashlib.sha256(packed).hexdigest(),compressed_byte_count=len(packed),uncompressed_sha256=hashlib.sha256(raw).hexdigest(),uncompressed_byte_count=len(raw))

def inspect(blob,meta,**kw):
    return m.inspect_gzip_raw(compressed_bytes=blob,metadata=meta,max_compressed_bytes=100000,max_uncompressed_bytes=100000,**kw)

class Tests(unittest.TestCase):
    def test_tiny_stream_all_values_and_bounded_probe(self):
        for value in (None,False,42,1.25,'汉字\\"',[None,False],{'x':'z'*4096}):
            blob,meta=sample(value);requests=[]
            class Tiny(io.BytesIO):
                def read(self,n):requests.append(n);return super().read(min(1,n))
            out=m.read_gzip_raw(Tiny(blob),metadata=meta,max_compressed_bytes=len(blob),max_uncompressed_bytes=meta['uncompressed_byte_count'])
            self.assertEqual(out['value'],value)
            self.assertLessEqual(max(requests),len(blob)+1)
            self.assertEqual(requests[-1],1)
            self.assertIs(out['inspection']['economic_evaluation_verified'],False)

    def test_rehashed_integrity_attacks_and_typed_encoding(self):
        blob,meta=sample({'x':1})
        crc=bytearray(blob);crc[-8]^=1
        size=bytearray(blob);size[-4]^=1
        for bad in (bytes(crc),bytes(size),blob+b'\0',blob+sample(None)[0],blob[:-1]):
            claim=deepcopy(meta);claim.update(compressed_sha256=hashlib.sha256(bad).hexdigest(),compressed_byte_count=len(bad))
            with self.assertRaises(ValueError):inspect(bad,claim)
        for key,value in (('mtime',False),('compresslevel',6.0),('filename',None)):
            claim=deepcopy(meta);claim['encoding'][key]=value
            with self.assertRaises(ValueError):inspect(blob,claim)

    def test_declared_output_bound_enforced_during_decompression(self):
        blob,meta=sample('a'*500000);meta['uncompressed_byte_count']=3
        with self.assertRaisesRegex(ValueError,'Inflation'):inspect(blob,meta)
        class Oversized:
            def read(self,n):return b'x'*(n+1)
        with self.assertRaisesRegex(ValueError,'read contract'):
            m.read_gzip_raw(Oversized(),metadata=sample(None)[1],max_compressed_bytes=1000,max_uncompressed_bytes=1000)

    def test_stream_cannot_replace_original_claims_after_validation(self):
        blob,meta=sample({'x':1});expected=deepcopy(meta)
        meta['compressed_sha256']='0'*64;meta['uncompressed_sha256']='0'*64
        class Mutation(io.BytesIO):
            def read(self,n):
                meta.update(expected)
                return super().read(n)
        with self.assertRaises(ValueError):
            m.read_gzip_raw(Mutation(blob),metadata=meta,max_compressed_bytes=1000,max_uncompressed_bytes=1000)

if __name__=='__main__':unittest.main()
