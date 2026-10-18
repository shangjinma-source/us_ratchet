import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_cash_neighbor_combined_selection_independent_readback_v2_20261008 as reader

class Tests(unittest.TestCase):
    def test_physical_old_span_and_engineering_reserve_boundary(self):
        with tempfile.TemporaryDirectory()as directory:
            raw=b'{}'+b' '*(33*1024**2);path=Path(directory)/'row.json';path.write_bytes(raw);h=hashlib.sha256(raw).hexdigest()
            loc=dict(source_reference=dict(path=str(path),sha256=h),byte_start=0,byte_stop=len(raw),row_sha256=h)
            evidence=reader.Evidence({str(path):h});reserve=2*1024**3+32*len(raw)
            try:
                with self.assertRaises(ValueError):evidence.span(loc)
                with patch.object(reader,'available_memory_bytes',return_value=reserve-1):
                    with self.assertRaises(ValueError):evidence.span(loc,old_row=True)
                with patch.object(reader,'available_memory_bytes',return_value=reserve):self.assertEqual(evidence.span(loc,old_row=True),{})
            finally:evidence.close()

    def test_oversize_old_rejected_before_open(self):
        loc=dict(source_reference=dict(path='fixture',sha256='a'*64),byte_start=0,byte_stop=64*1024**2+1)
        with patch.object(Path,'open',side_effect=AssertionError('must fail before IO')):
            with self.assertRaises(ValueError):reader.Evidence({'fixture':'a'*64}).span(loc,old_row=True)

if __name__=='__main__':unittest.main()
