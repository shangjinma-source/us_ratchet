import io,zipfile,unittest,importlib.util
from pathlib import Path
from copy import deepcopy
P=Path(__file__).resolve().parents[1]/'scripts/ndx_dated_overlay_native_links_20261003.py'
s=importlib.util.spec_from_file_location('overlaylinks',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def fixture():
    rels=''.join(f'<Relationship Id="r{i}" Type="{m.R}/hyperlink" Target="package-0001.xlsx" TargetMode="External"/>' for i in range(1632))
    links=[dict(worksheet='全部任务',cell=f'H{i+2}',target='../old/package-0001.xlsx',location=f"\'任务索引\'!A{i+2}",numerical_task_id=f'{i:064x}',expected_workbook_reference={'path':'D:/saved/old/package-0001.xlsx','sha256':'a'*64}) for i in range(1632)]
    hs=''.join(f'<hyperlink ref="H{i+2}" r:id="r{i}" location="{links[i]["location"]}"/>' for i in range(1632))
    parts={'xl/workbook.xml':f'<workbook xmlns="{m.M}" xmlns:r="{m.R}"><sheets><sheet name="全部任务" r:id="s1"/></sheets></workbook>', 'xl/_rels/workbook.xml.rels':f'<Relationships xmlns="{m.P}"><Relationship Id="s1" Target="worksheets/sheet1.xml"/></Relationships>','xl/worksheets/sheet1.xml':f'<worksheet xmlns="{m.M}" xmlns:r="{m.R}"><hyperlinks>{hs}</hyperlinks></worksheet>', 'xl/worksheets/_rels/sheet1.xml.rels':f'<Relationships xmlns="{m.P}">{rels}</Relationships>','untouched.bin':'original untouched'}
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        for k,v in parts.items():z.writestr(k,v.encode())
    return b.getvalue(),links
class Tests(unittest.TestCase):
    def test_exact_relationship_only_and_fullmap(self):
        raw,links=fixture();out=m.relocate_navigation(raw,links,'D:/saved/old','D:/saved/new')
        with zipfile.ZipFile(io.BytesIO(raw)) as a,zipfile.ZipFile(io.BytesIO(out)) as b:
            self.assertEqual(a.namelist(),b.namelist())
            for p in a.namelist():
                if p!='xl/worksheets/_rels/sheet1.xml.rels':self.assertEqual(a.read(p),b.read(p))
            self.assertIn(b'../old/package-0001.xlsx',b.read('xl/worksheets/_rels/sheet1.xml.rels'))
    def test_foreign_target_missing_reordered_or_swapped_id_rejected(self):
        raw,links=fixture()
        for mode in ('missing','foreign','location','duplicate','filename'):
            l=deepcopy(links)
            if mode=='missing':l.pop()
            elif mode=='foreign':l[0]['target']='../../foreign/package-0001.xlsx'
            elif mode=='location':l[0]['location']="'任务索引'!A3"
            elif mode=='duplicate':l[1]['numerical_task_id']=l[0]['numerical_task_id']
            else:l[0]['target']='package-0002.xlsx';l[0]['expected_workbook_reference']['path']='D:/saved/new/package-0002.xlsx'
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.relocate_navigation(raw,l,'D:/saved/old','D:/saved/new')
if __name__=='__main__':unittest.main()
