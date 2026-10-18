import ast
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_exact_two_delta_inverse(self):
        old = (ROOT / 'scripts/ndx_multidecision_h_workbook_export_v2_20261008.py').read_bytes()
        new = (ROOT / 'scripts/ndx_multidecision_h_workbook_export_v3_20261008.py').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(), '9ebac7e06135abd124892a20ea305b971f192dbeda2f82a8a3640230d861165d')
        restored = new.replace(b"OUTPUT=ROOT/'data/cache/research/multidecision_h_workbook_20261008_v3'", b"OUTPUT=ROOT/'data/cache/research/multidecision_h_workbook_20261008_v2'", 1)
        restored = restored.replace(b"subprocess.run([str(NODE),'--max-old-space-size=16384',str(BUILDER)", b"subprocess.run([str(NODE),str(BUILDER)", 1)
        self.assertEqual(restored, old)

    def test_heap_flag_is_node_argument_not_builder_argument(self):
        tree = ast.parse((ROOT / 'scripts/ndx_multidecision_h_workbook_export_v3_20261008.py').read_bytes())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) and n.func.value.id == 'subprocess' and n.func.attr == 'run']
        self.assertEqual(len(calls), 1)
        argv = calls[0].args[0].elts
        self.assertEqual(ast.unparse(argv[0]), 'str(NODE)')
        self.assertEqual(ast.literal_eval(argv[1]), '--max-old-space-size=16384')
        self.assertEqual(ast.unparse(argv[2]), 'str(BUILDER)')
        self.assertEqual(len(argv), 6)
        self.assertTrue(any(k.arg == 'check' and ast.literal_eval(k.value) is True for k in calls[0].keywords))


if __name__ == '__main__':
    unittest.main()
