import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROOFS = ROOT / 'tmp/multidecision_h_workbook_v4_layout_preparation_20261008'


class Tests(unittest.TestCase):
    def test_both_sources_exact_inverse(self):
        for role, current in [('builder', 'scripts/ndx_multidecision_h_workbook_v4_20261008.mjs'), ('exporter', 'scripts/ndx_multidecision_h_workbook_export_v4_20261008.py')]:
            proof = json.loads((PROOFS / (role + '_proof.json')).read_bytes())
            after = (ROOT / current).read_bytes()
            self.assertEqual(hashlib.sha256(after).hexdigest(), proof['after_sha256'])
            inverse = after
            for pair in reversed(proof['replacements']):
                self.assertEqual(inverse.count(pair['new'].encode()), 1)
                inverse = inverse.replace(pair['new'].encode(), pair['old'].encode(), 1)
            self.assertEqual(inverse, (PROOFS / (role + '_before')).read_bytes())


if __name__ == '__main__':
    unittest.main()
