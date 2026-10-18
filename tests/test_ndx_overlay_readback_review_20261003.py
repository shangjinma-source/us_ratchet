import copy
import io
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import test_ndx_singleton_overlay_reader_20261003 as f

m = f.m

class Review(unittest.TestCase):
    def test_native_xml_only_target_not_root_or_nested_nodes(self):
        old, links = f.n.fixture()
        new = f.n.m.relocate_navigation(old, links, 'D:/saved/old', 'D:/saved/new')
        m.inspect_navigation_relocation(old, new, links)
        for attack in ('root_attribute', 'root_text', 'nested_relationship', 'other_part'):
            result = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(new)) as z, zipfile.ZipFile(result, 'w') as out:
                for name in z.namelist():
                    raw = z.read(name)
                    if name == 'xl/worksheets/_rels/sheet1.xml.rels':
                        root = ET.fromstring(raw)
                        if attack == 'root_attribute': root.set('unexpected', 'true')
                        if attack == 'root_text': root.text = 'unregistered'
                        if attack == 'nested_relationship': ET.SubElement(root[0], 'unexpected')
                        raw = ET.tostring(root)
                    if name == 'untouched.bin' and attack == 'other_part': raw = b'changed'
                    out.writestr(name, raw)
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.inspect_navigation_relocation(old, result.getvalue(), links)

    def test_saved_cells_preserve_types_and_entire_stream(self):
        a, b = f.captures()
        for attack in ('false_zero', 'negative', 'formula', 'extra', 'missing'):
            old, new = copy.deepcopy(a), copy.deepcopy(b)
            old['values'][0][0] = new['values'][0][0] = False
            before, after = [old], [new]
            if attack == 'false_zero': new['values'][0][0] = 0
            if attack == 'negative': new['values'][0][2] = 2
            if attack == 'formula': new['formulas'][0][2] = '=2'
            if attack == 'extra': after.append(copy.deepcopy(new))
            if attack == 'missing': after = []
            with self.subTest(attack=attack), self.assertRaises(ValueError):
                m.inspect_capture_delta(iter(before), iter(after), 'a'*64)

    def test_namespace_sibling_and_late_failure_cannot_be_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)/'overlay'; root.mkdir()
            (root/'export_manifest.json').write_bytes(b'{}')
            (root/'publication.json').write_bytes(b'{}')
            good = dict(output_inventory_excludes=['export_manifest.json','publication.json'], output_inventory=[])
            self.assertEqual(m.namespace_files(root,good),{})
            other=Path(folder)/'overlay-extra';other.mkdir();(other/'a').write_bytes(b'x')
            bad=copy.deepcopy(good);bad['output_inventory']=[dict(path='../overlay-extra/a',byte_count=1,sha256=m.sha(b'x'))]
            with self.assertRaises(ValueError):m.namespace_files(root,bad)
            (root/'failure.json').write_bytes(b'{}')
            bad=copy.deepcopy(good);bad['output_inventory']=[dict(path='failure.json',byte_count=2,sha256=m.sha(b'{}'))]
            with self.assertRaises(ValueError):m.namespace_files(root,bad)

if __name__=='__main__':unittest.main()
