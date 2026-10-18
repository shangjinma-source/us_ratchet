import copy,io,unittest,zipfile
from xml.etree import ElementTree as ET
from scripts import ndx_workbook_native_hyperlinks_20261003 as m


def fixture():
    book=ET.Element('{'+m.MAIN+'}workbook');sheets=ET.SubElement(book,'{'+m.MAIN+'}sheets');ET.SubElement(sheets,'{'+m.MAIN+'}sheet',{'name':'全部任务','sheetId':'1','{'+m.REL+'}id':'sheet1'})
    rel=ET.Element('{'+m.PACKAGE+'}Relationships');ET.SubElement(rel,'{'+m.PACKAGE+'}Relationship',{'Id':'sheet1','Type':m.REL+'/worksheet','Target':'worksheets/sheet1.xml'})
    sheet=ET.Element('{'+m.MAIN+'}worksheet');data=ET.SubElement(sheet,'{'+m.MAIN+'}sheetData');links=[]
    for i in range(1632):
        r=ET.SubElement(data,'{'+m.MAIN+'}row',{'r':str(i+2)});c=ET.SubElement(r,'{'+m.MAIN+'}c',{'r':f'H{i+2}','t':'str'});ET.SubElement(c,'{'+m.MAIN+'}v').text='package-0000.xlsx';n=ET.SubElement(r,'{'+m.MAIN+'}c',{'r':f'I{i+2}','t':'n'});ET.SubElement(n,'{'+m.MAIN+'}v').text=str(i+1)
        links.append(dict(worksheet='全部任务',cell=f'H{i+2}',target='package-0000.xlsx',location=f"'任务索引'!A{i+2}"))
    ET.SubElement(sheet,'{'+m.MAIN+'}pageMargins',{'left':'0.5'})
    return {'xl/workbook.xml':ET.tostring(book),'xl/_rels/workbook.xml.rels':ET.tostring(rel),'xl/worksheets/sheet1.xml':ET.tostring(sheet),'unchanged.bin':b'\x00original\xff'},links

def archive(parts,duplicate=None):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for k,v in parts.items():z.writestr(k,v)
        if duplicate:z.writestr(duplicate,parts[duplicate])
    return out.getvalue()

def unzip(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:return {n:z.read(n) for n in z.namelist()}

class Tests(unittest.TestCase):
    def test_only_link_parts_and_original_cells_unchanged(self):
        parts,links=fixture();before=copy.deepcopy(links);result=unzip(m.add_native_navigation_links(archive(parts),links));self.assertEqual(links,before)
        self.assertEqual(set(result)-set(parts),{'xl/worksheets/_rels/sheet1.xml.rels'});self.assertEqual([k for k in parts if parts[k]!=result[k]],['xl/worksheets/sheet1.xml'])
        sheet=ET.fromstring(result['xl/worksheets/sheet1.xml']);nodes=sheet.find('{'+m.MAIN+'}hyperlinks');self.assertEqual(len(nodes),1632);sheet.remove(nodes);self.assertEqual(ET.tostring(sheet),ET.tostring(ET.fromstring(parts['xl/worksheets/sheet1.xml'])))
        rel=ET.fromstring(result['xl/worksheets/_rels/sheet1.xml.rels']);self.assertEqual(len(rel),1632);self.assertEqual(len({n.get('Id') for n in rel}),1632)
        with self.assertRaises(ValueError):m.add_native_navigation_links(archive(result),links)

    def test_target_escape_duplicate_intent_signature_and_collision_rejected(self):
        for fault in ('escape','cell','signature','collision','formula'):
            parts,links=fixture()
            if fault=='escape':links[0]['target']='../package-0000.xlsx'
            if fault=='cell':links[1]['cell']='H2'
            if fault=='signature':parts['_xmlsignatures/sig1.xml']=b'<sig/>'
            if fault=='collision':parts['xl/worksheets/_rels/sheet1.xml.rels']=f'<Relationships xmlns="{m.PACKAGE}"><Relationship Id="navTaskLink1" Type="x" Target="x"/></Relationships>'.encode()
            if fault=='formula':
                s=ET.fromstring(parts['xl/worksheets/sheet1.xml']);ET.SubElement(s.find('.//{'+m.MAIN+'}c'),'{'+m.MAIN+'}f').text='1+1';parts['xl/worksheets/sheet1.xml']=ET.tostring(s)
            with self.subTest(fault=fault),self.assertRaises(ValueError):m.add_native_navigation_links(archive(parts),links)
        parts,links=fixture()
        with self.assertWarns(UserWarning):blob=archive(parts,'unchanged.bin')
        with self.assertRaises(ValueError):m.add_native_navigation_links(blob,links)

    def test_destination_cannot_swap_same_package_or_point_header(self):
        for value in ("'任务索引'!A1","'任务索引'!A3","'任务索引'!A999999999999"):
            parts,links=fixture();links[0]['location']=value
            with self.subTest(value=value),self.assertRaises(ValueError):m.add_native_navigation_links(archive(parts),links)

    def test_duplicate_cells_wrong_relationship_or_root_rejected(self):
        for fault in ('cells','type','root'):
            parts,links=fixture()
            if fault=='type':
                r=ET.fromstring(parts['xl/_rels/workbook.xml.rels']);r[0].set('Type',m.REL+'/styles');parts['xl/_rels/workbook.xml.rels']=ET.tostring(r)
            else:
                s=ET.fromstring(parts['xl/worksheets/sheet1.xml'])
                if fault=='root':s.tag='{'+m.MAIN+'}styles'
                else:s.find('{'+m.MAIN+'}sheetData')[0].append(copy.deepcopy(s.find('.//{'+m.MAIN+'}c')))
                parts['xl/worksheets/sheet1.xml']=ET.tostring(s)
            with self.subTest(fault=fault),self.assertRaises(ValueError):m.add_native_navigation_links(archive(parts),links)

if __name__=='__main__':unittest.main()
