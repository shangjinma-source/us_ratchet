import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_dated_comparison_workbook_independent_readback_20261003 as m
from test_ndx_dated_comparison_workbook_independent_readback_20261003 import setup
class RuntimeAttachment(unittest.TestCase):
    def test_missing_drift_extra(self):
        for action in ('missing','drift','extra'):
            with self.subTest(action=action),tempfile.TemporaryDirectory() as t:
                root=Path(t);refs,export,*_=setup(root);p=Path(refs['runtime_inspection']['path'])
                if action=='missing':p.unlink()
                elif action=='drift':p.write_bytes(b'x'*10)
                else:(export/'unexpected').write_bytes(b'x')
                with patch.object(m,'BOUND',refs),patch.object(m,'EXPORT',export),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'RUNTIME_INSPECTION_SIZE',10):
                    with self.assertRaises((ValueError,FileNotFoundError)):m.readback(execute=True)
                    self.assertFalse((root/'out'/'independent_readback.json').exists())
    def test_arbitrary_diagnostic_not_parsed_and_postwrite_drift(self):
        for drift in (False,True):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as t:
                root=Path(t);refs,export,*_=setup(root);save=m.save
                def altered(path,value):
                    r=save(path,value)
                    if drift and path.name=='independent_readback.json':Path(refs['runtime_inspection']['path']).write_bytes(b'x'*10)
                    return r
                with patch.object(m,'BOUND',refs),patch.object(m,'EXPORT',export),patch.object(m,'OUTPUT',root/'out'),patch.object(m,'RUNTIME_INSPECTION_SIZE',10),patch.object(m,'save',side_effect=altered):
                    if drift:
                        with self.assertRaises(ValueError):m.readback(execute=True)
                        self.assertTrue((root/'out'/'failure.json').exists())
                    else:
                        ref=m.readback(execute=True);d=json.loads(Path(ref['path']).read_bytes());a=d['runtime_inspection_attachment']
                        self.assertEqual(a['status'],'OBSERVED_RUNTIME_DIAGNOSTIC_ATTACHMENT')
                        for k in ('manifest_bound','content_interpreted','numeric_input'):self.assertIs(a[k],False)
                        self.assertFalse(d['visual_acceptance_passed'])
