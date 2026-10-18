"""Focused reproduction of bytes consumed after a separate inventory hash pass.
No real export/audit invocation; execute only the actual read_workbook assignment.
"""
import ast,hashlib,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_dated_workbook_extension_independent_readback_20261003 as m

class Tests(unittest.TestCase):
 def test_package_and_navigation_consume_only_hashed_bytes(self):
  tree=ast.parse(Path(m.__file__).read_text(encoding='utf-8-sig'))
  assignments=[n for n in ast.walk(tree)if isinstance(n,ast.Assign)and isinstance(n.value,ast.Call)and isinstance(n.value.func,ast.Attribute)and n.value.func.attr=='read_workbook']
  self.assertEqual(len(assignments),2)
  for statement in assignments:
   with self.subTest(line=statement.lineno),tempfile.TemporaryDirectory()as td:
    path=Path(td)/'book.xlsx';good=b'good immutable bytes';bad=b'other transient bytes';path.write_bytes(good);ref=dict(path=str(path),sha256=hashlib.sha256(good).hexdigest());sources={str(path):ref['sha256']};seen=[]
    # The real inventory checks open/read their good bytes; the consuming read
    # returns different bytes, then final inventory again sees original bytes.
    m.guard(sources)
    scope=dict(Path=Path,wr=ref,nw=ref,read_bound_bytes=m.read_bound_bytes,core=types.SimpleNamespace(read_workbook=lambda b:seen.append(b)))
    code=compile(ast.fix_missing_locations(ast.Module(body=[statement],type_ignores=[])),'actual-consumer-statement','exec')
    with patch.object(Path,'read_bytes',return_value=bad):
     with self.assertRaisesRegex(ValueError,'Consumed workbook bytes'):exec(code,scope)
    m.guard(sources);self.assertEqual(seen,[])
    exec(code,scope);self.assertEqual(hashlib.sha256(seen[0]).hexdigest(),ref['sha256'])
if __name__=='__main__':unittest.main()
