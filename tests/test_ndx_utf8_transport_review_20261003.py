import unittest
from unittest.mock import patch
from test_ndx_native_navigation_utf8_transport_20261003 import packet,encode,unzip
from scripts import ndx_native_navigation_utf8_transport_20261003 as m

class Review(unittest.TestCase):
 def test_bounded_bytes_before_compile_and_original_parts(self):
  p=packet();raw=encode(p)
  with patch.object(m,'MAX_REQUEST_BYTES',len(raw)-1),patch('builtins.compile',side_effect=AssertionError('must reject before compile')):
   with self.assertRaises(ValueError):m.apply_navigation_request(raw)
  p['source']=p['source'][:-4]+'AAAA'
  with patch('builtins.compile',side_effect=AssertionError('untrusted source cannot compile')):
   with self.assertRaises(ValueError):m.apply_navigation_request(encode(p))
  p=packet();out=unzip(m.apply_navigation_request(encode(p)))
  self.assertEqual(out['unchanged.bin'],b'\x00original\xff')
  p['links'][1]['cell']=p['links'][0]['cell']
  with self.assertRaises(ValueError):m.apply_navigation_request(encode(p))

if __name__=='__main__':unittest.main()
