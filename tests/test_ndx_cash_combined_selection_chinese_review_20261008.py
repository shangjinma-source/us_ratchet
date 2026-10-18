import ast
import hashlib
import importlib
import os
from pathlib import Path
import tempfile
import unittest

MODULE=os.environ.get('CASH_SELECTION_REVIEW_MODULE','scripts.ndx_cash_neighbor_combined_selection_v2_20261008')
source=importlib.import_module(MODULE)
REVIEW=Path(source.BOUND['previous_review'][0])


def review_gate(text,result_sha=None):
    tree=ast.parse(Path(source.__file__).read_text(encoding='utf-8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_common')
    gate=next(n for n in function.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and any(isinstance(a,ast.Constant) and a.value=='Saved old review reference' for a in n.value.args))
    exec(compile(ast.Module(body=[gate],type_ignores=[]),'real-review-gate','exec'),dict(require=source.require,r={'previous':{'sha256':result_sha or source.BOUND['previous'][1]}},d={'previous_review':text}))


class Tests(unittest.TestCase):
    def test_real_frozen_chinese_success(self):
        raw=REVIEW.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'40f02f234a2661b0c3e0bb0ed2e7456a038d664c2e0e631561826f7b1e57f9ec')
        self.assertNotIn('PASS',raw.decode())
        review_gate(raw.decode())

    def test_resigned_failure_and_wrong_result_rejected(self):
        text=REVIEW.read_text(encoding='utf-8')
        for bad in (text.replace('核验通过','核验失败'),text.replace('exit 0','exit 1'),text.replace(source.BOUND['previous'][1],'0'*64)):
            with self.subTest(bad=bad[:140]),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'review.md';path.write_text(bad,encoding='utf-8');raw=path.read_bytes()
                # A newly signed fixture can pass byte authentication, never this semantic gate.
                saved=source.read({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()},{})
                with self.assertRaises(ValueError):review_gate(saved.decode())
                with self.assertRaises(ValueError):source.read({'path':str(path),'sha256':source.BOUND['previous_review'][1]}, {})

if __name__=='__main__':unittest.main()
