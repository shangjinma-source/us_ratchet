"""Independent Unicode split and malformed OOXML attack fixtures; no export."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree as ET
import test_ndx_multidecision_h_workbook_20261008 as fixtures


class ReviewTests(unittest.TestCase):
    def test_two_million_characters_and_utf16_boundaries(self):
        values = ['甲' * 32767, '🙂' * 16383 + '甲', '🙂' * 16384,
                  '{"original":"' + '甲🙂' * 1113265 + '"}']
        payload = dict(schema='MULTIDECISION_H_WORKBOOK_INPUT_V1', full_h_delivery_complete=False,
                       tables=[dict(name=name, headers=['原JSON'], rows=[[v] for v in values])
                               for name in fixtures.NAMES])
        script = ('import {sheets} from ' + json.dumps(fixtures.m.BUILDER.as_uri()) + ';'
                  'let text="";for await(const chunk of process.stdin)text+=chunk;'
                  'process.stdout.write(JSON.stringify(sheets(JSON.parse(text))));')
        actual = json.loads(subprocess.run([str(fixtures.m.NODE), '--input-type=module', '-e', script],
                                          input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, check=True).stdout)
        expected = fixtures.c.expected_sheets(payload)
        self.assertEqual(actual, [dict(name=n, headers=h, rows=r) for n, h, r in expected])
        chunks = actual[-1]['rows']
        for table in fixtures.NAMES:
            for row in (3, 4):
                parts = [r[-1] for r in chunks if r[0] == table and r[1] == row]
                self.assertEqual(''.join(parts), values[row - 1])
                self.assertTrue(all(len(p.encode('utf-16-le')) // 2 <= 28000 for p in parts))
        self.assertEqual(actual[1]['rows'][0][0], values[0])
        self.assertEqual(actual[1]['rows'][1][0], values[1])

    def test_invalid_boolean_xml_is_not_false(self):
        self.check_xml_attack('boolean')

    def test_formula_extra_cell_and_final_chunk_are_rejected(self):
        for attack in ('formula', 'extra', 'tail'):
            with self.subTest(attack=attack): self.check_xml_attack(attack)

    def check_xml_attack(self, attack):
        # A tiny independent malformed fixture exercises decoding, without SDK
        # authoring or any actual research source.
        payload = dict(tables=[dict(name='原表', headers=['状态'], rows=[[False], ['甲🙂' * 18000]])])
        expected = fixtures.c.expected_sheets(payload)
        ns = fixtures.c.NS['s']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'malformed.xlsx'
            with zipfile.ZipFile(path, 'w') as archive:
                workbook = ET.Element('{' + ns + '}workbook')
                sheets = ET.SubElement(workbook, '{' + ns + '}sheets')
                relations = ET.Element('Relationships')
                for number, (name, headers, rows) in enumerate(expected, 1):
                    rid = 'r' + str(number)
                    ET.SubElement(sheets, '{' + ns + '}sheet', {'name': name, fixtures.c.R: rid})
                    ET.SubElement(relations, 'Relationship', Id=rid, Target=f'worksheets/sheet{number}.xml')
                    root = ET.Element('{' + ns + '}worksheet')
                    data = ET.SubElement(root, '{' + ns + '}sheetData')
                    wanted = {'A1': name, 'A2': fixtures.c.SUBTITLE}
                    for r, row in enumerate([headers] + rows, 4):
                        for c, value in enumerate(row, 1): wanted[fixtures.c.address(r, c)] = value
                    for loc, value in wanted.items():
                        cell = ET.SubElement(ET.SubElement(data, '{' + ns + '}row'), '{' + ns + '}c', r=loc)
                        if type(value) is bool:
                            cell.set('t', 'b');ET.SubElement(cell, '{' + ns + '}v').text = '2' if attack == 'boolean' else '0'
                        elif type(value) is int:
                            ET.SubElement(cell, '{' + ns + '}v').text = str(value)
                        else:
                            cell.set('t', 'inlineStr')
                            ET.SubElement(ET.SubElement(cell, '{' + ns + '}is'), '{' + ns + '}t').text = str(value)
                    if number == len(expected):
                        if attack == 'formula':
                            ET.SubElement(cell, '{' + ns + '}f').text = '1+1'
                        elif attack == 'extra':
                            extra = ET.SubElement(ET.SubElement(data, '{' + ns + '}row'), '{' + ns + '}c', r='Z999')
                            ET.SubElement(extra, '{' + ns + '}v').text = '1'
                        elif attack == 'tail':
                            cell.find('s:is/s:t', fixtures.c.NS).text += '改'
                    archive.writestr(f'xl/worksheets/sheet{number}.xml', ET.tostring(root))
                archive.writestr('xl/workbook.xml', ET.tostring(workbook))
                archive.writestr('xl/_rels/workbook.xml.rels', ET.tostring(relations))
            with self.assertRaises(ValueError): fixtures.c.inspect_workbook(path, payload)


if __name__ == '__main__': unittest.main()
