import json
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_h_failed_export_recovery_independent_readback_v2_20261008 as r


class Tests(unittest.TestCase):
    def test_safe_integral_only(self):
        r.exact_display_metadata({'x':[4,1,True,'4']},{'x':[4.0,1.0,True,'4']})
        for left,right in [(True,1),(False,0),(4,'4'),(1,1.01),(2**53,float(2**53)),(2**53+1,float(2**53)),(float('inf'),float('inf')),({'x':1},{}),([1],[1,2])]:
            with self.subTest(left=left,right=right),self.assertRaises(ValueError):r.exact_display_metadata(left,right)
        r.exact_display_metadata(2**53+1,2**53+1)
        with self.assertRaises(ValueError):r.exact(4,4.0)

    def test_all_inventory_recorded_representations(self):
        p=Path('tmp/h_metadata_inventory_20261008_v1/report.json');report=r.loads(p.read_bytes())
        self.assertEqual(r.sha(p.read_bytes()),'4b380e110c213ac0e023d4c179a274426e1deb7d62ad5adc4f11c65037f9d941')
        ref=report['differences_reference'];raw=Path(ref['path']).read_bytes();self.assertEqual(r.sha(raw),ref['sha256'])
        count=0
        for line in raw.splitlines():
            row=json.loads(line);self.assertEqual(row['kind'],'EXACT_INTEGRAL_NUMBER_REPRESENTATION');r.exact_display_metadata(row['actual'],row['expected']);count+=1
        self.assertEqual(count,55488)

    def test_original_failed_predecessor_is_bound(self):
        sources=r.failed_predecessor();self.assertEqual(len(sources),4)
        self.assertIn(str(r.FAILED_SNAPSHOT),sources)
        with patch.object(r,'FAILED_SNAPSHOT_SHA','0'*64):
            with self.assertRaises(ValueError):r.failed_predecessor()


if __name__=='__main__':unittest.main()
